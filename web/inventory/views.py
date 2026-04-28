"""Views for inventory tracking."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView
from django_tables2 import SingleTableView

from csv_upc_omg.barcode_lookup import BarcodeAPIError

from .forms import UploadForm
from .models import CSVUpload, Location, LookupRecord, Scan, UPCProduct
from .services import UploadService
from .tables import LookupTable, UploadTable
from .tasks import lookup_batch_task, process_csv_task


@login_required
def dashboard(request):
    stats = UploadService.get_dashboard_stats(request.user)
    return render(request, "dashboard/index.html", {"stats": stats})


class UploadListView(LoginRequiredMixin, SingleTableView):
    model = CSVUpload
    template_name = "uploads/list.html"
    table_class = UploadTable
    table_pagination = {"per_page": 15}

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)


class UploadCreateView(LoginRequiredMixin, CreateView):
    model = CSVUpload
    form_class = UploadForm
    template_name = "uploads/upload.html"
    success_url = reverse_lazy("upload-list")

    def form_valid(self, form):
        form.instance.user = self.request.user

        try:
            response = super().form_valid(form)

            process_csv_task.enqueue(upload_id=str(self.object.id))
            lookup_batch_task.enqueue(upload_id=str(self.object.id))

            messages.success(self.request, "CSV processed and lookups completed!")
            return response
        except Exception as e:
            messages.error(self.request, f"Processing failed: {e}")
            context = self.get_context_data(form=form)
            return self.render_to_response(context)


class UploadDetailView(LoginRequiredMixin, DetailView):
    model = CSVUpload
    template_name = "uploads/detail.html"

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lookups"] = self.object.lookups.all()
        return context


class UploadExportView(LoginRequiredMixin, DetailView):
    model = CSVUpload
    template_name = "uploads/export.html"

    def get(self, request, *args, **kwargs):
        upload = self.get_object()

        if upload.status != "completed":
            messages.error(request, "Upload must be completed before exporting.")
            return redirect("upload-detail", pk=upload.id)

        try:
            csv_file = UploadService.export_to_csv(upload)
            response = HttpResponse(csv_file.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = (
                f'attachment; filename="{upload.filename}_export.csv"'
            )
            return response
        except Exception as e:
            messages.error(request, f"Export failed: {e}")
            return redirect("upload-detail", pk=upload.id)


class LookupListView(LoginRequiredMixin, SingleTableView):
    model = LookupRecord
    template_name = "lookups/list.html"
    table_class = LookupTable

    def get_queryset(self):
        return LookupRecord.objects.filter(
            csv_upload__user=self.request.user
        ).select_related("csv_upload")


@login_required
def scan(request):
    if request.method == "POST":
        upc = request.POST.get("upc", "").strip()
        if not upc:
            return JsonResponse({"error": "No UPC provided"}, status=400)

        try:
            details = UploadService.lookup_product_details(upc, timeout=10.0)
        except BarcodeAPIError as e:
            return render(
                request,
                "scan/_result.html",
                {"upc": upc, "title": None, "status": "error", "error": str(e)},
            )

        product, _ = UPCProduct.objects.get_or_create(
            upc=upc,
            defaults={
                "title": details.get("title") or f"Unknown Product ({upc})",
                "brand": details.get("brand") or "",
                "category": details.get("category") or "",
                "description": details.get("description") or "",
                "image_url": details.get("image_url") or "",
                "source": details.get("source") or "manual",
            },
        )

        if product.source == "manual":
            if details.get("title"):
                product.title = details["title"]
            if details.get("brand"):
                product.brand = details["brand"]
            if details.get("category"):
                product.category = details["category"]
            if details.get("description"):
                product.description = details["description"]
            if details.get("image_url"):
                product.image_url = details["image_url"]
            if details.get("source"):
                product.source = details["source"]
            product.save()

        locations = Location.objects.filter(user=request.user)
        return render(
            request,
            "scan/_product_form.html",
            {
                "upc": upc,
                "title": product.title,
                "brand": product.brand,
                "product_id": product.id,
                "locations": locations,
            },
        )

    return render(request, "scan/index.html")


@login_required
def scan_create_item(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    upc = request.POST.get("upc", "").strip()
    product_id = request.POST.get("product_id", "").strip()
    quantity = int(request.POST.get("quantity", 1))
    location_id = request.POST.get("location", "").strip() or None

    if not upc:
        return JsonResponse({"error": "Invalid UPC"}, status=400)

    try:
        product = UPCProduct.objects.get(id=product_id, upc=upc)
    except UPCProduct.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    location = None
    if location_id:
        try:
            location = Location.objects.get(id=location_id, user=request.user)
        except (Location.DoesNotExist, ValueError):
            return JsonResponse({"error": "Invalid location"}, status=400)

    from inventory.models import InventoryItem

    item = InventoryItem.objects.create(
        user=request.user,
        product=product,
        location=location,
        quantity=quantity,
    )
    return render(
        request,
        "scan/_item_created.html",
        {"item": item, "upc": upc},
    )


@login_required
def scan_history(request):
    scans = Scan.objects.filter(user=request.user).order_by("-created_at")[:50]
    if request.headers.get("HX-Request"):
        return render(request, "scan/_history_items.html", {"scans": scans})
    return render(request, "scan/history.html", {"scans": scans})


@require_POST
@login_required
def scan_delete(request, scan_id):
    Scan.objects.filter(user=request.user, id=scan_id).delete()
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    messages.success(request, "Scan deleted.")
    return redirect("scan-history")

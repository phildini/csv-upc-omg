"""Views for inventory tracking."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)
from django_tables2 import SingleTableView

from csv_upc_omg.barcode_lookup import BarcodeAPIError

from .forms import InventoryItemForm, LocationForm, UploadForm
from .models import CSVUpload, InventoryItem, Location, LookupRecord, Scan, UPCProduct
from .services import UploadService
from .tables import InventoryTable, LookupTable, UploadTable
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
            Scan.objects.create(
                user=request.user,
                upc=upc,
                product_title="",
                status="failed",
                raw_response=str(e),
            )
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

        Scan.objects.create(
            user=request.user,
            upc=upc,
            product_title=product.title,
            status="success",
        )

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


# ── Inventory Item Views ──────────────────────────────────────────────


class ItemListView(LoginRequiredMixin, SingleTableView):
    model = InventoryItem
    template_name = "inventory/list.html"
    table_class = InventoryTable
    table_pagination = {"per_page": 20}

    def get_queryset(self):
        qs = InventoryItem.objects.filter(user=self.request.user).select_related(
            "product", "location"
        )

        status = self.request.GET.get("status")
        if status == "low_stock":
            qs = qs.filter(quantity__lte=models.F("low_stock_threshold"))
        elif status == "expiring_soon":
            from django.utils import timezone
            import datetime

            today = timezone.now().date()
            soon = today + datetime.timedelta(days=30)
            qs = qs.filter(expiry_date__range=[today, soon])
        elif status == "expired":
            from django.utils import timezone

            qs = qs.filter(expiry_date__lt=timezone.now().date())

        location_id = self.request.GET.get("location")
        if location_id:
            qs = qs.filter(location_id=location_id)

        search = self.request.GET.get("q")
        if search:
            qs = qs.filter(
                models.Q(product__title__icontains=search)
                | models.Q(product__brand__icontains=search)
                | models.Q(product__upc__icontains=search)
                | models.Q(custom_name__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.filter(user=self.request.user)
        context["status_filter"] = self.request.GET.get("status", "")
        context["location_filter"] = self.request.GET.get("location", "")
        context["search_query"] = self.request.GET.get("q", "")
        return context


class InventoryItemFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["card_title"] = self.get_card_title()
        context["cancel_url"] = reverse_lazy("item-list")
        context["submit_text"] = "Save Changes" if self.is_update_view() else "Add Item"
        context["is_update"] = self.is_update_view()
        if self.is_update_view() and hasattr(self, "object") and self.object:
            context["item"] = self.object
        return context

    def get_card_title(self):
        if self.is_update_view():
            return "Edit Item"
        return "Add New Item"

    def is_update_view(self):
        return isinstance(self, UpdateView)


class ItemCreateView(LoginRequiredMixin, InventoryItemFormMixin, CreateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("item-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ItemUpdateView(LoginRequiredMixin, InventoryItemFormMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("item-list")

    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        photo = self.request.FILES.get("photo")
        photo_clear = self.request.POST.get("photo-clear")
        if photo_clear:
            old = self.get_object()
            if old.photo:
                old.photo.delete(save=False)
        if photo:
            form.instance.photo = photo
        return super().form_valid(form)

    def get_initial(self):
        initial = super().get_initial()
        initial["product"] = self.get_object().product.pk
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            post_data = self.request.POST.copy()
            if "product" not in post_data:
                post_data["product"] = self.get_object().product.pk
            kwargs["data"] = post_data
            if self.request.FILES:
                kwargs["files"] = self.request.FILES
        return kwargs


class ItemDeleteView(LoginRequiredMixin, DeleteView):
    model = InventoryItem
    success_url = reverse_lazy("item-list")

    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Item deleted.")
        return super().delete(request, *args, **kwargs)


@require_POST
@login_required
def item_use(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    if item.quantity > 0:
        item.quantity -= 1
        item.save(update_fields=["quantity"])
        if item.quantity == 0:
            messages.warning(request, f"{item.display_name} is now out of stock!")
        else:
            messages.success(
                request, f"Used 1 {item.display_name}. {item.quantity} remaining."
            )
    if request.headers.get("HX-Request"):
        return HttpResponse(f'<span class="badge badge-ghost">x{item.quantity}</span>')
    return redirect("item-list")


@require_POST
@login_required
def item_restock(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    quantity = int(request.POST.get("quantity", 1))
    item.quantity += quantity
    item.save(update_fields=["quantity"])
    messages.success(
        request,
        f"Restocked {item.display_name}. {item.quantity} total.",
    )
    if request.headers.get("HX-Request"):
        return HttpResponse(
            f'<span class="badge badge-success">x{item.quantity}</span>'
        )
    return redirect("item-list")


# ── Location Views ────────────────────────────────────────────────────


class LocationListView(LoginRequiredMixin, ListView):
    model = Location
    template_name = "locations/list.html"
    context_object_name = "locations"

    def get_queryset(self):
        return (
            Location.objects.filter(user=self.request.user)
            .annotate(item_count=models.Count("inventory_items"))
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_items"] = (
            InventoryItem.objects.filter(
                user=self.request.user, location__isnull=False
            ).aggregate(total=models.Sum("quantity"))["total"]
            or 0
        )
        return context


class LocationCreateView(LoginRequiredMixin, CreateView):
    model = Location
    form_class = LocationForm
    template_name = "locations/form.html"
    success_url = reverse_lazy("location-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class LocationDeleteView(LoginRequiredMixin, DeleteView):
    model = Location
    success_url = reverse_lazy("location-list")

    def get_queryset(self):
        return Location.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Location deleted.")
        return super().delete(request, *args, **kwargs)


# ── UPCProduct Catalogue Views ────────────────────────────────────────


class ProductListView(LoginRequiredMixin, ListView):
    model = UPCProduct
    template_name = "catalogue/list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        qs = UPCProduct.objects.all()
        search = self.request.GET.get("q", "")
        if search:
            qs = qs.filter(
                models.Q(title__icontains=search)
                | models.Q(brand__icontains=search)
                | models.Q(upc__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        return context


class ProductDetailView(LoginRequiredMixin, DetailView):
    model = UPCProduct
    slug_field = "upc"
    slug_url_kwarg = "upc"
    template_name = "catalogue/detail.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_items"] = InventoryItem.objects.filter(
            product=self.object, user=self.request.user
        ).select_related("location")
        return context

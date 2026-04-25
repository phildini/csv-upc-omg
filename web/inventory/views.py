"""Views for inventory tracking."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView
from django_tables2 import SingleTableView

from .forms import UploadForm
from .models import CSVUpload, LookupRecord
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

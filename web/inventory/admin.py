"""Admin configuration for core_app."""

from django.contrib import admin

from .models import CSVUpload, LookupRecord
from .tasks import lookup_batch_task, process_csv_task


@admin.register(CSVUpload)
class CSVUploadAdmin(admin.ModelAdmin):
    list_display = [
        "filename",
        "user",
        "status",
        "total_rows",
        "processed_rows",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["filename", "user__username"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.action(description="Re-process failed uploads")
    def reprocess_failed(self, request, queryset):
        for upload in queryset.filter(status="failed"):
            upload.status = "pending"
            upload.error_message = ""
            upload.save()
            process_csv_task.enqueue(upload_id=str(upload.id))
            lookup_batch_task.enqueue(upload_id=str(upload.id))

    actions = ["reprocess_failed"]


@admin.register(LookupRecord)
class LookupRecordAdmin(admin.ModelAdmin):
    list_display = ["upc", "csv_upload", "status", "product_title", "created_at"]
    list_filter = ["status", "csv_upload"]
    search_fields = ["upc", "product_title"]
    readonly_fields = ["created_at", "updated_at"]

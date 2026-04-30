"""Admin configuration for core_app."""

from django.contrib import admin

from .models import CSVUpload, Location, LookupRecord, Scan, UPCProduct, InventoryItem
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


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ["upc", "user", "status", "product_title", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["upc", "product_title", "user__username"]
    readonly_fields = ["created_at"]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "created_at", "updated_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "user__username"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(UPCProduct)
class UPCProductAdmin(admin.ModelAdmin):
    list_display = ["title", "upc", "brand", "source", "created_at"]
    list_filter = ["source", "created_at"]
    search_fields = ["title", "upc", "brand"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "user",
        "quantity",
        "location",
        "expiry_date",
        "created_at",
    ]
    list_filter = ["location", "created_at"]
    search_fields = ["product__title", "product__upc", "user__username"]
    readonly_fields = ["created_at", "updated_at"]

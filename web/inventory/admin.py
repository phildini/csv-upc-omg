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
        "display_name",
        "user",
        "quantity",
        "location",
        "has_custom_overrides",
        "created_at",
    ]
    list_filter = ["location", "created_at"]
    search_fields = [
        "product__title",
        "product__upc",
        "user__username",
        "custom_name",
    ]
    readonly_fields = ["created_at", "updated_at", "display_image_preview"]
    fieldsets = (
        ("Identity", {"fields": ("user", "product", "location")}),
        (
            "Stock",
            {
                "fields": (
                    "quantity",
                    "low_stock_threshold",
                    "purchase_date",
                    "expiry_date",
                )
            },
        ),
        (
            "Overrides",
            {
                "fields": (
                    "photo",
                    "display_image_preview",
                    "custom_name",
                    "custom_description",
                )
            },
        ),
        ("System", {"fields": ("created_at", "updated_at")}),
    )

    def has_custom_overrides(self, obj):
        has_photo = bool(obj.photo)
        has_name = bool(obj.custom_name)
        has_desc = bool(obj.custom_description)
        parts = []
        if has_photo:
            parts.append("photo")
        if has_name:
            parts.append("name")
        if has_desc:
            parts.append("desc")
        return ", ".join(parts) if parts else "—"

    def display_image_preview(self, obj):
        if obj.photo:
            from django.utils.html import format_html

            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.photo.url,
            )
        return "No custom photo uploaded"

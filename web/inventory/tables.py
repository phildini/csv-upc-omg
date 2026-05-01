"""Tables for inventory app."""

import django_tables2 as tables
from django.template import Template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import CSVUpload, InventoryItem, LookupRecord


class UploadTable(tables.Table):
    filename = tables.Column(linkify=("upload-detail", {"pk": tables.A("id")}))
    status = tables.Column()
    total_rows = tables.Column(verbose_name="Total Rows")
    processed_rows = tables.Column(verbose_name="Processed")
    created_at = tables.TemplateColumn(
        Template("{{ value|date:'Y-m-d H:i' }}"),
        verbose_name="Created",
    )

    class Meta:
        model = CSVUpload
        fields = ("filename", "status", "total_rows", "processed_rows", "created_at")
        attrs = {"class": "table table-zebra w-full"}
        order_by = "-created_at"


class LookupTable(tables.Table):
    upc = tables.Column()
    product_title = tables.Column(verbose_name="Product")
    status = tables.Column()
    csv_upload = tables.Column(
        verbose_name="Upload",
        linkify=("upload-detail", {"pk": tables.A("csv_upload_id")}),
    )
    created_at = tables.TemplateColumn(
        Template("{{ value|date:'Y-m-d H:i' }}"),
        verbose_name="Created",
    )

    class Meta:
        model = LookupRecord
        fields = ("upc", "product_title", "status", "csv_upload", "created_at")
        attrs = {"class": "table table-zebra w-full"}
        order_by = "-created_at"


class InventoryTable(tables.Table):
    image = tables.Column(empty_values=(), verbose_name="Image")
    product = tables.Column(verbose_name="Product")
    location = tables.Column(
        verbose_name="Location", accessor="location.name", default="—"
    )
    quantity = tables.Column()
    expiry_date = tables.TemplateColumn(
        Template("{{ value|default:'—' }}"),
        verbose_name="Expires",
    )
    status_badge = tables.Column(verbose_name="Status", empty_values=())
    actions = tables.TemplateColumn(
        Template(
            "<div class='flex gap-2 items-center'>"
            '<form method="post" action="{% url "item-use" record.pk %}">{% csrf_token %}'
            '<button type="submit" class="btn btn-ghost btn-xs" title="Use one">−</button></form>'
            '<a href="{% url "inventory-item-edit" record.pk %}" class="btn btn-ghost btn-xs">Edit</a>'
            '<form method="post" action="{% url "inventory-item-delete" record.pk %}" class="inline">'
            "{% csrf_token %}"
            '<button type="submit" class="btn btn-ghost btn-xs text-error" onclick="return confirm(\'Delete this item?\')">Delete</button>'
            "</form>"
            '<form method="post" action="{% url "item-restock" record.pk %}">{% csrf_token %}'
            '<input type="hidden" name="quantity" value="1" />'
            '<button type="submit" class="btn btn-ghost btn-xs text-success" title="Restock one">+</button></form>'
            "</div>"
        ),
        verbose_name="Actions",
    )

    class Meta:
        model = InventoryItem
        fields = (
            "image",
            "product",
            "location",
            "quantity",
            "expiry_date",
            "status_badge",
        )
        attrs = {"class": "table table-zebra w-full"}
        order_by = "-created_at"

    def render_image(self, record):
        image_url = record.display_image_url
        if image_url:
            return format_html(
                '<img src="{}" alt="Product Image" class="h-10 w-10 object-contain rounded" />',
                image_url,
            )
        return mark_safe('<span class="text-gray-400">No image</span>')

    def render_product(self, value, record):
        from django.urls import reverse

        return format_html(
            '<a href="{}" class="link link-hover">{}</a>',
            reverse("product-detail", kwargs={"upc": record.product.upc}),
            record.display_name,
        )

    def render_quantity(self, value, record):
        if record.quantity == 0:
            return mark_safe(
                '<span class="badge badge-error badge-sm">out of stock</span>'
            )
        if record.is_low_stock:
            return format_html(
                '<span class="badge badge-warning badge-sm gap-1">{} <span class="text-xs">(low)</span></span>',
                value,
            )
        return value

    def render_status_badge(self, record):
        if record.is_expired:
            return mark_safe('<span class="badge badge-error badge-sm">expired</span>')
        if record.is_expiring_soon:
            return mark_safe(
                '<span class="badge badge-warning badge-sm">expiring soon</span>'
            )
        if record.is_low_stock:
            return mark_safe(
                '<span class="badge badge-warning badge-sm">low stock</span>'
            )
        return mark_safe('<span class="badge badge-ghost badge-sm">OK</span>')

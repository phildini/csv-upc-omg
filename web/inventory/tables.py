"""Tables for inventory app."""

import django_tables2 as tables
from django.template import Template
from .models import CSVUpload, LookupRecord

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
        attrs = {"class": "table is-striped is-hoverable is-fullwidth"}
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
        attrs = {"class": "table is-striped is-hoverable is-fullwidth"}
        order_by = "-created_at"

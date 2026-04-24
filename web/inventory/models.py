import uuid

from django.conf import settings
from django.db import models


class CSVUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="csv_uploads"
    )
    file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("pending_lookups", "Pending Lookups"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.filename} ({self.get_status_display()})"


class LookupRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    csv_upload = models.ForeignKey(
        CSVUpload, on_delete=models.CASCADE, related_name="lookups"
    )
    upc = models.CharField(max_length=14)
    product_title = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("success", "Success"),
            ("not_found", "Not Found"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    error_message = models.TextField(blank=True, default="")
    raw_response = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["csv_upload", "upc"],
                name="unique_upc_per_upload",
            ),
        ]
        indexes = [
            models.Index(fields=["csv_upload", "status"]),
        ]

    def __str__(self):
        return f"{self.upc} - {self.get_status_display()}"

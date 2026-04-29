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


class Scan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scans"
    )
    upc = models.CharField(max_length=14)
    product_title = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("not_found", "Not Found"),
            ("failed", "Failed"),
        ],
    )
    raw_response = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.upc} - {self.get_status_display()}"


class Location(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="locations"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_location_name_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self):
        return f"{self.name}"


class UPCProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upc = models.CharField(max_length=14, unique=True)
    title = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    image_url = models.URLField(blank=True, default="")
    source = models.CharField(
        max_length=50,
        choices=[
            ("upcitemdb", "UPCItemDB"),
            ("openfoodfacts", "Open Food Facts"),
            ("manual", "Manual Entry"),
        ],
        default="manual",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["upc"]),
            models.Index(fields=["brand"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.upc})"


class InventoryItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inventory_items",
    )
    product = models.ForeignKey(
        UPCProduct, on_delete=models.CASCADE, related_name="inventory_items"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    low_stock_threshold = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    purchase_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "expiry_date"]),
            models.Index(fields=["user", "quantity"]),
        ]

    def __str__(self):
        return f"{self.product.title} (x{self.quantity})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        from django.utils import timezone

        return self.expiry_date < timezone.now().date()

    @property
    def is_expiring_soon(self, days=30):
        if not self.expiry_date:
            return False
        from django.utils import timezone
        import datetime

        threshold = timezone.now().date() + datetime.timedelta(days=days)
        return self.expiry_date <= threshold and not self.is_expired

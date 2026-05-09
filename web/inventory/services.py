"""Service layer wrapping core library for Django app."""

import csv
import io
from pathlib import Path

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from csv_upc_omg.barcode_lookup import (
    BarcodeAPIError,
    fetch_product_details_sync,
    fetch_product_title_sync,
)
from csv_upc_omg.csv_utils import extract_upcs_from_csv

from .models import (
    CSVUpload,
    InventoryItem,
    Location,
    LookupRecord,
    UPCProduct,
)


class UploadService:
    """Service layer for processing CSV uploads and barcode lookups."""

    @staticmethod
    def process_upload(upload: CSVUpload) -> int:
        """Read CSV and create LookupRecords, return count of UPCs found."""
        file_path = Path(upload.file.path)
        upcs = extract_upcs_from_csv(file_path)
        upload.total_rows = len(upcs)
        upload.save(update_fields=["total_rows"])

        records = [
            LookupRecord(csv_upload=upload, upc=upc, status="pending") for upc in upcs
        ]
        LookupRecord.objects.bulk_create(records, ignore_conflicts=True)
        return len(records)

    @staticmethod
    async def aprocess_upload(upload: CSVUpload) -> int:
        """Async version of process_upload."""
        return await sync_to_async(UploadService.process_upload)(upload)

    @staticmethod
    def lookup_upc(upc: str, timeout: float = 10.0) -> str | None:
        """Fetch product title for UPC.

        Returns the product title if found, None if not found.
        Raises BarcodeAPIError on network/API failures.
        """
        return fetch_product_title_sync(upc, timeout=timeout)

    @staticmethod
    def lookup_product_details(
        upc: str, timeout: float = 10.0
    ) -> dict[str, str | None]:
        """Fetch full product details for UPC from APIs.

        Returns dict with keys: title, brand, category, description, image_url, source.

        Raises:
            BarcodeAPIError: If no product data is found.
        """
        return fetch_product_details_sync(upc, timeout=timeout)

    @staticmethod
    async def alookup_upc(upc: str, timeout: float = 10.0) -> str | None:
        """Async version of lookup_upc."""
        return await sync_to_async(UploadService.lookup_upc, thread_sensitive=True)(
            upc, timeout
        )

    @staticmethod
    def batch_lookup(upload: CSVUpload, timeout: float = 10.0) -> dict:
        """Process all pending lookups for an upload."""
        pending = upload.lookups.filter(status="pending")
        results = {"success": 0, "not_found": 0, "failed": 0}

        for record in pending:
            try:
                title = UploadService.lookup_upc(record.upc, timeout)
                if title:
                    record.product_title = title
                    record.status = "success"
                    record.error_message = ""
                else:
                    record.status = "not_found"
                    record.error_message = ""
                record.save(update_fields=["product_title", "status", "error_message"])
            except BarcodeAPIError as e:
                record.status = "failed"
                record.error_message = str(e)
                record.save(update_fields=["status", "error_message"])

            results[record.status] += 1
            upload.processed_rows += 1
            upload.save(update_fields=["processed_rows"])

        upload.status = "completed"
        upload.save(update_fields=["status"])
        return results

    @staticmethod
    async def abatch_lookup(upload: CSVUpload, timeout: float = 10.0) -> dict:
        """Async version of batch_lookup."""
        return await sync_to_async(UploadService.batch_lookup, thread_sensitive=True)(
            upload, timeout
        )

    @staticmethod
    def scan_and_create_item(
        user: User,
        upc: str,
        location: Location | None = None,
        quantity: int = 1,
        timeout: float = 10.0,
    ) -> InventoryItem:
        """Scan a barcode and create an InventoryItem.

        First checks if UPCProduct already exists. If not, fetches from the API
        and creates the catalogue entry. Then creates an InventoryItem linked to
        the user, the UPCProduct, and optional location.

        Args:
            user: The user creating the item.
            upc: The UPC code scanned.
            location: Optional Location for where the item is stored.
            quantity: Number of items, defaults to 1.
            timeout: API timeout in seconds, defaults to 10.0.

        Returns:
            The newly created InventoryItem.

        Raises:
            BarcodeAPIError: If no product data is found in the API.
        """
        product, _ = UPCProduct.objects.get_or_create(
            upc=upc,
            defaults={
                "title": f"Unknown Product ({upc})",
                "source": "manual",
            },
        )

        if product.source == "manual" and not product.title.startswith("Unknown"):
            pass
        elif product.source == "manual":
            try:
                details = fetch_product_details_sync(upc, timeout=timeout)
                if details.get("title"):
                    product.title = details["title"] or product.title
                    product.brand = details.get("brand") or product.brand
                    product.category = details.get("category") or product.category
                    product.description = (
                        details.get("description") or product.description
                    )
                    product.image_url = details.get("image_url") or product.image_url
                    product.source = details.get("source") or product.source
                    product.save()
            except BarcodeAPIError:
                pass

        item = InventoryItem.objects.create(
            user=user,
            product=product,
            location=location,
            quantity=quantity,
        )
        return item

    @staticmethod
    def export_to_csv(upload: CSVUpload) -> io.BytesIO:
        """Generate enriched CSV with UPC + title + status."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["upc", "product_title", "status", "error_message"])

        for record in upload.lookups.all():
            writer.writerow(
                [
                    record.upc,
                    record.product_title or "",
                    record.status,
                    record.error_message,
                ]
            )

        output.seek(0)
        return io.BytesIO(output.getvalue().encode("utf-8"))

    @staticmethod
    def get_dashboard_stats(user: User) -> dict:
        """Aggregate stats for dashboard view."""
        from django.db import models
        from django.utils import timezone
        import datetime

        uploads = CSVUpload.objects.filter(user=user)
        total_lookups = LookupRecord.objects.filter(csv_upload__in=uploads)
        success_count = total_lookups.filter(status="success").count()
        total_count = total_lookups.count()

        items = InventoryItem.objects.filter(user=user)
        total_items = items.count()
        low_stock = items.filter(quantity__lte=models.F("low_stock_threshold")).count()
        today = timezone.now().date()
        soon = today + datetime.timedelta(days=7)
        expiring_soon = items.filter(expiry_date__range=[today, soon]).count()
        expired = items.filter(expiry_date__lt=today).count()

        return {
            "total_uploads": uploads.count(),
            "total_lookups": total_count,
            "success_rate": (
                (success_count / total_count * 100) if total_count > 0 else 0
            ),
            "recent_uploads": uploads[:5],
            "total_items": total_items,
            "total_products": items.values("product").distinct().count(),
            "total_locations": Location.objects.filter(user=user).count(),
            "low_stock_count": low_stock,
            "expiring_soon_count": expiring_soon,
            "expired_count": expired,
            "recent_items": items.select_related("product", "location")[:5],
        }

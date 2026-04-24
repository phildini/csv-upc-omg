"""Service layer wrapping core library for Django app."""

import csv
import io

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from csv_upc_omg.barcode_lookup import BarcodeAPIError, fetch_product_title_sync
from csv_upc_omg.csv_utils import extract_upcs_from_csv

from .models import CSVUpload, LookupRecord


class UploadService:
    """Service layer for processing CSV uploads and barcode lookups."""

    @staticmethod
    def process_upload(upload: CSVUpload) -> int:
        """Read CSV, create LookupRecords, return count of UPCs found."""
        upcs = extract_upcs_from_csv(upload.file.path)
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
    def lookup_upc(upc: str, timeout: float = 10.0) -> dict:
        """Call barcode_lookup, return dict with title/status/error."""
        try:
            title = fetch_product_title_sync(upc, timeout=timeout)
            if title:
                return {"title": title, "status": "success", "error": ""}
            return {"title": None, "status": "not_found", "error": ""}
        except BarcodeAPIError as e:
            return {"title": None, "status": "failed", "error": str(e)}

    @staticmethod
    async def alookup_upc(upc: str, timeout: float = 10.0) -> dict:
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
            lookup_result = UploadService.lookup_upc(record.upc, timeout)
            record.product_title = lookup_result["title"]
            record.status = lookup_result["status"]
            record.error_message = lookup_result["error"]
            record.save(update_fields=["product_title", "status", "error_message"])
            results[lookup_result["status"]] += 1
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
        uploads = CSVUpload.objects.filter(user=user)
        total_lookups = LookupRecord.objects.filter(csv_upload__in=uploads)
        success_count = total_lookups.filter(status="success").count()
        total_count = total_lookups.count()

        return {
            "total_uploads": uploads.count(),
            "total_lookups": total_count,
            "success_rate": (
                (success_count / total_count * 100) if total_count > 0 else 0
            ),
            "recent_uploads": uploads[:5],
        }

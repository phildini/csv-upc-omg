"""Background tasks using django-tasks."""

from django_tasks import task

from .models import CSVUpload
from .services import UploadService


@task
def process_csv_task(upload_id: str) -> int:
    """Process uploaded CSV and create LookupRecords."""
    upload = CSVUpload.objects.get(id=upload_id)
    upload.status = "processing"
    upload.save(update_fields=["status"])

    try:
        count = UploadService.process_upload(upload)
        upload.status = "pending_lookups"
        upload.save(update_fields=["status"])
        return count
    except Exception as e:
        upload.status = "failed"
        upload.error_message = str(e)
        upload.save(update_fields=["status", "error_message"])
        raise


@task
def lookup_batch_task(upload_id: str, timeout: float = 10.0) -> dict:
    """Run barcode lookups for all rows in an upload."""
    upload = CSVUpload.objects.get(id=upload_id)
    upload.status = "processing"
    upload.save(update_fields=["status"])

    try:
        results = UploadService.batch_lookup(upload, timeout)
        return results
    except Exception as e:
        upload.status = "failed"
        upload.error_message = str(e)
        upload.save(update_fields=["status", "error_message"])
        raise

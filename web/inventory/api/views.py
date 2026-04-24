"""DRF API views for core_app."""

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import CSVUpload
from ..tasks import lookup_batch_task, process_csv_task
from .serializers import CSVUploadSerializer


class UploadViewSet(viewsets.ModelViewSet):
    """API endpoint for CSV uploads."""

    serializer_class = CSVUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Process an upload by enqueuing tasks."""
        upload = self.get_object()
        try:
            result = process_csv_task.enqueue(upload_id=str(upload.id))
            return Response(
                {
                    "task_id": result.id,
                    "status": result.status.name,
                }
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def lookup(self, request, pk=None):
        """Run barcode lookups for an upload."""
        upload = self.get_object()
        try:
            timeout = request.data.get("timeout", 10.0)
            result = lookup_batch_task.enqueue(
                upload_id=str(upload.id),
                timeout=timeout,
            )
            return Response(
                {
                    "task_id": result.id,
                    "status": result.status.name,
                    "results": result.return_value if result.return_value else {},
                }
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

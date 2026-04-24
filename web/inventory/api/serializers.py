"""DRF serializers for core_app."""

from rest_framework import serializers

from ..models import CSVUpload, LookupRecord


class LookupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LookupRecord
        fields = [
            "id",
            "upc",
            "product_title",
            "status",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields


class CSVUploadSerializer(serializers.ModelSerializer):
    lookups = LookupRecordSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CSVUpload
        fields = [
            "id",
            "user",
            "filename",
            "file",
            "status",
            "total_rows",
            "processed_rows",
            "error_message",
            "created_at",
            "updated_at",
            "lookups",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

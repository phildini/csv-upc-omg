"""Tests for the inventory Django app."""
import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from inventory.models import CSVUpload, LookupRecord


class URLResolutionTests(TestCase):
    """Test that all URL patterns resolve correctly."""

    def test_dashboard_url_resolves(self):
        url = reverse("dashboard")
        self.assertEqual(url, "/")

    def test_upload_list_url_resolves(self):
        url = reverse("upload-list")
        self.assertEqual(url, "/uploads/")

    def test_upload_create_url_resolves(self):
        url = reverse("upload-create")
        self.assertEqual(url, "/uploads/create/")

    def test_upload_detail_url_resolves(self):
        fake_id = uuid.uuid4()
        url = reverse("upload-detail", kwargs={"pk": fake_id})
        self.assertEqual(url, f"/uploads/{fake_id}/")

    def test_upload_export_url_resolves(self):
        fake_id = uuid.uuid4()
        url = reverse("upload-export", kwargs={"pk": fake_id})
        self.assertEqual(url, f"/uploads/{fake_id}/export/")

    def test_lookup_list_url_resolves(self):
        url = reverse("lookup-list")
        self.assertEqual(url, "/lookups/")

    def test_api_upload_list_url_resolves(self):
        url = reverse("api-upload-list")
        self.assertEqual(url, "/api/v1/uploads/")


class ModelTests(TestCase):
    """Test Inventory model behavior."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_csv_upload_creation(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="pending"
        )
        self.assertEqual(upload.filename, "test.csv")
        self.assertEqual(upload.status, "pending")
        self.assertEqual(upload.total_rows, 0)
        self.assertEqual(upload.processed_rows, 0)
        self.assertEqual(upload.user, self.user)

    def test_csv_upload_str_representation(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="products.csv", status="processing"
        )
        self.assertEqual(str(upload), "products.csv (Processing)")

    def test_lookup_record_creation(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        lookup = LookupRecord.objects.create(
            csv_upload=upload,
            upc="012345678905",
            status="success",
            product_title="Test Product",
        )
        self.assertEqual(lookup.upc, "012345678905")
        self.assertEqual(lookup.product_title, "Test Product")
        self.assertEqual(lookup.status, "success")

    def test_lookup_record_str_representation(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        lookup = LookupRecord.objects.create(
            csv_upload=upload, upc="012345678905", status="success"
        )
        self.assertIn("012345678905", str(lookup))

    def test_csv_upload_status_choices(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        self.assertEqual(upload.get_status_display(), "Completed")

    def test_lookup_record_status_choices(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        lookup = LookupRecord.objects.create(
            csv_upload=upload, upc="012345678905", status="not_found"
        )
        self.assertEqual(lookup.get_status_display(), "Not Found")

    def test_csv_upload_uuid_pk(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="pending"
        )
        self.assertIsInstance(upload.id, uuid.UUID)

    def test_lookup_record_uuid_pk(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        lookup = LookupRecord.objects.create(
            csv_upload=upload, upc="012345678905", status="success"
        )
        self.assertIsInstance(lookup.id, uuid.UUID)

    def test_lookup_record_unique_per_upload(self):
        upload = CSVUpload.objects.create(
            user=self.user, filename="test.csv", status="completed"
        )
        LookupRecord.objects.create(
            csv_upload=upload, upc="012345678905", status="success"
        )
        with self.assertRaises(Exception):
            LookupRecord.objects.create(
                csv_upload=upload, upc="012345678905", status="success"
            )


class ViewTests(TestCase):
    """Test inventory views require authentication."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.login(username="testuser", password="testpass")

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)

    def test_upload_list_requires_login(self):
        self.client.logout()
        response = self.client.get("/uploads/")
        self.assertEqual(response.status_code, 302)

    def test_upload_create_requires_login(self):
        self.client.logout()
        response = self.client.get("/uploads/create/")
        self.assertEqual(response.status_code, 302)

    def test_lookup_list_requires_login(self):
        self.client.logout()
        response = self.client.get("/lookups/")
        self.assertEqual(response.status_code, 302)

    def test_dashboard_returns_200_when_authenticated(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_upload_list_returns_200_when_authenticated(self):
        response = self.client.get("/uploads/")
        self.assertEqual(response.status_code, 200)

    def test_lookup_list_returns_200_when_authenticated(self):
        response = self.client.get("/lookups/")
        self.assertEqual(response.status_code, 200)

    def test_upload_create_returns_200_when_authenticated(self):
        response = self.client.get("/uploads/create/")
        self.assertEqual(response.status_code, 200)

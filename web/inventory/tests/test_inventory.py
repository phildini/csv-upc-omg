"""Tests for inventory Django app business logic."""

import csv
import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from csv_upc_omg.barcode_lookup import BarcodeAPIError
from inventory.models import CSVUpload, LookupRecord
from inventory.services import UploadService

CSV_WITH_UPCS_IN_COL_0 = b"""012345678905
071710276009
INVALID
071710276009
012345678905
"""

CSV_FIVE_UNIQUE = b"""000000000001
000000000002
000000000003
000000000004
000000000005
"""

CSV_EMPTY = b""


def make_uploaded_csv(filename="test.csv", content=CSV_WITH_UPCS_IN_COL_0):
    return SimpleUploadedFile(filename, content, content_type="text/csv")


# ── user isolation ──────────────────────────────────────────────────


class UserIsolationTests(TestCase):
    """Views only return data belonging to the requesting user."""

    def setUp(self):
        self.user_a = User.objects.create_user(username="alice", password="pass")
        self.user_b = User.objects.create_user(username="bob", password="pass")
        self.upload_a = CSVUpload.objects.create(
            user=self.user_a, filename="alice.csv", status="completed"
        )
        self.upload_b = CSVUpload.objects.create(
            user=self.user_b, filename="bob.csv", status="completed"
        )

    def test_upload_list_user_a_sees_only_own(self):
        self.client.login(username="alice", password="pass")
        resp = self.client.get("/uploads/")
        qs = resp.context["table"].data.data
        self.assertQuerySetEqual(qs, [self.upload_a.pk], transform=lambda o: o.pk)

    def test_upload_list_user_b_sees_only_own(self):
        self.client.login(username="bob", password="pass")
        resp = self.client.get("/uploads/")
        qs = resp.context["table"].data.data
        self.assertQuerySetEqual(qs, [self.upload_b.pk], transform=lambda o: o.pk)

    def test_dashboard_stats_reflect_user_data(self):
        LookupRecord.objects.create(
            csv_upload=self.upload_a, upc="111", status="success"
        )
        LookupRecord.objects.create(
            csv_upload=self.upload_b, upc="222", status="success"
        )

        self.client.login(username="alice", password="pass")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        stats = resp.context["stats"]
        self.assertEqual(stats["total_uploads"], 1)
        self.assertEqual(stats["total_lookups"], 1)


# ── service layer ───────────────────────────────────────────────────


class UploadServiceTests(TestCase):
    """Core service: CSV parsing, barcode lookup, export, stats."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass")
        self.upload = CSVUpload.objects.create(
            user=self.user,
            filename="test.csv",
            status="pending",
            file=make_uploaded_csv(),
        )

    def test_process_upload_creates_records(self):
        count = UploadService.process_upload(self.upload)
        self.upload.refresh_from_db()
        self.assertEqual(count, 5)
        self.assertEqual(self.upload.total_rows, 5)
        self.assertEqual(LookupRecord.objects.filter(csv_upload=self.upload).count(), 3)

    def test_process_upload_deduplicates(self):
        UploadService.process_upload(self.upload)
        upload2 = CSVUpload.objects.create(
            user=self.user,
            filename="dup.csv",
            status="pending",
            file=make_uploaded_csv(),
        )
        UploadService.process_upload(upload2)
        self.assertEqual(LookupRecord.objects.filter(csv_upload=upload2).count(), 3)

    @patch("inventory.services.fetch_product_title_sync")
    def test_lookup_upc_success(self, mock_fetch):
        mock_fetch.return_value = "Test Widget"
        result = UploadService.lookup_upc("012345678905")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["title"], "Test Widget")

    @patch("inventory.services.fetch_product_title_sync")
    def test_lookup_upc_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        result = UploadService.lookup_upc("000000000000")
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["title"])

    @patch("inventory.services.fetch_product_title_sync")
    def test_lookup_upc_api_error(self, mock_fetch):
        mock_fetch.side_effect = BarcodeAPIError("Rate limited")
        result = UploadService.lookup_upc("012345678905")
        self.assertEqual(result["status"], "failed")
        self.assertIn("Rate limited", result["error"])

    @patch("inventory.services.fetch_product_title_sync")
    def test_batch_lookup_updates_records(self, mock_fetch):
        rec = LookupRecord.objects.create(
            csv_upload=self.upload, upc="012345678905", status="pending"
        )
        mock_fetch.return_value = "Found Product"
        results = UploadService.batch_lookup(self.upload)
        self.assertEqual(results["success"], 1)
        rec.refresh_from_db()
        self.assertEqual(rec.product_title, "Found Product")
        self.assertEqual(rec.status, "success")
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.status, "completed")

    def test_export_to_csv_produces_valid_output(self):
        LookupRecord.objects.create(
            csv_upload=self.upload,
            upc="012345678905",
            status="success",
            product_title="Widget",
        )
        output = UploadService.export_to_csv(self.upload)
        reader = csv.reader(io.StringIO(output.getvalue().decode("utf-8")))
        rows = list(reader)
        self.assertEqual(rows[0], ["upc", "product_title", "status", "error_message"])
        self.assertEqual(rows[1][0], "012345678905")
        self.assertEqual(rows[1][1], "Widget")

    def test_dashboard_stats_with_data(self):
        upload2 = CSVUpload.objects.create(
            user=self.user,
            filename="data.csv",
            status="completed",
            file=make_uploaded_csv(),
        )
        LookupRecord.objects.create(csv_upload=upload2, upc="999", status="success")
        LookupRecord.objects.create(csv_upload=upload2, upc="888", status="failed")
        stats = UploadService.get_dashboard_stats(self.user)
        self.assertEqual(stats["total_uploads"], 2)
        self.assertEqual(stats["total_lookups"], 2)
        self.assertEqual(stats["success_rate"], 50.0)
        self.assertGreaterEqual(len(stats["recent_uploads"]), 1)


# ── view integration ────────────────────────────────────────────────


class ViewIntegrationTests(TestCase):
    """End-to-end: auth, form submission, detail/export."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.login(username="tester", password="pass")
        self.upload = CSVUpload.objects.create(
            user=self.user,
            filename="test.csv",
            status="completed",
            file=make_uploaded_csv(),
        )
        LookupRecord.objects.create(
            csv_upload=self.upload,
            upc="012345678905",
            status="success",
            product_title="Widget",
        )

    def test_upload_detail_user_scoped(self):
        hacker = User.objects.create_user(username="hacker", password="x")
        secret = CSVUpload.objects.create(
            user=hacker, filename="secret.csv", status="completed"
        )
        resp = self.client.get(f"/uploads/{secret.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_export_incomplete_upload_redirects(self):
        incomplete = CSVUpload.objects.create(
            user=self.user, filename="pending.csv", status="processing"
        )
        resp = self.client.get(f"/uploads/{incomplete.pk}/export/")
        self.assertEqual(resp.status_code, 302)

    def test_export_completing_success(self):
        resp = self.client.get(f"/uploads/{self.upload.pk}/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment;", resp["Content-Disposition"])

    def test_create_upload_via_post(self):
        """POST to upload-create saves a CSV and processes it."""
        before = CSVUpload.objects.count()
        csv_file = make_uploaded_csv("new_upload.csv", CSV_FIVE_UNIQUE)
        resp = self.client.post(
            "/uploads/create/",
            {"file": csv_file},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CSVUpload.objects.count(), before + 1)

    def test_auth_required_for_all_views(self):
        """All inventory views require authentication."""
        for path in ["/", "/uploads/", "/uploads/create/", "/lookups/"]:
            self.client.logout()
            resp = self.client.get(path)
            self.assertEqual(
                resp.status_code,
                302,
                f"{path} did not redirect when unauthenticated",
            )

"""Tests for inventory Django app business logic."""

import csv
import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from csv_upc_omg.barcode_lookup import BarcodeAPIError
from inventory.models import (
    CSVUpload,
    InventoryItem,
    Location,
    LookupRecord,
    Scan,
    UPCProduct,
)
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
        self.assertEqual(result, "Test Widget")

    @patch("inventory.services.fetch_product_title_sync")
    def test_lookup_upc_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        result = UploadService.lookup_upc("000000000000")
        self.assertIsNone(result)

    @patch("inventory.services.fetch_product_title_sync")
    def test_lookup_upc_api_error(self, mock_fetch):
        mock_fetch.side_effect = BarcodeAPIError("Rate limited")
        with self.assertRaises(BarcodeAPIError):
            UploadService.lookup_upc("012345678905")

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


# ── Scan → Inventory flow ───────────────────────────────────────────


class ScanInventoryFlowTests(TestCase):
    """End-to-end: scanning a UPC creates inventory items."""

    def setUp(self):
        self.user = User.objects.create_user(username="scanner", password="pass")
        self.client.login(username="scanner", password="pass")

    def test_scan_successful_lookup_creates_scan_record(self):
        """POST to scan with a valid UPC creates a Scan record."""
        with patch("inventory.services.fetch_product_details_sync") as mock_api:
            mock_api.return_value = {
                "title": "Test Widget",
                "brand": "TestBrand",
                "category": "TestCategory",
                "description": "",
                "image_url": "",
                "source": "upcitemdb",
            }
            resp = self.client.post(
                "/scan/",
                {"upc": "012345678905"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Widget", resp.content)
        self.assertTrue(UPCProduct.objects.filter(upc="012345678905").exists())
        scan = Scan.objects.get(user=self.user, upc="012345678905")
        self.assertEqual(scan.status, "success")
        self.assertEqual(scan.product_title, "Test Widget")

    def test_scan_failed_lookup_creates_failed_scan_record(self):
        """POST to scan with an API error creates a failed Scan record."""
        with patch("inventory.services.fetch_product_details_sync") as mock_api:
            from csv_upc_omg.barcode_lookup import BarcodeAPIError

            mock_api.side_effect = BarcodeAPIError("Rate limited")
            resp = self.client.post(
                "/scan/",
                {"upc": "012345678905"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Lookup failed", resp.content)
        scan = Scan.objects.get(user=self.user, upc="012345678905")
        self.assertEqual(scan.status, "failed")

    def test_scan_create_item_adds_to_inventory(self):
        """POST to scan/create-item creates an InventoryItem."""
        from inventory.models import InventoryItem, Location, UPCProduct

        product = UPCProduct.objects.create(
            upc="012345678905",
            title="Test Widget",
            brand="TestBrand",
            source="upcitemdb",
        )
        location = Location.objects.create(user=self.user, name="Kitchen Pantry")

        before = InventoryItem.objects.count()
        resp = self.client.post(
            "/scan/create-item/",
            {
                "upc": "012345678905",
                "product_id": str(product.id),
                "quantity": 2,
                "location": str(location.id),
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Added to Inventory", resp.content)
        self.assertEqual(InventoryItem.objects.count(), before + 1)

        item = InventoryItem.objects.get(user=self.user, product=product)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.location, location)

    def test_scan_create_item_without_location(self):
        """POST to scan/create-item works with no location selected."""
        from inventory.models import InventoryItem, UPCProduct

        product = UPCProduct.objects.create(
            upc="012345678905",
            title="Test Widget",
            source="upcitemdb",
        )

        resp = self.client.post(
            "/scan/create-item/",
            {
                "upc": "012345678905",
                "product_id": str(product.id),
                "quantity": 1,
            },
        )

        self.assertEqual(resp.status_code, 200)
        item = InventoryItem.objects.get(user=self.user, product=product)
        self.assertIsNone(item.location)

    def test_scan_create_item_invalid_product_returns_404(self):
        """POST with nonexistent product_id returns 404."""
        import uuid

        resp = self.client.post(
            "/scan/create-item/",
            {
                "upc": "012345678905",
                "product_id": str(uuid.uuid4()),
                "quantity": 1,
            },
        )
        self.assertEqual(resp.status_code, 404)

    def test_scan_create_item_wrong_user_location(self):
        """POST with another user's location returns 400."""
        from inventory.models import Location, UPCProduct

        hacker = User.objects.create_user(username="hacker", password="x")
        location = Location.objects.create(user=hacker, name="Hacker's Shelf")
        product = UPCProduct.objects.create(
            upc="012345678905", title="Widget", source="upcitemdb"
        )

        resp = self.client.post(
            "/scan/create-item/",
            {
                "upc": "012345678905",
                "product_id": str(product.id),
                "quantity": 1,
                "location": str(location.id),
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_scan_get_returns_page(self):
        """GET /scan/ renders the scan page."""
        resp = self.client.get("/scan/")
        self.assertEqual(resp.status_code, 200)
        # Updated to match new UI - the page title is now "Scan UPC"
        self.assertContains(resp, "Scan UPC")

    def test_scan_requires_auth(self):
        self.client.logout()
        for method in ["GET", "POST"]:
            resp = self.client.get("/scan/")
            self.assertEqual(resp.status_code, 302)


# ── Inventory CRUD ────────────────────────────────────────────────────


class InventoryCRUDTests(TestCase):
    """Tests for inventory item list, create, edit, delete, use, restock."""

    def setUp(self):
        self.user = User.objects.create_user(username="invuser", password="pass")
        self.client.login(username="invuser", password="pass")
        self.product = UPCProduct.objects.create(
            upc="012345678905", title="Test Widget", source="upcitemdb"
        )
        self.location = Location.objects.create(user=self.user, name="Kitchen")
        self.item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            location=self.location,
            quantity=3,
            low_stock_threshold=1,
        )

    def test_item_list_shows_items(self):
        resp = self.client.get("/items/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Widget")

    def test_item_list_user_isolation(self):
        another = User.objects.create_user(username="other", password="pass")
        InventoryItem.objects.create(
            user=another,
            product=UPCProduct.objects.create(upc="999999999999", title="Other Item"),
            quantity=1,
        )
        resp = self.client.get("/items/")
        self.assertNotContains(resp, "Other Item")
        self.assertContains(resp, "Test Widget")

    def test_item_list_empty_state(self):
        InventoryItem.objects.filter(user=self.user).delete()
        resp = self.client.get("/items/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No inventory items yet")

    def test_item_create(self):
        before = InventoryItem.objects.count()
        resp = self.client.post(
            "/items/create/",
            {
                "product": str(self.product.id),
                "quantity": 5,
                "location": str(self.location.id),
                "low_stock_threshold": 1,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(InventoryItem.objects.count(), before + 1)

    def test_item_edit(self):
        resp = self.client.get(f"/items/{self.item.id}/edit/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Widget")

        resp = self.client.post(
            f"/items/{self.item.id}/edit/",
            {
                "product": str(self.product.id),
                "quantity": 10,
                "location": str(self.location.id),
                "low_stock_threshold": 2,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)

    def test_item_edit_other_user_404(self):
        hacker = User.objects.create_user(username="hacker", password="x")
        other_item = InventoryItem.objects.create(
            user=hacker,
            product=UPCProduct.objects.create(upc="888888888888", title="Hacker Item"),
            quantity=1,
        )
        resp = self.client.get(f"/items/{other_item.id}/edit/")
        self.assertEqual(resp.status_code, 404)

    def test_item_delete(self):
        before = InventoryItem.objects.count()
        resp = self.client.post(f"/items/{self.item.id}/delete/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(InventoryItem.objects.count(), before - 1)

    def test_item_use_decrements(self):
        resp = self.client.post(f"/items/{self.item.id}/use/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 2)

    def test_item_use_doesnt_go_negative(self):
        zero_item = InventoryItem.objects.create(
            user=self.user,
            product=UPCProduct.objects.create(upc="777777777777", title="Zero"),
            quantity=0,
        )
        self.client.post(f"/items/{zero_item.id}/use/", follow=True)
        zero_item.refresh_from_db()
        self.assertEqual(zero_item.quantity, 0)

    def test_item_restock_increments(self):
        resp = self.client.post(
            f"/items/{self.item.id}/restock/",
            {"quantity": 5},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)

    def test_item_requires_auth(self):
        self.client.logout()
        for path in ["/items/", "/items/create/", f"/items/{self.item.id}/edit/"]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302, f"{path} didn't redirect")


# ── Location CRUD ─────────────────────────────────────────────────────


class LocationCRUDTests(TestCase):
    """Tests for location list, create, delete."""

    def setUp(self):
        self.user = User.objects.create_user(username="locuser", password="pass")
        self.client.login(username="locuser", password="pass")
        self.location = Location.objects.create(
            user=self.user, name="Kitchen", description="Main pantry"
        )

    def test_location_list_shows_locations(self):
        resp = self.client.get("/locations/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kitchen")

    def test_location_create(self):
        before = Location.objects.filter(user=self.user).count()
        resp = self.client.post(
            "/locations/create/",
            {"name": "Garage", "description": "Tool storage"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Location.objects.filter(user=self.user).count(), before + 1)

    def test_location_delete(self):
        before = Location.objects.filter(user=self.user).count()
        resp = self.client.post(f"/locations/{self.location.id}/delete/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Location.objects.filter(user=self.user).count(), before - 1)


# ── Catalogue Views ───────────────────────────────────────────────────


class CatalogueTests(TestCase):
    """Tests for product catalogue list and detail."""

    def setUp(self):
        self.user = User.objects.create_user(username="catuser", password="pass")
        self.client.login(username="catuser", password="pass")
        self.product = UPCProduct.objects.create(
            upc="012345678905",
            title="Cola",
            brand="BrandCo",
            category="Beverages",
            source="upcitemdb",
        )

    def test_product_list_shows_products(self):
        resp = self.client.get("/catalogue/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cola")

    def test_product_list_search(self):
        resp = self.client.get("/catalogue/", {"q": "Cola"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cola")

        resp = self.client.get("/catalogue/", {"q": "NonExistent"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Cola")

    def test_product_detail(self):
        resp = self.client.get(f"/catalogue/{self.product.upc}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cola")
        self.assertContains(resp, "BrandCo")

    def test_product_detail_shows_user_items(self):
        InventoryItem.objects.create(user=self.user, product=self.product, quantity=2)
        resp = self.client.get(f"/catalogue/{self.product.upc}/")
        self.assertEqual(resp.status_code, 200)
        # Check that it shows the inventory items section
        self.assertIn(b"Inventory Items", resp.content)
        # Check that it shows the quantity in the table
        self.assertIn(b"2", resp.content)


# ── Dashboard ─────────────────────────────────────────────────────────


class DashboardTests(TestCase):
    """Tests for dashboard with inventory stats."""

    def setUp(self):
        self.user = User.objects.create_user(username="dashuser", password="pass")
        self.client.login(username="dashuser", password="pass")
        self.product = UPCProduct.objects.create(
            upc="012345678905", title="Widget", source="upcitemdb"
        )
        self.location = Location.objects.create(user=self.user, name="Kitchen")

    def test_dashboard_shows_inventory_stats(self):
        InventoryItem.objects.create(
            user=self.user, product=self.product, quantity=5, location=self.location
        )
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "5")  # total_items stat

    def test_dashboard_shows_low_stock_alert(self):
        InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            low_stock_threshold=5,
        )
        resp = self.client.get("/")
        self.assertContains(resp, "low stock")

    def test_dashboard_shows_expired_alert(self):
        import datetime

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            expiry_date=yesterday,
        )
        resp = self.client.get("/")
        self.assertContains(resp, "expired")

    def test_dashboard_empty_state(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "0")  # total_items

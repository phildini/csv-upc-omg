"""Regression tests for item overrides, HTMX multipart forms, and catalogue immutability."""

import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from inventory.models import InventoryItem, Location, UPCProduct


class CatalogueImmutabilityTests(TestCase):
    """Ensure users cannot edit UPCProduct (catalogue) data directly."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="catalogue_user", password="testpass"
        )
        self.client.login(username="catalogue_user", password="testpass")
        self.product = UPCProduct.objects.create(
            upc="012345678905",
            title="Immutable Catalogue Product",
            brand="BrandCo",
            description="Official description from API",
            source="upcitemdb",
        )
        self.item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            custom_name="My Custom Name",
        )

    def test_no_direct_edit_url_for_catalogue_product(self):
        """Catalogue product detail page has no edit button for users."""
        resp = self.client.get(f"/catalogue/{self.product.upc}/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Edit Product")
        self.assertNotContains(resp, "edit-product")

    def test_item_edit_only_affects_inventory_item(self):
        """Editing inventory item does not modify the underlying UPCProduct."""
        original_title = self.product.title
        resp = self.client.post(
            f"/items/{self.item.id}/edit/",
            {
                "product": str(self.product.id),
                "quantity": 5,
                "custom_name": "Completely Different Name",
                "custom_description": "My custom description",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.title, original_title)
        self.assertEqual(self.product.brand, "BrandCo")
        self.assertEqual(self.product.description, "Official description from API")

    def test_item_overrides_dont_pollute_other_items(self):
        """Custom overrides on one item don't affect another item using same product."""
        item2 = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=2,
        )
        self.assertEqual(item2.display_name, "Immutable Catalogue Product")
        self.assertEqual(item2.display_description, "Official description from API")


class HTMXFormRegressionTests(TestCase):
    """Ensure HTMX form submissions work correctly with multipart file uploads."""

    def setUp(self):
        self.user = User.objects.create_user(username="htmx_user", password="testpass")
        self.client.login(username="htmx_user", password="testpass")
        self.product = UPCProduct.objects.create(
            upc="999999999999",
            title="HTMX Test Product",
            source="manual",
        )
        self.location = Location.objects.create(user=self.user, name="HTMX Shelf")

    def _make_test_image(self, size=(100, 100), color="red"):
        img = Image.new("RGB", size, color=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile("test.jpg", buf.getvalue(), content_type="image/jpeg")

    def test_create_form_renders_with_htmx_attributes(self):
        """GET item-create returns form with correct HTMX multipart encoding."""
        resp = self.client.get("/items/create/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"multipart/form-data", resp.content)
        self.assertIn(b"/items/create/", resp.content)

    def test_create_with_photo_via_htmx(self):
        """POST create with photo and multipart data succeeds."""
        photo = self._make_test_image()
        before = InventoryItem.objects.count()
        resp = self.client.post(
            "/items/create/",
            {
                "product": str(self.product.id),
                "quantity": 3,
                "location": str(self.location.id),
                "low_stock_threshold": 1,
                "custom_name": "HTMX Created Item",
                "custom_description": "Created via HTMX multipart form",
                "photo": photo,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(InventoryItem.objects.count(), before + 1)
        item = InventoryItem.objects.get(custom_name="HTMX Created Item")
        self.assertTrue(item.photo)
        self.assertEqual(item.custom_description, "Created via HTMX multipart form")

    def test_edit_form_renders_with_current_overrides(self):
        """GET item-edit shows current custom values in form."""
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            custom_name="Existing Custom Name",
            custom_description="Existing Custom Description",
        )
        resp = self.client.get(
            f"/items/{item.id}/edit/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Existing Custom Name", resp.content)

    def test_edit_with_photo_replacement_via_htmx(self):
        """POST item-edit with new photo replaces the existing one."""
        from inventory.models import Location

        location = Location.objects.create(user=self.user, name="HTMX Edit Shelf")
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            location=location,
        )
        old_photo_name = None

        photo1 = self._make_test_image(color="blue")
        item.photo = photo1
        item.save()
        item.refresh_from_db()
        old_photo_name = item.photo.name
        self.assertTrue(old_photo_name)

        photo2 = self._make_test_image(color="green")
        resp = self.client.post(
            f"/items/{item.id}/edit/",
            {
                "product": str(self.product.id),
                "quantity": 1,
                "location": str(location.id),
                "low_stock_threshold": 1,
                "photo": photo2,
                "custom_name": "Updated with new photo",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.custom_name, "Updated with new photo")
        self.assertTrue(item.photo)
        self.assertNotEqual(item.photo.name, old_photo_name)

    def test_edit_clear_photo_deletes_file(self):
        """POST item-edit with photo-clear checkbox removes the photo."""
        from inventory.models import Location

        location = Location.objects.create(user=self.user, name="Clear Shelf")
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            location=location,
        )
        photo = self._make_test_image()
        item.photo = photo
        item.save()
        self.assertTrue(item.photo)

        resp = self.client.post(
            f"/items/{item.id}/edit/",
            {
                "product": str(self.product.id),
                "quantity": 1,
                "location": str(location.id),
                "low_stock_threshold": 1,
                "photo-clear": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(bool(item.photo))

    def test_create_form_validation_rejects_empty_product(self):
        """POST create without product field fails validation."""
        resp = self.client.post(
            "/items/create/",
            {
                "quantity": 1,
                "low_stock_threshold": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_htmx_create_success_redirects(self):
        """HTMX form submission on create redirects to item list."""
        resp = self.client.post(
            "/items/create/",
            {
                "product": str(self.product.id),
                "quantity": 1,
                "low_stock_threshold": 1,
            },
            follow=True,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            InventoryItem.objects.filter(
                user=self.user, product=self.product, quantity=1
            ).exists()
        )


class ScanFlowRegressionTests(TestCase):
    """Ensure scan-to-create flow still works with new fields."""

    def setUp(self):
        self.user = User.objects.create_user(username="scan_user", password="testpass")
        self.client.login(username="scan_user", password="testpass")

    @patch("inventory.services.fetch_product_details_sync")
    def test_scan_then_create_item_with_overrides(self, mock_api):
        """Scan a UPC, then create item with custom fields via HTMX."""
        mock_api.return_value = {
            "title": "Scanned Widget",
            "brand": "ScanBrand",
            "category": "ScanCategory",
            "description": "Scan description",
            "image_url": "https://example.com/scan.jpg",
            "source": "upcitemdb",
        }

        resp = self.client.post(
            "/scan/",
            {"upc": "012345678905"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)

        product = UPCProduct.objects.get(upc="012345678905")
        location = Location.objects.create(user=self.user, name="Scan Shelf")

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
        self.assertEqual(InventoryItem.objects.count(), before + 1)

        item = InventoryItem.objects.get(user=self.user, product=product)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.custom_name, "")
        self.assertEqual(item.custom_description, "")
        self.assertFalse(item.photo)

    def test_scan_create_item_user_isolation(self):
        """Scan create-item rejects another user's location."""
        from inventory.models import InventoryItem, Location, UPCProduct

        hacker = User.objects.create_user(username="hacker2", password="x")
        hacker_location = Location.objects.create(user=hacker, name="Hacker Shelf")
        product = UPCProduct.objects.create(
            upc="012345678905", title="Widget", source="upcitemdb"
        )

        resp = self.client.post(
            "/scan/create-item/",
            {
                "upc": "012345678905",
                "product_id": str(product.id),
                "quantity": 1,
                "location": str(hacker_location.id),
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            InventoryItem.objects.filter(user=self.user, product=product).exists()
        )


class DisplayPropertyFallbackTests(TestCase):
    """Comprehensive tests for display_name, display_image_url, display_description."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="display_user", password="testpass"
        )
        self.client.login(username="display_user", password="testpass")
        self.product = UPCProduct.objects.create(
            upc="0123456789",
            title="Base Product",
            brand="BaseBrand",
            description="Base Description",
            image_url="https://example.com/base.jpg",
            source="upcitemdb",
        )

    def test_all_catalogue_fallbacks(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        self.assertEqual(item.display_name, "Base Product")
        self.assertEqual(item.display_description, "Base Description")
        self.assertEqual(item.display_image_url, "https://example.com/base.jpg")

    def test_partial_overrides(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            custom_name="My Item",
        )
        self.assertEqual(item.display_name, "My Item")
        self.assertEqual(item.display_description, "Base Description")
        self.assertEqual(item.display_image_url, "https://example.com/base.jpg")

    def test_full_overrides(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            custom_name="Full Override Name",
            custom_description="Full Override Description",
        )
        self.assertEqual(item.display_name, "Full Override Name")
        self.assertEqual(item.display_description, "Full Override Description")
        self.assertEqual(item.display_image_url, "https://example.com/base.jpg")

    def test_photo_overrides_catalogue_image(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        photo = SimpleUploadedFile(
            "custom.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
            photo=photo,
        )
        self.assertTrue(item.display_image_url)
        self.assertNotEqual(item.display_image_url, "https://example.com/base.jpg")

    def test_photo_and_catalogue_image_fallback_order(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        self.assertEqual(item.display_image_url, "https://example.com/base.jpg")

        from io import BytesIO
        from PIL import Image

        img = Image.new("RGB", (50, 50), color="white")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        item.photo = SimpleUploadedFile(
            "custom.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        item.save()
        self.assertIn("inventory-items/", item.display_image_url)

    def test_str_method_uses_display_name(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=3,
        )
        self.assertEqual(str(item), "Base Product (x3)")

        item.custom_name = "My Custom"
        item.save()
        self.assertEqual(str(item), "My Custom (x3)")

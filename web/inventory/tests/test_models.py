"""Tests for new inventory tracker models."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from inventory.models import InventoryItem, Location, UPCProduct


class LocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")

    def test_create_location(self):
        location = Location.objects.create(user=self.user, name="Kitchen Pantry")
        self.assertEqual(location.name, "Kitchen Pantry")
        self.assertEqual(str(location), "Kitchen Pantry")
        self.assertIsNotNone(location.created_at)
        self.assertIsNotNone(location.updated_at)

    def test_unique_location_name_per_user(self):
        Location.objects.create(user=self.user, name="Garage")
        with self.assertRaises(IntegrityError):
            Location.objects.create(user=self.user, name="Garage")

    def test_different_users_same_name(self):
        user2 = User.objects.create_user(username="user2", password="pass")
        Location.objects.create(user=self.user, name="Basement")
        Location.objects.create(user=user2, name="Basement")
        self.assertEqual(Location.objects.filter(name="Basement").count(), 2)

    def test_ordering_by_name(self):
        Location.objects.create(user=self.user, name="Zebra Room")
        Location.objects.create(user=self.user, name="Alpha Room")
        Location.objects.create(user=self.user, name="Middle Room")
        locations = list(Location.objects.filter(user=self.user))
        self.assertEqual(locations[0].name, "Alpha Room")
        self.assertEqual(locations[1].name, "Middle Room")
        self.assertEqual(locations[2].name, "Zebra Room")


class UPCProductTests(TestCase):
    def test_create_product(self):
        product = UPCProduct.objects.create(
            upc="012345678905",
            title="Test Widget",
            brand="Acme Corp",
            category="Household",
            source="manual",
        )
        self.assertEqual(str(product), "Test Widget (012345678905)")
        self.assertEqual(product.brand, "Acme Corp")
        self.assertEqual(product.source, "manual")

    def test_unique_upc(self):
        UPCProduct.objects.create(upc="000000000001", title="Product A")
        with self.assertRaises(IntegrityError):
            UPCProduct.objects.create(upc="000000000001", title="Product B")

    def test_defaults(self):
        product = UPCProduct.objects.create(upc="111111111111", title="Bare Bones")
        self.assertEqual(product.brand, "")
        self.assertEqual(product.category, "")
        self.assertEqual(product.description, "")
        self.assertEqual(product.image_url, "")
        self.assertEqual(product.source, "manual")

    def test_ordering_by_title(self):
        UPCProduct.objects.create(upc="100000000001", title="Zebra Product")
        UPCProduct.objects.create(upc="100000000002", title="Alpha Product")
        UPCProduct.objects.create(upc="100000000003", title="Middle Product")
        products = list(UPCProduct.objects.all())
        self.assertEqual(products[0].title, "Alpha Product")
        self.assertEqual(products[1].title, "Middle Product")
        self.assertEqual(products[2].title, "Zebra Product")

    def test_all_sources(self):
        for source_code, _ in UPCProduct._meta.get_field("source").choices:
            product = UPCProduct.objects.create(
                upc=f"20000000000{source_code[0]}",
                title=f"Source Test {source_code}",
                source=source_code,
            )
            self.assertEqual(product.source, source_code)


class InventoryItemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.product = UPCProduct.objects.create(
            upc="012345678905", title="Canned Beans"
        )
        self.location = Location.objects.create(user=self.user, name="Pantry")

    def test_create_inventory_item(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            quantity=5,
            low_stock_threshold=2,
        )
        self.assertEqual(str(item), "Canned Beans (x5)")
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.low_stock_threshold, 2)

    def test_defaults(self):
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
        )
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.low_stock_threshold, 1)
        self.assertIsNone(item.purchase_date)
        self.assertIsNone(item.expiry_date)
        self.assertIsNone(item.location)
        self.assertEqual(item.notes, "")

    def test_with_location_and_dates(self):
        tomorrow = date.today() + timedelta(days=1)
        last_week = date.today() - timedelta(days=7)
        item = InventoryItem.objects.create(
            user=self.user,
            product=self.product,
            location=self.location,
            quantity=3,
            purchase_date=last_week,
            expiry_date=tomorrow,
        )
        self.assertEqual(item.location, self.location)
        self.assertEqual(item.purchase_date, last_week)
        self.assertEqual(item.expiry_date, tomorrow)

    def test_ordering_by_created_at(self):
        item1 = InventoryItem.objects.create(
            user=self.user, product=self.product, quantity=1
        )
        item2 = InventoryItem.objects.create(
            user=self.user, product=self.product, quantity=2
        )
        items = list(InventoryItem.objects.filter(user=self.user))
        self.assertIn(item2, items)
        self.assertIn(item1, items)
        self.assertEqual(items[0], item2)

    def test_location_set_null_on_delete(self):
        item = InventoryItem.objects.create(
            user=self.user, product=self.product, location=self.location
        )
        self.location.delete()
        item.refresh_from_db()
        self.assertIsNone(item.location)

    def test_product_cascade_delete(self):
        item = InventoryItem.objects.create(
            user=self.user, product=self.product
        )
        self.product.delete()
        self.assertEqual(InventoryItem.objects.filter(id=item.id).count(), 0)


class ModelRelationshipTests(TestCase):
    def test_user_locations_count(self):
        user = User.objects.create_user(username="testuser", password="pass")
        Location.objects.create(user=user, name="Kitchen")
        Location.objects.create(user=user, name="Garage")
        self.assertEqual(user.locations.count(), 2)

    def test_user_inventory_items_count(self):
        user = User.objects.create_user(username="testuser", password="pass")
        product = UPCProduct.objects.create(upc="012345678905", title="Widget")
        InventoryItem.objects.create(user=user, product=product, quantity=2)
        InventoryItem.objects.create(user=user, product=product, quantity=5)
        self.assertEqual(user.inventory_items.count(), 2)

    def test_product_inventory_items_count(self):
        product = UPCProduct.objects.create(upc="012345678905", title="Widget")
        user1 = User.objects.create_user(username="user1", password="pass")
        user2 = User.objects.create_user(username="user2", password="pass")
        InventoryItem.objects.create(user=user1, product=product, quantity=1)
        InventoryItem.objects.create(user=user2, product=product, quantity=3)
        self.assertEqual(product.inventory_items.count(), 2)

    def test_location_inventory_items_count(self):
        user = User.objects.create_user(username="testuser", password="pass")
        location = Location.objects.create(user=user, name="Shelf A")
        product = UPCProduct.objects.create(upc="012345678905", title="Widget")
        InventoryItem.objects.create(user=user, product=product, location=location)
        InventoryItem.objects.create(user=user, product=product, location=location)
        self.assertEqual(location.inventory_items.count(), 2)


class ModelValidationTests(TestCase):
    def test_negative_quantity_raises(self):
        user = User.objects.create_user(username="testuser", password="pass")
        product = UPCProduct.objects.create(upc="012345678905", title="Widget")
        with self.assertRaises(Exception):
            InventoryItem.objects.create(user=user, product=product, quantity=-1)

    def test_negative_threshold_raises(self):
        user = User.objects.create_user(username="testuser", password="pass")
        product = UPCProduct.objects.create(upc="012345678905", title="Widget")
        with self.assertRaises(Exception):
            InventoryItem.objects.create(
                user=user, product=product, low_stock_threshold=-1
            )

    def test_empty_location_name(self):
        user = User.objects.create_user(username="testuser", password="pass")
        with self.assertRaises(Exception):
            location = Location(user=user, name="")
            location.full_clean()

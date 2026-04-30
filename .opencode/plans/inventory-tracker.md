# Inventory Tracker Expansion Plan

## Goal
Transform the current CSV/barcode lookup tool into a full household inventory tracker with product cataloguing, item tracking, location management, quantity tracking, and expiration alerts.

## New Data Model

### Location
Physical places where inventory items live.
- `id` UUID PK
- `user` FK to auth.User (CASCADE)
- `name` CharField(100) — "Kitchen Pantry", "Garage Shelf A"
- `room` CharField(50) with choices (kitchen, pantry, fridge, bathroom, bedroom, garage, laundry, office, other)
- `description` TextField blank default=""
- `created_at` DateTimeField auto_now_add
- UniqueConstraint: `(user, name)`
- Related name: `user.locations`

### UPCProduct (Catalogue)
Canonical product library populated by API lookups or manual entry. Shared across users (global table).
- `id` UUID PK
- `upc` CharField(14) unique, db_index
- `title` CharField(255)
- `brand` CharField(200) blank default=""
- `category` CharField(100) blank default=""
- `notes` TextField blank default=""
- `source` CharField(20) choices: ("api", "Manual API"), ("manual", "Manual Entry"), default="api"
- `created_at` DateTimeField auto_now_add
- `updated_at` DateTimeField auto_now
- Indexes: title, category, upc

### InventoryItem
A physical instance the user owns and tracks.
- `id` UUID PK
- `user` FK to auth.User (CASCADE)
- `product` FK to UPCProduct (PROTECT) — the catalogue entry
- `location` FK to Location (SET_NULL, blank, null)
- `quantity` PositiveIntegerField default=1
- `quantity_unit` CharField(20) blank default=""
- `min_quantity` PositiveIntegerField default=1 (low stock threshold)
- `purchase_date` DateField null blank
- `expiration_date` DateField null blank
- `notes` TextField blank default=""
- `created_at` DateTimeField auto_now_add
- `updated_at` DateTimeField auto_now
- UniqueConstraint: `(user, product, location, expiration_date)` — one record per item instance
- Indexes: (user, quantity), (user, expiration_date)
- Helper properties: `is_low_stock`, `is_expired`, `is_expiring_soon(days=30)`

### Existing models — no changes
- `CSVUpload`, `LookupRecord`, `Scan` stay as-is for backwards compatibility
- Scans now also create InventoryItems automatically

## Implementation Phases

### Phase 1: New Models & Migrations
1. Add `Location`, `UPCProduct`, `InventoryItem` to `web/inventory/models.py`
2. Run `makemigrations` → creates `0004_location_upcproduct_inventoryitem.py`
3. Register new models in `web/inventory/admin.py` with list_display, filters, search
4. Test with a quick smoke: `python manage.py migrate`, create a few test records in admin

**Success criteria:** Migrations apply cleanly, admin works, no regressions to existing tests

---

### Phase 2: Update Scan Flow to Auto-Catalogue
1. Modify `BarcodeAPIError` → `fetch_product_title_sync` should also return metadata:
   - `_fetch_upcitemdb` → returns dict with `{"title", "brand", "category"}`
   - `_fetch_openfoodfacts` → returns dict with `{"title", "brand", "category"}`
2. New `CatalogueService` class in `web/inventory/services.py`:
   - `get_or_create_product(upc, api_data)` — returns UPCProduct
   - `create_item(user, product, quantity=1, location=None, expiration_date=None)` — returns InventoryItem
3. Update `scan()` view:
   - On successful lookup: create/get UPCProduct → create InventoryItem
   - Keep Scan record as historical log
   - Show richer result with product name, brand, category

**Success criteria:** Scanning a UPC creates catalogue entry + inventory item, existing scan flow works

---

### Phase 3: Update CSV Upload Flow for Catalogue
1. Update `UploadService.process_upload()` or add `process_upload_to_inventory()`:
   - For each UPC that resolves, create/get UPCProduct → create InventoryItem
   - Batch mode: allow skipping unknown UPCs
2. Update `tasks.py` to use new flow
3. Optionally keep old behavior behind a flag

**Success criteria:** CSV uploads populate inventory automatically

---

### Phase 4: Views & URLS
1. Location CRUD:
   - `LocationListView` → `/locations/`
   - `LocationCreateView` → `/locations/create/`
   - `LocationDeleteView` → `/locations/<uuid>/delete/`
2. InventoryItem views:
   - `ItemListView` → `/items/` (table with search, filter by location/status)
   - `ItemCreateView` → `/items/create/` (select product, location, qty, expiry)
   - `ItemUpdateView` → `/items/<uuid>/edit/`
   - `ItemDeleteView` → `/items/<uuid>/delete/`
   - `ItemUseView` → `/items/<uuid>/use/` (POST: decrement qty by 1)
   - `ItemRestockView` → `/items/<uuid>/restock/` (POST: increment qty)
3. UPCProduct catalogue:
   - `ProductListView` → `/catalogue/`
   - `ProductDetailView` → `/catalogue/<upc>/`
4. Quick item add via HTMX inline form

**Success criteria:** All CRUD endpoints work, HTMX actions work, 404s on wrong user scope

---

### Phase 5: Dashboard Overhaul
1. New `InventoryService.get_stats(user)` returns:
   - `total_items` (sum of quantity where qty > 0)
   - `total_products` (distinct UPCProducts)
   - `total_locations` (user's locations)
   - `low_stock_count` (items where qty <= min_quantity)
   - `expiring_soon_count` (items expiring in next 7 days)
   - `expired_count` (items past expiry)
   - `recent_items` (last 5 created/updated)
   - `recent_scans` (last 5 scan history)
2. Rebuild `dashboard/index.html` with:
   - **Quick actions row:** [Scan UPC] [Add Item] [Browse Locations]
   - **Alerts row:** Low Stock count (badge), Expiring Soon count (badge), Expired count (badge)
   - **Summary stat cards:** Total Items, Products Catalogued, Locations
   - **Activity table:** recent inventory changes (add, use, restock, scan)
   - Empty state with onboarding CTA

**Success criteria:** Dashboard shows meaningful inventory data, quick actions link correctly

---

### Phase 6: Templates & Polishing
1. Create template structure:
   - `items/list.html` → table with qty badges, location, expiry, status icons, action buttons
   - `items/form.html` → create/edit form with product select, HTMX search
   - `items/detail.html` → product info card, history, location
   - `catalogue/list.html` → browsable product grid with images (if available)
   - `catalogue/detail.html` → product detail + all user's items tracking this product
   - `locations/list.html` → location cards with item counts per location
   - `locations/form.html` → location create/edit
2. Update `base.html` navbar:
   - Add "Items", "Catalogue", "Locations" links
   - Remove old "Lookups" link or repurpose
   - Active state handling for all new views
3. Add HTMX inline actions:
   - "Use" button → decrements qty in-place
   - "Restock" button → increments qty in-place
   - Inline edit for quantity/location

---

## Implementation Order & Milestones

Each phase is independently mergeable:
1. **Phase 1** (models) → can review and merge without breaking anything
2. **Phase 2** (scan flow) → existing scan functionality gets richer
3. **Phase 3** (upload flow) → CSV uploads become full inventory population
4. **Phase 4** (views/URLs) → full CRUD for all new models
5. **Phase 5** (dashboard) → homepage transforms to inventory hub
6. **Phase 6** (templates) → polished UI with HTMX

## Key Design Principles
- **No breaking changes to existing data** — all new tables are additive
- **User isolation** — all InventoryItem and Location queries are scoped to `request.user`
- **UPCProduct is global** — shared product catalogue, no user FK on this table
- **HTMX for interactions** — in-place restock/use without page reloads
- **DaisyUI components** — consistent badge, card, table, alert styling

"""URLs for core_app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    # Uploads
    path("uploads/", views.UploadListView.as_view(), name="upload-list"),
    path("uploads/create/", views.UploadCreateView.as_view(), name="upload-create"),
    path("uploads/<uuid:pk>/", views.UploadDetailView.as_view(), name="upload-detail"),
    path(
        "uploads/<uuid:pk>/export/",
        views.UploadExportView.as_view(),
        name="upload-export",
    ),
    path("lookups/", views.LookupListView.as_view(), name="lookup-list"),

    # Scan
    path("scan/", views.scan, name="scan"),
    path("scan/create-item/", views.scan_create_item, name="scan-create-item"),
    path("scan/history/", views.scan_history, name="scan-history"),
    path("scan/<uuid:scan_id>/", views.scan_delete, name="scan-delete"),

    # Inventory Items
    path("items/", views.ItemListView.as_view(), name="item-list"),
    path("items/create/", views.ItemCreateView.as_view(), name="item-create"),
    path(
        "items/<uuid:pk>/edit/",
        views.ItemUpdateView.as_view(),
        name="inventory-item-edit",
    ),
    path(
        "items/<uuid:pk>/delete/",
        views.ItemDeleteView.as_view(),
        name="inventory-item-delete",
    ),
    path("items/<uuid:pk>/use/", views.item_use, name="item-use"),
    path("items/<uuid:pk>/restock/", views.item_restock, name="item-restock"),

    # Locations
    path("locations/", views.LocationListView.as_view(), name="location-list"),
    path(
        "locations/create/",
        views.LocationCreateView.as_view(),
        name="location-create",
    ),
    path(
        "locations/<uuid:pk>/delete/",
        views.LocationDeleteView.as_view(),
        name="location-delete",
    ),

    # Catalogue
    path("catalogue/", views.ProductListView.as_view(), name="product-list"),
    path(
        "catalogue/<str:upc>/",
        views.ProductDetailView.as_view(),
        name="product-detail",
    ),
]

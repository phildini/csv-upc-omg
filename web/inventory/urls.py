"""URLs for core_app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("uploads/", views.UploadListView.as_view(), name="upload-list"),
    path("uploads/create/", views.UploadCreateView.as_view(), name="upload-create"),
    path("uploads/<uuid:pk>/", views.UploadDetailView.as_view(), name="upload-detail"),
    path(
        "uploads/<uuid:pk>/export/",
        views.UploadExportView.as_view(),
        name="upload-export",
    ),
    path("lookups/", views.LookupListView.as_view(), name="lookup-list"),
]

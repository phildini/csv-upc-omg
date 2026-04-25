"""URLs for core_app API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"uploads", views.UploadViewSet, basename="api-upload")

urlpatterns = [
    path("", include(router.urls)),
]

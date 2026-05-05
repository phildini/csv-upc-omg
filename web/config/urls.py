from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
import time


def health_check(request):
    return JsonResponse(
        {"status": "healthy", "timestamp": time.time(), "service": "csv-upc-omg"}
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("stagedoor.urls", namespace="stagedoor")),
    path("", include("inventory.urls")),
    path("api/v1/", include("inventory.api.urls")),
    path("health/", health_check, name="health-check"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

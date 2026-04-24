# Final Implementation Plan: Django App with ImmediateBackend

## Architecture Overview

**Monorepo structure** - `src/` (core library) stays unchanged, `web/` (Django) wraps and reuses it. Tasks defined with Django's `@task` decorator. With `ImmediateBackend`, tasks run synchronously in the same process, which simplifies the initial implementation. Easy to swap to a real backend later without refactoring task code.

```
csv-upc-omg/
├── src/                               # EXISTING - no changes
│   └── csv_upc_omg/
│       ├── __init__.py
│       ├── barcode_lookup.py
│       ├── csv_utils.py
│       └── main.py
├── tests/                             # EXISTING - no changes
├── web/                               # NEW: Django project
│   ├── manage.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   └── core_app/                      # NEW: Django app
│       ├── __init__.py
│       ├── apps.py
│       ├── models.py
│       ├── views.py
│       ├── forms.py
│       ├── urls.py
│       ├── admin.py
│       ├── services.py
│       ├── tasks.py
│       ├── management/
│       │   └── commands/
│       │       ├── process_csv.py
│       │       └── lookup_batch.py
│       ├── templates/
│       │   ├── base.html
│       │   ├── dashboard/
│       │   │   └── index.html
│       │   ├── uploads/
│       │   │   ├── list.html
│       │   │   ├── upload.html
│       │   │   └── detail.html
│       │   └── lookups/
│       │       └── list.html
│       ├── static/
│       │   └── css/
│       │       └── main.css
│       ├── api/
│       │   ├── urls.py
│       │   ├── serializers.py
│       │   └── views.py
│       └── tests/
│           ├── test_models.py
│           ├── test_services.py
│           ├── test_tasks.py
│           └── test_views.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml                     # Add Django deps
```

---

## New Dependencies (added to `pyproject.toml`)

```toml
[project.optional-dependencies]
web = [
    "django>=6.0",
    "django-environ>=0.11",
    "djangorestframework>=3.14",
    "django-tables2>=2.6",
    "django-filter>=23",
    "django-htmx>=1.17",
    "psycopg2-binary>=2.9",
    "gunicorn>=21",
    "whitenoise>=6.6",
    "django-debug-toolbar>=4.0",
]
```

Note: `asgiref` comes as a Django dependency. `csv-upc-omg` core library dependencies (`beautifulsoup4`, `click`, `httpx`) are already defined in the project's main dependencies.

---

## Data Models

### `CSVUpload` (models.py)
```python
import uuid
from django.conf import settings
from django.db import models

class CSVUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('pending_lookups', 'Pending Lookups'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending',
    )
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.filename} ({self.get_status_display()})"
```

### `LookupRecord` (models.py)
```python
class LookupRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    csv_upload = models.ForeignKey(
        CSVUpload,
        on_delete=models.CASCADE,
        related_name='lookups'
    )
    upc = models.CharField(max_length=14)
    product_title = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('success', 'Success'),
            ('not_found', 'Not Found'),
            ('failed', 'Failed'),
        ],
        default='pending',
    )
    error_message = models.TextField(blank=True, default='')
    raw_response = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['csv_upload', 'upc'],
                name='unique_upc_per_upload'
            ),
        ]
        indexes = [
            models.Index(fields=['csv_upload', 'status']),
        ]

    def __str__(self):
        return f"{self.upc} - {self.get_status_display()}"
```

---

## Service Layer (`services.py`)

Wraps core library calls and handles Django model interactions. Uses `sync_to_async` when called from async contexts.

```python
import io
import csv
from django.contrib.auth.models import User
from csv_upc_omg.csv_utils import extract_upcs_from_csv
from csv_upc_omg.barcode_lookup import (
    fetch_product_title_sync,
    BarcodeAPIError,
)
from .models import CSVUpload, LookupRecord


class UploadService:
    """Service layer for processing CSV uploads and barcode lookups."""

    @staticmethod
    def process_upload(upload: CSVUpload) -> int:
        """Read CSV, create LookupRecords, return count of UPCs found."""
        upcs = extract_upcs_from_csv(upload.file.path)

        upload.total_rows = len(upcs)
        upload.save(update_fields=['total_rows'])

        records = [
            LookupRecord(csv_upload=upload, upc=upc, status='pending')
            for upc in upcs
        ]
        LookupRecord.objects.bulk_create(records, ignore_conflicts=True)
        return len(records)

    @staticmethod
    def lookup_upc(upc: str, timeout: float = 10.0) -> dict:
        """Call barcode_lookup, return dict with title/status/error."""
        try:
            title = fetch_product_title_sync(upc, timeout=timeout)
            if title:
                return {'title': title, 'status': 'success', 'error': ''}
            return {'title': None, 'status': 'not_found', 'error': ''}
        except BarcodeAPIError as e:
            return {'title': None, 'status': 'failed', 'error': str(e)}

    @staticmethod
    def batch_lookup(upload: CSVUpload, timeout: float = 10.0) -> dict:
        """Process all pending lookups for an upload."""
        pending = upload.lookups.filter(status='pending')
        results = {'success': 0, 'not_found': 0, 'failed': 0}

        for record in pending:
            lookup_result = UploadService.lookup_upc(record.upc, timeout)
            record.product_title = lookup_result['title']
            record.status = lookup_result['status']
            record.error_message = lookup_result['error']
            record.save(
                update_fields=['product_title', 'status', 'error_message']
            )
            results[lookup_result['status']] += 1
            upload.processed_rows += 1
            upload.save(update_fields=['processed_rows'])

        upload.status = 'completed'
        upload.save(update_fields=['status'])
        return results

    @staticmethod
    def export_to_csv(upload: CSVUpload) -> io.BytesIO:
        """Generate enriched CSV with UPC + title + status."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['upc', 'product_title', 'status', 'error_message'])

        for record in upload.lookups.all():
            writer.writerow([
                record.upc,
                record.product_title or '',
                record.status,
                record.error_message,
            ])

        output.seek(0)
        return io.BytesIO(output.getvalue().encode('utf-8'))

    @staticmethod
    def get_dashboard_stats(user: User) -> dict:
        """Aggregate stats for dashboard view."""
        uploads = CSVUpload.objects.filter(user=user)
        total_lookups = LookupRecord.objects.filter(csv_upload__in=uploads)
        success_count = total_lookups.filter(status='success').count()
        total_count = total_lookups.count()

        return {
            'total_uploads': uploads.count(),
            'total_lookups': total_count,
            'success_rate': (
                (success_count / total_count * 100) if total_count > 0 else 0
            ),
            'recent_uploads': uploads[:5],
        }
```

---

## Task Definitions (`tasks.py`)

Using Django's `@task` decorator with `ImmediateBackend`. Tasks run synchronously when enqueued.

```python
from django.tasks import task
from .models import CSVUpload
from .services import UploadService


@task
def process_csv_task(upload_id: str) -> int:
    """Process uploaded CSV and create LookupRecords."""
    upload = CSVUpload.objects.get(id=upload_id)
    upload.status = 'processing'
    upload.save(update_fields=['status'])

    try:
        count = UploadService.process_upload(upload)
        upload.status = 'pending_lookups'
        upload.save(update_fields=['status'])
        return count
    except Exception as e:
        upload.status = 'failed'
        upload.error_message = str(e)
        upload.save(update_fields=['status', 'error_message'])
        raise


@task
def lookup_batch_task(upload_id: str, timeout: float = 10.0) -> dict:
    """Run barcode lookups for all rows in an upload."""
    upload = CSVUpload.objects.get(id=upload_id)
    upload.status = 'processing'
    upload.save(update_fields=['status'])

    try:
        results = UploadService.batch_lookup(upload, timeout)
        return results
    except Exception as e:
        upload.status = 'failed'
        upload.error_message = str(e)
        upload.save(update_fields=['status', 'error_message'])
        raise
```

**Note:** With `ImmediateBackend`, calling `.enqueue()` runs the task immediately and returns a `TaskResult`. No polling or background workers needed. Later, when swapping to a real backend (e.g., `django-tasks-db`), the same `@task` definitions will work without changes - only the view logic needs to handle async status checking.

---

## Views (`views.py`)

### Dashboard
```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .services import UploadService


@login_required
def dashboard(request):
    stats = UploadService.get_dashboard_stats(request.user)
    return render(request, 'dashboard/index.html', {'stats': stats})
```

### Upload Views
```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView
from .models import CSVUpload
from .forms import UploadForm
from .services import UploadService
from .tasks import process_csv_task, lookup_batch_task


class UploadListView(LoginRequiredMixin, ListView):
    model = CSVUpload
    template_name = 'uploads/list.html'

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)


class UploadCreateView(LoginRequiredMixin, CreateView):
    model = CSVUpload
    form_class = UploadForm
    template_name = 'uploads/upload.html'
    success_url = reverse_lazy('upload-list')

    def form_valid(self, form):
        form.instance.user = self.request.user

        try:
            response = super().form_valid(form)

            # With ImmediateBackend, these run synchronously
            # Later: swap backend and these become async
            process_csv_task.enqueue(upload_id=str(self.object.id))
            lookup_batch_task.enqueue(upload_id=str(self.object.id))

            messages.success(self.request, 'CSV processed and lookups completed!')
            return response
        except Exception as e:
            messages.error(self.request, f'Processing failed: {e}')
            context = self.get_context_data(form=form)
            return self.render_to_response(context)


class UploadDetailView(LoginRequiredMixin, DetailView):
    model = CSVUpload
    template_name = 'uploads/detail.html'

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)


class UploadExportView(LoginRequiredMixin, DetailView):
    """Trigger export and return file download."""
    model = CSVUpload
    template_name = 'uploads/export.html'

    def get(self, request, *args, **kwargs):
        upload = self.get_object()
        if upload.status != 'completed':
            messages.error(request, 'Upload must be completed before exporting.')
            return redirect('upload-detail', pk=upload.id)

        try:
            csv_file = UploadService.export_to_csv(upload)
            response = HttpResponse(csv_file.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{upload.filename}_export.csv"'
            return response
        except Exception as e:
            messages.error(request, f'Export failed: {e}')
            return redirect('upload-detail', pk=upload.id)
```

### Serializers (api/serializers.py)
```python
from rest_framework import serializers
from ..models import CSVUpload, LookupRecord


class LookupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LookupRecord
        fields = ['id', 'upc', 'product_title', 'status',
                  'error_message', 'created_at']
        read_only_fields = fields


class CSVUploadSerializer(serializers.ModelSerializer):
    lookups = LookupRecordSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CSVUpload
        fields = [
            'id', 'user', 'filename', 'file', 'status',
            'total_rows', 'processed_rows', 'error_message',
            'created_at', 'updated_at', 'lookups'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
```

---

### Additional Views (views.py continued)

```python
from django_tables2 import SingleTableView
from django_filters.views import FilterView
from django_tables2 import Table, Column
from django_filters import FilterSet, CharFilter
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from .models import LookupRecord


class UploadDetailView(LoginRequiredMixin, DetailView):
    model = CSVUpload
    template_name = 'uploads/detail.html'

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lookups'] = LookupRecord.objects.filter(
            csv_upload=self.object
        ).select_related('csv_upload')
        return context


class LookupListView(LoginRequiredMixin, SingleTableView):
    model = LookupRecord
    template_name = 'lookups/list.html'
    table_class = Table  # or define a custom table class

    def get_queryset(self):
        return LookupRecord.objects.filter(
            csv_upload__user=self.request.user
        ).select_related('csv_upload')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', '')
        return context


class UploadForm(forms.ModelForm):
    class Meta:
        model = CSVUpload
        fields = ['file']
```

---

### API Views (DRF)
```python
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CSVUpload
from .serializers import CSVUploadSerializer
from .tasks import process_csv_task, lookup_batch_task


class UploadViewSet(viewsets.ModelViewSet):
    serializer_class = CSVUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CSVUpload.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        upload = self.get_object()
        try:
            result = process_csv_task.enqueue(upload_id=str(upload.id))
            return Response({
                'task_id': result.id,
                'status': result.status.name,
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['post'])
    def lookup(self, request, pk=None):
        upload = self.get_object()
        try:
            timeout = request.data.get('timeout', 10.0)
            result = lookup_batch_task.enqueue(
                upload_id=str(upload.id),
                timeout=timeout,
            )
            return Response({
                'task_id': result.id,
                'status': result.status.name,
                'results': result.return_value if result.return_value else {},
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
```

---

## Settings

### `base.py`
```python
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# web/ is the Django project root
WEB_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = WEB_DIR.parent  # Points to csv-upc-omg/ root

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_tasks',
    'rest_framework',
    'django_tables2',
    'django_filters',
    'django_htmx',
    'core_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django_htmx.middleware.HxRequestMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Tasks
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend"
    }
}

# Auth
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/'

# Files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# django-tables2
DJANGO_TABLES2_TEMPLATE = 'django_tables2/bootstrap5.html'
```

### `dev.py`
```python
from .base import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE.insert(1, 'debug_toolbar.middleware.DebugToolbarMiddleware')
INTERNAL_IPS = ['127.0.0.1']
```

### `production.py`
```python
from .base import *
import environ

env = environ.Env()

DEBUG = False
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

DATABASES = {
    'default': env.db('DATABASE_URL')
}

# When ready to move to a real task backend:
# pip install django-tasks-db
# TASKS = {
#     "default": {
#         "BACKEND": "django_tasks_db.backends.database.DatabaseBackend"
#     }
# }

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

---

## Forms (`forms.py`)
```python
from django import forms
from .models import CSVUpload


class UploadForm(forms.ModelForm):
    class Meta:
        model = CSVUpload
        fields = ['file']
```

---

## URLs

### `config/urls.py`
```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core_app.urls')),
    path('api/v1/', include('core_app.api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
```

### `core_app/urls.py`
```python
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('uploads/', views.UploadListView.as_view(), name='upload-list'),
    path('uploads/create/', views.UploadCreateView.as_view(), name='upload-create'),
    path('uploads/<uuid:pk>/', views.UploadDetailView.as_view(), name='upload-detail'),
    path('uploads/<uuid:pk>/export/', views.UploadExportView.as_view(), name='upload-export'),
    path('lookups/', views.LookupListView.as_view(), name='lookup-list'),
]
```

### `core_app/api/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'uploads', views.UploadViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
```

---

## Admin Panel

```python
from django.contrib import admin
from .models import CSVUpload, LookupRecord


@admin.register(CSVUpload)
class CSVUploadAdmin(admin.ModelAdmin):
    list_display = ['filename', 'user', 'status', 'total_rows', 'processed_rows', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['filename', 'user__username']
    readonly_fields = ['created_at', 'updated_at']

    @admin.action(description='Re-process failed uploads')
    def reprocess_failed(self, request, queryset):
        from .tasks import process_csv_task, lookup_batch_task

        for upload in queryset.filter(status='failed'):
            upload.status = 'pending'
            upload.error_message = ''
            upload.save()
            process_csv_task.enqueue(upload_id=str(upload.id))
            lookup_batch_task.enqueue(upload_id=str(upload.id))

    actions = ['reprocess_failed']


@admin.register(LookupRecord)
class LookupRecordAdmin(admin.ModelAdmin):
    list_display = ['upc', 'csv_upload', 'status', 'product_title', 'created_at']
    list_filter = ['status', 'csv_upload']
    search_fields = ['upc', 'product_title']
    readonly_fields = ['created_at', 'updated_at']
```

---

## Management Commands

Mirror existing CLI functionality through Django:

### `process_csv` command
```python
from django.core.management.base import BaseCommand
from core_app.services import UploadService

class Command(BaseCommand):
    help = 'Process a CSV file directly (wrapper around existing CLI)'

    def add_arguments(self, parser):
        parser.add_argument('directory', help='Directory containing CSV files')
        parser.add_argument('--verbose', '-v', action='store_true')

    def handle(self, *args, **options):
        from csv_upc_omg.csv_utils import find_most_recent_csv, extract_upcs_from_csv

        csv_path = find_most_recent_csv(options['directory'])
        if csv_path is None:
            self.stdout.write(self.style.WARNING('No CSV files found.'))
            return

        if options['verbose']:
            self.stdout.write(f'Processing: {csv_path}')

        upcs = extract_upcs_from_csv(csv_path)
        for upc in upcs:
            self.stdout.write(upc)
```

---

## Implementation Phases

### Phase 1: Django Skeleton & Models ✅ Ready
- Create `web/` project structure
- Add models, migrations, admin
- Set up settings (dev/prod split)
- Add `ImmediateBackend` config
- Run migrations, verify server

### Phase 2: Service Layer & Tasks
- Create `services.py` wrapping core library
- Define `@task` decorators in `tasks.py`
- Create management commands
- Test task enqueue/execution

### Phase 3: Web UI
- Dashboard with stats
- Upload list/detail views with django-tables2
- Upload form with file handling
- django-filter for lookup search
- django-htmx for status polling
- Export functionality

### Phase 4: REST API
- DRF serializers and views
- API endpoints for uploads/lookups
- Token authentication for API clients
- API documentation

### Phase 5: DevOps & Polish
- Dockerfile + docker-compose.yml (Django + SQLite/Postgres)
- Production settings with env vars
- Static file serving with whitenoise
- CI/CD configuration
- README updates
- Tests (models, services, views, tasks)

---

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Task Backend** | `ImmediateBackend` initially | Simplest start, runs in-process, portable to real backend later |
| **Database** | SQLite (dev), PostgreSQL (prod) | Easy local setup, production scales |
| **Auth** | Django built-in User model | No over-engineering, can add Social Auth later |
| **UI Framework** | HTMX + django-tables2 | Lightweight, no JS build step, good UX |
| **API** | DRF | Industry standard, well-documented |
| **Deployment** | Docker + Gunicorn | Simple, reproducible |

---

## Migration Path to Real Task Backend (Later)

When you're ready to graduate from `ImmediateBackend`:

1. **Install backend** (e.g., `django-tasks-db`, `django-q2`, or Celery)
2. **Update settings** - swap backend in `TASKS['default']['BACKEND']`
3. **No task definition changes** - your `@task` decorated functions stay identical
4. **Update views if needed** - views that call `.enqueue()` will get async behavior, so adjust UX to poll for completion
5. **Test** - ImmediateBackend was already validating the task signatures during development

---

## ImmediateBackend Limitations (Known)

- **`get_result()` not supported** - Cannot retrieve task result from another thread/request. With ImmediateBackend, this is fine because tasks run synchronously in the same request and return immediately.
- **Task args must be JSON-serializable** - UUID must be passed as `str`, not as UUID object. Model instances cannot be passed directly.
- **No retries** - If a task fails, it fails. No automatic retry mechanism.
- **No rate limiting** - All requests process immediately. Fine for small batches, but consider rate limiting if scaling.

---

## Next Steps

Ready to start building. Let me know which phase to begin with or if you'd like me to start from Phase 1.

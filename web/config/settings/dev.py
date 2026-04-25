from .base import *  # noqa: F401,F403

DJANGO_SETTINGS_MODULE = "config.settings.dev"

DEBUG = True
SECRET_KEY = "django-insecure-dev-key-not-for-production-use-only"  # noqa: F405

ALLOWED_HOSTS += ["0.0.0.0", "*", "localhost", "127.0.0.1"]  # noqa: F405

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

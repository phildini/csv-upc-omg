import environ

from .base import *  # noqa: F401,F403

env = environ.Env()

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

DATABASES = {
    "default": env.db("DATABASE_URL"),  # noqa: F405
}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Override MEDIA_ROOT for Fly volume
MEDIA_ROOT = env("MEDIA_ROOT", default="/data/media")

# Configure CSRF for custom domain and Fly.io
CSRF_TRUSTED_ORIGINS = [
    "https://omgupc.com",
    "https://*.fly.dev",
]

# Configure proxy headers for Fly.io
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Production logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "django": {
        "handlers": ["console"],
        "level": "INFO",
        "propagate": False,
    },
    "django.request": {
        "handlers": ["console"],
        "level": "WARNING",
        "propagate": False,
    },
}

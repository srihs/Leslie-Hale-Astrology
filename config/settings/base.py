"""
Base settings shared by every environment.

Nothing in this file may hard-code a secret — not a SECRET_KEY, not a
database credential, not an API key, not even a value that "looks like" a
harmless development default. Every secret is read from the environment.
See .env.example for the full list of variables this project needs.

dev.py and prod.py each import * from here and then override what differs
(DEBUG, ALLOWED_HOSTS, email backend, SECURE_* hardening).
"""

import os
from pathlib import Path

import dj_database_url

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# config/settings/base.py -> config/settings -> config -> repo root
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Environment variable helper
# ---------------------------------------------------------------------------

class ImproperlyConfiguredEnv(Exception):
    """A required environment variable was not set."""


def env(key, required=True, default=None):
    """
    Read an environment variable.

    Required variables raise loudly at import time rather than silently
    falling back to a value that looks plausible — a missing SECRET_KEY or
    DATABASE_URL should stop the process, not start it insecurely.
    """
    value = os.environ.get(key, default)
    if required and (value is None or value == ""):
        raise ImproperlyConfiguredEnv(
            f"Required environment variable {key!r} is not set. "
            "Copy .env.example to .env and fill in a value, or set it in "
            "the deployment environment."
        )
    return value


def env_list(key, required=True, default=None):
    """Comma-separated environment variable -> list of stripped strings."""
    raw = env(key, required=required, default=default)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_bool(key, required=True, default=None):
    raw = env(key, required=required, default=default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY")

# DEBUG is deliberately NOT read from the environment. It is hard-coded in
# dev.py (True) and prod.py (False) so a missing or mistyped env var can
# never leave DEBUG=True running in production.
DEBUG = False

# ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS are set per-environment in dev.py and
# prod.py — dev is permissive for localhost, prod is locked to the real
# domain with an env override for staging.
ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = []

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The booking feature stores and compares appointment times; every datetime
# must be timezone-aware end to end.
USE_TZ = True
TIME_ZONE = env("DJANGO_TIME_ZONE", required=False, default="Pacific/Auckland")
LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", required=False, default="en-nz")
USE_I18N = True


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

WAGTAIL_APPS = [
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.contrib.sitemaps",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    # Not used directly by any of our own models any more (the blog uses
    # BlogCategory, not tags — see apps/blog/models.py), but Wagtail's own
    # built-in Image and Document models each have a `tags` field that
    # depends on taggit's Tag model being installed, so this stays.
    "taggit",
]

THIRD_PARTY_APPS = [
    "django_htmx",
]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

# Owned by other agents — packages do not exist yet at scaffold time.
# wagtail-backend, htmx-frontend, booking-payments, blog-migration and
# seo-analytics create these under apps/ next.
LOCAL_APPS = [
    "apps.core",
    "apps.home",
    "apps.readings",
    "apps.bookings",
    "apps.blog",
    "apps.contact",
]

INSTALLED_APPS = WAGTAIL_APPS + THIRD_PARTY_APPS + DJANGO_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL"),
        conn_max_age=600,
    ),
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Static files (Whitenoise) and media
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media is user-uploaded content (Leslie's portrait, blog images) that must
# survive a redeploy. It is never baked into the image. In docker-compose it
# is a named volume; in production it must be a persistent path or external
# object storage — see docker-compose.yml and the deployment notes for the
# Prohosting assumption this still depends on.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False


# ---------------------------------------------------------------------------
# Wagtail
# ---------------------------------------------------------------------------

WAGTAIL_SITE_NAME = env("WAGTAIL_SITE_NAME", required=False, default="Leslie Hale Astrology")
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL")
WAGTAIL_ENABLE_UPDATE_CHECK = False


# ---------------------------------------------------------------------------
# Email — credentials are always from the environment; dev overrides the
# backend to console in dev.py.
# ---------------------------------------------------------------------------

EMAIL_HOST = env("EMAIL_HOST", required=False, default="")
EMAIL_PORT = int(env("EMAIL_PORT", required=False, default="587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", required=False, default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", required=False, default="")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", required=False, default="True")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", required=False, default="")


# ---------------------------------------------------------------------------
# Payments (booking-payments owns usage; these are the env-backed settings)
# ---------------------------------------------------------------------------

STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", required=False, default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", required=False, default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", required=False, default="")


# ---------------------------------------------------------------------------
# Analytics (seo-analytics owns usage)
# ---------------------------------------------------------------------------

GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", required=False, default="")


# ---------------------------------------------------------------------------
# Logging — plain to stdout/stderr; the container runtime collects it.
# ---------------------------------------------------------------------------

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
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", required=False, default="INFO"),
            "propagate": False,
        },
    },
}

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
#
# Default is America/New_York because Leslie is US-based — this was
# previously Pacific/Auckland, the agency's own timezone, not the
# client's (same defect class as BOOKING_CURRENCY below, and as the
# hardcoded domain fixed in 4309631). apps/bookings/availability.py's
# `SITE_ZONE = ZoneInfo(settings.TIME_ZONE)` and everywhere else that
# reads `settings.TIME_ZONE` already take this from settings rather than
# a second hardcoded literal, so this one default change is what actually
# moves the site — no other code change was needed for the zone itself.
# `apps/bookings/availability.py:tz_label` computes the DST abbreviation
# (e.g. 'EST'/'EDT') from the appointment's *own instant*
# (`reference.astimezone(tz).tzname()`), never from "now" — the same fix
# already applied for Auckland's NZST/NZDT split applies unchanged to
# Eastern's EST/EDT split.
USE_TZ = True
TIME_ZONE = env("DJANGO_TIME_ZONE", required=False, default="America/New_York")
LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", required=False, default="en-us")
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
    # The bespoke admin at /manage/ (wagtail-backend, 2026-09-23) — see
    # apps/backoffice/models.py's own docstring for why it defines a
    # marker permission rather than content models.
    "apps.backoffice",
]

# django-axes — admin login brute-force protection (finding 4,
# reviews/2026-09-22-final-security-review.md). Listed after DJANGO_APPS
# (which includes django.contrib.auth) since axes hooks auth's signals and
# needs it already registered. Ships its own migrations (AccessAttempt /
# AccessLog / AccessFailureLog), applied by the normal `manage.py migrate`
# step in docker/entrypoint.sh — no app-owned migration needed for this.
THIRD_PARTY_APPS_LATE = [
    "axes",
]

INSTALLED_APPS = (
    WAGTAIL_APPS + THIRD_PARTY_APPS + DJANGO_APPS + LOCAL_APPS + THIRD_PARTY_APPS_LATE
)


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Explicit lock on /admin/ and /django-admin/ to superusers only
    # (wagtail-backend, 2026-09-23 — task brief: "Wagtail's admin stays
    # available to superusers only. Lock it down."). Must run after
    # AuthenticationMiddleware (needs request.user) — see its own
    # docstring for why this is a standing rule, not just relying on
    # nobody granting Leslie's account a Wagtail admin group.
    "apps.backoffice.middleware.WagtailAdminSuperuserOnlyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
    # django-axes docs: must be the last middleware in the list — it needs
    # every other middleware (notably AuthenticationMiddleware) to have run
    # first. Finding 4, reviews/2026-09-22-final-security-review.md.
    "axes.middleware.AxesMiddleware",
]

# axes.backends.AxesStandaloneBackend must be listed first: it intercepts
# every call to django.contrib.auth.authenticate() to enforce lockouts,
# then falls through to ModelBackend for the actual credential check. This
# is what gives brute-force coverage on BOTH admin entry points
# (config/urls.py: "django-admin/" -> django.contrib.admin, "admin/" ->
# Wagtail's own login view) from one settings-only change — Wagtail's login
# view is a subclass of Django's own LoginView and still calls
# authenticate(), so it goes through this backend chain too. Do not set
# AXES_ONLY_ADMIN_SITE = True to "focus" this: that setting scopes
# protection to whatever URL reverses as "admin:index", which in this
# urlconf resolves only to /django-admin/ and would silently stop
# protecting /admin/ — the one editors actually use day to day.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# --- django-axes tuning (finding 4) -----------------------------------
# Realistic threat here is slow credential-stuffing against one or two
# real accounts (Leslie, SAS Creative), not a targeted attack — see the
# review's own severity call. A short cooloff over a permanent lockout
# means a genuine user who mistypes a password repeatedly is never
# permanently locked out of their own site.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_RESET_ON_SUCCESS = True


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
                "apps.core.context_processors.seo",
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
# Cache — shared backend for django-ratelimit (finding 1,
# reviews/2026-09-22-final-security-review.md)
# ---------------------------------------------------------------------------
#
# django-ratelimit counts requests through Django's cache framework. The
# default LocMemCache is per-process: gunicorn runs WEB_CONCURRENCY worker
# processes (see .env.example, docker/Dockerfile CMD), so local-memory
# counts would let an attacker's requests spread across workers each get
# their own separate, useless counter — the exact bug this exists to avoid.
#
# Backend chosen: Django's own database cache, against the "default"
# Postgres connection this project already requires (DATABASE_URL is not
# optional — see env() above) rather than adding Redis or another new
# service. This project's touch scope for this change is settings/deps
# only (docker-compose.yml is out of scope here), and Prohosting's actual
# capabilities beyond shared PHP/MySQL-style hosting are unconfirmed per
# PROJECT-SCOPE.md §1 — reusing the database every environment already has
# is the more portable choice than assuming Prohosting can also run Redis.
# If sustained rate-limit traffic ever makes the extra DB writes a real
# cost, revisit with Redis once Prohosting's actual capabilities are
# confirmed, not before.
#
# The "django_cache" table is created by docker/entrypoint.sh
# (`manage.py createcachetable`, idempotent — checks
# connection.introspection.table_names() first) under the same
# RUN_MIGRATIONS=true guard as `migrate`, so it is a deliberate one-off
# step, not something that races across replicas on every container start.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    },
}

# Explicit rather than relying on django-ratelimit's own default (which is
# already "default", but an unreviewed default is not a decision) — the
# views that apply @ratelimit (booking-payments, contact) rate-limit
# against this cache.
RATELIMIT_USE_CACHE = "default"


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

# --- Upload limits (finding 3, reviews/2026-09-22-final-security-review.md) ---
# Uploads are admin-only (Wagtail admin, not a public form) so severity is
# bounded, but an unreviewed framework default is still not a decision.
#
# Two settings named in this project's brief for this fix,
# WAGTAILIMAGES_MAX_ANIMATED_GIF_SIZE and WAGTAILDOCS_MAX_UPLOAD_SIZE, do
# not exist on the Wagtail branch this project is pinned to (verified
# against wagtail==6.3.8's own source and docs, both pulled from GitHub at
# that tag — neither name appears anywhere). WAGTAILDOCS_MAX_UPLOAD_SIZE is
# real, but only from Wagtail 7.4 onward (CHANGELOG.txt); pulling it in
# would mean the minor/major version jump task 1 explicitly rules out, not
# a same-branch patch. WAGTAILIMAGES_MAX_ANIMATED_GIF_SIZE does not appear
# in any Wagtail release, past or current main branch. Neither is set here
# — a setting Wagtail never reads is not a control, just a comment that
# looks like one.
#
# What this branch actually offers, and what's set instead:
#
# Images — a portrait and blog photos, nothing larger expected:
WAGTAILIMAGES_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB — Wagtail's own
# default value, made explicit rather than implicit.
WAGTAILIMAGES_MAX_IMAGE_PIXELS = 40 * 1_000_000  # 40 megapixels — tightened
# from Wagtail's 128-megapixel default. Generous for a professional
# portrait or blog photo (well beyond any consumer camera's native
# resolution) while bounding decompression-bomb-style originals; the pixel
# count is calculated across animation frames too (Wagtail's own docs), so
# this is also the real lever against an oversized animated GIF on this
# branch, not a same-named setting that does not exist here.
#
# Documents — Wagtail's own default (WAGTAILDOCS_EXTENSIONS unset) accepts
# any file extension at all. There is no size-limiting equivalent on this
# branch (Django's DATA_UPLOAD_MAX_MEMORY_SIZE explicitly excludes file
# uploads — confirmed against django==5.1's global_settings.py), so the
# only lever available without an app-level form change (wagtail-backend's
# file, not this one) is the extension allowlist. Kept small and
# unsurprising for a solo astrologer's site — a downloadable PDF is
# plausible, an uploaded spreadsheet or archive is not:
WAGTAILDOCS_EXTENSIONS = ["pdf", "doc", "docx"]


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

# ISO 4217 code new bookings are priced and charged in
# (apps.bookings.models.Booking.currency's default, and the value stamped
# onto every new Booking row in apps.bookings.views.start_checkout).
# Previously a bare `CURRENCY = "NZD"` literal in apps/bookings/models.py
# — the agency building this site is NZ-based, and that fact leaked into
# money, not a decision Leslie ever made. Same defect class as a
# hardcoded domain: a fact about the deployment baked into code instead
# of read from it. Defaults to USD (Leslie is US-based) so an absent env
# var fails toward the client's actual country, not the agency's.
#
# §8 still lists "the final list of readings and their prices" as open
# with the client; this is the other side of that same open item (which
# currency those prices are IN) and is exactly why it belongs here, not
# as a second hardcoded literal — the next currency change is now a
# config edit, not a code edit.
#
# CAUTION — zero-decimal currencies: USD is two-decimal, the same shape
# as NZD, so `Booking.amount_minor` staying integer cents is correct for
# this change, and Stripe's Checkout `unit_amount` for USD is already
# exactly `amount_minor` with no conversion (see
# apps/bookings/payments/stripe_provider.py's own docstring). That is
# NOT true for every ISO 4217 code: Stripe defines a fixed list of
# "zero-decimal currencies" (e.g. JPY, KRW, VND) whose smallest unit has
# no subdivision, where its `unit_amount` is already the whole-currency
# amount. apps/bookings/views.py's `amount_minor = int((Decimal(reading
# .price) * 100)...)` hardcodes a *100 multiplication for every currency,
# and `Booking.amount_display` hardcodes a divmod-by-100 to redisplay it
# — neither is derived from this setting. If BOOKING_CURRENCY is ever set
# to a zero-decimal currency without also changing both of those, every
# real charge sent to Stripe would be exactly 100x the intended amount —
# silently, since Stripe would accept and charge it. This setting only
# makes the currency configurable for a same-shape currency (USD, the
# confirmed decision); it does not add zero-decimal support, and must
# not be read as having done so.
BOOKING_CURRENCY = env("BOOKING_CURRENCY", required=False, default="USD")


# ---------------------------------------------------------------------------
# Analytics (seo-analytics owns usage)
# ---------------------------------------------------------------------------

# Not read by any template — kept here only because docker-infra's original
# scaffold already committed it to .env.example and it costs nothing to
# leave in place for a future deploy script. The GA4 measurement ID Leslie
# actually controls lives in AnalyticsSettings (apps/core/models.py,
# Wagtail admin -> Settings -> Analytics), per the seo-analytics brief: it
# must be editable by her without a redeploy, the same way ContactSettings
# is. templates/includes/_analytics.html reads it from there.
GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", required=False, default="")


# ---------------------------------------------------------------------------
# SEO (seo-analytics owns usage)
# ---------------------------------------------------------------------------

# The one domain every canonical URL, sitemap entry, structured-data `url`
# and Open Graph `og:url` is built against — apex, not `www`, whatever that
# apex currently is (this project is served from leslie.testground.shop
# for testing before the PROJECT-SCOPE.md §1 cutover to
# lesliehale-astrology.com). Deliberately independent of both
# ALLOWED_HOSTS (a security allowlist, not a canonicalisation choice) and
# Wagtail's own Site.hostname (editable in Wagtail admin, and if it were
# ever left at Wagtail's "localhost" default or pointed at a staging host,
# every page's canonical URL would silently follow it). request.get_host()
# is used as a fallback only so local dev still renders a valid URL without
# this being set.
#
# No hardcoded production default here, deliberately — the same reasoning
# already applied to SECRET_KEY. A domain default that is silently wrong
# (still lesliehale-astrology.com while actually serving
# leslie.testground.shop, or vice versa after cutover) is worse than an
# empty value that visibly falls back to request.get_host() below. Every
# environment, including the real production deploy, must set this
# explicitly — see .env.example.
CANONICAL_DOMAIN = env("CANONICAL_DOMAIN", required=False, default="")

# Drives robots.txt (apps/core/views.py:robots_txt) — NOT a static file, so
# an environment can control it without a code change or redeploy of a
# text file. Defaults to False (disallow everything) everywhere, including
# prod.py: prod.py's own comment records that a staging host on Prohosting
# is expected to reuse config.settings.prod with only ALLOWED_HOSTS
# overridden, so DEBUG=False can never be used to tell staging and
# production apart. The real production deploy must set this explicitly —
# see .env.example. A production site that silently stays un-indexed for a
# day because someone forgot the flag is a minor, visible, quickly-fixed
# problem; a staging site Google indexed by default is the "real and
# embarrassing failure" PROJECT-SCOPE.md's brief warns about, and default
# behaviour must fail toward the smaller problem.
SEARCH_ENGINE_INDEXING_ALLOWED = env_bool(
    "SEARCH_ENGINE_INDEXING_ALLOWED", required=False, default="False"
)


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

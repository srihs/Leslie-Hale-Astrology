"""
Production settings.

DEBUG is hard-coded False here, deliberately not sourced from the
environment, so a missing or mistyped env var can never re-enable it.

ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS default to the real domain
(lesliehale-astrology.com) per PROJECT-SCOPE.md, with an environment
override available for a staging host on Prohosting once one exists.
"""

from .base import env_bool, env_list  # noqa: F401
from .base import *  # noqa: F401,F403

DEBUG = False

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    required=False,
    default="lesliehale-astrology.com,www.lesliehale-astrology.com",
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    required=False,
    default="https://lesliehale-astrology.com,https://www.lesliehale-astrology.com",
)

# --- Email: SMTP, credentials required in prod (no blank fallback here) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")  # noqa: F405
EMAIL_HOST_USER = env("EMAIL_HOST_USER")  # noqa: F405
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")  # noqa: F405
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")  # noqa: F405

# --- HTTPS / cookie / header hardening ---
# ASSUMPTION (needs Prohosting confirmation): the edge that terminates TLS
# sits in front of this container and forwards X-Forwarded-Proto. If
# Prohosting terminates TLS itself and does NOT set that header, this must
# change or SECURE_SSL_REDIRECT will loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# WAGTAILADMIN_BASE_URL must be the real HTTPS domain in prod; base.py
# already requires it from the environment, so nothing extra to set here.

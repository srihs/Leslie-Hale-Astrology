"""
Local development settings.

Still reads SECRET_KEY, DATABASE_URL etc. from the environment — there is no
"looks harmless" dev default for a secret. Copy .env.example to .env and
docker-compose will load it.
"""

from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

# Mail is never actually sent in dev; it's printed to the console the
# process is running in.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Verbose template errors, no HTTPS enforcement — this is DEBUG=True only,
# never the settings module prod uses.
INTERNAL_IPS = ["127.0.0.1"]

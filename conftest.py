"""
pytest-django entry point for the whole suite.

DJANGO_SETTINGS_MODULE is set in pyproject.toml
([tool.pytest.ini_options]) to config.settings.dev; DATABASE_URL and every
other required environment variable come from the process environment —
this suite is run inside the docker-infra web container (or anywhere else
that already has the same .env loaded), never against a fabricated
in-process settings module.

No network calls happen anywhere in this suite: Stripe is mocked at
`apps.bookings.views.get_provider` (see apps/bookings/tests/payments.py)
and email is exercised through Django's own console backend (dev
settings) or asserted via a call-count spy — nothing here reaches the
network. See apps/*/tests/factories.py for the model factories, and
apps/home/tests/factories.py / apps/core/tests/factories.py for the
StreamField-heavy Wagtail page builders every page-rendering test in
tests/test_page_rendering.py depends on.
"""

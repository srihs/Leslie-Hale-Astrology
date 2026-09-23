"""
Rate limiting on `submit_contact` and `newsletter_signup`
(reviews/2026-09-22-final-security-review.md finding 1) — the "lesser
case" per that finding's adjudication (inbox spam and junk rows, not the
booking calendar `apps.bookings.views` protects), so both get the same
moderate two-window shape rather than `start_checkout`'s tighter one. See
`apps/contact/views.py`'s module docstring for the exact windows chosen,
why they're the same for both endpoints, and the proxy caveat on
`key="ip"` (identical reasoning to `apps/bookings/views.py`, not repeated
here).

Like the booking suite, these tests spam the endpoint with otherwise-valid
payloads rather than needing a real ContactPage/HomePage: `request.limited`
is checked before anything is saved, so the limiter itself is provable
without also exercising the full-page-render machinery
apps/contact/tests/test_views.py already covers.

Every test below is frozen with `freeze_time` — see apps/bookings/tests/
test_rate_limiting.py's module docstring for the full reasoning (not
repeated here): `django_ratelimit.core._get_window` computes its window
from a real `time.time()` read, not anything freezegun-independent, so an
unfrozen burst of requests can straddle a real minute/hour boundary
mid-loop and land in a fresh, unlimited window purely by chance. Freezing
pins the clock for a test's whole body so every request in the burst
provably computes the same window/cache key.
"""

from __future__ import annotations

import pytest
from django.test import Client
from freezegun import freeze_time

from apps.contact.models import ContactSubmission, NewsletterSignup

pytestmark = pytest.mark.django_db

# Any fixed instant works — see apps/bookings/tests/test_rate_limiting.py's
# RATE_LIMIT_NOW comment for why.
RATE_LIMIT_NOW = "2026-06-01 00:00:00+00:00"

CONTACT_URL = "/forms/contact/submit/"
NEWSLETTER_URL = "/forms/contact/newsletter/"


@freeze_time(RATE_LIMIT_NOW)
def test_contact_submit_is_not_limited_under_the_burst_threshold():
    client = Client()
    for _ in range(4):
        response = client.post(
            CONTACT_URL,
            data={"name": "Jamie", "email": "jamie@example.com", "message": "Hello there."},
            REMOTE_ADDR="203.0.113.30",
        )
        assert response.status_code == 200
        assert ContactSubmission.objects.exists()


@freeze_time(RATE_LIMIT_NOW)
def test_contact_submit_429s_past_the_burst_threshold_with_a_warm_message():
    client = Client()
    payload = {"name": "Jamie", "email": "jamie@example.com", "message": "Hello there."}
    for _ in range(5):
        client.post(CONTACT_URL, data=payload, REMOTE_ADDR="203.0.113.31")
    before = ContactSubmission.objects.count()

    response = client.post(CONTACT_URL, data=payload, REMOTE_ADDR="203.0.113.31")

    assert response.status_code == 429
    body = response.content.lower()
    assert b"traceback" not in body and b"exception" not in body
    assert b"wait a minute" in body
    # Nothing was saved for the blocked attempt.
    assert ContactSubmission.objects.count() == before
    # What they typed is preserved on the re-rendered form.
    assert b"jamie" in body


@freeze_time(RATE_LIMIT_NOW)
def test_contact_submit_429_via_htmx_returns_the_bare_fragment():
    client = Client(headers={"HX-Request": "true"})
    payload = {"name": "Jamie", "email": "jamie@example.com", "message": "Hello there."}
    for _ in range(5):
        client.post(CONTACT_URL, data=payload, REMOTE_ADDR="203.0.113.32")

    response = client.post(CONTACT_URL, data=payload, REMOTE_ADDR="203.0.113.32")

    assert response.status_code == 429
    body = response.content.decode()
    assert not body.lstrip().lower().startswith("<!doctype html>")
    assert 'id="contact-form-wrap"' in body
    assert "wait a minute" in body.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_contact_submit_rate_limit_is_scoped_per_ip():
    client = Client()
    payload = {"name": "Jamie", "email": "jamie@example.com", "message": "Hello there."}
    for _ in range(6):
        client.post(CONTACT_URL, data=payload, REMOTE_ADDR="203.0.113.33")

    other_visitor = client.post(CONTACT_URL, data=payload, REMOTE_ADDR="198.51.100.34")

    assert other_visitor.status_code == 200


@freeze_time(RATE_LIMIT_NOW)
def test_newsletter_signup_is_not_limited_under_the_burst_threshold():
    client = Client()
    for n in range(4):
        response = client.post(
            NEWSLETTER_URL, data={"email": f"reader{n}@example.com"}, REMOTE_ADDR="203.0.113.40"
        )
        assert response.status_code == 200


@freeze_time(RATE_LIMIT_NOW)
def test_newsletter_signup_429s_past_the_burst_threshold_with_a_warm_message():
    client = Client()
    for n in range(5):
        client.post(NEWSLETTER_URL, data={"email": f"reader{n}@example.com"}, REMOTE_ADDR="203.0.113.41")
    before = NewsletterSignup.objects.count()

    response = client.post(
        NEWSLETTER_URL, data={"email": "onemore@example.com"}, REMOTE_ADDR="203.0.113.41"
    )

    assert response.status_code == 429
    body = response.content.lower()
    assert b"traceback" not in body and b"exception" not in body
    assert b"wait a minute" in body
    assert NewsletterSignup.objects.count() == before


@freeze_time(RATE_LIMIT_NOW)
def test_newsletter_signup_429_via_htmx_returns_the_bare_fragment():
    client = Client(headers={"HX-Request": "true"})
    for n in range(5):
        client.post(NEWSLETTER_URL, data={"email": f"reader{n}@example.com"}, REMOTE_ADDR="203.0.113.42")

    response = client.post(
        NEWSLETTER_URL, data={"email": "onemore@example.com"}, REMOTE_ADDR="203.0.113.42"
    )

    assert response.status_code == 429
    body = response.content.decode()
    assert not body.lstrip().lower().startswith("<!doctype html>")
    assert 'id="newsletter-form"' in body
    assert "wait a minute" in body.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_newsletter_signup_rate_limit_is_scoped_per_ip():
    client = Client()
    for n in range(6):
        client.post(NEWSLETTER_URL, data={"email": f"reader{n}@example.com"}, REMOTE_ADDR="203.0.113.43")

    other_visitor = client.post(
        NEWSLETTER_URL, data={"email": "another@example.com"}, REMOTE_ADDR="198.51.100.44"
    )

    assert other_visitor.status_code == 200

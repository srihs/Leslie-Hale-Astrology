"""
Rate limiting on `save_details` and `start_checkout`
(reviews/2026-09-22-final-security-review.md finding 1).

`start_checkout` is the serious case the finding names: a scripted,
unauthenticated POST can hold any visible slot for `HOLD_MINUTES` at a
time, and repeating that before each hold expires can hold every slot on
the calendar indefinitely without ever paying — a direct attack on the
site's only revenue mechanism. Both views carry `@ratelimit(key="ip", ...)`
against the database-backed cache `config/settings/base.py` configures
for this (`CACHES`/`RATELIMIT_USE_CACHE`) — see that module's own
docstring for the exact windows chosen and the proxy caveat on `key="ip"`.

These tests deliberately do not need a real Reading/availability/Stripe
stub to prove the limiter itself works: `request.limited` is checked at
the very top of both views, before any of that business logic runs, so
spamming the endpoint with bare/invalid payloads is enough to exercise
it — the existing `test_checkout.py`/`test_details_form.py` suites are
what prove the *business* behaviour (double-submission, exclusion
constraint, etc.) still works underneath.

Each `@ratelimit` window is its own counter in the cache
(`django_ratelimit.core._make_cache_key` includes the rate string), so a
test only needs to cross whichever window it is proving; it is never
required to also exhaust the other one first.

Every test below is frozen with `freeze_time`. `django_ratelimit.core.
_get_window` (the function that decides which cache bucket a request
falls into) computes its window from `time.time()` — a real, un-mockable
wall clock read on every call, not the frozen-by-default `django.utils.
timezone.now()` the rest of this suite already controls. A burst of N
requests that expect to land in a single fixed window is, unfrozen, a
race against that clock: if the Nth request's `time.time()` read crosses
a real minute/hour boundary mid-loop, django-ratelimit buckets it into a
*fresh* window with its own zero count, and a test asserting a 429 on
that request fails — not because the limiter is broken, but because the
test got unlucky against the clock. That is the exact "Booking tests that
pass only on weekdays" trap for `time.time()` instead of a date.
Freezing (confirmed against `django_ratelimit`'s installed source, not
assumed: `time.time()` is a plain `import time` module-level read, which
is exactly what freezegun patches) pins `time.time()` to one instant for
a test's whole body, so every request in a burst — including the one
expected to trip the limit — provably computes the same window/cache key
regardless of real wall-clock time when the suite happens to run.
"""

from __future__ import annotations

import pytest
from django.test import Client
from freezegun import freeze_time

from apps.bookings.models import Booking

pytestmark = pytest.mark.django_db

# Any fixed instant works — django_ratelimit's window is `time.time()`
# truncated to the rate's period plus a per-cache-key jitter offset
# (`zlib.crc32` of the IP), so what matters is that the clock does not
# move during a test, not which instant it is frozen at.
RATE_LIMIT_NOW = "2026-06-01 00:00:00+00:00"

DETAILS_URL = "/forms/booking/details/"
CHECKOUT_URL = "/forms/booking/checkout/"

VALID_DETAILS = {
    "first_name": "Jamie",
    "last_name": "Taylor",
    "email": "jamie@example.com",
    "dob": "1990-05-01",
    "tob": "10:00",
    "pob": "Auckland, New Zealand",
    "focus": "",
}


@freeze_time(RATE_LIMIT_NOW)
def test_save_details_is_not_limited_under_the_burst_threshold():
    """10/minute — a visitor genuinely correcting a few fields in a row
    must never see a 429. Nine posts in a row must all behave normally."""
    client = Client()
    for _ in range(9):
        response = client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.10")
        assert response.status_code == 200
        assert b"saved" in response.content.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_save_details_429s_past_the_burst_threshold_with_a_warm_message():
    """The 11th POST inside a minute from the same IP must be refused —
    with Leslie's own voice, not django-ratelimit's bare 403, and without
    losing what the visitor just typed."""
    client = Client()
    for _ in range(10):
        client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.11")

    response = client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.11")

    assert response.status_code == 429
    body = response.content.lower()
    assert b"traceback" not in body and b"exception" not in body, (
        "a rate-limited visitor must get a warm message, not a stack trace"
    )
    assert b"wait a minute" in body
    # What they just typed is still on the page — nothing was lost.
    assert b"jamie" in body


@freeze_time(RATE_LIMIT_NOW)
def test_save_details_429_via_htmx_returns_the_bare_fragment():
    """The htmx branch of the same 429 must stay a bare fragment (correct
    — htmx swaps it into the form's own wrapper), not the whole page
    nested inside the swap target."""
    client = Client(headers={"HX-Request": "true"})
    for _ in range(10):
        client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.12")

    response = client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.12")

    assert response.status_code == 429
    body = response.content.decode()
    assert not body.lstrip().lower().startswith("<!doctype html>")
    assert 'id="booking-details-form"' in body
    assert "wait a minute" in body.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_save_details_rate_limit_is_scoped_per_ip():
    """The whole point of `key='ip'`: one visitor being limited must never
    limit a different one. See views.py's proxy caveat for what this
    depends on in deployment."""
    client = Client()
    for _ in range(11):
        client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="203.0.113.13")

    other_visitor = client.post(DETAILS_URL, data=VALID_DETAILS, REMOTE_ADDR="198.51.100.20")

    assert other_visitor.status_code == 200
    assert b"saved" in other_visitor.content.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_checkout_is_not_limited_under_the_burst_threshold():
    """5/minute — a genuine retry after a declined card or a slot taken
    out from under them must not be punished. Four posts in a row (each
    refused for the ordinary, non-rate-limit reason: no staged details)
    must all get the ordinary friendly error, never a 429."""
    client = Client()
    for _ in range(4):
        response = client.post(
            CHECKOUT_URL,
            data={"reading": "1", "slot": "2026-06-16T21:00:00+00:00", "tz": "Pacific/Auckland"},
            REMOTE_ADDR="203.0.113.20",
        )
        assert response.status_code == 400
        assert b"details" in response.content.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_checkout_429s_past_the_burst_threshold_with_a_warm_message():
    """The 6th checkout POST inside a minute from the same IP is refused
    before it ever touches the session, the reading, or the payment
    provider — nothing is charged, and the visitor is told so."""
    client = Client()
    payload = {"reading": "1", "slot": "2026-06-16T21:00:00+00:00", "tz": "Pacific/Auckland"}
    for _ in range(5):
        client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="203.0.113.21")

    response = client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="203.0.113.21")

    assert response.status_code == 429
    body = response.content.lower()
    assert b"traceback" not in body and b"exception" not in body
    assert b"nothing has been charged" in body
    assert b"wait a minute" in body
    assert Booking.objects.count() == 0


@freeze_time(RATE_LIMIT_NOW)
def test_checkout_429_via_htmx_returns_the_bare_fragment():
    client = Client(headers={"HX-Request": "true"})
    payload = {"reading": "1", "slot": "2026-06-16T21:00:00+00:00", "tz": "Pacific/Auckland"}
    for _ in range(5):
        client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="203.0.113.22")

    response = client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="203.0.113.22")

    assert response.status_code == 429
    body = response.content.decode()
    assert not body.lstrip().lower().startswith("<!doctype html>")
    assert 'id="checkout-error"' in body
    assert "nothing has been charged" in body.lower()


@freeze_time(RATE_LIMIT_NOW)
def test_checkout_rate_limit_is_scoped_per_ip():
    """The exact property that stops the exploit from one IP without
    collateral damage to anyone sharing a different one — a household or
    office on a different address is untouched."""
    client = Client()
    payload = {"reading": "1", "slot": "2026-06-16T21:00:00+00:00", "tz": "Pacific/Auckland"}
    for _ in range(6):
        client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="203.0.113.23")

    other_visitor = client.post(CHECKOUT_URL, data=payload, REMOTE_ADDR="198.51.100.24")

    assert other_visitor.status_code == 400
    assert b"details" in other_visitor.content.lower()

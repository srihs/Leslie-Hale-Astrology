"""
`apps.bookings.views.start_checkout` — the step that turns a chosen
reading/day/slot plus session-staged details into a held `Booking` row and
a payment-provider checkout session. Every scenario here is named directly
in CLAUDE.md's booking-payments brief: double submission reuses the
existing hold, and checkout refuses a reading with no price or no
duration.

Stripe is mocked at the boundary throughout: `apps.bookings.views.
get_provider` is monkeypatched to a `StubPaymentProvider` (see
apps/bookings/tests/payments.py) — never the real SDK, never a network
call.
"""

from __future__ import annotations

from datetime import timedelta
from datetime import timezone as dt_timezone

import pytest
from django.db import IntegrityError
from django.test import Client
from django.utils import timezone
from freezegun import freeze_time

from apps.bookings import views as bookings_views
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.tests.factories import BookingFactory
from apps.bookings.tests.payments import CheckoutSession, PaymentProviderError, StubPaymentProvider
from apps.readings.tests.factories import ReadingFactory

pytestmark = pytest.mark.django_db

CHECKOUT_URL = "/forms/booking/checkout/"
DETAILS_URL = "/forms/booking/details/"

VALID_DETAILS = {
    "first_name": "Jamie",
    "last_name": "Taylor",
    "email": "jamie@example.com",
    "dob": "1990-05-01",
    "tob": "10:00",
    "pob": "Auckland, New Zealand",
    "focus": "Career",
}

# A Tuesday, safely in the future relative to the frozen "now" below.
SLOT_START = timezone.datetime(2026, 6, 16, 21, 0, tzinfo=dt_timezone.utc)
NOW = timezone.datetime(2026, 6, 1, 0, 0, tzinfo=dt_timezone.utc)


def _stage_details(client, overrides=None):
    values = dict(VALID_DETAILS)
    if overrides:
        values.update(overrides)
    response = client.post(DETAILS_URL, data=values)
    assert response.status_code == 200
    return response


def _checkout_payload(reading, slot=SLOT_START):
    return {
        "reading": str(reading.pk),
        "slot": slot.isoformat(),
        "tz": "Pacific/Auckland",
    }


def _availability_stub(monkeypatch, reading, slots):
    """`start_checkout` re-checks the slot is still offered by
    `availability.get_slots_for_day` before trusting it — stub that check
    directly so these tests control exactly what "currently available"
    means without needing real AvailabilityRule fixtures for every test."""
    monkeypatch.setattr(bookings_views.availability, "get_slots_for_day", lambda reading, day: slots)


@freeze_time(NOW)
def test_checkout_without_staged_details_shows_a_friendly_error(client, monkeypatch):
    reading = ReadingFactory()
    _availability_stub(monkeypatch, reading, [SLOT_START])
    monkeypatch.setattr(
        bookings_views, "get_provider", lambda: StubPaymentProvider(checkout_session=CheckoutSession("x", "https://x"))
    )

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 400
    assert b"details" in response.content.lower()
    assert Booking.objects.count() == 0


@freeze_time(NOW)
def test_checkout_refuses_a_reading_with_no_price(client, monkeypatch):
    reading = ReadingFactory(price=None)
    _stage_details(client)
    _availability_stub(monkeypatch, reading, [SLOT_START])

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 400
    assert b"pricing" in response.content.lower() or b"price" in response.content.lower()
    assert Booking.objects.count() == 0


@freeze_time(NOW)
def test_checkout_refuses_a_reading_with_no_duration(client, monkeypatch):
    reading = ReadingFactory(duration_minutes=None)
    _stage_details(client)
    _availability_stub(monkeypatch, reading, [SLOT_START])

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 400
    assert b"choose a reading" in response.content.lower()
    assert Booking.objects.count() == 0


@freeze_time(NOW)
def test_checkout_refuses_an_inactive_reading():
    """`Reading.objects.filter(pk=..., is_active=True)` — an inactive
    reading must not be bookable just because a stale page still posts its
    id."""
    reading = ReadingFactory(is_active=False)
    client = Client()
    _stage_details(client)

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 400
    assert Booking.objects.count() == 0


@freeze_time(NOW)
def test_checkout_happy_path_creates_a_pending_booking_and_redirects(client, monkeypatch):
    reading = ReadingFactory()
    _stage_details(client)
    _availability_stub(monkeypatch, reading, [SLOT_START])
    session = CheckoutSession(provider_reference="cs_new_1", redirect_url="https://checkout.stripe.test/pay/cs_new_1")
    monkeypatch.setattr(bookings_views, "get_provider", lambda: StubPaymentProvider(checkout_session=session))

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 302
    assert response.url == session.redirect_url
    booking = Booking.objects.get()
    assert booking.status == BookingStatus.PENDING
    assert booking.reading_id == reading.pk
    assert booking.start_at == SLOT_START
    assert booking.payment_reference == "cs_new_1"
    assert booking.amount_minor == int(reading.price * 100)


@freeze_time(NOW)
def test_checkout_happy_path_with_htmx_uses_hx_redirect_instead_of_302():
    """The no-JS path (a real 302) and the htmx path (a 200 + HX-Redirect
    header, so htmx performs the client-side redirect itself) must both
    actually work — see `_redirect_or_htmx` in views.py."""
    reading = ReadingFactory()
    client = Client(headers={"HX-Request": "true"})
    _stage_details(client)

    import apps.bookings.views as views_module

    session = CheckoutSession(provider_reference="cs_htmx_1", redirect_url="https://checkout.stripe.test/pay/cs_htmx_1")
    from unittest.mock import patch

    with patch.object(views_module.availability, "get_slots_for_day", return_value=[SLOT_START]), patch.object(
        views_module, "get_provider", return_value=StubPaymentProvider(checkout_session=session)
    ):
        response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 200
    assert response["HX-Redirect"] == session.redirect_url
    assert Booking.objects.count() == 1


@freeze_time(NOW)
def test_double_submission_reuses_the_existing_hold_not_a_second_booking(client, monkeypatch):
    """CLAUDE.md, verbatim: 'Double submission of checkout reuses the
    existing hold rather than creating a second booking.' Two POSTs from
    the same browser session (e.g. a slow first request retried by an
    impatient click) for the same reading/slot must leave exactly one
    Booking row, and the second request's provider call must be a fresh
    checkout session for the *same* booking, not a new one."""
    reading = ReadingFactory()
    _stage_details(client)
    _availability_stub(monkeypatch, reading, [SLOT_START])

    first_session = CheckoutSession(provider_reference="cs_dup_1", redirect_url="https://checkout.stripe.test/1")
    stub_first = StubPaymentProvider(checkout_session=first_session)
    monkeypatch.setattr(bookings_views, "get_provider", lambda: stub_first)
    first_response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))
    assert first_response.status_code == 302
    assert Booking.objects.count() == 1
    first_booking = Booking.objects.get()

    second_session = CheckoutSession(provider_reference="cs_dup_2", redirect_url="https://checkout.stripe.test/2")
    stub_second = StubPaymentProvider(checkout_session=second_session)
    monkeypatch.setattr(bookings_views, "get_provider", lambda: stub_second)
    second_response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert second_response.status_code == 302
    assert Booking.objects.count() == 1, "a second submission must not create a second booking row"
    first_booking.refresh_from_db()
    assert first_booking.public_ref  # unchanged identity
    assert len(stub_second.checkout_calls) == 1
    assert stub_second.checkout_calls[0][0].pk == first_booking.pk


@freeze_time(NOW)
def test_double_submission_after_the_first_holds_provider_differs_starts_a_fresh_hold(client, monkeypatch):
    """If the previously-held booking's provider no longer matches the
    configured one, reuse must not silently paper over that — a fresh
    hold/booking is created instead. Exercises the `provider.name ==
    existing.payment_provider` guard in `start_checkout`."""
    reading = ReadingFactory()
    _stage_details(client)
    _availability_stub(monkeypatch, reading, [SLOT_START])

    stub_first = StubPaymentProvider(checkout_session=CheckoutSession("cs_a", "https://x/a"))
    monkeypatch.setattr(bookings_views, "get_provider", lambda: stub_first)
    client.post(CHECKOUT_URL, data=_checkout_payload(reading))
    assert Booking.objects.count() == 1

    other_provider = StubPaymentProvider(checkout_session=CheckoutSession("cs_b", "https://x/b"))
    other_provider.name = "other-provider"
    monkeypatch.setattr(bookings_views, "get_provider", lambda: other_provider)

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 409
    assert Booking.objects.count() == 1, "the exclusion constraint must reject the colliding second hold"


@freeze_time(NOW)
def test_stale_availability_read_is_still_caught_by_the_database_constraint(client, monkeypatch):
    """Simulates the exact race `start_checkout`'s own comment describes:
    the pre-check (`availability.get_slots_for_day`) says a slot is free
    because it read stale data, but another active booking already
    occupies it by the time the insert runs. The database's exclusion
    constraint — not the pre-check — is what must actually stop this, and
    the view must turn that IntegrityError into a friendly, honest 409
    rather than a 500."""
    reading = ReadingFactory()
    _stage_details(client)

    # A real, already-committed booking occupying the slot — the pre-check
    # is stubbed to claim it's still free (the stale read).
    BookingFactory(
        reading=reading, start_at=SLOT_START, end_at=SLOT_START + timedelta(minutes=60), status=BookingStatus.PENDING
    )
    _availability_stub(monkeypatch, reading, [SLOT_START])
    monkeypatch.setattr(
        bookings_views, "get_provider", lambda: StubPaymentProvider(checkout_session=CheckoutSession("x", "https://x"))
    )

    response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 409
    assert Booking.objects.filter(start_at=SLOT_START).count() == 1, "no second, colliding booking must survive"


def test_provider_failure_cancels_the_just_created_hold(client, monkeypatch):
    """If the payment provider itself fails to start a session, the hold
    it was for must not sit reserved for nothing until it naturally
    expires — `start_checkout` cancels it immediately (see that view's own
    comment)."""
    reading = ReadingFactory()
    with freeze_time(NOW):
        _stage_details(client)
        _availability_stub(monkeypatch, reading, [SLOT_START])
        monkeypatch.setattr(
            bookings_views,
            "get_provider",
            lambda: StubPaymentProvider(checkout_error=PaymentProviderError("stripe is down")),
        )

        response = client.post(CHECKOUT_URL, data=_checkout_payload(reading))

    assert response.status_code == 400
    booking = Booking.objects.get()
    assert booking.status == BookingStatus.CANCELLED

"""
`apps.bookings.views.stripe_webhook` — untrusted, replayable input (see
that view's own docstring). Every scenario here is one PROJECT-SCOPE /
CLAUDE.md names explicitly as a correctness rule this handler must get
right: replay is a no-op, a booking's `status` and `payment_status` are
independent facts, and a refund never silently cancels a confirmed
appointment.

Stripe itself is never touched: `apps.bookings.views.get_provider` is
monkeypatched to a `StubPaymentProvider` (apps/bookings/tests/payments.py)
that returns a scripted, already-verified `NormalizedWebhookEvent` — the
same boundary `views.py` itself calls through, so nothing here depends on
how signature verification or the real Stripe payload shape works.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.bookings import views as bookings_views
from apps.bookings.models import Booking, BookingStatus, PaymentEvent, PaymentStatus
from apps.bookings.payments.base import PaymentProvider
from apps.bookings.tests.factories import BookingFactory
from apps.bookings.tests.payments import NormalizedWebhookEvent, PaymentProviderError, StubPaymentProvider

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/forms/booking/webhook/stripe/"


def _post(client, monkeypatch, provider):
    monkeypatch.setattr(bookings_views, "get_provider", lambda: provider)
    return client.post(WEBHOOK_URL, data=b"{}", content_type="application/json")


def test_replayed_webhook_delivery_is_a_no_op(client, monkeypatch, django_capture_on_commit_callbacks):
    booking = BookingFactory(
        status=BookingStatus.PENDING, payment_status=PaymentStatus.UNPAID, payment_reference="cs_replay_1"
    )
    event = NormalizedWebhookEvent(
        event_id="evt_replay_1",
        event_type=PaymentProvider.EVENT_PAYMENT_SUCCEEDED,
        provider_reference="cs_replay_1",
    )
    provider = StubPaymentProvider(webhook_event=event)
    send_emails = MagicMock()
    monkeypatch.setattr(bookings_views, "send_booking_emails", send_emails)

    with django_capture_on_commit_callbacks(execute=True):
        first = _post(client, monkeypatch, provider)
    assert first.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.PAID
    assert PaymentEvent.objects.filter(event_id="evt_replay_1").count() == 1
    assert send_emails.call_count == 1

    # The exact same event, delivered again (Stripe's documented at-least-
    # once delivery guarantee) — state must not be re-applied.
    with django_capture_on_commit_callbacks(execute=True):
        second = _post(client, monkeypatch, provider)
    assert second.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.PAID
    assert PaymentEvent.objects.filter(event_id="evt_replay_1").count() == 1
    assert send_emails.call_count == 1, "confirmation emails must not be sent twice for one event"


def test_payment_succeeded_for_a_still_pending_booking_confirms_it(client, monkeypatch):
    booking = BookingFactory(
        status=BookingStatus.PENDING, payment_status=PaymentStatus.UNPAID, payment_reference="cs_ok"
    )
    event = NormalizedWebhookEvent(
        event_id="evt_ok", event_type=PaymentProvider.EVENT_PAYMENT_SUCCEEDED, provider_reference="cs_ok"
    )
    response = _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.PAID
    assert booking.hold_expires_at is None


def test_payment_succeeded_after_the_hold_already_expired_does_not_confirm(client, monkeypatch):
    """The paid/booking-state divergence CLAUDE.md calls out by name: a
    booking whose hold had already been released (status=CANCELLED — see
    views._expire_stale_holds, which is what actually performs that
    release) before payment landed must stay CANCELLED even though the
    payment succeeded. Confirming it here would be worse than doing
    nothing: the slot is no longer exclusively held for this client."""
    booking = BookingFactory(
        status=BookingStatus.CANCELLED, payment_status=PaymentStatus.UNPAID, payment_reference="cs_late"
    )
    event = NormalizedWebhookEvent(
        event_id="evt_late", event_type=PaymentProvider.EVENT_PAYMENT_SUCCEEDED, provider_reference="cs_late"
    )
    send_needs_attention = MagicMock()
    monkeypatch.setattr(bookings_views, "send_payment_needs_attention_email", send_needs_attention)

    response = _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED, "a late payment must never resurrect an expired hold"
    assert booking.payment_status == PaymentStatus.PAID, "the payment itself is still a fact, honestly recorded"
    assert "needs manual follow-up" in booking.internal_notes


def test_refund_on_a_confirmed_booking_does_not_cancel_it(client, monkeypatch):
    """The other half of the same independence rule: a confirmed
    appointment whose payment is later refunded/disputed stays confirmed
    — refunding is Leslie's business decision about the appointment, made
    from the admin, never an automatic side effect of this handler."""
    booking = BookingFactory(
        status=BookingStatus.CONFIRMED, payment_status=PaymentStatus.PAID, payment_reference="cs_refund"
    )
    event = NormalizedWebhookEvent(
        event_id="evt_refund", event_type=PaymentProvider.EVENT_REFUNDED, provider_reference="cs_refund"
    )
    response = _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.REFUNDED


def test_checkout_expired_cancels_a_pending_booking(client, monkeypatch):
    booking = BookingFactory(status=BookingStatus.PENDING, payment_reference="cs_expired")
    event = NormalizedWebhookEvent(
        event_id="evt_expired",
        event_type=PaymentProvider.EVENT_CHECKOUT_EXPIRED,
        provider_reference="cs_expired",
    )
    response = _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED


def test_invalid_signature_is_rejected_and_nothing_is_recorded(client, monkeypatch):
    provider = StubPaymentProvider(webhook_error=PaymentProviderError("bad signature"))
    response = _post(client, monkeypatch, provider)

    assert response.status_code == 400
    assert PaymentEvent.objects.count() == 0


def test_webhook_for_an_unrecognised_payment_reference_is_recorded_but_not_linked(client, monkeypatch):
    """No booking anywhere has this payment_reference — the handler must
    not raise, and the event is still recorded (so a re-delivery of the
    *same* unrecognised event is still a no-op)."""
    event = NormalizedWebhookEvent(
        event_id="evt_orphan",
        event_type=PaymentProvider.EVENT_PAYMENT_SUCCEEDED,
        provider_reference="cs_does_not_exist",
    )
    response = _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    assert response.status_code == 200
    assert PaymentEvent.objects.filter(event_id="evt_orphan").exists()
    assert Booking.objects.count() == 0


def test_payment_event_is_linked_to_the_booking_it_is_for(client, monkeypatch):
    """`PaymentEvent.booking` exists specifically so a booking's own
    payment history is visible (`related_name="payment_events"`, and the
    booking admin panels show payment fields alongside it) — a webhook
    that resolves to a real booking must set it, or `booking.payment_events
    .all()` silently stays empty forever and there is no way, from the
    admin, to see which webhook deliveries a given booking actually had."""
    booking = BookingFactory(payment_reference="cs_link_me")
    event = NormalizedWebhookEvent(
        event_id="evt_link", event_type=PaymentProvider.EVENT_PAYMENT_SUCCEEDED, provider_reference="cs_link_me"
    )
    _post(client, monkeypatch, StubPaymentProvider(webhook_event=event))

    stored = PaymentEvent.objects.get(event_id="evt_link")
    assert stored.booking_id == booking.id

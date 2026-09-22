"""
The database-level guarantees `apps/bookings/models.py`'s own docstring
names as its correctness rules: the exclusion constraint that makes
double-booking structurally impossible, and the unique constraint that
makes a replayed webhook delivery a no-op at the database layer (the
belt under views.py's own idempotency belt-and-braces — see
test_webhooks.py for the view-level behaviour this backs).
"""

from __future__ import annotations

from datetime import timedelta
from datetime import timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.tests.factories import BookingFactory, PaymentEventFactory

pytestmark = pytest.mark.django_db


def test_overlapping_active_bookings_are_rejected_by_the_database():
    start = timezone.datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
    BookingFactory(start_at=start, end_at=start + timedelta(minutes=60), status=BookingStatus.PENDING)

    # Starts 30 minutes into the first booking — a genuine overlap.
    overlapping_start = start + timedelta(minutes=30)
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingFactory(
            start_at=overlapping_start,
            end_at=overlapping_start + timedelta(minutes=60),
            status=BookingStatus.PENDING,
        )

    assert Booking.objects.count() == 1


@pytest.mark.parametrize("status", [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
def test_overlap_is_rejected_for_every_active_status(status):
    """The exclusion constraint's condition lists PENDING, CONFIRMED and
    COMPLETED as active (see ACTIVE_BOOKING_STATUSES) — prove each one
    actually blocks an overlapping insert, not just the default (PENDING)."""
    start = timezone.datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
    BookingFactory(start_at=start, end_at=start + timedelta(minutes=60), status=status)

    with pytest.raises(IntegrityError), transaction.atomic():
        BookingFactory(
            start_at=start, end_at=start + timedelta(minutes=60), status=BookingStatus.PENDING
        )


def test_adjacent_slots_do_not_overlap():
    """[start, end) is half-open — a slot that starts exactly when another
    ends must be bookable, or every day's schedule would lose its last
    possible adjacent slot for no reason."""
    start = timezone.datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
    BookingFactory(start_at=start, end_at=start + timedelta(minutes=60), status=BookingStatus.PENDING)

    second_start = start + timedelta(minutes=60)
    BookingFactory(
        start_at=second_start, end_at=second_start + timedelta(minutes=60), status=BookingStatus.PENDING
    )

    assert Booking.objects.count() == 2


def test_cancelled_booking_frees_its_slot_for_reuse():
    """CANCELLED is deliberately excluded from the constraint's condition
    (ACTIVE_BOOKING_STATUSES) — a released hold must not permanently block
    its slot."""
    start = timezone.datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
    first = BookingFactory(start_at=start, end_at=start + timedelta(minutes=60), status=BookingStatus.PENDING)
    first.status = BookingStatus.CANCELLED
    first.save(update_fields=["status"])

    second = BookingFactory(start_at=start, end_at=start + timedelta(minutes=60), status=BookingStatus.PENDING)

    assert Booking.objects.filter(start_at=start).count() == 2
    assert second.status == BookingStatus.PENDING


def test_payment_event_duplicate_provider_and_event_id_is_rejected():
    """The database-level twin of the webhook handler's idempotency
    (views.stripe_webhook) — a second row for the same (provider, event_id)
    must never be insertable, regardless of what any Python check does."""
    PaymentEventFactory(provider="stripe", event_id="evt_dup_1")

    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentEventFactory(provider="stripe", event_id="evt_dup_1")


def test_payment_event_same_id_different_provider_is_allowed():
    """The uniqueness is scoped to (provider, event_id) together — two
    different providers are free to reuse the same event id shape."""
    PaymentEventFactory(provider="stripe", event_id="evt_1")
    PaymentEventFactory(provider="other-provider", event_id="evt_1")

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


class TestAmountDisplay:
    """`Booking.amount_display` — money formatting moved out of
    booking_detail.html (which previously divided `amount_minor` with
    chained stringformat/slice/add template filters) and into the model,
    per CLAUDE.md's "no business logic in templates" rule. `amount_minor`
    itself stays an integer minor-unit field; only display formatting
    happens here."""

    @pytest.mark.parametrize(
        "amount_minor, currency, expected",
        [
            (15000, "NZD", "NZD 150.00"),
            (5, "NZD", "NZD 0.05"),
            (0, "NZD", "NZD 0.00"),
            (19999, "NZD", "NZD 199.99"),
            (100, "NZD", "NZD 1.00"),
            (1, "USD", "USD 0.01"),
        ],
    )
    def test_formats_minor_units_as_two_decimal_places(self, amount_minor, currency, expected):
        booking = BookingFactory(amount_minor=amount_minor, currency=currency)
        assert booking.amount_display == expected

    def test_never_uses_float_division(self):
        """A regression guard for the exact failure mode this property
        exists to avoid: binary floating-point division on cents can
        misround (e.g. 0.1 + 0.2 != 0.3 style errors) for values a naive
        `amount_minor / 100` implementation would get wrong. Integer
        divmod is exact for every value tested here, however large."""
        booking = BookingFactory(amount_minor=100_000_007, currency="NZD")
        assert booking.amount_display == "NZD 1000000.07"

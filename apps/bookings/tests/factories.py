from __future__ import annotations

from datetime import timedelta
from datetime import timezone as dt_timezone

import factory
from django.utils import timezone

from apps.bookings.models import (
    AvailabilityException,
    AvailabilityRule,
    Booking,
    BookingStatus,
    PaymentEvent,
    PaymentStatus,
)
from apps.readings.tests.factories import ReadingFactory


class AvailabilityRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AvailabilityRule

    weekday = 0  # Monday
    start_time = "09:00"
    end_time = "17:00"
    is_active = True


class AvailabilityExceptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AvailabilityException

    is_closed = True


class BookingFactory(factory.django.DjangoModelFactory):
    """
    A held/confirmed appointment. `start_at`/`end_at` default to a fixed,
    arbitrary future UTC instant (not `timezone.now()`-relative) so tests
    that build two bookings and reason about overlap aren't at the mercy of
    wall-clock time when the suite happens to run — pass explicit
    `start_at`/`end_at` for anything that actually tests scheduling.
    """

    class Meta:
        model = Booking

    reading = factory.SubFactory(ReadingFactory)
    client_first_name = "Jamie"
    client_last_name = "Taylor"
    client_email = "jamie@example.com"
    birth_place = "Auckland, New Zealand"
    start_at = factory.LazyFunction(
        lambda: timezone.datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
    )
    end_at = factory.LazyAttribute(lambda o: o.start_at + timedelta(minutes=60))
    duration_minutes = 60
    display_timezone = "Pacific/Auckland"
    status = BookingStatus.PENDING
    hold_expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=15))
    payment_status = PaymentStatus.UNPAID
    amount_minor = 15000
    currency = "NZD"


class PaymentEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentEvent

    provider = "stripe"
    event_id = factory.Sequence(lambda n: f"evt_{n}")
    event_type = "payment_succeeded"


def make_booking_page(**overrides):
    """
    A real, live `bookings.BookingPage` under a real HomePage.

    Needed by any test asserting the non-htmx branch of `save_details` /
    `_checkout_error` actually renders the *owning page*
    (`apps.bookings.views._render_booking_page`) rather than its "no
    BookingPage published" fallback — without a live BookingPage in the
    test database, `BookingPage.objects.live().first()` is `None` and
    every one of those views silently takes the fallback path instead of
    the one FINDING 1 (reviews/2026-09-22-final-build-review.md) fixed,
    which would make a shape assertion pass for the wrong reason.
    """
    from apps.bookings.models import BookingPage
    from apps.home.tests.factories import make_home_page

    home = overrides.pop("home", None) or make_home_page()
    field_defaults = dict(title="Book a Reading", slug=overrides.pop("slug", "book-a-reading-test"))
    field_defaults.update(overrides)
    page = BookingPage(**field_defaults)
    home.add_child(instance=page)
    return page

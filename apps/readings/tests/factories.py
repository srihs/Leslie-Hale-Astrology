"""factory_boy factories for apps.readings — the CMS-owned source of
truth for what can be booked and at what price (see apps/bookings/models.py's
own module docstring). Booking/payment tests build a Reading through this
factory rather than a bare `Reading.objects.create(...)` so every test that
needs "a bookable reading" gets one with sane, non-None price/duration by
default, and can override just the field the test is actually about."""

from __future__ import annotations

from decimal import Decimal

import factory

from apps.readings.models import Reading


class ReadingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reading

    name = factory.Sequence(lambda n: f"Natal Chart Reading {n}")
    tag_label = "Natal chart"
    summary = "A deep look at your birth chart."
    duration_minutes = 60
    price = Decimal("150.00")
    price_note = ""
    is_active = True
    order = factory.Sequence(lambda n: n)

"""
Turns Leslie's Wagtail-edited availability (AvailabilityRule /
AvailabilityException) into bookable slots, in UTC, with already-active
bookings excluded — and assembles the exact context dict BookingPage's
existing, locked templates already document needing (see
templates/bookings/partials/_booking_panel_form.html and
_booking_summary.html's own header comments, written before this module
existed).

This module never writes to the database. It only decides what to *offer*
a visitor. The actual reservation happens in
apps.bookings.views.start_checkout, inside a transaction guarded by
Booking's database exclusion constraint (see models.py) — nothing here is
a substitute for that constraint, since two requests could always race
between a slot being "offered" here and one of them being booked.
"""

from __future__ import annotations

import calendar as calendar_module
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, available_timezones

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

SITE_ZONE = ZoneInfo(settings.TIME_ZONE)


def resolve_timezone(tz_name: str | None) -> ZoneInfo:
    """
    Validate a visitor-supplied IANA timezone name (from the `tz` query
    param — see the context contract in the final report), falling back
    to the site's own timezone (Leslie's local time, clearly labelled) if
    it's missing or not real. Never trust the query string blindly: an
    unrecognised string here would otherwise raise inside `ZoneInfo()`.
    """
    if tz_name and tz_name in available_timezones():
        return ZoneInfo(tz_name)
    return SITE_ZONE


def tz_label(tz: ZoneInfo, at: datetime | None = None) -> str:
    """
    A short, human label for a timezone, e.g. 'EDT' or 'EST' — always
    shown next to a time in this app, per the SCOPE correctness rule that
    the timezone must be visible in the UI and in every confirmation
    email. `at` should be the actual instant being labelled (an
    appointment's start time), not left to default to now — daylight
    saving means the correct abbreviation can differ between "today" and
    the appointment date (e.g. America/New_York moves from EST to EDT
    in mid-March each year). This is generic to whatever IANA zone is
    passed in — it is not specific to the site's own `settings.TIME_ZONE`
    (see test_availability.py, which exercises this with Pacific/Auckland
    directly, independent of whatever the site's own zone is).
    """
    reference = at if at is not None else timezone.now()
    return reference.astimezone(tz).tzname() or str(tz)


def _format_time_label(local_dt: datetime) -> str:
    """'10:00 am' — matches the locked v1-ephemeris design's slot button
    labels. Written by hand rather than with a %-I strftime flag, which
    isn't portable across platforms."""
    hour = local_dt.hour % 12 or 12
    period = "am" if local_dt.hour < 12 else "pm"
    return f"{hour}:{local_dt.minute:02d} {period}"


def _day_windows(day: date) -> list[tuple[datetime, datetime]]:
    """Local-time (SITE_ZONE) open windows for one calendar day: an
    AvailabilityException for that date wins outright if one exists,
    otherwise every active AvailabilityRule matching that weekday."""
    from apps.bookings.models import AvailabilityException, AvailabilityRule

    exception = AvailabilityException.objects.filter(date=day).first()

    if exception is not None:
        if exception.is_closed or not exception.start_time or not exception.end_time:
            return []
        windows = [(exception.start_time, exception.end_time)]
    else:
        windows = [
            (r.start_time, r.end_time)
            for r in AvailabilityRule.objects.filter(weekday=day.weekday(), is_active=True)
        ]

    return [
        (datetime.combine(day, start, tzinfo=SITE_ZONE), datetime.combine(day, end, tzinfo=SITE_ZONE))
        for start, end in windows
        if end > start
    ]


def _candidate_starts(day: date, duration_minutes: int) -> list[datetime]:
    """UTC start datetimes for every duration_minutes-long slot that fits
    inside that day's open windows, without regard to existing bookings."""
    step = timedelta(minutes=duration_minutes)
    starts = []
    for window_start, window_end in _day_windows(day):
        cursor = window_start
        while cursor + step <= window_end:
            starts.append(cursor.astimezone(dt_timezone.utc))
            cursor += step
    return starts


def get_slots_for_day(reading, day: date | None) -> list[datetime]:
    """
    Open, still-in-the-future, not-already-booked UTC start times for
    `reading` on `day`. Excluding already-booked slots here is purely a
    courtesy to the visitor (don't offer what's gone) — it is NOT what
    prevents a double booking; see the module docstring.
    """
    from apps.bookings.models import ACTIVE_BOOKING_STATUSES, Booking

    if not reading or not day or not reading.duration_minutes:
        return []

    candidates = _candidate_starts(day, reading.duration_minutes)
    if not candidates:
        return []

    now = timezone.now()
    candidates = [c for c in candidates if c > now]
    if not candidates:
        return []

    duration = timedelta(minutes=reading.duration_minutes)
    window_start, window_end = candidates[0], candidates[-1] + duration
    taken = list(
        Booking.objects.filter(
            status__in=ACTIVE_BOOKING_STATUSES,
            start_at__lt=window_end,
            end_at__gt=window_start,
        ).values_list("start_at", "end_at")
    )

    def is_free(start: datetime) -> bool:
        end = start + duration
        return not any(start < t_end and end > t_start for t_start, t_end in taken)

    return [c for c in candidates if is_free(c)]


def is_day_available(reading, day: date) -> bool:
    return len(get_slots_for_day(reading, day)) > 0


def _month_cells(first_of_month: date) -> list[date | None]:
    """35/42 cells, row-major, Monday-first — matches the locked design's
    calendar grid and templates/bookings/partials/_booking_panel_form.html's
    documented `calendar_cells` contract exactly."""
    cal = calendar_module.Calendar(firstweekday=0)
    return [
        d if d.month == first_of_month.month else None
        for week in cal.monthdatescalendar(first_of_month.year, first_of_month.month)
        for d in week
    ]


def _parse_month(month_param: str, today_local: date) -> date:
    try:
        year_str, month_str = month_param.split("-", 1)
        return date(int(year_str), int(month_str), 1)
    except (ValueError, TypeError):
        return today_local.replace(day=1)


def _adjacent_month_iso(first_of_month: date, delta_months: int) -> str:
    if delta_months < 0:
        target = (first_of_month - timedelta(days=1)).replace(day=1)
    else:
        target = (first_of_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return target.strftime("%Y-%m")


def booking_panel_context(request) -> dict:
    """
    Everything templates/bookings/partials/_booking_panel_form.html and
    _booking_summary.html already document needing under "Context (apps.
    bookings view): ...", plus `payment_return` for the redirect back from
    the payment provider. Called from BookingPage.get_context — see
    models.py.
    """
    from apps.bookings.models import Booking
    from apps.readings.models import Reading

    readings = list(Reading.objects.filter(is_active=True).order_by("order", "name"))

    reading_param = request.GET.get("reading", "").strip()
    selected_reading = next((r for r in readings if str(r.pk) == reading_param), None)
    if selected_reading is None and readings:
        selected_reading = readings[0]

    tz = resolve_timezone(request.GET.get("tz", "").strip())
    today_local = timezone.now().astimezone(tz).date()

    first_of_month = _parse_month(request.GET.get("month", "").strip(), today_local)

    day_param = request.GET.get("day", "").strip()
    try:
        selected_day = date.fromisoformat(day_param) if day_param else None
    except ValueError:
        selected_day = None

    day_slots = get_slots_for_day(selected_reading, selected_day)

    slot_param = request.GET.get("slot", "").strip()
    selected_slot = next((s for s in day_slots if s.isoformat() == slot_param), None)

    calendar_cells = [
        {
            "day": d.day if d else None,
            "iso": d.isoformat() if d else "",
            "available": bool(d and d >= today_local and is_day_available(selected_reading, d)),
            "selected": bool(d and selected_day and d == selected_day),
        }
        for d in _month_cells(first_of_month)
    ]

    reading_types = [
        {
            "slug": str(r.pk),
            "label": r.name,
            "price": r.price,
            "duration_minutes": r.duration_minutes,
            "blurb": r.summary,
            "selected": bool(selected_reading and r.pk == selected_reading.pk),
        }
        for r in readings
    ]

    slots = [
        {
            "value": s.isoformat(),
            "label": _format_time_label(s.astimezone(tz)),
            "selected": bool(selected_slot and s == selected_slot),
        }
        for s in day_slots
    ]

    ready = bool(selected_reading and selected_reading.price is not None and selected_day and selected_slot)
    summary = {
        "reading_label": selected_reading.name if selected_reading else None,
        "price": selected_reading.price if selected_reading else None,
        "date_label": selected_day.strftime("%A %-d %B") if selected_day else None,
        "time_label": (
            f"{_format_time_label(selected_slot.astimezone(tz))} {tz_label(tz, at=selected_slot)}"
            if selected_slot
            else None
        ),
        "ready": ready,
        "reading_slug": str(selected_reading.pk) if selected_reading else "",
        "day_iso": selected_day.isoformat() if selected_day else "",
        "slot_value": selected_slot.isoformat() if selected_slot else "",
    }

    context = {
        "reading_types": reading_types,
        "month_label": first_of_month.strftime("%B %Y"),
        "prev_month_iso": _adjacent_month_iso(first_of_month, -1),
        "next_month_iso": _adjacent_month_iso(first_of_month, 1),
        "calendar_cells": calendar_cells,
        "slots": slots,
        "summary": summary,
        "timezone_label": tz_label(tz, at=selected_slot),
        "display_timezone": str(tz),
        "hold_minutes": _hold_minutes(),
    }

    ref = request.GET.get("ref", "").strip()
    if ref:
        booking = Booking.objects.filter(public_ref=ref).select_related("reading").first()
        context["payment_return"] = {
            "result": request.GET.get("result", "").strip(),
            "booking": booking,
            "status_url": reverse("bookings:booking_status", args=[ref]) if booking else "",
        }

    return context


def _hold_minutes() -> int:
    from apps.bookings.models import HOLD_MINUTES

    return HOLD_MINUTES

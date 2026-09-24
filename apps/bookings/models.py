"""
Booking, availability and payment-event data.

This module now does the work its earlier "data shape only" version
deliberately deferred (see git history) — see PROJECT-SCOPE.md §8 and
CLAUDE.md's booking-payments brief for why that deferral was correct at
the time and what has changed:

- The final list of readings and their prices is still §8-open and still
  lives entirely in `apps.readings.Reading` (a CMS snippet) — nothing
  here invents a reading or a price. `Booking.amount_minor` is a snapshot
  of whatever `Reading.price` said *at the moment of booking*, taken so
  that a later price change in the CMS never rewrites the historical
  record of what a client actually agreed to pay.
- The booking/payment tool is still §8-open with the client, but the
  agent instruction directing this build named Stripe as the concrete
  choice to implement now (docker-infra already plumbed the three
  STRIPE_* env vars). `Booking.payment_provider` and `payment_reference`
  stay provider-agnostic free text/reference fields — see
  `apps/bookings/payments/` for the swappable adapter interface that
  keeps Stripe specifics out of this file entirely.
- The contact email for confirmations is still §8-open — see
  `apps/bookings/emails.py`, which reads `ContactSettings.contact_email`
  live rather than storing or hardcoding an address here.

Correctness rules this module exists to enforce (see CLAUDE.md):

- **Never double-book.** `Booking.Meta.constraints` carries a Postgres
  `ExclusionConstraint` (`booking_no_overlapping_active_slots`) that makes
  two active bookings with overlapping `[start_at, end_at)` ranges
  impossible at the database level, regardless of what any Python
  availability check said a moment earlier. `apps/bookings/availability.py`
  only decides what to *offer* a visitor; this constraint is what actually
  prevents two people from ever holding the same appointment.
- **Payment state is not booking state.** `status` (BookingStatus) and
  `payment_status` (PaymentStatus) are separate fields with no CHECK
  constraint coupling them, on purpose: a booking can be `confirmed` with
  `payment_status=refunded` (paid, then disputed, after the appointment
  was already confirmed), and a booking can be `cancelled` (its hold
  expired) with `payment_status=paid` (the client's payment landed just
  after the hold was released) — both states are representable and both
  are handled explicitly in `apps/bookings/views.py`'s webhook handler.
- **Store UTC, render in the client's timezone.** `start_at`/`end_at` are
  ordinary timezone-aware `DateTimeField`s; with `USE_TZ=True` Django
  stores them in UTC in Postgres. `display_timezone` records which IANA
  zone was actually shown to the client when they booked (see
  `apps/bookings/availability.py:resolve_timezone`), so confirmation
  emails describe the same time the client actually clicked, not a
  re-derived one.
- **Money is integer minor units.** `amount_minor` is a `PositiveIntegerField`
  (cents), never a float or a bare Decimal dollar amount, from the moment
  it's captured (`apps/bookings/views.py:start_checkout`) through to
  whatever the payment provider is told to charge.
- **Never log card data, tokens or full personal details.** Nothing here
  logs anything; see `apps/bookings/emails.py` and `views.py` for the
  logging discipline (booking reference + exception type only).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import Func, Q
from django.utils import timezone
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

# Reading is the CMS-owned, §8-open source of truth for what can be
# booked and at what price — see apps/readings/models.py. This module
# only ever reads it.
from apps.readings.models import Reading

# The currency new bookings are priced and charged in. Read from
# `settings.BOOKING_CURRENCY` (config/settings/base.py, env-backed,
# default "USD") rather than hardcoded here — this used to be a bare
# `CURRENCY = "NZD"` literal, which was the agency's own timezone/country
# leaking into money, not a fact about Leslie's business. See
# config/settings/base.py's own comment for the zero-decimal-currency
# caution (JPY, KRW, VND, ...) before this is ever changed to anything
# other than a two-decimal currency like USD. Kept as one named constant,
# not read from settings at each call site, so call sites (views.py) stay
# unchanged and a currency change is still a one-line/config-only fix.
CURRENCY = settings.BOOKING_CURRENCY

# Minutes a slot is held, unpaid, before it's treated as abandoned and
# released back to availability. Not a §8 item (it's an operational
# default, not a price or a provider choice) — 15 minutes is long enough
# to complete a Stripe Checkout without feeling arbitrary. Leslie can ask
# to change it; it isn't CMS content because changing it doesn't need her
# involvement the way a price or a reading does.
HOLD_MINUTES = 15


class BookingStatus(models.TextChoices):
    PENDING = "pending", "Pending — held, awaiting payment"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


# Statuses that occupy the calendar and must never overlap another active
# booking. CANCELLED is the only status that frees a slot — see the
# ExclusionConstraint below, which references this list's SQL equivalent
# directly in its `condition`.
ACTIVE_BOOKING_STATUSES = [
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.COMPLETED,
]


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    NOT_REQUIRED = "not_required", "Not required"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


@register_snippet
class AvailabilityRule(models.Model):
    """
    Leslie's recurring weekly availability, editable in Wagtail admin
    (Snippets → Availability rules) without any technical help — this is
    what makes "Leslie must be able to define when she is available"
    (task item 1) true. Times are in the site's own local time zone
    (`settings.TIME_ZONE`, America/New_York) because that's how Leslie
    will naturally think about her week; `apps/bookings/availability.py`
    converts to UTC when turning these into bookable slots.
    """

    weekday = models.IntegerField(
        choices=Weekday.choices,
        help_text="Which day of the week this window applies to, every week.",
    )
    start_time = models.TimeField(
        help_text="When you become available that day, in your own local time."
    )
    end_time = models.TimeField(
        help_text="When you stop being available that day. Must be after the start time."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Untick to switch off this window without deleting it.",
    )

    panels = [
        FieldPanel("weekday"),
        MultiFieldPanel([FieldPanel("start_time"), FieldPanel("end_time")], heading="Window"),
        FieldPanel("is_active"),
    ]

    class Meta:
        verbose_name = "Availability rule"
        verbose_name_plural = "Availability rules"
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"


@register_snippet
class AvailabilityException(models.Model):
    """
    A one-off change to a specific date — a day off, a public holiday, or
    special hours that replace the usual weekly rules just for that date.
    Also editable in Wagtail admin without technical help. Checked before
    `AvailabilityRule` for any given date (see
    `apps/bookings/availability.py:_day_windows`), so an exception always
    wins over the recurring weekly pattern.
    """

    date = models.DateField(unique=True)
    is_closed = models.BooleanField(
        default=True,
        help_text="Tick to block this date entirely. Untick to set special "
        "one-off hours below instead of your usual weekly availability.",
    )
    start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Only used when 'Closed all day' is unticked.",
    )
    end_time = models.TimeField(null=True, blank=True)
    note = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional private note for your own reference, e.g. 'Public holiday'.",
    )

    panels = [
        FieldPanel("date"),
        FieldPanel("is_closed", heading="Closed all day"),
        MultiFieldPanel(
            [FieldPanel("start_time"), FieldPanel("end_time")],
            heading="Special hours (only if not closed all day)",
        ),
        FieldPanel("note"),
    ]

    class Meta:
        verbose_name = "Availability exception"
        verbose_name_plural = "Availability exceptions"
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} — {'closed' if self.is_closed else 'special hours'}"


@register_snippet
class Booking(models.Model):
    """
    One held or confirmed appointment. See the module docstring for how
    the fields below enforce the correctness rules — in short:
    `start_at`/`end_at` plus the exclusion constraint prevent double
    booking; `status` and `payment_status` are independent; birth data has
    its own explicit, typed fields rather than living in free text.

    `public_ref` (not the numeric primary key) is what's ever exposed to
    the browser or the payment provider — a UUID doesn't let a client
    guess at or enumerate other people's bookings by incrementing a URL.
    """

    public_ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    reading = models.ForeignKey(
        Reading,
        on_delete=models.PROTECT,
        related_name="bookings",
        help_text="Which reading this booking is for.",
    )

    # --- Client identity ------------------------------------------------
    client_first_name = models.CharField(max_length=80)
    client_last_name = models.CharField(max_length=80)
    client_email = models.EmailField()
    client_phone = models.CharField(max_length=30, blank=True)

    # --- Birth data (task item 4) ---------------------------------------
    # Explicit, typed fields — not free text — because the booking form
    # collects them specifically so Leslie can prepare a chart before the
    # session. Sensitive personal data: never included in log lines (see
    # apps/bookings/emails.py and views.py), only in the booking record
    # itself and in the two emails that legitimately need it.
    birth_date = models.DateField(
        null=True, blank=True, help_text="Client's date of birth."
    )
    birth_time = models.TimeField(
        null=True, blank=True, help_text="Client's time of birth, if known."
    )
    birth_time_unknown = models.BooleanField(
        default=False,
        help_text="Client told us they don't know their exact birth time.",
    )
    birth_place = models.CharField(
        max_length=150, blank=True, help_text="City/country of birth, as given by the client."
    )
    client_notes = models.TextField(
        blank=True,
        help_text="What the client said they'd like to focus on (optional, client-provided free text).",
    )

    # --- When ------------------------------------------------------------
    start_at = models.DateTimeField(help_text="Appointment start, stored in UTC.")
    end_at = models.DateTimeField(help_text="Appointment end, stored in UTC.")
    duration_minutes = models.PositiveIntegerField(
        help_text="Snapshot of the reading's duration at the time of booking, "
        "so a later change to the reading's typical duration never rewrites "
        "what was actually booked."
    )
    display_timezone = models.CharField(
        max_length=64,
        help_text="The IANA timezone name shown to the client when they chose "
        "this slot (e.g. 'America/New_York'), so confirmation emails describe "
        "the same time the client actually saw and clicked, not a re-derived one.",
    )

    # --- Booking state -----------------------------------------------------
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    hold_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="While status is 'pending', when this hold releases the slot "
        "back to availability if payment hasn't completed by then.",
    )

    # --- Payment state (deliberately independent of `status` — see the
    # module docstring) ------------------------------------------------
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    payment_provider = models.CharField(
        max_length=30,
        blank=True,
        help_text="Which payment tool processed this booking, e.g. 'stripe'. "
        "Set by whichever adapter in apps/bookings/payments/ handled it.",
    )
    payment_reference = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        unique=True,
        help_text="The payment provider's own reference for this booking "
        "(e.g. a Stripe Checkout Session ID) — how incoming webhooks are "
        "matched back to this row.",
    )
    amount_minor = models.PositiveIntegerField(
        default=0,
        help_text="The amount charged, in integer minor currency units (e.g. "
        "cents) — never a float. Snapshot of the reading's price at the time "
        "of booking.",
    )
    currency = models.CharField(max_length=3, default=CURRENCY)

    # --- Confirmation email tracking (so a send failure is visible and
    # resendable rather than silently lost) -----------------------------
    confirmation_email_sent_at = models.DateTimeField(null=True, blank=True)
    confirmation_email_error = models.CharField(
        max_length=200,
        blank=True,
        help_text="Set automatically if the confirmation email failed to send "
        "(exception type only — never message content that could carry "
        "personal data). Cleared once a resend succeeds.",
    )

    internal_notes = models.TextField(
        blank=True,
        help_text="Private notes for Leslie only — never shown to the client.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Visible to Leslie in Wagtail admin (Snippets → Bookings) so she can
    # see who's booked in without asking SAS Creative — the calendar/slot
    # data itself is never edited here, only the record of what was
    # booked. `internal_notes` and `status` are the two fields she's
    # actually expected to change by hand (e.g. marking a booking
    # `completed`, or noting a manual reschedule); the rest is shown for
    # reference. Birth data and payment reference are included because
    # Leslie legitimately needs them (chart prep, matching up a payment
    # query) — this is staff-only Wagtail admin, not public.
    panels = [
        MultiFieldPanel(
            [FieldPanel("reading"), FieldPanel("start_at"), FieldPanel("end_at"), FieldPanel("display_timezone")],
            heading="Appointment",
        ),
        MultiFieldPanel(
            [
                FieldPanel("client_first_name"),
                FieldPanel("client_last_name"),
                FieldPanel("client_email"),
                FieldPanel("client_phone"),
            ],
            heading="Client",
        ),
        MultiFieldPanel(
            [
                FieldPanel("birth_date"),
                FieldPanel("birth_time"),
                FieldPanel("birth_time_unknown"),
                FieldPanel("birth_place"),
                FieldPanel("client_notes"),
            ],
            heading="Birth details & focus",
        ),
        MultiFieldPanel(
            [FieldPanel("status"), FieldPanel("hold_expires_at"), FieldPanel("internal_notes")],
            heading="Status",
        ),
        MultiFieldPanel(
            [
                FieldPanel("payment_status"),
                FieldPanel("payment_provider"),
                FieldPanel("payment_reference"),
                FieldPanel("amount_minor"),
                FieldPanel("currency"),
            ],
            heading="Payment",
        ),
        MultiFieldPanel(
            [FieldPanel("confirmation_email_sent_at"), FieldPanel("confirmation_email_error")],
            heading="Confirmation email",
        ),
    ]

    class Meta:
        verbose_name = "Booking"
        ordering = ["-start_at"]
        constraints = [
            # The actual double-booking guard. Two rows whose [start_at,
            # end_at) ranges overlap, both in an ACTIVE_BOOKING_STATUSES
            # status, are rejected by Postgres itself (IntegrityError) —
            # not by a check in Python that could race. Requires the
            # btree_gist extension (see the 000x migration).
            ExclusionConstraint(
                name="booking_no_overlapping_active_slots",
                expressions=[
                    (Func("start_at", "end_at", function="tstzrange"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=[s.value for s in ACTIVE_BOOKING_STATUSES]),
            ),
        ]

    def __str__(self):
        return f"{self.full_name} — {self.reading} ({self.start_at:%Y-%m-%d %H:%M} UTC)"

    @property
    def full_name(self) -> str:
        return f"{self.client_first_name} {self.client_last_name}".strip()

    @property
    def is_hold_expired(self) -> bool:
        return bool(self.hold_expires_at and self.hold_expires_at < timezone.now())

    @property
    def amount_display(self) -> str:
        """`amount_minor`/`currency` formatted for display, e.g. "USD
        150.00". `amount_minor` stays an integer minor-unit field on the
        model (never a float or Decimal dollars) — this only formats it
        for reading, using integer division/modulo (never a float
        division, which risks binary floating-point rounding on the
        exact cents figure a client was charged) — the same conversion
        booking_detail.html previously did itself with
        stringformat/slice/add template filters. Money arithmetic
        belongs here, not in a template.

        The divmod-by-100 below assumes a two-decimal currency, same as
        `settings.BOOKING_CURRENCY`'s own docstring caution and the
        `amount_minor` calculation in views.py: correct for USD/NZD, and
        NOT currency-aware. A zero-decimal currency (JPY, KRW, VND, ...)
        would need this changed too, in the same pass as that setting's
        caution — it is not handled by `currency` alone being
        configurable."""
        dollars, cents = divmod(self.amount_minor, 100)
        return f"{self.currency} {dollars}.{cents:02d}"


class PaymentEvent(models.Model):
    """
    One received, verified webhook delivery. Its whole purpose is the
    unique constraint below: webhooks are untrusted and arrive more than
    once (SCOPE correctness rule), and inserting a row here — inside the
    same transaction as acting on the event — is what makes
    apps/bookings/views.py's webhook handler idempotent. A second delivery
    of the same (provider, event_id) hits a database IntegrityError and is
    treated as a no-op, not reprocessed.
    """

    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=60)
    booking = models.ForeignKey(
        Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_events"
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Payment event"
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="unique_provider_event"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id} ({self.event_type})"


class BookingPage(Page):
    """
    The Booking page (§4): the copy around the booking system, plus (via
    `get_context` below) the whole step-1/2 choose-reading/choose-slot
    flow and the return leg from the payment provider. The calendar/slot
    data itself is never CMS content — it's live, derived availability —
    only the surrounding policy text is.
    """

    template = "bookings/booking.html"

    intro = models.TextField(
        blank=True,
        help_text="Shown above the booking calendar, e.g. how the process works.",
    )
    cancellation_policy = models.TextField(
        blank=True,
        help_text="Your cancellation/rescheduling policy, shown near the "
        "booking form and included in confirmation emails.",
    )
    confirmation_message = models.TextField(
        blank=True,
        help_text="Shown to a client immediately after they submit a booking "
        "request, before payment or confirmation is complete.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        MultiFieldPanel(
            [FieldPanel("cancellation_policy"), FieldPanel("confirmation_message")],
            heading="Policies & confirmation",
        ),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1

    class Meta:
        verbose_name = "Booking page"

    def get_context(self, request, *args, **kwargs):
        # Imported here, not at module level, to avoid a circular import —
        # availability.py imports the models defined above.
        from apps.bookings import availability

        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "booking"
        context.update(availability.booking_panel_context(request))
        return context

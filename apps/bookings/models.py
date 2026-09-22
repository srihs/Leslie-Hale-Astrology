"""
Booking data shape only.

This module intentionally stops short of a working booking system. It
gives booking-payments a `Booking` record to write to and a `BookingPage`
to attach the calendar/payment widget to, but it does not model
availability, calendar slots, or any specific payment gateway — §8 lists
"booking/payment tools already in use" as unconfirmed, and building
around a guessed provider (Calendly, Stripe, etc.) would be expensive to
reverse if the real answer turns out to be something else. The
`payment_provider` field records whichever tool is eventually wired up,
as free text, rather than a hardcoded choice.
"""

from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.models import Page


class BookingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"
    NOT_REQUIRED = "not_required", "Not required"


class Booking(models.Model):
    """
    One appointment request. `requested_start` is an ordinary
    timezone-aware DateTimeField — with USE_TZ on, Django stores it in
    UTC and converts to the site's local time zone for display, so no
    special handling is needed here as long as callers never pass in a
    naive datetime.

    `duration_minutes` is copied from the reading at booking time rather
    than looked up live, so that changing a reading's typical duration
    later doesn't silently rewrite the record of what was actually
    booked.
    """

    reading = models.ForeignKey(
        "readings.Reading",
        on_delete=models.PROTECT,
        related_name="bookings",
        help_text="Which reading this booking is for.",
    )
    client_name = models.CharField(max_length=120)
    client_email = models.EmailField()
    client_phone = models.CharField(max_length=30, blank=True)
    requested_start = models.DateTimeField(
        help_text="The date and time requested, in the site's local time zone."
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Snapshot of the reading's duration at the time of booking.",
    )
    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    payment_provider = models.CharField(
        max_length=30,
        blank=True,
        help_text="Which payment tool processed this booking (e.g. Stripe, "
        "PayPal). Left blank until the payment integration is confirmed and "
        "wired up.",
    )
    payment_reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="The payment processor's own reference/transaction ID, once "
        "payment has been taken.",
    )
    client_notes = models.TextField(
        blank=True,
        help_text="Anything the client added when requesting this booking.",
    )
    internal_notes = models.TextField(
        blank=True,
        help_text="Private notes for Leslie only — never shown to the client.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Booking"
        ordering = ["-requested_start"]

    def __str__(self):
        return f"{self.client_name} — {self.reading} ({self.requested_start:%Y-%m-%d %H:%M})"


class BookingPage(Page):
    """
    The Booking page (§4): the copy around the booking system. The
    calendar/availability widget itself is not CMS content — it's live,
    dynamic availability — so it is not a field here; booking-payments
    will render it into this page's template.
    """

    # templates/bookings/booking.html is the real file (FINDING 3).
    template = "bookings/booking.html"

    intro = models.TextField(
        blank=True,
        help_text="Shown above the booking calendar, e.g. how the process works.",
    )
    cancellation_policy = models.TextField(
        blank=True,
        help_text="Your cancellation/rescheduling policy, shown near the "
        "booking form.",
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
        """
        Nav-highlighting only (out of scope note: this is the one line
        booking-payments needs from this page model — the booking flow
        itself, availability and payment remain booking-payments' to
        build).
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "booking"
        return context

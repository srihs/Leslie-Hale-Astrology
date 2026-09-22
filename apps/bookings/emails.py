"""
Confirmation email to the client and a notification to Leslie, sent once
a booking is actually confirmed (see views.py's webhook handler, which
calls `send_booking_emails` via `transaction.on_commit` — never before
the confirming database write has actually landed).

The recipient for Leslie's copy is `ContactSettings.contact_email`
(apps/core/models.py), read fresh at send time — SCOPE §8 lists the
contact email as unconfirmed, so it is never stored or hardcoded here.
If it's still blank, Leslie's copy is skipped (logged, not raised): a
missing settings field must never be the reason a paid client's
confirmation email fails to send.

Copy is written in Leslie's voice (§2: warm, grounded, non-judgemental —
see PROJECT-SCOPE.md and the designer-toolkit:ux-writing skill). These
are plain-text bodies built in Python rather than template files, on
purpose: booking-payments does not touch templates/ (that directory, and
its HTML review, belongs to htmx-frontend) — see the final report for
where these could move if the team later prefers .txt template files.

Logging discipline (SCOPE correctness rule — never log full personal
details): every log line below carries only `booking.public_ref` and an
exception's type name, never an email body, address, or birth detail.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _local_when(booking) -> str:
    tz = ZoneInfo(booking.display_timezone) if booking.display_timezone else timezone.get_default_timezone()
    local = booking.start_at.astimezone(tz)
    label = local.tzname() or booking.display_timezone
    return f"{local.strftime('%A %-d %B %Y, %-I:%M %p')} ({label})"


def _contact_email() -> str:
    from apps.core.models import ContactSettings

    settings_obj = ContactSettings.load()
    return (settings_obj.contact_email or "").strip()


def send_booking_emails(booking_id: int) -> None:
    """Sends both emails for a newly-confirmed booking. Each is attempted
    independently — a failure on one never prevents the other, and neither
    failure changes the booking's already-committed confirmed state (see
    the module docstring: payment succeeding is the fact; email is only a
    notification of it)."""
    from apps.bookings.models import Booking

    booking = Booking.objects.select_related("reading").filter(pk=booking_id).first()
    if not booking:
        return

    client_sent = _send_client_confirmation(booking)
    _send_leslie_notification(booking)

    if client_sent:
        booking.confirmation_email_sent_at = timezone.now()
        booking.confirmation_email_error = ""
    booking.save(update_fields=["confirmation_email_sent_at", "confirmation_email_error", "updated_at"])


def _send_client_confirmation(booking) -> bool:
    when = _local_when(booking)
    policy = ""
    try:
        from apps.bookings.models import BookingPage

        page = BookingPage.objects.live().first()
        if page and page.cancellation_policy:
            policy = page.cancellation_policy.strip()
    except Exception:
        policy = ""

    lines = [
        f"Hello {booking.client_first_name},",
        "",
        f"Your {booking.reading.name} with Leslie is booked and paid for — thank you.",
        "",
        f"When:      {when}",
        "Format:    Online or by phone — Leslie will be in touch beforehand with how to connect",
        f"Reference: {booking.public_ref}",
        "",
    ]
    if policy:
        lines += [policy, ""]
    lines += [
        "If anything looks wrong about the time above, or your plans change, just "
        "reply to this email — happy to help sort it out.",
        "",
        "Looking forward to it,",
        "Leslie Hale Astrology",
    ]
    body = "\n".join(lines)

    try:
        send_mail(
            subject=f"Your reading is confirmed — {booking.reading.name}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[booking.client_email],
        )
        return True
    except Exception as exc:
        # The booking is already confirmed in the database and the client
        # has already paid — an email problem doesn't get to undo either
        # of those facts. Recorded on the booking itself so it's visible
        # in the admin and resendable (see the resend_booking_confirmation
        # management command), not silently lost.
        logger.error(
            "confirmation email to client failed booking_ref=%s error_type=%s",
            booking.public_ref,
            type(exc).__name__,
        )
        booking.confirmation_email_error = f"{type(exc).__name__} at {timezone.now().isoformat()}"
        return False


def _send_leslie_notification(booking) -> None:
    contact_email = _contact_email()
    if not contact_email:
        logger.warning(
            "ContactSettings.contact_email is blank — Leslie's booking "
            "notification was not sent booking_ref=%s",
            booking.public_ref,
        )
        return

    when = _local_when(booking)
    lines = [
        "New booking received and paid.",
        "",
        f"Client:      {booking.full_name} <{booking.client_email}>",
        f"Reading:     {booking.reading.name}",
        f"When:        {when}",
        f"Reference:   {booking.public_ref}",
        "",
        f"Birth date:  {booking.birth_date or 'not given'}",
        f"Birth time:  {('not known' if booking.birth_time_unknown else booking.birth_time) or 'not given'}",
        f"Birth place: {booking.birth_place or 'not given'}",
        f"Focus:       {booking.client_notes or '—'}",
    ]
    body = "\n".join(lines)

    try:
        send_mail(
            subject=f"New booking: {booking.reading.name} — {when}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[contact_email],
        )
    except Exception as exc:
        logger.error(
            "booking notification to Leslie failed booking_ref=%s error_type=%s",
            booking.public_ref,
            type(exc).__name__,
        )


def send_payment_needs_attention_email(booking_id: int) -> None:
    """
    The "paid, but the hold had already expired" edge case (see views.py's
    webhook handler) — an internal alert to Leslie only. Deliberately
    never sends the client a confirmation here: the slot this payment was
    for may since have gone to someone else, so telling the client
    "confirmed" would risk exactly the wrong-hour/double-booked failure
    the SCOPE correctness rules exist to prevent.
    """
    from apps.bookings.models import Booking

    booking = Booking.objects.select_related("reading").filter(pk=booking_id).first()
    if not booking:
        return

    contact_email = _contact_email()
    if not contact_email:
        logger.warning(
            "payment-needs-attention alert has nowhere to send — "
            "ContactSettings.contact_email is blank booking_ref=%s",
            booking.public_ref,
        )
        return

    when = _local_when(booking)
    body = "\n".join(
        [
            "A payment came in for a booking whose hold had already expired "
            "— the slot may have since gone to someone else. Nothing has "
            "been confirmed to the client automatically.",
            "",
            f"Client:      {booking.full_name} <{booking.client_email}>",
            f"Reading:     {booking.reading.name}",
            f"Was for:     {when}",
            f"Reference:   {booking.public_ref}",
            "",
            "Please check the calendar and either confirm this booking manually "
            "or arrange a refund/reschedule.",
        ]
    )
    try:
        send_mail(
            subject=f"Payment received for an expired hold — {booking.public_ref}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[contact_email],
        )
    except Exception as exc:
        logger.error(
            "needs-attention alert email failed booking_ref=%s error_type=%s",
            booking.public_ref,
            type(exc).__name__,
        )

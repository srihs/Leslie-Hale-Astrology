"""
Manual recovery for the "payment succeeded but the confirmation email
failed" case (see apps/bookings/emails.py). A confirmed booking with a
non-empty `confirmation_email_error` is visible to Leslie in the Wagtail
admin (Snippets → Bookings); SAS Creative runs this command to resend
once whatever caused the failure (a bad address, a mail server hiccup) is
fixed. Deliberately a management command rather than a public or
booking-page endpoint — resending a confirmation is a staff action.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.bookings.emails import send_booking_emails
from apps.bookings.models import Booking, BookingStatus


class Command(BaseCommand):
    help = "Resend the confirmation email for a confirmed booking, by its reference."

    def add_arguments(self, parser):
        parser.add_argument("public_ref", help="The booking's public_ref (shown in the admin).")

    def handle(self, *args, **options):
        try:
            booking = Booking.objects.get(public_ref=options["public_ref"])
        except (Booking.DoesNotExist, ValueError):
            raise CommandError(f"No booking found with reference {options['public_ref']!r}.")

        if booking.status != BookingStatus.CONFIRMED:
            raise CommandError(
                f"Booking {booking.public_ref} is '{booking.status}', not confirmed — refusing to "
                "send a confirmation email for a booking that isn't confirmed."
            )

        send_booking_emails(booking.pk)
        booking.refresh_from_db()
        if booking.confirmation_email_error:
            raise CommandError(f"Resend failed again: {booking.confirmation_email_error}")
        self.stdout.write(self.style.SUCCESS(f"Confirmation email resent for {booking.public_ref}."))

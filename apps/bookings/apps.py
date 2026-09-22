from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """
    Booking data shape only. The Booking page (editor-facing copy) and the
    Booking record (an appointment request) live here; availability,
    calendar UI, payment processing and confirmation emails are owned by
    the booking-payments agent and are deliberately not modelled yet.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"
    label = "bookings"
    verbose_name = "Bookings"

from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """
    Booking, availability and payment for the site (owned by the
    booking-payments agent — see apps/bookings/models.py, availability.py,
    views.py, emails.py and payments/ for the full flow).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"
    label = "bookings"
    verbose_name = "Bookings"

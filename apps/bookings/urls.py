"""
Non-page endpoint only (FINDING 1, reviews/2026-09-22-project-structure-
scaffold.md). BookingPage itself is a Wagtail page, served by the
wagtail_urls catch-all in config/urls.py, and does not get an entry here.

Included in config/urls.py under "forms/booking/" (not "booking/…", which
would collide with whatever URL Leslie's Booking page ends up at).

`checkout/` and `webhook/stripe/` exist now that a concrete payment
provider has been directed (see apps/bookings/payments/ for why the
provider name never appears in this file or in views.py's business
logic). `status/<ref>/` supports the payment-return polling fragment —
see views.booking_status.
"""

from django.urls import path

from apps.bookings import views

app_name = "bookings"

urlpatterns = [
    path("details/", views.save_details, name="save_details"),
    path("checkout/", views.start_checkout, name="checkout"),
    path("status/<uuid:ref>/", views.booking_status, name="booking_status"),
    path("webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
]

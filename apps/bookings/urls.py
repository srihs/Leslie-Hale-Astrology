"""
Non-page endpoint only (FINDING 1, reviews/2026-09-22-project-structure-
scaffold.md). BookingPage itself is a Wagtail page, served by the
wagtail_urls catch-all in config/urls.py, and does not get an entry here.

`bookings:checkout` (payment initiation) is deliberately NOT defined here
yet — the booking/payment tool is an unconfirmed §8 open item, and
booking-payments owns wiring it up once it's chosen. Building a checkout
endpoint now would mean guessing at that provider.

Included in config/urls.py under "forms/booking/" (not "booking/…", which
would collide with whatever URL Leslie's Booking page ends up at).
"""

from django.urls import path

from apps.bookings import views

app_name = "bookings"

urlpatterns = [
    path("details/", views.save_details, name="save_details"),
]

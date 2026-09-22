"""
Non-page endpoint for the Booking page's step-3 "your details" form
(FINDING 1, reviews/2026-09-22-project-structure-scaffold.md). BookingPage
itself is a Wagtail page, served by wagtail_urls, and has no entry in
apps/bookings/urls.py.

This deliberately stops short of creating a `Booking` row. The reading,
date and time chosen in steps 1-2 live in that step's own form (a GET
against BookingPage's own URL — see templates/bookings/partials/
_booking_panel_form.html), not posted alongside this one, and stitching
the two together — plus starting payment — needs availability/session
logic that does not exist yet (apps/bookings/models.py's own docstring:
booking-payments owns availability, slot selection and payment). What
this view can honestly do today is validate the posted details and stage
them in the session, so that work has something to read back once it
exists, without guessing at a payment/booking flow that isn't built.
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseNotAllowed
from django.shortcuts import render

SESSION_KEY = "booking_details"


def save_details(request):
    """Validate the client's personal/birth details (POST only)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    values = {
        "first_name": request.POST.get("first_name", "").strip(),
        "last_name": request.POST.get("last_name", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "dob": request.POST.get("dob", "").strip(),
        "tob": request.POST.get("tob", "").strip(),
        "pob": request.POST.get("pob", "").strip(),
        "focus": request.POST.get("focus", "").strip(),
    }
    errors = {}
    if not values["first_name"]:
        errors.setdefault("first_name", []).append("Please enter your first name.")
    if not values["last_name"]:
        errors.setdefault("last_name", []).append("Please enter your last name.")
    try:
        validate_email(values["email"])
    except ValidationError:
        errors.setdefault("email", []).append("Please enter a valid email.")
    if not values["dob"]:
        errors.setdefault("dob", []).append("Please enter your date of birth.")
    if not values["pob"]:
        errors.setdefault("pob", []).append("Please enter your place of birth.")

    submitted = False
    if not errors:
        request.session[SESSION_KEY] = values
        submitted = True

    return render(
        request,
        "bookings/partials/_details_form.html",
        {
            "details_values": values,
            "details_errors": errors,
            "details_submitted": submitted,
        },
    )

"""
`apps.bookings.views.save_details` — step 3's form, and `booking_status`,
the payment-return polling fragment. Both are non-page htmx endpoints
(apps/bookings/urls.py) and both must work identically whether or not
htmx is driving the request — the no-JS path is a real user path (a
client with JS disabled, or an interrupted page load) and this file
proves it, not just the htmx-enhanced one.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.bookings.models import BookingStatus
from apps.bookings.tests.factories import BookingFactory

pytestmark = pytest.mark.django_db

DETAILS_URL = "/forms/booking/details/"

VALID = {
    "first_name": "Jamie",
    "last_name": "Taylor",
    "email": "jamie@example.com",
    "dob": "1990-05-01",
    "tob": "10:00",
    "pob": "Auckland, New Zealand",
    "focus": "",
}


@pytest.mark.parametrize("use_htmx", [False, True])
def test_valid_details_are_staged_in_the_session(use_htmx):
    client = Client(headers={"HX-Request": "true"} if use_htmx else {})

    response = client.post(DETAILS_URL, data=VALID)

    assert response.status_code == 200
    assert client.session["booking_details"]["email"] == "jamie@example.com"
    assert b"saved" in response.content.lower()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_missing_required_fields_re_render_without_saving_or_500ing(use_htmx):
    client = Client(headers={"HX-Request": "true"} if use_htmx else {})
    incomplete = dict(VALID)
    incomplete["first_name"] = ""
    incomplete["email"] = "not-an-email"
    incomplete["pob"] = ""

    response = client.post(DETAILS_URL, data=incomplete)

    assert response.status_code == 200
    assert "booking_details" not in client.session


def test_get_is_not_allowed():
    client = Client()
    response = client.get(DETAILS_URL)
    assert response.status_code == 405


def test_details_missing_date_of_birth_is_rejected():
    """`dob` is required — a booking must have chartable birth data before
    it can reach checkout (booking.birth_date is used for chart prep)."""
    client = Client()
    values = dict(VALID)
    values["dob"] = ""

    response = client.post(DETAILS_URL, data=values)

    assert response.status_code == 200
    assert "booking_details" not in client.session


def test_email_validation_error_is_visible_in_the_rendered_form():
    """`_details_form.html` does render a visible error for `email`
    (`#em-err`) — confirms that field's error path end to end, view and
    template together."""
    client = Client()
    values = dict(VALID)
    values["email"] = "not-an-email"

    response = client.post(DETAILS_URL, data=values)

    assert "Please enter a valid email." in response.content.decode()


@pytest.mark.parametrize(
    "field, message",
    [
        ("first_name", "Please enter your first name."),
        ("last_name", "Please enter your last name."),
        ("pob", "Please enter your place of birth."),
        ("dob", "Please enter your date of birth."),
    ],
)
def test_non_email_validation_errors_are_not_shown_to_the_visitor(field, message):
    """FINDING: `save_details` (views.py) computes a per-field error
    message for every required field, but `_details_form.html` only has a
    visible `.err` element wired up for `email` (`#em-err`) — first_name,
    last_name, pob and dob get the form's `.invalid` red-outline styling
    with no visible explanation of what to fix. This test documents that
    gap; it is expected to fail until the template renders those messages
    too (or the fields get equivalent `aria-describedby` error text for
    screen reader users, who get nothing at all right now)."""
    client = Client()
    values = dict(VALID)
    values[field] = ""

    response = client.post(DETAILS_URL, data=values)

    assert message in response.content.decode()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_booking_status_fragment_renders_for_an_existing_booking(use_htmx):
    client = Client(headers={"HX-Request": "true"} if use_htmx else {})
    booking = BookingFactory(status=BookingStatus.CONFIRMED)

    response = client.get(f"/forms/booking/status/{booking.public_ref}/")

    assert response.status_code == 200


@pytest.mark.parametrize("use_htmx", [False, True])
def test_booking_status_fragment_handles_an_unknown_reference_without_500(use_htmx):
    import uuid

    client = Client(headers={"HX-Request": "true"} if use_htmx else {})

    response = client.get(f"/forms/booking/status/{uuid.uuid4()}/")

    assert response.status_code == 200

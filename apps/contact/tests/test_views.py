"""
`apps.contact.views` — the contact enquiry form and the newsletter
signup, both non-page htmx endpoints. Tested with and without the
`HX-Request` header throughout: the same view/template must serve a
working no-JS POST-and-reload flow, not just the htmx-enhanced one.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.contact.models import ContactSubmission, NewsletterSignup

pytestmark = pytest.mark.django_db

CONTACT_URL = "/forms/contact/submit/"
NEWSLETTER_URL = "/forms/contact/newsletter/"


def _client(use_htmx: bool) -> Client:
    return Client(headers={"HX-Request": "true"} if use_htmx else {})


@pytest.mark.parametrize("use_htmx", [False, True])
def test_valid_contact_submission_is_saved(use_htmx):
    client = _client(use_htmx)
    response = client.post(
        CONTACT_URL,
        data={"name": "Jamie Taylor", "email": "jamie@example.com", "subject": "Question", "message": "Hello there."},
    )

    assert response.status_code == 200
    submission = ContactSubmission.objects.get()
    assert submission.name == "Jamie Taylor"
    assert submission.email == "jamie@example.com"
    assert submission.message == "[Question] Hello there."
    assert submission.newsletter_opt_in is False
    assert b"sent" in response.content.lower() or b"thank" in response.content.lower()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_contact_submission_with_newsletter_opt_in_is_recorded(use_htmx):
    client = _client(use_htmx)
    client.post(
        CONTACT_URL,
        data={
            "name": "Jamie",
            "email": "jamie@example.com",
            "message": "Hi",
            "newsletter_opt_in": "on",
        },
    )

    assert ContactSubmission.objects.get().newsletter_opt_in is True


@pytest.mark.parametrize("use_htmx", [False, True])
def test_contact_submission_missing_message_re_renders_with_errors_not_500(use_htmx):
    client = _client(use_htmx)
    response = client.post(CONTACT_URL, data={"name": "Jamie", "email": "jamie@example.com", "message": ""})

    assert response.status_code == 200
    assert ContactSubmission.objects.count() == 0
    assert "Please write a short message." in response.content.decode()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_contact_submission_invalid_email_re_renders_with_errors_not_500(use_htmx):
    client = _client(use_htmx)
    response = client.post(
        CONTACT_URL, data={"name": "Jamie", "email": "not-an-email", "message": "Hello"}
    )

    assert response.status_code == 200
    assert ContactSubmission.objects.count() == 0
    assert "Please enter a valid email." in response.content.decode()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_missing_name_is_rejected_without_saving_or_500ing(use_htmx):
    client = _client(use_htmx)
    response = client.post(
        CONTACT_URL, data={"name": "", "email": "jamie@example.com", "message": "Hello"}
    )

    assert response.status_code == 200
    assert ContactSubmission.objects.count() == 0


@pytest.mark.parametrize("use_htmx", [False, True])
def test_missing_name_error_is_visible_to_the_visitor(use_htmx):
    """FINDING: `_contact_form.html` has a visible `.err` element wired up
    for `email` (`#e-err`) and `message` (`#m-err`) but not for `name` —
    the field gets the form's `.invalid` red-outline styling with no
    visible explanation of what to fix (same gap as
    apps/bookings/tests/test_details_form.py's non-email fields). This
    test documents it; expected to fail until the template adds a
    `#n-err` element for `name`."""
    client = _client(use_htmx)
    response = client.post(
        CONTACT_URL, data={"name": "", "email": "jamie@example.com", "message": "Hello"}
    )

    assert "Please enter your name." in response.content.decode()


def test_contact_get_is_not_allowed():
    response = Client().get(CONTACT_URL)
    assert response.status_code == 405


@pytest.mark.parametrize("use_htmx", [False, True])
def test_valid_newsletter_signup_is_saved(use_htmx):
    client = _client(use_htmx)
    response = client.post(NEWSLETTER_URL, data={"email": "reader@example.com", "next": "homepage footer"})

    assert response.status_code == 200
    signup = NewsletterSignup.objects.get()
    assert signup.email == "reader@example.com"
    assert signup.source == "homepage footer"


@pytest.mark.parametrize("use_htmx", [False, True])
def test_newsletter_signup_invalid_email_re_renders_with_errors_not_500(use_htmx):
    client = _client(use_htmx)
    response = client.post(NEWSLETTER_URL, data={"email": "not-an-email"})

    assert response.status_code == 200
    assert NewsletterSignup.objects.count() == 0
    assert "Please enter a valid email address." in response.content.decode()


@pytest.mark.parametrize("use_htmx", [False, True])
def test_duplicate_newsletter_signup_is_not_an_error(use_htmx):
    """`get_or_create` — signing up twice with the same address must not
    500 or create a second row; it's a courtesy no-op, not a validation
    failure the visitor needs to see."""
    NewsletterSignup.objects.create(email="reader@example.com", source="first time")
    client = _client(use_htmx)

    response = client.post(NEWSLETTER_URL, data={"email": "reader@example.com", "next": "second time"})

    assert response.status_code == 200
    assert NewsletterSignup.objects.count() == 1
    assert NewsletterSignup.objects.get().source == "first time", "the original source is not silently overwritten"


def test_newsletter_get_is_not_allowed():
    response = Client().get(NEWSLETTER_URL)
    assert response.status_code == 405

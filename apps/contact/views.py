"""
Non-page endpoints for the Contact page's two forms: the enquiry form
(saves a ContactSubmission) and the newsletter signup (saves a
NewsletterSignup). ContactPage itself is a Wagtail page, served by
wagtail_urls, and has no entry in apps/contact/urls.py — see FINDING 1,
reviews/2026-09-22-project-structure-scaffold.md.

Both views work with and without JavaScript: htmx swaps just the returned
fragment into the form's own wrapper; without htmx, the browser does a
full POST and reload, and the exact same fragment/context renders the
same success or error state either way (see the templates' own comments
for the no-JS path).
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseNotAllowed
from django.shortcuts import render

from apps.contact.models import ContactSubmission, NewsletterSignup


def submit_contact(request):
    """Validate and save a contact enquiry (POST only)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    values = {
        "name": request.POST.get("name", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "subject": request.POST.get("subject", "").strip(),
        "message": request.POST.get("message", "").strip(),
    }
    errors = {}
    if not values["name"]:
        errors.setdefault("name", []).append("Please enter your name.")
    try:
        validate_email(values["email"])
    except ValidationError:
        errors.setdefault("email", []).append("Please enter a valid email.")
    if not values["message"]:
        errors.setdefault("message", []).append("Please write a short message.")

    submitted = False
    if not errors:
        ContactSubmission.objects.create(
            name=values["name"],
            email=values["email"],
            message=(
                f"[{values['subject']}] {values['message']}"
                if values["subject"]
                else values["message"]
            ),
            newsletter_opt_in=bool(request.POST.get("newsletter_opt_in")),
        )
        submitted = True

    return render(
        request,
        "contact/partials/_contact_form.html",
        {
            "contact_values": values,
            "contact_errors": errors,
            "contact_submitted": submitted,
        },
    )


def newsletter_signup(request):
    """Validate and save a newsletter signup (POST only)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    email = request.POST.get("email", "").strip()
    source = request.POST.get("next", "").strip() or "unknown page"
    errors = {}
    try:
        validate_email(email)
    except ValidationError:
        errors.setdefault("email", []).append("Please enter a valid email address.")

    submitted = False
    if not errors:
        NewsletterSignup.objects.get_or_create(email=email, defaults={"source": source})
        submitted = True

    return render(
        request,
        "includes/_newsletter_form.html",
        {
            "newsletter_email": email,
            "newsletter_errors": errors,
            "newsletter_submitted": submitted,
        },
    )

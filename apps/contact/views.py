"""
Non-page endpoints for the Contact page's two forms: the enquiry form
(saves a ContactSubmission) and the newsletter signup (saves a
NewsletterSignup). ContactPage itself is a Wagtail page, served by
wagtail_urls, and has no entry in apps/contact/urls.py — see FINDING 1,
reviews/2026-09-22-project-structure-scaffold.md.

Both views work with and without JavaScript, and genuinely branch on
`request.htmx` (django_htmx) to do it — see FINDING 1, reviews/2026-09-22-
final-build-review.md: this file used to `render()` the bare partial for
*every* request, htmx or not, which meant a real no-JS POST (a full page
navigation, not an ajax swap) got back a fragment with no `<!DOCTYPE>`,
no `<head>`, no nav, no stylesheet — the templates' own "full page
reload on submit" comments were aspirational, not true. Now: an htmx
request still gets the bare fragment (that's correct — htmx swaps it into
the form's own wrapper); a plain request gets the *page* that form lives
on, rendered whole, with the same success/error context — see
`_render_contact_page`/`_render_referring_page` below.
"""

from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseNotAllowed
from django.shortcuts import render
from wagtail.models import Page

from apps.contact.models import ContactPage, ContactSubmission, NewsletterSignup


def _render_contact_page(request, extra_context, *, status=200):
    """
    No-JS fallback for the contact form: unlike the newsletter form (see
    `_render_referring_page` below), this form only ever lives on the
    Contact page, so there's no need to guess where the visitor posted
    from — go straight to it. Builds the same context ContactPage's own
    GET would (`page.get_context`), so the full page — nav, footer,
    stylesheet, the rest of the contact page's own content — renders
    exactly as it would on a normal visit, with the submitted form's
    values/errors laid over the top.
    """
    page = ContactPage.objects.live().first()
    if not page:
        # No ContactPage published yet — an unusual/edge state this fix
        # isn't responsible for; fall back to the bare fragment rather
        # than crash.
        return render(request, "contact/partials/_contact_form.html", extra_context, status=status)
    context = page.get_context(request)
    context.update(extra_context)
    return render(request, page.get_template(request), context, status=status)


def _render_referring_page(request, hint_path, partial_template, extra_context, *, status=200):
    """
    No-JS fallback for the newsletter form, which — unlike the contact
    form — is included on several different pages (home, blog index,
    contact: see includes/_newsletter_form.html's own comment). Resolves
    whichever page the visitor actually posted from, from `hint_path`
    (the form's own `next` hidden field, which in real use holds
    `request.path` of the page it was rendered on — see
    includes/_newsletter_form.html) or, failing that, the HTTP Referer
    header — both of which a genuine no-JS browser navigation supplies —
    so a no-JS visitor lands back on the *actual* page they were on, with
    this form's own success/error state rendered in place.

    Deliberately does not guess further than that (e.g. falling back to
    the site's home page) if neither resolves: rendering the *wrong* page
    would show a visitor their submission "succeeded" on a page that
    doesn't even contain the form they filled in — worse than the bare
    fragment this falls back to instead, which is at least accurate about
    what happened, if not fully chrome-dressed. In practice this only
    happens when a request carries neither a real referring path nor a
    Referer header, which a genuine no-JS browser POST never does.
    """
    candidates = [p for p in (hint_path, urlparse(request.META.get("HTTP_REFERER", "")).path) if p]
    route_result = None
    for path in candidates:
        try:
            route_result = Page.route_for_request(request, path)
        except Exception:
            route_result = None
        if route_result:
            break
    if not route_result:
        return render(request, partial_template, extra_context, status=status)
    page, args, kwargs = route_result
    context = page.get_context(request, *args, **kwargs)
    context.update(extra_context)
    return render(request, page.get_template(request, *args, **kwargs), context, status=status)


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

    context = {
        "contact_values": values,
        "contact_errors": errors,
        "contact_submitted": submitted,
    }
    if getattr(request, "htmx", False):
        return render(request, "contact/partials/_contact_form.html", context)
    return _render_contact_page(request, context)


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

    context = {
        "newsletter_email": email,
        "newsletter_errors": errors,
        "newsletter_submitted": submitted,
    }
    if getattr(request, "htmx", False):
        return render(request, "includes/_newsletter_form.html", context)
    # The raw posted `next` value, not `source` above — that's already
    # been defaulted to the human-readable "unknown page" label for
    # NewsletterSignup.source, which is never a real page path.
    return _render_referring_page(
        request, request.POST.get("next", "").strip(), "includes/_newsletter_form.html", context
    )

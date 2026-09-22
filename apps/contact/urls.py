"""
Non-page endpoints only (FINDING 1, reviews/2026-09-22-project-structure-
scaffold.md). ContactPage itself is a Wagtail page, served by the
wagtail_urls catch-all in config/urls.py, and does not get an entry here —
it does not need a reversible Django URL name; templates address it with
{% pageurl %} instead.

Included in config/urls.py under "forms/contact/" (not "contact/…", which
would collide with whatever URL Leslie's Contact page, and any future
child pages under it, end up at).
"""

from django.urls import path

from apps.contact import views

app_name = "contact"

urlpatterns = [
    path("submit/", views.submit_contact, name="submit"),
    path("newsletter/", views.newsletter_signup, name="newsletter_signup"),
]

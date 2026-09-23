"""
Website text screen (task item 7): one flat form collapsing the editable
copy from Home, About and Contact into plain labelled fields — no page
tree, no StreamField UI (see apps/backoffice/content.py for exactly how
each field maps onto the underlying StreamField/StructBlock data these
pages actually store).

Fields covered, and deliberately NOT covered — the literal list the task
brief gave for this screen:

Covered: hero headline/intro (HomePage.hero), her story
(AboutPage.body), pull quote (AboutPage.pull_quote), the three promises
(AboutPage.three_promises), the Contact page intro (ContactPage.intro),
and every ContactSettings field.

NOT covered, and still only editable via Wagtail admin (superuser-only —
see apps/backoffice/middleware.py) until a future iteration of this
screen is explicitly scoped to include them: the hero's eyebrow and both
its buttons (carried over unchanged by
content.py:hero_stream_with_text — editing a button here risks silently
breaking a page link), AboutPage.intro, AboutPage.training_background,
and every homepage section besides the hero (services/testimonials/
latest_blog/final_cta — built from Reading/Testimonial snippets and
StreamField structure this screen's field list did not name). See this
task's final report for the same list with the reasoning spelled out.

Saves go straight to each page's `.save()` — not through Wagtail's
revision/publish workflow. That's a deliberate simplification consistent
with "no StreamField UI, no page tree": Leslie never sees a draft/preview
state for this copy, it is simply live the moment she saves, the same as
every other field on this screen.
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.backoffice.content import (
    body_from_story_text,
    hero_stream_with_text,
    hero_value,
    story_text_from_body,
    three_promises_stream,
    three_promises_value,
)
from apps.backoffice.forms import WebsiteTextForm
from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.contact.models import ContactPage
from apps.core.models import AboutPage, ContactSettings
from apps.home.models import HomePage

REQUIRED_PAGES = ("home", "about", "contact")


def _promise_or_blank(promises, index: int) -> dict:
    if promises and len(promises) > index:
        return promises[index]["value"]
    return {"title": "", "description": ""}


class WebsiteTextView(BackofficeAccessRequiredMixin, View):
    template_name = "backoffice/website_text.html"

    def _load(self) -> dict:
        return {
            "home": HomePage.objects.first(),
            "about": AboutPage.objects.first(),
            "contact": ContactPage.objects.first(),
            "settings": ContactSettings.load(),
        }

    def _missing(self, pages: dict) -> list[str]:
        return [name for name in REQUIRED_PAGES if pages[name] is None]

    def _initial(self, pages: dict) -> dict:
        home, about, contact, settings_obj = (
            pages["home"],
            pages["about"],
            pages["contact"],
            pages["settings"],
        )
        hero = hero_value(home.hero) if home else {}
        promises_section = three_promises_value(about.three_promises) if about else None
        promises = promises_section["promises"] if promises_section else []

        data = {
            "hero_headline": hero.get("headline", ""),
            "hero_subheading": hero.get("subheading", ""),
            "story_text": story_text_from_body(about.body) if about else "",
            "pull_quote": about.pull_quote if about else "",
            "promises_eyebrow": promises_section["eyebrow"] if promises_section else "",
            "promises_heading": promises_section["heading"] if promises_section else "",
            "contact_intro": contact.intro if contact else "",
            "contact_email": settings_obj.contact_email,
            "contact_phone": settings_obj.contact_phone,
            "studio_address": settings_obj.studio_address,
            "instagram_url": settings_obj.instagram_url,
            "facebook_url": settings_obj.facebook_url,
            "years_experience_label": settings_obj.years_experience_label,
        }
        for i in range(3):
            promise = _promise_or_blank(promises, i)
            data[f"promise_{i + 1}_title"] = promise["title"]
            data[f"promise_{i + 1}_description"] = promise["description"]
        return data

    def get(self, request):
        pages = self._load()
        missing = self._missing(pages)
        if missing:
            messages.error(
                request,
                "Some pages haven't been set up yet (" + ", ".join(missing) + ") — ask "
                "your developer to create them before editing this text.",
            )
        form = WebsiteTextForm(initial=self._initial(pages))
        return render(request, self.template_name, {"form": form, "missing_pages": missing})

    def post(self, request):
        pages = self._load()
        missing = self._missing(pages)
        if missing:
            messages.error(
                request, "Can't save — some pages haven't been set up yet (" + ", ".join(missing) + ")."
            )
            return redirect(reverse("backoffice:website_text"))

        form = WebsiteTextForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "missing_pages": []})

        data = form.cleaned_data
        home, about, contact, settings_obj = (
            pages["home"],
            pages["about"],
            pages["contact"],
            pages["settings"],
        )

        home.hero = hero_stream_with_text(
            home.hero, headline=data["hero_headline"], subheading=data["hero_subheading"]
        )
        home.save()

        about.body = body_from_story_text(about.body, data["story_text"])
        about.pull_quote = data["pull_quote"]
        about.three_promises = three_promises_stream(
            eyebrow=data["promises_eyebrow"],
            heading=data["promises_heading"],
            promises=[
                (data["promise_1_title"], data["promise_1_description"]),
                (data["promise_2_title"], data["promise_2_description"]),
                (data["promise_3_title"], data["promise_3_description"]),
            ],
        )
        about.save()

        contact.intro = data["contact_intro"]
        contact.save()

        settings_obj.contact_email = data["contact_email"]
        settings_obj.contact_phone = data["contact_phone"]
        settings_obj.studio_address = data["studio_address"]
        settings_obj.instagram_url = data["instagram_url"]
        settings_obj.facebook_url = data["facebook_url"]
        settings_obj.years_experience_label = data["years_experience_label"]
        settings_obj.save()

        messages.success(request, "Website text saved.")
        return redirect(reverse("backoffice:website_text"))

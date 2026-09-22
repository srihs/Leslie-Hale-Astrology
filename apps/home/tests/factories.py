"""
Builds a real, valid `home.HomePage` — the one page every other page type
in this site requires as its parent (see each page model's own
`parent_page_types`, all pointing at `home.HomePage`). §5's Wagtail page
tests need this to exist and actually render before anything can be hung
under it, so this is shared test infrastructure, not just home's own.

Every StreamField section below is filled with the minimum content its own
block definition requires (see apps/home/blocks.py) — not empty, and not
guessed-at business copy: each value is either an obviously-fake test
string or a real linked object (Image, Reading) created for the test.
Wagtail's `min_num=1, max_num=1` on every one of HomePage's six sections
(see apps/home/models.py's own docstring on why) means a HomePage built
with any section missing is not a HomePage this site could actually have —
a test asserting behaviour against one would not be testing anything real.
"""

from __future__ import annotations

from wagtail.models import Page, Site

from apps.readings.tests.factories import ReadingFactory
from tests.images import make_test_image


def _hero_value():
    return {
        "eyebrow": "PERSONAL ASTROLOGY READINGS",
        "headline": "Find clarity in the stars",
        "subheading": "Warm, grounded readings for whatever you're facing.",
        "primary_button": {"text": "Book a Reading", "page": None, "url": ""},
        "secondary_button": {"text": "", "page": None, "url": ""},
    }


def _services_value(reading):
    return {
        "heading": "Services",
        "subline": "A reading for wherever you are.",
        "featured_readings": [reading],
        "image": make_test_image("Services image"),
        "image_caption": "",
        "image_link": {"text": "", "page": None, "url": ""},
    }


def _about_value():
    return {
        "portrait": make_test_image("About portrait"),
        "story": "<p>Leslie has been reading charts for years.</p>",
        "pull_quote": "Astrology helps in day-to-day life.",
        "link_text": "Read my story",
        "link_page": None,
    }


def _testimonials_value():
    return {"heading": "What clients say", "testimonials": []}


def _latest_blog_value():
    return {"heading": "From the Blog", "subline": "", "view_all_link_text": "View all posts"}


def _final_cta_value():
    return {
        "headline": "Ready to find out more?",
        "subline": "",
        "button": {"text": "Book a Reading", "page": None, "url": ""},
    }


def make_home_page(**overrides) -> "HomePage":  # noqa: F821 - imported lazily below
    from apps.home.models import HomePage

    root = Page.objects.get(depth=1)

    reading = overrides.pop("reading", None) or ReadingFactory()

    field_defaults = dict(
        title="Home",
        slug=overrides.pop("slug", "home-test"),
        hero=[("hero", _hero_value())],
        services=[("services", _services_value(reading))],
        about=[("about", _about_value())],
        testimonials=[("testimonials", _testimonials_value())],
        latest_blog=[("latest_blog", _latest_blog_value())],
        final_cta=[("final_cta", _final_cta_value())],
    )
    field_defaults.update(overrides)

    home_page = HomePage(**field_defaults)
    root.add_child(instance=home_page)

    site = Site.objects.first()
    if site is not None:
        site.root_page = home_page
        site.is_default_site = True
        site.save()
    else:
        Site.objects.create(hostname="testserver", root_page=home_page, is_default_site=True)

    return home_page

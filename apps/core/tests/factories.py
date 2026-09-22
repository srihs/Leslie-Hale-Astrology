from __future__ import annotations

import factory

from apps.core.models import Testimonial


class TestimonialFactory(factory.django.DjangoModelFactory):
    __test__ = False  # not a pytest test class despite the name prefix

    class Meta:
        model = Testimonial

    quote = "Leslie's reading gave me real clarity."
    author_name = "Sarah M."
    author_descriptor = "Natal Chart Reading"
    is_featured = True


def make_about_page(home_page, **overrides):
    """A real, valid `core.AboutPage` — `three_promises` (exactly three)
    and `training_background` are min_num=1/max_num=1 required
    StreamFields (see apps/core/models.py), so a page built without them
    is not one this site could actually have."""
    from apps.core.models import AboutPage

    field_defaults = dict(
        title="About Leslie",
        slug=overrides.pop("slug", "about-test"),
        intro="A short introduction.",
        body=[("text", "<p>My story.</p>")],
        pull_quote="Astrology helps in day-to-day life.",
        three_promises=[
            (
                "section",
                {
                    "eyebrow": "What you can expect",
                    "heading": "Three promises",
                    "promises": [
                        {"title": "No judgement", "description": "A warm, welcoming space."},
                        {"title": "Practical answers", "description": "Grounded, everyday guidance."},
                        {"title": "Your pace", "description": "We go as deep as you want to."},
                    ],
                },
            )
        ],
        training_background=[
            (
                "section",
                {
                    "eyebrow": "Training & background",
                    "heading": "Where the knowledge comes from",
                    "body": "<p>Years of study and practice.</p>",
                    "link": {"text": "", "page": None, "url": ""},
                },
            )
        ],
        cta=[],
    )
    field_defaults.update(overrides)
    page = AboutPage(**field_defaults)
    home_page.add_child(instance=page)
    return page


def set_contact_email(email: str = "leslie@example.com"):
    """`apps.bookings.emails` reads `ContactSettings.contact_email` live at
    send time (see that module's own docstring on why) — tests for the
    notification-to-Leslie half of a confirmation email need a non-blank
    value here, since a blank one is a deliberate no-op, not a bug."""
    from apps.core.models import ContactSettings

    settings_obj = ContactSettings.load()
    settings_obj.contact_email = email
    settings_obj.save()
    return settings_obj

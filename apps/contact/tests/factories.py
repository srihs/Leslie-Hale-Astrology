"""factory_boy-style page builder for apps.contact — mirrors the
`make_*_page` helpers in apps.core.tests.factories / apps.home.tests.factories
(see those modules' own docstrings for why a real, live page beats an
empty stand-in)."""

from __future__ import annotations


def make_contact_page(**overrides):
    """
    A real, live `contact.ContactPage` under a real HomePage.

    Needed by any test asserting the non-htmx branch of `submit_contact`
    actually renders the *owning page* (`apps.contact.views.
    _render_contact_page`) rather than its "no ContactPage published"
    fallback — without a live ContactPage in the test database,
    `ContactPage.objects.live().first()` is `None` and the view silently
    takes the fallback path instead of the one FINDING 1 (reviews/
    2026-09-22-final-build-review.md) fixed, which would make a shape
    assertion pass for the wrong reason.
    """
    from apps.contact.models import ContactPage
    from apps.home.tests.factories import make_home_page

    home = overrides.pop("home", None) or make_home_page()
    field_defaults = dict(title="Contact", slug=overrides.pop("slug", "contact-test"))
    field_defaults.update(overrides)
    page = ContactPage(**field_defaults)
    home.add_child(instance=page)
    return page

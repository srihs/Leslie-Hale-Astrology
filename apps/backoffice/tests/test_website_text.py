"""
Website text screen (apps/backoffice/views/website_text.py) — no coverage
existed before this test module, which is exactly how FINDING 1 (a 500 on
every GET, caused by apps/backoffice/content.py:_promise_or_blank indexing
a StructValue as if it were still the raw `{"type", "value"}` StreamField
dict) shipped unnoticed. These tests exercise the view the way a browser
actually would — through `Client.get`/`Client.post` against the real URL,
using WebsiteTextForm and the real page/settings models — rather than
calling `apps.backoffice.content` functions in isolation, because the bug
this guards against was only reachable through the view's actual data
flow (`three_promises_value(about.three_promises)["promises"]`, a
Wagtail-resolved `ListValue`, not a raw dict).

A second, undiscovered bug surfaced while building this coverage: writing
a fresh `promises` ListBlock value without an explicit "id" per item
(`content.py:three_promises_stream`, as originally written) saved
successfully and loaded without error, but every promise's `title`/
`description` silently read back as `None` — confirmed against a real
save/reload cycle in this project's dev database before being fixed. Top-
level StreamField blocks (hero, body/text, body/image) don't have this
problem — Wagtail assigns a missing top-level block "id" automatically —
so `test_promises_round_trip_preserves_content` below exists specifically
to catch a regression of the nested-ListBlock case, not just the
`_promise_or_blank` KeyError.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.backoffice.tests.factories import make_backoffice_user
from apps.contact.tests.factories import make_contact_page
from apps.core.models import ContactSettings
from apps.core.tests.factories import make_about_page
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db


def _make_pages():
    home = make_home_page()
    about = make_about_page(home)
    contact = make_contact_page(home=home)
    return home, about, contact


def _valid_post_data(**overrides):
    data = {
        "hero_headline": "New headline for the homepage",
        "hero_subheading": "New one-line subheading",
        "story_text": "First paragraph of the story.\n\nSecond paragraph.",
        "pull_quote": "A new pull quote.",
        "promises_eyebrow": "What to expect",
        "promises_heading": "Three promises",
        "promise_1_title": "No judgement",
        "promise_1_description": "A warm, welcoming space.",
        "promise_2_title": "Plain language",
        "promise_2_description": "No jargon, no mystery.",
        "promise_3_title": "Clear next steps",
        "promise_3_description": "You leave knowing what to do.",
        "contact_intro": "Get in touch below.",
        "contact_email": "leslie@example.com",
        "contact_phone": "021 000 0000",
        "studio_address": "1 Example Street",
        "instagram_url": "https://instagram.com/example",
        "facebook_url": "https://facebook.com/example",
        "years_experience_label": "15+ years",
    }
    data.update(overrides)
    return data


class TestWebsiteTextGet:
    def test_get_returns_200_not_500(self, client):
        """FINDING 1 regression test: loading the screen against a real
        AboutPage with three real promises must not raise. Before the
        fix, `_promise_or_blank` raised `KeyError('value')` inside
        `WebsiteTextView.get()`, before any template rendered."""
        _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:website_text"))

        assert response.status_code == 200

    def test_get_prefills_existing_promises(self, client):
        home, about, contact = _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:website_text"))

        form = response.context["form"]
        assert form.initial["promise_1_title"] == "No judgement"
        assert form.initial["promise_2_title"] == "Practical answers"
        assert form.initial["promise_3_title"] == "Your pace"
        assert form.initial["hero_headline"] == home.hero[0].value["headline"]
        assert form.initial["pull_quote"] == "Astrology helps in day-to-day life."
        assert form.initial["contact_intro"] == contact.intro


class TestWebsiteTextRoundTrip:
    """Save through the real view, then reload every affected model from
    the database (not from the in-memory instance the view already
    mutated) and confirm the values that come back are exactly what was
    submitted — a form that renders but corrupts content on save is worse
    than one that 500s (task brief)."""

    def test_hero_round_trips_and_preserves_buttons(self, client):
        home, about, contact = _make_pages()
        original_primary_button = dict(home.hero[0].value["primary_button"])
        user = make_backoffice_user()
        client.force_login(user)

        response = client.post(
            reverse("backoffice:website_text"), data=_valid_post_data(), follow=True
        )
        assert response.status_code == 200

        home.refresh_from_db()
        hero = home.hero[0].value
        assert hero["headline"] == "New headline for the homepage"
        assert hero["subheading"] == "New one-line subheading"
        # The hero's buttons are explicitly NOT covered by this screen
        # (see content.py:hero_stream_with_text) — they must survive a
        # save completely unchanged.
        assert dict(hero["primary_button"]) == original_primary_button

    def test_story_and_pull_quote_round_trip(self, client):
        home, about, contact = _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        client.post(reverse("backoffice:website_text"), data=_valid_post_data(), follow=True)

        about.refresh_from_db()
        text_blocks = [str(block.value) for block in about.body if block.block_type == "text"]
        assert len(text_blocks) == 1
        assert "First paragraph of the story." in text_blocks[0]
        assert "Second paragraph." in text_blocks[0]
        assert about.pull_quote == "A new pull quote."

    def test_promises_round_trip_preserves_content(self, client):
        """The specific regression this task's brief calls out: saving
        new promise text must read back as that text, not
        `None`/`None`, from a database reload (not the same Python
        object the view already had in memory)."""
        home, about, contact = _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        client.post(reverse("backoffice:website_text"), data=_valid_post_data(), follow=True)

        about.refresh_from_db()
        section = about.three_promises[0].value
        assert section["eyebrow"] == "What to expect"
        assert section["heading"] == "Three promises"
        promises = section["promises"]
        assert len(promises) == 3
        assert promises[0]["title"] == "No judgement"
        assert promises[0]["description"] == "A warm, welcoming space."
        assert promises[1]["title"] == "Plain language"
        assert promises[1]["description"] == "No jargon, no mystery."
        assert promises[2]["title"] == "Clear next steps"
        assert promises[2]["description"] == "You leave knowing what to do."

    def test_promises_round_trip_twice_in_a_row(self, client):
        """Each save must generate fresh ids for the rebuilt ListBlock
        items (content.py:three_promises_stream) — saving a second time
        must not collide with or reuse ids from the first save in a way
        that breaks the read-back."""
        home, about, contact = _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        client.post(reverse("backoffice:website_text"), data=_valid_post_data(), follow=True)
        client.post(
            reverse("backoffice:website_text"),
            data=_valid_post_data(promise_1_title="Updated title"),
            follow=True,
        )

        about.refresh_from_db()
        promises = about.three_promises[0].value["promises"]
        assert promises[0]["title"] == "Updated title"
        assert promises[1]["title"] == "Plain language"

    def test_contact_page_and_settings_round_trip(self, client):
        home, about, contact = _make_pages()
        user = make_backoffice_user()
        client.force_login(user)

        client.post(reverse("backoffice:website_text"), data=_valid_post_data(), follow=True)

        contact.refresh_from_db()
        settings_obj = ContactSettings.load()
        assert contact.intro == "Get in touch below."
        assert settings_obj.contact_email == "leslie@example.com"
        assert settings_obj.contact_phone == "021 000 0000"
        assert settings_obj.studio_address == "1 Example Street"
        assert settings_obj.instagram_url == "https://instagram.com/example"
        assert settings_obj.facebook_url == "https://facebook.com/example"
        assert settings_obj.years_experience_label == "15+ years"

    def test_missing_pages_blocks_save(self, client):
        """No AboutPage/HomePage/ContactPage at all — the view must
        refuse to save rather than raise `AttributeError` on `None`."""
        user = make_backoffice_user()
        client.force_login(user)

        response = client.post(
            reverse("backoffice:website_text"), data=_valid_post_data(), follow=True
        )

        assert response.status_code == 200
        assert not ContactSettings.load().contact_email

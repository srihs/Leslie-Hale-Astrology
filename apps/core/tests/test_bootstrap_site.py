"""
`manage.py bootstrap_site` — builds the initial page tree (PROJECT-SCOPE.md
§4: HomePage plus About, Readings, Booking, Blog and Contact) on a database
that doesn't have it yet, since nothing else in this project does. See
`apps.core.site_bootstrap` for what it does and why.

A bare pytest-django test database (nothing beyond migrations) is exactly
the "completely empty" case this command exists for: Wagtail's own
`wagtailcore.0002_initial_data` migration always leaves a "Root" page, its
"Welcome to your new Wagtail site!" child and one default Site row pointed
at it — the same starting state a freshly deployed database has, and the
one that was silently serving that default page instead of the real site.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client
from wagtail.models import Page, Site

from apps.blog.models import BlogIndexPage
from apps.bookings.models import BookingPage
from apps.contact.models import ContactPage
from apps.core.models import AboutPage
from apps.home.models import HomePage
from apps.home.tests.factories import make_home_page
from apps.readings.models import ReadingsIndexPage

pytestmark = pytest.mark.django_db

CHILD_PAGE_MODELS_AND_PATHS = (
    (AboutPage, "/about/"),
    (ReadingsIndexPage, "/readings/"),
    (BookingPage, "/booking/"),
    (BlogIndexPage, "/blog/"),
    (ContactPage, "/contact/"),
)
ALL_PAGE_MODELS = (HomePage,) + tuple(model for model, _path in CHILD_PAGE_MODELS_AND_PATHS)


def _run(*args) -> str:
    out = StringIO()
    call_command("bootstrap_site", *args, stdout=out)
    return out.getvalue()


def test_dry_run_on_empty_database_creates_nothing():
    output = _run()

    for model in ALL_PAGE_MODELS:
        assert not model.objects.exists()
    # Wagtail's own default page/Site are exactly as migrations left them.
    assert Page.objects.filter(title="Welcome to your new Wagtail site!").exists()

    assert "Created:  6" in output
    assert "Existing: 0" in output
    assert "would create" in output
    assert "This was a dry run" in output


def test_write_on_empty_database_builds_the_whole_tree_and_serves_every_page():
    output = _run("--write")
    assert "Created:  6" in output

    home = HomePage.objects.get()
    assert home.get_parent().depth == 1  # a direct child of the true tree root
    assert home.live is True

    for model, path in CHILD_PAGE_MODELS_AND_PATHS:
        page = model.objects.get()
        assert page.get_parent().pk == home.pk
        assert page.live is True
        assert page.url == path

    site = Site.objects.get(is_default_site=True)
    assert site.root_page_id == home.pk

    # Wagtail's own placeholder is gone, not left live and orphaned in the tree.
    assert not Page.objects.filter(title="Welcome to your new Wagtail site!").exists()

    client = Client()
    for path in ("/", "/about/", "/readings/", "/booking/", "/blog/", "/contact/"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_second_write_run_is_a_no_op():
    _run("--write")
    pks_before = {
        model: set(model.objects.values_list("pk", flat=True)) for model in ALL_PAGE_MODELS
    }
    site_before = Site.objects.get(is_default_site=True)

    output = _run("--write")

    assert "Created:  0" in output
    assert "Updated:  0" in output
    assert "Skipped:  0" in output
    for model in ALL_PAGE_MODELS:
        assert set(model.objects.values_list("pk", flat=True)) == pks_before[model]
    site_after = Site.objects.get(is_default_site=True)
    assert site_after.root_page_id == site_before.root_page_id


def test_second_dry_run_reports_everything_as_existing():
    _run("--write")

    output = _run()

    assert "Created:  0" in output
    for model in ALL_PAGE_MODELS:
        assert model.objects.count() == 1


def test_partially_populated_database_only_creates_what_is_missing():
    _run("--write")
    AboutPage.objects.get().delete()

    output = _run("--write")

    assert "Created:  1" in output
    assert "AboutPage (About)" in output
    new_about = AboutPage.objects.get()
    assert new_about.get_parent().pk == HomePage.objects.get().pk
    # everything else from the first run is untouched
    for model, _path in CHILD_PAGE_MODELS_AND_PATHS[1:]:
        assert model.objects.count() == 1


def test_existing_human_edited_home_page_is_never_touched_or_duplicated():
    home = make_home_page(title="Leslie's Actual Homepage")
    original_headline = home.hero[0].value["headline"]
    original_revision_count = home.revisions.count()

    output = _run("--write")

    home.refresh_from_db()
    assert home.title == "Leslie's Actual Homepage"
    assert home.hero[0].value["headline"] == original_headline
    assert home.revisions.count() == original_revision_count
    assert HomePage.objects.count() == 1
    assert "HomePage (site root)" in output

    # the missing §4 children are still filled in under the real HomePage
    for model, _path in CHILD_PAGE_MODELS_AND_PATHS:
        page = model.objects.get()
        assert page.get_parent().pk == home.pk


def test_default_wagtail_page_with_children_is_left_alone():
    """
    Belt-and-braces: every page type this command creates restricts its
    own `parent_page_types` to `home.HomePage` (see each model), so the
    admin can never actually put a child under Wagtail's default page —
    but this command doesn't trust the admin's own guardrails against
    itself. A default page that somehow has children is left in place
    rather than deleted out from under them.
    """
    default_page = Page.objects.get(title="Welcome to your new Wagtail site!")
    default_page.add_child(
        instance=Page(title="Unexpected child", slug="unexpected-child", live=True)
    )

    output = _run("--write")

    assert Page.objects.filter(pk=default_page.pk).exists()
    assert "left in place" in output

"""
pytest-django entry point for the whole suite.

DJANGO_SETTINGS_MODULE is set in pyproject.toml
([tool.pytest.ini_options]) to config.settings.dev; DATABASE_URL and every
other required environment variable come from the process environment —
this suite is run inside the docker-infra web container (or anywhere else
that already has the same .env loaded), never against a fabricated
in-process settings module.

No network calls happen anywhere in this suite: Stripe is mocked at
`apps.bookings.views.get_provider` (see apps/bookings/tests/payments.py)
and email is exercised through Django's own console backend (dev
settings) or asserted via a call-count spy — nothing here reaches the
network. See apps/*/tests/factories.py for the model factories, and
apps/home/tests/factories.py / apps/core/tests/factories.py for the
StreamField-heavy Wagtail page builders every page-rendering test in
tests/test_page_rendering.py depends on.
"""

from __future__ import annotations

import re

# Response-shape assertions for the no-JS/htmx branch pair every public
# form POST must keep (FINDING 1, reviews/2026-09-22-final-build-review.md,
# fixed in e96cbf2 — apps.contact.views.submit_contact/newsletter_signup
# and apps.bookings.views.save_details/_checkout_error all render a bare
# partial to an htmx request and the whole owning page to everything else).
# Shared here because apps/contact/tests/test_views.py and
# apps/bookings/tests/test_details_form.py + test_checkout.py all need the
# same two checks and must not quietly drift apart on what "a full page"
# or "a bare fragment" means.
#
# Before this pair existed, every one of the tests using them asserted
# only `status_code == 200` and a text substring — which is exactly what
# 110/110 passing looked like while the no-JS branch of all four endpoints
# returned the bare fragment unconditionally. These check structure that
# only the fixed code produces: a doctype, the primary nav landmark, the
# skip link and the stylesheet for the full-page branch; their absence —
# and the fragment's own root element — for the htmx branch.
#
# The stylesheet's filename is not a literal "main.css": STORAGES
# ["staticfiles"] (config/settings/base.py) is Whitenoise's
# CompressedManifestStaticFilesStorage, so the rendered href carries a
# content hash (e.g. "main.d686fcc0d857.css") that changes on every
# `collectstatic`. Matched by pattern, not a literal string, so this
# doesn't go stale — and still fails if the stylesheet is dropped
# entirely, which is the actual regression this guards against.
MAIN_STYLESHEET_RE = re.compile(r'<link rel="stylesheet" href="/static/css/main(?:\.[0-9a-f]+)?\.css">')


def assert_full_page_response(response, *, fragment_id):
    """
    The non-htmx branch of a form POST must render the whole owning page
    — not the bare fragment on its own — with the posted form/fragment
    still present inside it. Checked against real chrome from
    templates/base.html, not an invented marker, so this only passes for
    an actual full-document render:

    - `<!doctype html>` — the document itself, from base.html:1
    - `<nav aria-label="Primary">` — the primary nav landmark,
      templates/includes/_nav.html:34, a no-JS visitor's way back into
      the site
    - the skip link, base.html:58
    - the site stylesheet, base.html:54

    Any one of these missing means the response is not actually a full
    page — which is exactly what shipped, silently, before e96cbf2.
    """
    body = response.content.decode()
    assert body.lstrip().lower().startswith("<!doctype html>"), (
        "expected a full HTML document (starting '<!doctype html>') for the "
        f"non-htmx response; got a body starting {body[:120]!r} instead — "
        "this looks like the bare fragment was returned on its own again "
        "(FINDING 1, reviews/2026-09-22-final-build-review.md)"
    )
    assert '<nav aria-label="Primary">' in body, (
        "non-htmx response has no primary nav landmark "
        '(<nav aria-label="Primary">, templates/includes/_nav.html) — a '
        "no-JS visitor submitting this form would have no way back into "
        "the site"
    )
    assert '<a class="skip" href="#main">' in body, (
        "non-htmx response has no skip link (base.html:58) — this is page "
        "chrome that a bare fragment does not carry"
    )
    assert MAIN_STYLESHEET_RE.search(body), (
        "non-htmx response has no <link> to the site stylesheet "
        "(/static/css/main[.<hash>].css) — a real no-JS browser would "
        "render this response completely unstyled"
    )
    assert f'id="{fragment_id}"' in body, (
        f'non-htmx response is missing the form itself (id="{fragment_id}") — '
        "the page rendered without the form a visitor just posted to"
    )


def assert_htmx_fragment_response(response, *, fragment_id):
    """
    The inverse of `assert_full_page_response`: the htmx branch must stay
    a bare fragment, so the two branches can never silently converge (in
    either direction — a future change that made *every* branch render
    the full page would break htmx's `outerHTML` swap by nesting a whole
    second `<html>` document inside the swap target, invisibly, since
    htmx would still show 200 and swap *something*).
    """
    body = response.content.decode()
    assert not body.lstrip().lower().startswith("<!doctype html>"), (
        "htmx response is a full HTML document (starts '<!doctype html>') "
        "— htmx swaps this response straight into an element already on "
        "the page, so a full document here nests a second "
        "<html><head><body> inside the DOM"
    )
    assert '<nav aria-label="Primary">' not in body, (
        "htmx response contains the site nav landmark — the full page has "
        "leaked into what must be a bare fragment for the htmx swap"
    )
    assert not MAIN_STYLESHEET_RE.search(body), (
        "htmx response contains the site stylesheet link — the full page "
        "has leaked into what must be a bare fragment for the htmx swap"
    )
    assert f'id="{fragment_id}"' in body, (
        f'htmx response is missing the fragment itself (id="{fragment_id}")'
    )

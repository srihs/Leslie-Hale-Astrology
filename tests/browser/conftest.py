"""
Browser-driven regression tests (Playwright + Chromium) for defects that
shipped with byte-identical server output and a correct DOM, and were
invisible to all 256 pytest-django tests because of it:

  - f989c39: two `htmx:afterSwap` handlers in static/js/main.js read the
    swapped content off `e.detail.target` (the OLD, already-detached
    node) instead of `e.target`. Blog tiles stayed at computed opacity 0
    forever after a category/pager swap, and the confirmation-focus
    handler on every form (contact, newsletter, booking details) had
    never fired, on any submission, since it was written.
  - 3bf095e: the pager rendered every page number in one unwrapped flex
    row — 163 links at the real ~1460-post Keen-import volume — and
    overflowed the page horizontally. Only reproducible at that real
    volume; the seeded dev database used everywhere else had a handful.
  - a7d778a: htmx calls preventDefault() on a filter/pager click before
    sending its request; if that request then fails, nothing falls back
    to the plain navigation the anchor's own href would have given, and
    the control goes silently dead.

None of these can be caught by asserting on response HTML: the server
was never wrong in any of them. Only a real browser, actually running
the page's own JS/CSS, can see them.

## Why this is a separate directory, not part of the main suite

See conftest.py at the repo root — `collect_ignore` there skips this
whole directory unless `LHA_RUN_BROWSER_TESTS` is set, so a bare
`pytest` continues to run exactly the same 256 tests it always has, with
no Playwright/Chromium/running-stack dependency. These tests are also
marked `@pytest.mark.browser` (registered there too) for anyone who does
want to select them by marker instead of by directory.

## What a fresh machine needs

  1. The stack actually running and reachable — `docker compose up -d`
     (this project's normal dev stack; see docker-compose.yml /
     docker-compose.override.yml for the local port, 8005 on this
     machine) — with the real Keen archive already imported:
         docker compose exec web python manage.py import_keen keen_blog_archive --write
     `test_blog_overflow.py` and the "paging while filtered" case in
     `test_blog_reveal_opacity.py` depend on that real ~1460-post volume
     to have more than one page per category; they say so explicitly and
     fail with a clear message (not a false pass) if the data isn't
     there, rather than faking the volume with a monkeypatched page size
     the way apps/blog/tests/test_pagination.py's unit test safely can
     for the algorithm alone.
  2. Playwright + a Chromium build, in whatever Python actually runs
     `pytest tests/browser` — NOT currently part of pyproject.toml's
     `[project.optional-dependencies].dev` group (that's docker-infra's
     pin to add; see the final report for the exact versions this was
     built and verified against):
         pip install playwright pytest-playwright
         playwright install --with-deps chromium
     `--with-deps` also apt-installs the ~40 shared libraries Chromium
     needs (libnss3, libatk*, libgbm1, fonts, ...) that the slim runtime
     image's OS layer doesn't carry — needed once per image, not once
     per test run.
  3. Outbound network access to the CDNs templates/base.html loads
     GSAP/ScrollTrigger/Lenis/htmx from (cdnjs.cloudflare.com,
     cdn.jsdelivr.net, unpkg.com) and to Google Fonts. This is a
     deliberate, narrow exception to this project's "no network calls in
     tests" rule (root conftest.py's own docstring): the opacity defect
     these tests exist to catch only exists once that real client-side
     JS has actually run, so there is nothing to assert against without
     letting the real page load it. It is still true of the rest of the
     suite — nothing here mocks Stripe or email differently, and no
     pytest-django test gains a network dependency from this directory
     existing.

## Run

    LHA_RUN_BROWSER_TESTS=1 pytest tests/browser -v

Or, targeting the host-mapped port instead of the container's own:

    LHA_RUN_BROWSER_TESTS=1 LHA_BASE_URL=http://localhost:8005 pytest tests/browser -v

`LHA_BASE_URL` defaults to `http://localhost:8000` — the address the
"web" container sees itself on, which is where these tests were actually
run and verified from (`docker compose exec web pytest tests/browser`).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.browser


@pytest.fixture(scope="session")
def base_url() -> str:
    """
    Overrides pytest-playwright's own `base_url` fixture (normally set via
    --base-url) with one read from the environment, so this suite needs no
    extra CLI flag beyond LHA_BASE_URL — see this file's own "Run" section.
    Every test in this directory builds its own full URL from this rather
    than relying on `page.goto`'s relative-URL behaviour, so it stays
    unambiguous which host each request went to.
    """
    return os.environ.get("LHA_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture
def no_js_context(browser):
    """
    A browser context with JavaScript disabled outright — not merely "don't
    call the endpoint the JS would have called", the JS never runs at all,
    same as a real visitor with scripting blocked. This is the no-JS
    contract templates/blog/partials/_post_list.html's own comment claims
    ("every filter and pager control below is a real `<a href>`") — made to
    actually run rather than trusted as a comment.
    """
    context = browser.new_context(java_script_enabled=False)
    yield context
    context.close()


@pytest.fixture
def no_js_page(no_js_context):
    page = no_js_context.new_page()
    yield page
    page.close()

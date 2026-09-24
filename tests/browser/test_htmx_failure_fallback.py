"""
a7d778a — every filter/pager anchor carries both `href` and `hx-get`.
htmx calls `preventDefault()` on the click the moment it decides to
handle it, *before* the request is even sent — so if that request then
fails (a dropped connection, a mid-deploy server restart, a blocked CDN),
the click's own default navigation never happens either, and nothing
else was listening for the failure. The chip looked pressed; nothing on
screen changed; nothing was reported. "Indistinguishable from dead," per
the fix's own commit message. static/js/main.js's fix listens for
`htmx:sendError` / `htmx:responseError` / `htmx:timeout` and navigates to
the control's own `href` — exactly what a plain anchor would already
have done.

Reproduced the same way the original commit's own investigation did:
abort only the XHR, matched on the `HX-Request` header htmx always sends
and a real document navigation never does, while leaving the ordinary
document GET for that same URL reachable — so a genuine fallback
navigation still succeeds, and this test can tell "no fallback ran"
apart from "the fallback also failed for an unrelated reason".

Proof that a real navigation happened, not an in-place DOM patch: a
marker written onto `window` before the click. A real navigation
destroys the page's JS execution context; an htmx swap does not. If the
fallback never fires, the marker is still there — this fails for exactly
the right reason instead of a coincidental one.
"""

from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def test_failed_htmx_request_falls_back_to_a_real_navigation(page, base_url):
    page.goto(f"{base_url}/blog/")
    category_link = page.locator("nav.filters a[id^='cat-']:not(#cat-all)").first
    category_id = category_link.get_attribute("id")
    href = category_link.get_attribute("href")

    def maybe_abort_htmx_request(route):
        request = route.request
        if request.headers.get("hx-request"):
            route.abort("failed")
        else:
            route.continue_()

    # Matched by a predicate on the URL, not a glob string: `href` contains
    # a literal "?", which glob syntax would otherwise treat as a
    # single-character wildcard.
    page.route(lambda url: href in url, maybe_abort_htmx_request)
    page.evaluate("() => { window.__pwAliveMarker = true; }")

    try:
        with page.expect_navigation(timeout=8000):
            category_link.click()
    except PlaywrightTimeoutError:
        raise AssertionError(
            f"no real navigation happened after the htmx request for the {category_id} "
            "filter failed — the control is silently dead, exactly the a7d778a symptom"
        )

    marker_survived = page.evaluate("() => window.__pwAliveMarker === true")
    assert not marker_survived, (
        "window state survived the click — this was an in-place DOM update, not the "
        "real navigation the a7d778a fallback is supposed to trigger"
    )
    assert href in page.url, f"navigated, but not to {href!r} (ended up at {page.url!r})"
    assert page.locator(f"#{category_id}[aria-current='page']").count() == 1

"""
f989c39 — htmx's own `afterSwap` event fired correctly on every category
filter and pager click: the grid content changed, pagination updated, and
`aria-current` moved to the clicked control. But the reveal handler in
static/js/main.js read the swapped-in content off `e.detail.target` —
the OLD `#post-list` node htmx was about to remove, fixed at request
time and never updated — instead of `e.target`, the new one `afterSwap`
actually hands you for an `outerHTML` swap. `gsap.set(items, {opacity:1})`
ran against the old, detached cards; the new ones, still governed by
`[data-reveal]{opacity:0}` (static/css/_base.css), never got their
opacity cleared. Correct DOM, correct pagination, invisible tiles.

No pytest-django assertion on response content can see this: the server
returns the exact same HTML either way. Only a browser's own computed
style, after its own JS has actually run, tells the two cases apart —
which is why this asserts `getComputedStyle(...).opacity`, never DOM
presence (an element sitting at opacity 0 is the bug, and it is very
much present in the DOM).

Not a timing-flaky assertion: `gsap.set` (as opposed to `gsap.to`) applies
its target values immediately, with no animation duration, so there is no
window to race — by the time `aria-current` has moved (part of the same
swapped content), the opacity fix, if present, has already applied.
"""

from __future__ import annotations


def _category_ids(page):
    """Every real category filter link's id on /blog/ (id="cat-<slug>"), never "All"."""
    locator = page.locator("nav.filters a[id^='cat-']:not(#cat-all)")
    ids = [locator.nth(i).get_attribute("id") for i in range(locator.count())]
    assert ids, "no category filter links found on /blog/ — cannot exercise this defect at all"
    return ids


def _assert_tiles_opaque(page, *, context_label):
    tiles = page.locator("#post-list .post[data-reveal]")
    count = tiles.count()
    assert count > 0, f"{context_label}: no post tiles rendered to check opacity against"
    for i in range(count):
        opacity = tiles.nth(i).evaluate("el => getComputedStyle(el).opacity")
        assert opacity == "1", (
            f"{context_label}: tile {i} has computed opacity {opacity!r}, not \"1\" — "
            "present in the DOM but invisible, the exact f989c39 symptom"
        )


def test_each_category_filter_leaves_tiles_visible(page, base_url):
    page.goto(f"{base_url}/blog/")
    for category_id in _category_ids(page):
        # Fresh load per category: isolates each swap rather than compounding
        # state from the previous click, and matches how a real visitor
        # arrives at /blog/ and picks one category at a time.
        page.goto(f"{base_url}/blog/")
        page.locator(f"#{category_id}").click()
        page.wait_for_selector(f"#{category_id}[aria-current='page']")
        _assert_tiles_opaque(page, context_label=f"category {category_id}")


def test_paging_while_filtered_leaves_tiles_visible(page, base_url):
    page.goto(f"{base_url}/blog/")
    category_id = None
    for candidate in _category_ids(page):
        page.goto(f"{base_url}/blog/")
        page.locator(f"#{candidate}").click()
        page.wait_for_selector(f"#{candidate}[aria-current='page']")
        if page.locator("#pager-next").count():
            category_id = candidate
            break

    assert category_id, (
        "no category in the current dataset has more than one page of results, so "
        "'paging while filtered' cannot be exercised — this needs the real Keen "
        "import (see tests/browser/conftest.py's 'What a fresh machine needs')"
    )

    current = page.locator(".pager a[aria-current='page']")
    before_id = current.get_attribute("id") if current.count() else None
    page.locator("#pager-next").click()
    page.wait_for_function(
        """(beforeId) => {
            const el = document.querySelector('.pager a[aria-current="page"]');
            return !!el && el.id !== beforeId;
        }""",
        arg=before_id,
    )
    _assert_tiles_opaque(page, context_label=f"category {category_id}, next page")

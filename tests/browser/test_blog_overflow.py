"""
3bf095e — templates/blog/partials/_post_list.html used to loop
`paginator.page_range` directly: every page number the paginator knows
about, with no cap. At the real Keen-import volume (1460 posts, ~163
pages at BlogIndexPage.POSTS_PER_PAGE=9) that is 163 pager links in one
row, and `.pager` had no `flex-wrap` — the row ran off the right edge of
the page. Two independent fixes landed together: `build_elided_page_range`
(apps/blog/models.py) caps what the template ever loops to at most 7
items, and `.pager` gained `flex-wrap` so it would no longer be a hazard
even if something else drove its item count up again.

apps/blog/tests/test_pagination.py already proves the elision algorithm
itself never grows past 7 items, at the unit level, by driving a bare
Paginator's `num_pages` up to 5000 without creating that many real pages.
It cannot see the actual rendered width, though, which is what this file
tests instead: a real browser, real CSS, and the real ~1460-post dataset
already imported into this environment (see tests/browser/conftest.py) —
at 360px (§2: "the audience is women 27-70") and at a wide desktop width,
on the unfiltered index and on every category's filtered view.

Deliberately not faked with a smaller POSTS_PER_PAGE or a synthetic large
page-range in a test context: the actual bug was CSS overflow at real
content volume, and only a render at real volume can show it. If this
environment's dataset is thin, these tests say so explicitly (via the
category-discovery assertion) rather than silently passing over nothing.
"""

from __future__ import annotations

import pytest

WIDTHS = [360, 1440]


def _assert_no_horizontal_overflow(page, *, context_label):
    scroll_width, client_width = page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    assert scroll_width == client_width, (
        f"{context_label}: document.documentElement.scrollWidth ({scroll_width}) != "
        f"clientWidth ({client_width}) — the page overflows horizontally, the exact "
        "3bf095e symptom (there, the pager ran 163 links off the right edge)"
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_blog_index_does_not_overflow(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/blog/")
    _assert_no_horizontal_overflow(page, context_label=f"/blog/ at {width}px")


@pytest.mark.parametrize("width", WIDTHS)
def test_every_filtered_category_view_does_not_overflow(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/blog/")

    category_links = page.locator("nav.filters a[id^='cat-']:not(#cat-all)")
    count = category_links.count()
    assert count > 0, "no category filter links found on /blog/ — cannot exercise a filtered view"
    hrefs = [category_links.nth(i).get_attribute("href") for i in range(count)]

    for href in hrefs:
        page.goto(f"{base_url}{href}")
        _assert_no_horizontal_overflow(page, context_label=f"{href} at {width}px")

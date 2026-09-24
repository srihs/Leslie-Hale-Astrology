"""
Every filter/pager control on /blog/ is meant to be a real `<a href>`
first and htmx second (templates/blog/partials/_post_list.html's own
comment). a7d778a's commit message names exactly this as the gap in the
project's own testing: "the no-JS path was tested; the broken-JS path
was not" — implying the no-JS path itself had actually been checked, by
hand, at some point. This file is that check, made to run on every
change instead of trusted as a past claim: a genuinely JS-disabled
Playwright context (the JS never runs at all — not "don't call the
endpoint it would have called"), clicking a category filter and a pager
link, and expecting exactly what a plain browser does with a plain link:
a real page load, driven by the anchor's own href.

Also covers the `.no-js [data-reveal]{opacity:1}` fallback
(static/css/_base.css): with no JS, `document.body` never loses its
`no-js` class (removing it is the first line of static/js/main.js), so
tiles must be visible immediately with no GSAP pass at all — checked the
same way test_blog_reveal_opacity.py does, by computed style.
"""

from __future__ import annotations


def _assert_tiles_visible(page, *, context_label):
    tiles = page.locator("#post-list .post[data-reveal]")
    count = tiles.count()
    assert count > 0, f"{context_label}: no tiles rendered"
    for i in range(count):
        opacity = tiles.nth(i).evaluate("el => getComputedStyle(el).opacity")
        assert opacity == "1", f"{context_label}: tile {i} not visible without JS (opacity {opacity!r})"


def test_blog_filter_and_pager_work_with_javascript_disabled(no_js_page, base_url):
    page = no_js_page
    page.goto(f"{base_url}/blog/")
    _assert_tiles_visible(page, context_label="/blog/ with JS disabled")

    category_link = page.locator("nav.filters a[id^='cat-']:not(#cat-all)").first
    category_id = category_link.get_attribute("id")
    category_href = category_link.get_attribute("href")
    assert category_href, (
        f"the {category_id} filter has no href at all — with JS disabled this control "
        "has no way to navigate anywhere"
    )
    category_link.click()
    page.wait_for_load_state("load")

    assert category_href in page.url, (
        f"clicking the {category_id} filter with JS disabled did not navigate to "
        f"{category_href!r} (ended up at {page.url!r}) — the no-JS path is not a "
        "real link"
    )
    assert page.locator(f"#{category_id}[aria-current='page']").count() == 1, (
        f"landed on {page.url!r} but {category_id} is not marked as the active filter "
        "there — the no-JS navigation did not land on the filtered result"
    )
    _assert_tiles_visible(page, context_label=f"filtered to {category_id} with JS disabled")

    pager_next = page.locator("#pager-next")
    if pager_next.count() == 0:
        return  # this category has only one page in the current dataset — nothing more to page through
    pager_href = pager_next.get_attribute("href")
    pager_next.click()
    page.wait_for_load_state("load")

    assert pager_href in page.url, (
        f"clicking the pager's next link with JS disabled did not navigate to "
        f"{pager_href!r} (ended up at {page.url!r}) — the no-JS pager is not a real link"
    )
    _assert_tiles_visible(page, context_label="next page with JS disabled")

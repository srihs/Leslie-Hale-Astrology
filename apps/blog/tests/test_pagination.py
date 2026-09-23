"""
`BlogIndexPage`'s pager (apps/blog/models.py).

The bug this guards against: `templates/blog/partials/_post_list.html`
used to loop `posts_page.paginator.page_range` — every page number in the
paginator. With the Keen import alone (1460 posts, ~163 pages at
`BlogIndexPage.POSTS_PER_PAGE`), that is 163 links in one row and
overflows the page horizontally (reported with a screenshot). The fix is
`build_elided_page_range()`, which wraps Django's own
`Paginator.get_elided_page_range()`.

`test_build_elided_page_range_stays_short_regardless_of_page_count` is the
regression that matters: it drives the *paginator's own* `num_pages` up to
5000 directly (a plain `Paginator` over an in-memory list — no need to
create that many real `BlogPost` pages to prove the algorithm doesn't
scale the pager with it) and asserts the built range never grows past the
small bound `on_each_side=1, on_ends=1` promises, at the first page, a
middle page and the last page.

The remaining tests exercise `BlogIndexPage.get_context` itself (with a
small, real set of `BlogPost` pages, via `POSTS_PER_PAGE` monkeypatched
down so a handful of posts already produce enough pages to see an
ellipsis) to confirm `get_context` wires `build_elided_page_range` in
correctly and — the thing htmx-frontend depends on staying stable while
this fix lands — leaves `posts_page`, `posts`, `categories` and
`active_category` unchanged.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.test import RequestFactory

import pytest

from apps.blog.models import BlogIndexPage, build_elided_page_range
from apps.blog.tests.factories import make_blog_index_page, make_blog_post
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db


# The bound `on_each_side=1, on_ends=1` promises: up to `on_ends` pages at
# each end, one ellipsis on each side of the gap, and up to
# `2 * on_each_side + 1` pages around the current page.
MAX_ITEMS = 1 + 1 + (2 * 1 + 1) + 1 + 1  # 7


@pytest.mark.parametrize("num_pages", [2, 21, 163, 5000])
def test_build_elided_page_range_stays_short_regardless_of_page_count(num_pages):
    """The whole point of the fix: however many pages exist, the pager
    handed to the template stays short. Checked at the first page, a
    middle page and the last page — the three shapes the ellipsis can
    take (none needed near an end, one on each side in the middle)."""
    paginator = Paginator(list(range(num_pages)), 1)

    for current_page_number in {1, max(1, num_pages // 2), num_pages}:
        elided = build_elided_page_range(paginator, current_page_number)
        assert len(elided) <= MAX_ITEMS, (
            f"num_pages={num_pages}, current_page={current_page_number}: "
            f"got {len(elided)} items, expected at most {MAX_ITEMS}"
        )


def test_build_elided_page_range_item_shape():
    """Every item is a dict; an ellipsis is exactly {"is_ellipsis": True}
    with no `number`/`is_current`, so the template can test the plain
    boolean `item.is_ellipsis` without ever needing to know what sentinel
    value a page number is compared against."""
    paginator = Paginator(list(range(21)), 1)

    elided = build_elided_page_range(paginator, 11)

    saw_ellipsis = False
    for item in elided:
        assert set(item.keys()) in ({"is_ellipsis"}, {"is_ellipsis", "number", "is_current"})
        if item["is_ellipsis"]:
            saw_ellipsis = True
        else:
            assert isinstance(item["number"], int)
            assert item["is_current"] == (item["number"] == 11)
    assert saw_ellipsis, "expected at least one ellipsis with 21 pages and page 11 current"


def test_build_elided_page_range_marks_current_page():
    paginator = Paginator(list(range(5)), 1)

    elided = build_elided_page_range(paginator, 3)

    current_items = [item for item in elided if not item["is_ellipsis"] and item["is_current"]]
    assert [item["number"] for item in current_items] == [3]


@pytest.fixture
def index_page(monkeypatch):
    # One post per page turns a small, fast-to-create set of posts into
    # enough pages to exercise the ellipsis, without creating anywhere
    # near the real Keen import's 1460 pages.
    monkeypatch.setattr(BlogIndexPage, "POSTS_PER_PAGE", 1)
    home = make_home_page()
    index = make_blog_index_page(home)
    for n in range(12):
        make_blog_post(index, title=f"Post {n}", slug=f"post-{n}")
    return index


def _get_context(index_page, **get_params):
    request = RequestFactory().get("/", get_params)
    return index_page.get_context(request)


def test_get_context_elided_range_at_first_page(index_page):
    context = _get_context(index_page, page="1")

    elided = context["elided_page_range"]
    assert len(elided) <= MAX_ITEMS
    assert elided[0] == {"is_ellipsis": False, "number": 1, "is_current": True}


def test_get_context_elided_range_at_middle_page(index_page):
    context = _get_context(index_page, page="6")

    elided = context["elided_page_range"]
    assert len(elided) <= MAX_ITEMS
    assert any(item["is_ellipsis"] for item in elided), (
        "expected at least one ellipsis with 12 pages and page 6 current"
    )
    current_items = [item for item in elided if not item["is_ellipsis"] and item["is_current"]]
    assert [item["number"] for item in current_items] == [6]


def test_get_context_elided_range_at_last_page(index_page):
    context = _get_context(index_page, page="12")

    elided = context["elided_page_range"]
    assert len(elided) <= MAX_ITEMS
    assert elided[-1] == {"is_ellipsis": False, "number": 12, "is_current": True}


def test_get_context_keeps_existing_keys_unchanged(index_page):
    """htmx-frontend is updating the template concurrently against these
    same keys — this fix must not touch any of them."""
    context = _get_context(index_page, page="1")

    assert "posts_page" in context
    assert "posts" in context
    assert "categories" in context
    assert "active_category" in context
    assert list(context["posts"]) == list(context["posts_page"].object_list)
    assert context["active_category"] is None

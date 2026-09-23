"""
Title search on the Blog posts screen (apps/backoffice/views/blog.py:
BlogPostListView) — added so Leslie can find her own post among the
~1460 imported from the Keen archive across ~73 pages, not the public
site search PROJECT-SCOPE.md §4 excludes (this is behind /manage/, over
her own content, not a visitor-facing feature).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.backoffice.tests.factories import make_backoffice_user
from apps.blog.tests.factories import make_blog_index_page, make_blog_post
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db


def _make_posts():
    home = make_home_page()
    index = make_blog_index_page(home)
    saturn = make_blog_post(index, title="Saturn Return: what to expect", slug="saturn-return")
    venus = make_blog_post(index, title="Venus in retrograde", slug="venus-retrograde")
    moon = make_blog_post(index, title="New Moon rituals", slug="new-moon-rituals")
    return saturn, venus, moon


class TestBlogSearch:
    def test_no_query_returns_all_posts(self, client):
        saturn, venus, moon = _make_posts()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"))

        titles = {post.title for post in response.context["posts"]}
        assert titles == {saturn.title, venus.title, moon.title}
        assert response.context["q"] == ""

    def test_query_filters_by_title_case_insensitively(self, client):
        saturn, venus, moon = _make_posts()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"), {"q": "saturn"})

        titles = [post.title for post in response.context["posts"]]
        assert titles == [saturn.title]
        assert response.context["q"] == "saturn"

    def test_query_matches_substring_anywhere_in_title(self, client):
        saturn, venus, moon = _make_posts()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"), {"q": "moon"})

        titles = [post.title for post in response.context["posts"]]
        assert titles == [moon.title]

    def test_query_with_no_matches_returns_empty_list(self, client):
        _make_posts()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"), {"q": "nonexistent-topic"})

        assert list(response.context["posts"]) == []
        assert response.context["q"] == "nonexistent-topic"

    def test_query_is_stripped_of_surrounding_whitespace(self, client):
        saturn, venus, moon = _make_posts()
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"), {"q": "  saturn  "})

        titles = [post.title for post in response.context["posts"]]
        assert titles == [saturn.title]
        assert response.context["q"] == "saturn"

    def test_pagination_still_works_with_a_query(self, client):
        home = make_home_page()
        index = make_blog_index_page(home)
        for i in range(25):
            make_blog_post(index, title=f"Saturn post {i}", slug=f"saturn-post-{i}")
        user = make_backoffice_user()
        client.force_login(user)

        response = client.get(reverse("backoffice:blog_list"), {"q": "saturn"})

        assert response.context["is_paginated"] is True
        assert response.context["paginator"].count == 25

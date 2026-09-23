"""
`manage.py remove_sample_blog_posts` — the explicit, separate cleanup step
for the "Sample post N" placeholder pages seeded during the build. Kept
deliberately apart from `import_keen`, which must never delete content.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.blog.models import BlogPost
from apps.blog.tests.factories import make_blog_index_page, make_blog_post
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db


@pytest.fixture
def index_page():
    home = make_home_page()
    return make_blog_index_page(home)


def test_dry_run_lists_sample_posts_but_deletes_nothing(index_page):
    make_blog_post(index_page, title="Sample post 1", slug="sample-post-1")
    make_blog_post(index_page, title="Sample post 2", slug="sample-post-2")
    make_blog_post(index_page, title="A Real Post", slug="a-real-post")

    out = StringIO()
    call_command("remove_sample_blog_posts", stdout=out)

    assert BlogPost.objects.count() == 3
    assert "Sample post 1" in out.getvalue()
    assert "Sample post 2" in out.getvalue()
    assert "would be deleted" in out.getvalue()


def test_write_deletes_only_sample_posts(index_page):
    make_blog_post(index_page, title="Sample post 1", slug="sample-post-1")
    make_blog_post(index_page, title="Sample post 11", slug="sample-post-11")
    real_post = make_blog_post(index_page, title="A Real Post", slug="a-real-post")

    out = StringIO()
    call_command("remove_sample_blog_posts", "--write", stdout=out)

    remaining = list(BlogPost.objects.all())
    assert remaining == [real_post]


def test_title_match_is_exact_not_a_prefix():
    """A post that merely starts with "Sample post" but isn't an exact
    "Sample post <number>" match (e.g. a real post someone titled
    descriptively) must never be swept up by this."""
    home = make_home_page()
    index = make_blog_index_page(home)
    lookalike = make_blog_post(index, title="Sample post about Mercury retrograde", slug="lookalike")

    call_command("remove_sample_blog_posts", "--write", stdout=StringIO())

    assert BlogPost.objects.filter(pk=lookalike.pk).exists()


def test_no_sample_posts_is_a_no_op(index_page):
    real_post = make_blog_post(index_page, title="A Real Post", slug="a-real-post")

    out = StringIO()
    call_command("remove_sample_blog_posts", "--write", stdout=out)

    assert list(BlogPost.objects.all()) == [real_post]
    assert "nothing to do" in out.getvalue()

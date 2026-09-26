"""
`apps.blog.blogger_import.importer.BloggerImporter` — the orchestrator
this task names as the second-highest-risk area in the codebase, and
specifically: a second run over identical input must create and update
nothing.

No network: every test here builds a local Atom export file and points
the importer at its path (`feed.fetch_documents` treats a local path as
one document — see test_feed.py). Image "downloads" are stubbed at
`BloggerImporter._download_image` so no `urllib.request.urlopen` call is
ever made.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape
from unittest.mock import patch

import pytest
from django.utils import timezone
from wagtail.contrib.redirects.models import Redirect

from apps.blog.blogger_import.importer import BloggerImporter
from apps.blog.models import BlogCategory, BlogPost
from apps.blog.tests.factories import make_blog_index_page
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db

ATOM_NS = "http://www.w3.org/2005/Atom"


def _atom_entry(*, post_id, title, content, published, updated=None, url_slug=None, labels=()):
    updated = updated or published
    url_slug = url_slug or title.lower().replace(" ", "-")
    label_xml = "".join(
        f'<category scheme="http://www.blogger.com/atom/ns#" term="{label}"/>' for label in labels
    )
    return f"""
  <entry>
    <id>tag:blogger.com,1999:blog-1.post-{post_id}</id>
    <published>{published}</published>
    <updated>{updated}</updated>
    <title type="text">{title}</title>
    <content type="html">{xml_escape(content)}</content>
    <author><name>Leslie Hale</name></author>
    <link rel="alternate" type="text/html" href="https://old-blog.example.com/{url_slug}.html"/>
    <category scheme="http://schemas.google.com/g/2005#kind" term="http://schemas.google.com/blogger/2008/kind#post"/>
    {label_xml}
  </entry>
"""


def _atom_feed(*entries: str) -> str:
    body = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}">
{body}
</feed>"""


def _write_export(tmp_path, xml: str, name="export.xml"):
    path = tmp_path / name
    path.write_text(xml, encoding="utf-8")
    return str(path)


@pytest.fixture
def index_page():
    home = make_home_page()
    return make_blog_index_page(home)


def _run(index_page, source, *, write=True, **kwargs):
    importer = BloggerImporter(write=write, index_page=index_page, **kwargs)
    # No network for images: any test exercising an <img> stubs this out
    # explicitly. Everything else has no images in its fixture content.
    return importer.run(source)


def test_first_run_creates_a_new_post(tmp_path, index_page):
    xml = _atom_feed(
        _atom_entry(post_id="1", title="First Post", content="<p>Hello world.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source = _write_export(tmp_path, xml)

    report = _run(index_page, source)

    assert report.imported == ["'First Post' (post-1)"]
    assert report.updated == []
    post = BlogPost.objects.get(blogger_post_id="post-1")
    assert post.title == "First Post"
    assert post.live is True


def test_second_identical_run_is_fully_idempotent(tmp_path, index_page):
    """The binding rule from this task's brief, verbatim: a second run
    over identical input creates and updates nothing."""
    xml = _atom_feed(
        _atom_entry(post_id="1", title="First Post", content="<p>Hello world.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source = _write_export(tmp_path, xml)

    _run(index_page, source)
    assert BlogPost.objects.count() == 1

    report2 = _run(index_page, source)

    assert report2.imported == []
    assert report2.updated == []
    assert report2.unchanged == ["'First Post' (post-1)"]
    assert BlogPost.objects.count() == 1


def test_second_run_does_not_bump_last_published_at_or_create_a_new_revision(tmp_path, index_page):
    """A no-op run must genuinely touch nothing — not even a redundant
    save — matching the importer module's own docstring ("does nothing at
    all to that post beyond confirming it is unchanged")."""
    xml = _atom_feed(
        _atom_entry(post_id="1", title="First Post", content="<p>Hello world.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source = _write_export(tmp_path, xml)

    _run(index_page, source)
    post = BlogPost.objects.get(blogger_post_id="post-1")
    first_revision_created_at = post.latest_revision_created_at
    revision_count_before = post.revisions.count()

    _run(index_page, source)

    post.refresh_from_db()
    assert post.latest_revision_created_at == first_revision_created_at
    assert post.revisions.count() == revision_count_before


def test_changed_post_updates_in_place_same_page_same_slug_same_url(tmp_path, index_page):
    xml_v1 = _atom_feed(
        _atom_entry(post_id="1", title="Original Title", content="<p>Original content.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source_v1 = _write_export(tmp_path, xml_v1, name="v1.xml")
    _run(index_page, source_v1)

    original = BlogPost.objects.get(blogger_post_id="post-1")
    original_pk = original.pk
    original_slug = original.slug
    original_url_path = original.url_path

    xml_v2 = _atom_feed(
        _atom_entry(post_id="1", title="Original Title", content="<p>Updated content, genuinely different.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source_v2 = _write_export(tmp_path, xml_v2, name="v2.xml")
    report = _run(index_page, source_v2)

    assert report.updated == ["'Original Title' (post-1)"]
    assert report.imported == []
    assert BlogPost.objects.count() == 1

    updated = BlogPost.objects.get(blogger_post_id="post-1")
    assert updated.pk == original_pk
    assert updated.slug == original_slug
    assert updated.url_path == original_url_path
    assert "Updated content" in str(updated.body)


def test_publication_dates_are_preserved(tmp_path, index_page):
    published_raw = "2019-03-14T09:26:00.000-07:00"
    xml = _atom_feed(_atom_entry(post_id="1", title="Old Post", content="<p>Text.</p>", published=published_raw))
    source = _write_export(tmp_path, xml)

    _run(index_page, source)

    post = BlogPost.objects.get(blogger_post_id="post-1")
    expected = timezone.datetime.fromisoformat(published_raw)
    assert post.published_date == expected
    assert post.first_published_at == expected


def test_redirects_are_created_and_not_duplicated_on_re_run(tmp_path, index_page):
    xml = _atom_feed(
        _atom_entry(
            post_id="1",
            title="Redirect Me",
            content="<p>Text.</p>",
            published="2020-06-01T08:00:00.000-07:00",
            url_slug="2020/06/redirect-me",
        )
    )
    source = _write_export(tmp_path, xml)

    report1 = _run(index_page, source)
    assert report1.redirects_created == 1
    assert Redirect.objects.count() == 1
    redirect = Redirect.objects.get()
    assert redirect.old_path == Redirect.normalise_path("https://old-blog.example.com/2020/06/redirect-me.html")

    report2 = _run(index_page, source)
    assert report2.redirects_created == 0
    assert Redirect.objects.count() == 1


def test_dry_run_writes_nothing_to_the_database(tmp_path, index_page):
    xml = _atom_feed(
        _atom_entry(post_id="1", title="Preview Only", content="<p>Text.</p>", published="2020-06-01T08:00:00.000-07:00")
    )
    source = _write_export(tmp_path, xml)

    report = _run(index_page, source, write=False)

    assert report.imported == ["'Preview Only' (post-1)"]
    assert BlogPost.objects.count() == 0
    assert Redirect.objects.count() == 0


def test_uncategorised_posts_stay_uncategorised_without_a_category_map(tmp_path, index_page):
    xml = _atom_feed(
        _atom_entry(
            post_id="1", title="Labelled Post", content="<p>Text.</p>", published="2020-06-01T08:00:00.000-07:00",
            labels=["Transits"],
        )
    )
    source = _write_export(tmp_path, xml)

    report = _run(index_page, source)

    post = BlogPost.objects.get(blogger_post_id="post-1")
    assert post.category is None
    assert any("Transits" in note for note in report.notes)


def test_category_map_assigns_an_existing_category(tmp_path, index_page):
    # "transits" is seeded by blog.0004_seed_keen_categories (which runs
    # against the test database too, like any other migration) — fetched
    # here rather than (re-)created, to avoid colliding with that row's
    # own unique name/slug.
    category = BlogCategory.objects.get(slug="transits")
    xml = _atom_feed(
        _atom_entry(
            post_id="1", title="Labelled Post", content="<p>Text.</p>", published="2020-06-01T08:00:00.000-07:00",
            labels=["Transits"],
        )
    )
    source = _write_export(tmp_path, xml)

    _run(index_page, source, category_map={"Transits": "transits"})

    post = BlogPost.objects.get(blogger_post_id="post-1")
    assert post.category_id == category.id


def test_draft_posts_are_imported_unpublished(tmp_path, index_page):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}" xmlns:app="http://purl.org/atom/app#">
  <entry>
    <id>tag:blogger.com,1999:blog-1.post-7</id>
    <published>2020-06-01T08:00:00.000-07:00</published>
    <updated>2020-06-01T08:00:00.000-07:00</updated>
    <title type="text">A Draft</title>
    <content type="html">&lt;p&gt;Draft text.&lt;/p&gt;</content>
    <author><name>Leslie Hale</name></author>
    <link rel="alternate" type="text/html" href="https://old-blog.example.com/a-draft.html"/>
    <category scheme="http://schemas.google.com/g/2005#kind" term="http://schemas.google.com/blogger/2008/kind#post"/>
    <app:control><app:draft>yes</app:draft></app:control>
  </entry>
</feed>"""
    source = _write_export(tmp_path, xml)

    _run(index_page, source)

    post = BlogPost.objects.get(blogger_post_id="post-7")
    assert post.live is False


def test_a_single_malformed_entry_does_not_abort_the_whole_run(tmp_path, index_page):
    """One entry with no <id> (unmatched/unmatchable on re-import) is
    skipped by feed.py's own parser; the rest of the run must still
    complete."""
    good = _atom_entry(post_id="1", title="Good Post", content="<p>Text.</p>", published="2020-06-01T08:00:00.000-07:00")
    bad = """
  <entry>
    <published>2020-06-01T08:00:00.000-07:00</published>
    <title type="text">No ID</title>
    <content type="html">&lt;p&gt;Text.&lt;/p&gt;</content>
    <category scheme="http://schemas.google.com/g/2005#kind" term="http://schemas.google.com/blogger/2008/kind#post"/>
  </entry>
"""
    xml = _atom_feed(good, bad)
    source = _write_export(tmp_path, xml)

    report = _run(index_page, source)

    assert BlogPost.objects.filter(blogger_post_id="post-1").exists()
    assert len(report.skipped) == 1


def test_second_run_downloads_no_images_for_an_unchanged_post_with_an_image(tmp_path, index_page):
    """Unchanged detection happens *before* any image download (the
    importer module's own docstring) — a second identical run must not
    re-fetch images at all, imported or not."""
    xml = _atom_feed(
        _atom_entry(
            post_id="1",
            title="Post With Image",
            content='<p>Before</p><img src="https://old-blog.example.com/photo.jpg" alt="A photo"><p>After</p>',
            published="2020-06-01T08:00:00.000-07:00",
        )
    )
    source = _write_export(tmp_path, xml)

    fake_image_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    class _FakeResponse:
        headers = {"Content-Type": "image/png"}

        def read(self, *a, **k):
            return fake_image_bytes

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("urllib.request.urlopen", return_value=_FakeResponse()) as urlopen:
        _run(index_page, source)
        assert urlopen.call_count == 1

        urlopen.reset_mock()
        report2 = _run(index_page, source)
        assert urlopen.call_count == 0
        assert report2.unchanged == ["'Post With Image' (post-1)"]


def test_new_import_does_not_duplicate_the_hero_image_in_the_body(tmp_path, index_page):
    """templates/blog/post.html renders featured_image as the article hero
    and then the body — an image promoted to featured_image must not also
    survive as an in-body CaptionedImageBlock, or it prints twice."""
    xml = _atom_feed(
        _atom_entry(
            post_id="1",
            title="Post With Image",
            content='<p>Before</p><img src="https://old-blog.example.com/photo.jpg" alt="A photo"><p>After</p>',
            published="2020-06-01T08:00:00.000-07:00",
        )
    )
    source = _write_export(tmp_path, xml)

    fake_image_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    class _FakeResponse:
        headers = {"Content-Type": "image/png"}

        def read(self, *a, **k):
            return fake_image_bytes

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("urllib.request.urlopen", return_value=_FakeResponse()):
        _run(index_page, source)

    post = BlogPost.objects.get(blogger_post_id="post-1")
    assert post.featured_image is not None
    image_blocks = [entry for entry in post.body.raw_data if entry.get("type") == "image"]
    assert image_blocks == []
    assert "Before" in str(post.body) and "After" in str(post.body)

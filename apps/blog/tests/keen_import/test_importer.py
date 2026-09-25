"""
`apps.blog.keen_import.importer.KeenImporter` — the orchestrator this
task names as the highest-risk area: a second run over an unchanged
archive must create and update nothing, and nothing already in the
database is ever deleted.

No stubbing of network calls is needed here (unlike the Blogger
importer): the Keen archive is local files on disk, so these tests build
a tiny real archive directory (articles/*.html + images/*) under
`tmp_path` and point the importer at it directly — the same code path
`manage.py import_keen` uses against the real 1460-post archive.
"""

from __future__ import annotations

import base64

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from wagtail.contrib.redirects.models import Redirect
from wagtail.images import get_image_model

from apps.blog.keen_import.importer import (
    _PERMISSION_MARKER,
    ImportReport,
    KeenImporter,
)
from apps.blog.models import BlogCategory, BlogPost, KeenImportedImage
from apps.blog.tests.factories import make_blog_index_page
from apps.home.tests.factories import make_home_page

pytestmark = pytest.mark.django_db

# A real, minimal, decodable 1x1 transparent GIF — needed because
# KeenImporter._copy_image both magic-byte-sniffs *and* (in write mode)
# saves through Wagtail's own image pipeline, which decodes the file for
# real (via Willow) to populate width/height. Arbitrary bytes with a
# correct-looking extension are not enough to exercise that path.
_TINY_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7")

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><title>{title}</title></head>
<body>
<main class="article">
  <h1>{title}</h1>
  <div class="date">{date_line}</div>
  <div class="source"><a href="{url}" target="_blank" rel="noopener">view original on keen.com</a></div>
  <article class="content">
    <div class="col-sm-12 blog-body">{body}</div>
  </article>
</main>
</body>
</html>
"""


def _default_date_line(labels=()):
    suffix = f" Filed Under: {', '.join(labels)}" if labels else ""
    return f"posted Wed, Apr 15, 2020 15:11 PM by Astrology readings Leslie Hale{suffix} 0 Comments"


def _write_article(archive, post_id, *, title="A Test Post", labels=(), body="<p>Hello world.</p>", date_line=None):
    articles_dir = archive / "articles"
    articles_dir.mkdir(exist_ok=True)
    (archive / "images").mkdir(exist_ok=True)
    url = f"https://www.keen.com/CommunityServer/UserBlogPosts/Astrology_readings_Leslie_Hale/Slug/{post_id}.aspx"
    html = ARTICLE_TEMPLATE.format(
        title=title,
        date_line=date_line or _default_date_line(labels),
        url=url,
        body=body,
    )
    (articles_dir / f"{post_id}-post.html").write_text(html, encoding="utf-8")


def _write_local_image(archive, filename, data=_TINY_GIF):
    (archive / "images").mkdir(exist_ok=True)
    (archive / "images" / filename).write_bytes(data)


@pytest.fixture
def index_page():
    home = make_home_page()
    return make_blog_index_page(home)


@pytest.fixture
def transits_category():
    # Seeded by the blog.0004_seed_keen_categories data migration (which
    # runs against the test database too, like any other migration) —
    # fetched, not (re-)created, so this doesn't collide with that
    # migration's own row on BlogCategory.name/slug's unique constraints.
    return BlogCategory.objects.get(slug="transits")


def _run(archive, index_page, *, write=True, **kwargs):
    importer = KeenImporter(write=write, index_page=index_page, **kwargs)
    return importer.run(str(archive))


def test_first_run_creates_a_new_post(tmp_path, index_page, transits_category):
    _write_article(tmp_path, "1001", title="First Post", labels=["Saturn"])

    report = _run(tmp_path, index_page)

    assert report.imported == ["'First Post' (1001)"]
    assert report.updated == []
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.title == "First Post"
    assert post.live is True
    assert post.category == transits_category
    assert post.original_category_label == "Saturn"


def test_second_identical_run_is_fully_idempotent(tmp_path, index_page, transits_category):
    """The binding rule from this task's brief, verbatim: a second run
    over identical input creates and updates nothing."""
    _write_article(tmp_path, "1001", title="First Post", labels=["Saturn"])

    _run(tmp_path, index_page)
    assert BlogPost.objects.count() == 1

    report2 = _run(tmp_path, index_page)

    assert report2.imported == []
    assert report2.updated == []
    assert report2.unchanged == ["'First Post' (1001)"]
    assert BlogPost.objects.count() == 1


def test_second_run_does_not_bump_revision_or_last_published(tmp_path, index_page):
    """A no-op run must genuinely touch nothing — not even a redundant
    save — matching the Blogger importer's own guarantee."""
    _write_article(tmp_path, "1001", title="First Post")

    _run(tmp_path, index_page)
    post = BlogPost.objects.get(keen_post_id="1001")
    revision_count_before = post.revisions.count()
    last_published_before = post.last_published_at

    _run(tmp_path, index_page)

    post.refresh_from_db()
    assert post.revisions.count() == revision_count_before
    assert post.last_published_at == last_published_before


def test_changed_post_updates_in_place_same_page_same_slug_same_url(tmp_path, index_page):
    _write_article(tmp_path, "1001", title="Original Title", body="<p>Original content.</p>")
    _run(tmp_path, index_page)

    original = BlogPost.objects.get(keen_post_id="1001")
    original_pk = original.pk
    original_slug = original.slug
    original_url_path = original.url_path

    _write_article(tmp_path, "1001", title="Original Title", body="<p>Updated content, genuinely different.</p>")
    report = _run(tmp_path, index_page)

    assert report.updated == ["'Original Title' (1001)"]
    assert report.imported == []
    assert BlogPost.objects.count() == 1

    updated = BlogPost.objects.get(keen_post_id="1001")
    assert updated.pk == original_pk
    assert updated.slug == original_slug
    assert updated.url_path == original_url_path
    assert "Updated content" in str(updated.body)


def test_publication_date_hour_0_am_is_preserved_exactly(tmp_path, index_page):
    """This task's own trap case: "0:51 AM" is midnight-ish, hour 0, not
    an invalid 12-hour hour — the imported post's published_date must
    reflect that literal date/time, localised, not corrupted."""
    _write_article(
        tmp_path, "1001", title="Midnight Post",
        date_line="posted Tue, Sep 10, 2013 0:51 AM by Astrology readings Leslie Hale Filed Under: Neptune 9 Comments",
    )

    _run(tmp_path, index_page)

    post = BlogPost.objects.get(keen_post_id="1001")
    local_time = post.published_date.astimezone(post.published_date.tzinfo)
    # Compare against Django's configured local timezone via a round trip
    # through timezone.localtime rather than assuming UTC.
    from django.utils import timezone as dj_timezone

    local = dj_timezone.localtime(post.published_date)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2013, 9, 10, 0, 51)


def test_redirects_are_created_and_not_duplicated_on_rerun(tmp_path, index_page):
    _write_article(tmp_path, "1001", title="Redirect Me")

    report1 = _run(tmp_path, index_page)
    assert report1.redirects_created == 1
    assert Redirect.objects.count() == 1
    redirect = Redirect.objects.get()
    post = BlogPost.objects.get(keen_post_id="1001")
    assert redirect.redirect_page_id == post.id

    report2 = _run(tmp_path, index_page)
    assert report2.redirects_created == 0
    assert Redirect.objects.count() == 1


def test_dry_run_writes_nothing_to_the_database(tmp_path, index_page):
    _write_article(tmp_path, "1001", title="Preview Only")

    report = _run(tmp_path, index_page, write=False)

    assert report.imported == ["'Preview Only' (1001)"]
    assert BlogPost.objects.count() == 0
    assert Redirect.objects.count() == 0


def test_post_with_no_filed_under_imports_uncategorised(tmp_path, index_page):
    _write_article(tmp_path, "1001", title="No Label Post", labels=[])

    report = _run(tmp_path, index_page)

    assert report.uncategorised_no_label == 1
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.category is None
    assert post.original_category_label == ""


def test_unmapped_label_is_surfaced_not_silently_dropped(tmp_path, index_page):
    _write_article(tmp_path, "1001", title="Mystery Label Post", labels=["A Totally New Label"])

    report = _run(tmp_path, index_page)

    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.category is None
    assert post.original_category_label == "A Totally New Label"
    assert any("A Totally New Label" in note for note in report.notes)


def test_local_image_is_copied_and_attached_as_featured_image(tmp_path, index_page):
    _write_local_image(tmp_path, "abc123.gif")
    _write_article(
        tmp_path, "1001", title="Post With Image",
        body='<img src="../images/abc123.gif" alt="A description"/><p>Text after image.</p>',
    )

    report = _run(tmp_path, index_page)

    assert report.images_copied == 1
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.featured_image is not None
    assert post.featured_image.title == "A description"


def test_same_local_image_referenced_by_two_posts_is_copied_once(tmp_path, index_page):
    # index_page (via make_home_page) already seeds a couple of images of
    # its own for HomePage's required StreamField sections — so this
    # asserts the *change* in image count, not an absolute total.
    before = get_image_model().objects.count()
    _write_local_image(tmp_path, "shared.gif")
    _write_article(tmp_path, "1001", title="Post One", body='<img src="../images/shared.gif"/><p>One.</p>')
    _write_article(tmp_path, "1002", title="Post Two", body='<img src="../images/shared.gif"/><p>Two.</p>')

    report = _run(tmp_path, index_page)

    assert report.images_copied == 1
    assert report.images_reused == 1
    assert get_image_model().objects.count() - before == 1


def test_rerun_reuses_already_copied_images_and_copies_none_new(tmp_path, index_page):
    before = get_image_model().objects.count()
    _write_local_image(tmp_path, "abc123.gif")
    _write_article(tmp_path, "1001", title="Post With Image", body='<img src="../images/abc123.gif"/><p>Text.</p>')

    _run(tmp_path, index_page)
    assert get_image_model().objects.count() - before == 1

    report2 = _run(tmp_path, index_page)

    assert report2.images_copied == 0
    assert get_image_model().objects.count() - before == 1


def test_broken_local_image_is_skipped_and_post_still_imports(tmp_path, index_page):
    """The real archive contains 268 files under images/ that are, on
    inspection, saved HTML error pages rather than real images (a dead
    external image link at archive time) — importing must not crash on
    these, or take the whole post down with them."""
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "broken.jpg").write_text("<!DOCTYPE html><html>404</html>", encoding="utf-8")
    _write_article(
        tmp_path, "1001", title="Post With Broken Image",
        body='<img src="../images/broken.jpg"/><p>Real text survives.</p>',
    )

    report = _run(tmp_path, index_page)

    assert report.imported == ["'Post With Broken Image' (1001)"]
    assert len(report.images_failed) == 1
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.featured_image is None
    assert "Real text survives" in str(post.body)


def test_external_image_is_dropped_not_downloaded(tmp_path, index_page):
    """Out of this import's explicit scope: local images are a file copy,
    external addresses are not fetched over the network."""
    _write_article(
        tmp_path, "1001", title="Post With External Image",
        body='<img src="https://dead-image-host.example/old.jpg"/><p>Text survives.</p>',
    )

    report = _run(tmp_path, index_page)

    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.featured_image is None
    assert "Text survives" in str(post.body)
    assert any("external address" in note for note in report.notes)


def test_original_category_label_preserves_every_label_even_though_one_bucket_is_chosen(tmp_path, index_page):
    # "relationships" and "transits" are both seeded by
    # blog.0004_seed_keen_categories already — not (re-)created here.
    _write_article(tmp_path, "1001", title="Multi Label Post", labels=["Jupiter", "Relationships and love"])

    _run(tmp_path, index_page)

    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.original_category_label == "Jupiter, Relationships and love"
    # "relationships" outranks "transits" in BUCKET_PRIORITY.
    assert post.category.slug == "relationships"


# ---------------------------------------------------------------------------
# Repair: a post whose content is unchanged but whose image(s) previously
# failed to copy (e.g. an unwritable media directory at the time) gets its
# image(s) on a later run, without a rewrite of content that already
# succeeded. This is the defect this module's own task fixed.
# ---------------------------------------------------------------------------


def test_image_that_failed_to_copy_is_repaired_on_a_later_run(tmp_path, index_page):
    # First run: the archive file under images/ is not a real image (the
    # same "archived error page" case as test_broken_local_image_is_
    # skipped_and_post_still_imports) — the post still imports, but with
    # no image, exactly as this task's real-world trigger (every image
    # copy failing) played out for content.
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "photo.jpg").write_text("<!DOCTYPE html><html>404</html>", encoding="utf-8")
    _write_article(
        tmp_path, "1001", title="Post Needing Repair",
        body='<img src="../images/photo.jpg"/><p>Real text survives.</p>',
    )

    report1 = _run(tmp_path, index_page)
    assert report1.imported == ["'Post Needing Repair' (1001)"]
    assert len(report1.images_failed) == 1
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.featured_image is None
    hash_after_run1 = post.keen_content_hash

    # "Fix the environment": the same archive filename now resolves to a
    # real image. Content (title, text, labels, filenames referenced) is
    # completely unchanged, so the content hash will not change either —
    # this is exactly the case the content hash is blind to.
    (tmp_path / "images" / "photo.jpg").write_bytes(_TINY_GIF)

    report2 = _run(tmp_path, index_page)

    assert report2.imported == []
    assert report2.updated == []
    assert report2.unchanged == []
    assert report2.repaired == ["'Post Needing Repair' (1001)"]
    assert report2.images_copied == 1

    post.refresh_from_db()
    assert post.keen_content_hash == hash_after_run1  # content itself never changed
    assert post.featured_image is not None
    assert "Real text survives" in str(post.body)
    assert KeenImportedImage.objects.filter(archive_filename="photo.jpg").exists()


def test_repair_does_not_touch_a_post_whose_image_is_still_broken(tmp_path, index_page):
    """Content unchanged, image still failing (media directory still
    unwritable, say) — must stay a genuine no-op on the DB side, not be
    reported as a repair that didn't happen."""
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "photo.jpg").write_text("<!DOCTYPE html><html>404</html>", encoding="utf-8")
    _write_article(
        tmp_path, "1001", title="Still Broken",
        body='<img src="../images/photo.jpg"/><p>Text.</p>',
    )
    _run(tmp_path, index_page)
    post = BlogPost.objects.get(keen_post_id="1001")
    revision_count_before = post.revisions.count()

    report2 = _run(tmp_path, index_page)  # image file is still the broken one

    assert report2.repaired == []
    assert report2.unchanged == ["'Still Broken' (1001)"]
    assert len(report2.images_failed) == 1
    post.refresh_from_db()
    assert post.revisions.count() == revision_count_before
    assert post.featured_image is None


def test_rerun_after_a_repair_is_a_true_no_op(tmp_path, index_page):
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "photo.jpg").write_text("<!DOCTYPE html><html>404</html>", encoding="utf-8")
    _write_article(
        tmp_path, "1001", title="Repaired Then Stable",
        body='<img src="../images/photo.jpg"/><p>Text.</p>',
    )
    _run(tmp_path, index_page)
    (tmp_path / "images" / "photo.jpg").write_bytes(_TINY_GIF)
    _run(tmp_path, index_page)  # the repair run

    post = BlogPost.objects.get(keen_post_id="1001")
    revision_count_after_repair = post.revisions.count()
    last_published_after_repair = post.last_published_at
    images_before = get_image_model().objects.count()

    report3 = _run(tmp_path, index_page)

    assert report3.repaired == []
    assert report3.unchanged == ["'Repaired Then Stable' (1001)"]
    assert report3.imported == []
    assert report3.updated == []
    assert report3.images_copied == 0
    post.refresh_from_db()
    assert post.revisions.count() == revision_count_after_repair
    assert post.last_published_at == last_published_after_repair
    assert get_image_model().objects.count() == images_before


def test_dry_run_previews_a_repair_without_writing_anything(tmp_path, index_page):
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "photo.jpg").write_text("<!DOCTYPE html><html>404</html>", encoding="utf-8")
    _write_article(
        tmp_path, "1001", title="Preview Repair",
        body='<img src="../images/photo.jpg"/><p>Text.</p>',
    )
    _run(tmp_path, index_page)
    (tmp_path / "images" / "photo.jpg").write_bytes(_TINY_GIF)
    images_before = get_image_model().objects.count()

    report = _run(tmp_path, index_page, write=False)

    assert report.repaired == ["'Preview Repair' (1001)"]
    assert any("DRY RUN" in note and "photo.jpg" in note for note in report.notes)
    post = BlogPost.objects.get(keen_post_id="1001")
    assert post.featured_image is None  # nothing actually written
    assert get_image_model().objects.count() == images_before


def test_cross_run_dedup_survives_a_wagtail_storage_rename(tmp_path, index_page):
    """
    Regression test for the defect found while building the repair path:
    Wagtail's storage renames a file on a storage-name collision, which
    broke the pre-existing cross-run "already copied, don't copy again"
    guarantee for any archive filename that happens to collide with
    something already on disk. KeenImportedImage removes the dependency
    on Wagtail's own stored filename, so this must keep working even
    when a rename happens.
    """
    default_storage.save("original_images/collide.gif", ContentFile(_TINY_GIF))

    _write_local_image(tmp_path, "collide.gif")
    _write_article(tmp_path, "1001", title="Post One", body='<img src="../images/collide.gif"/><p>One.</p>')

    before = get_image_model().objects.count()
    _run(tmp_path, index_page)
    assert get_image_model().objects.count() - before == 1

    _write_article(tmp_path, "1002", title="Post Two", body='<img src="../images/collide.gif"/><p>Two.</p>')
    report2 = _run(tmp_path, index_page)

    assert report2.images_copied == 0
    assert report2.images_reused == 1
    assert get_image_model().objects.count() - before == 1


# ---------------------------------------------------------------------------
# Up-front media-root writability check. A loud warning, not a refusal to
# run — a post's text still matters even when its images can't land right
# now, and this run's own posts are exactly what a later repair run fixes.
# ---------------------------------------------------------------------------


def test_write_mode_warns_up_front_when_media_root_is_not_writable_but_still_imports(
    tmp_path, index_page, monkeypatch
):
    from apps.blog.keen_import import importer as importer_module

    def _boom(name, content, max_length=None):
        raise PermissionError("Permission denied (simulated)")

    monkeypatch.setattr(importer_module.default_storage, "save", _boom)
    _write_article(tmp_path, "1001", title="Still Imports As Text")

    report = KeenImporter(write=True, index_page=index_page).run(str(tmp_path))

    assert report.media_root_warning is not None
    assert "not" in report.media_root_warning and "writable" in report.media_root_warning
    assert report.imported == ["'Still Imports As Text' (1001)"]
    assert BlogPost.objects.filter(keen_post_id="1001").exists()

    lines: list[str] = []
    report.write_summary(lines.append)
    assert "MEDIA DIRECTORY NOT WRITABLE" in lines[1]


def test_dry_run_does_not_check_media_root_writability(tmp_path, index_page, monkeypatch):
    from apps.blog.keen_import import importer as importer_module

    def _boom(name, content, max_length=None):
        raise PermissionError("Permission denied (simulated)")

    monkeypatch.setattr(importer_module.default_storage, "save", _boom)
    _write_article(tmp_path, "1001", title="Preview Only")

    report = KeenImporter(write=False, index_page=index_page).run(str(tmp_path))

    assert report.media_root_warning is None
    assert report.imported == ["'Preview Only' (1001)"]


# ---------------------------------------------------------------------------
# Reporting: a permission-flavoured image failure must be unmissable, not
# just one more line among many indistinguishable ones.
# ---------------------------------------------------------------------------


def test_write_summary_calls_out_permission_failures_loudly():
    report = ImportReport()
    report.images_failed.append(
        ("'Some Post' (1001): photo.jpg", f"{_PERMISSION_MARKER} writing to the media directory: boom")
    )

    lines: list[str] = []
    report.write_summary(lines.append)

    text = "\n".join(lines)
    assert "ENVIRONMENT PROBLEM" in text
    assert "not writable" in text


def test_write_summary_says_nothing_extra_when_failures_are_not_permission_related():
    report = ImportReport()
    report.images_failed.append(("'Some Post' (1001): photo.jpg", "not a valid image file"))

    lines: list[str] = []
    report.write_summary(lines.append)

    text = "\n".join(lines)
    assert "ENVIRONMENT PROBLEM" not in text

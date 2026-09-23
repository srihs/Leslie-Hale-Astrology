"""
Orchestrate the Keen archive import against the real database.

This is the only module in `apps.blog.keen_import` that writes anything.
Reading the archive (`parser.py`) and choosing a category bucket
(`categories.py`) are already tested in isolation; this module's job is
narrower and higher-stakes: decide, for each parsed entry, whether it is
new/changed/unchanged, and — only when `write=True` — create or update
exactly one `BlogPost`, copy its local images into Wagtail, and record a
redirect from its old keen.com address.

Body HTML is sanitised through `apps.blog.blogger_import.sanitize`
unchanged — the *same* Wagtail allowlist path the Blogger importer uses,
not a second copy of it, per this task's brief. The Keen HTML is messier
in places (Word's `MsoNormal`/nested-span markup, `<font>` tags, IM-chat
transcript markup in a few "astro-chat" posts) but nothing about it needs
a different allowlist, only the same defensive cleanup already built.

Idempotency (binding, per the migration rules this app operates under):

- Matching is on `BlogPost.keen_post_id` (the numeric ID at the end of
  each post's original keen.com URL), never on title or slug.
- A content fingerprint (`BlogPost.keen_content_hash`) is compared
  *before* any write or image copy, so a second run over an unchanged
  archive does nothing at all to that post beyond confirming it is
  unchanged — reported separately as "unchanged", not "updated".
- A post whose parsed content genuinely differs from what is stored is
  updated in place — same page, same URL, same `keen_post_id` — never
  duplicated.
- A local image already copied into Wagtail (matched by its archive
  filename, which — Keen's own convention — is already a content hash
  like `ff89d795bce6c539.jpg`, not a display name) is reused rather than
  copied again, so a second run copies zero new image files.
- Nothing already in the database is ever deleted. A post/image/redirect
  that cannot be reconciled is logged (`failed`/`skipped`/`notes`) and the
  run moves on to the next entry.

Images: the task scope is explicit — "Import the 779 local images into
Wagtail images and rewrite references... a file copy, not a download."
The real archive also contains `<img>` tags pointing at *external*
addresses (long-dead image hosts like tinypic.com/postimg.org, and Keen's
own live-chat-widget avatar icons embedded in a handful of "astro-chat"
transcript posts) that were evidently never archived locally. Those are
out of this import's scope — fetching them would be a network download
this task didn't ask for, and several of the hosts are confirmed dead —
so they are dropped from the imported body and logged as a note, the same
"log it and move on, never invent" treatment as any other unreconcilable
image.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from apps.blog.blogger_import.importer import _derive_excerpt, _title_from_filename
from apps.blog.blogger_import.sanitize import ExtractedImage, sanitize_content
from apps.blog.keen_import.categories import resolve_bucket_slug
from apps.blog.keen_import.parser import KeenEntry, parse_archive

EXCERPT_MAX_LENGTH = 300
DEFAULT_AUTHOR = "Leslie Hale"  # matches BlogPost.author_name's own model default
MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: Magic-byte sniffing for the handful of archived images whose filename
#: extension does not match their real format (confirmed against the real
#: archive: one file, `51c65241f051eeb4.aspx`, is actually a GIF — Wagtail
#: validates the *file's* extension, so it is copied in under a corrected
#: name, same bytes, rather than rejected or renamed to something
#: invented). Checked in order; first match wins.
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
]

#: A real archive turned out to include, under `images/` and with an
#: image extension, files that are not images at all: 268 of the 779
#: local files are actually saved HTML (`<!DOCTYPE html>...`) — almost
#: certainly a dead external image link that whatever tool built this
#: archive followed and saved the resulting error page for, under the
#: filename the real image would have had. Wagtail's image pipeline
#: (Willow) does not fail gracefully on this: asked to open HTML as an
#: image, one of its format probes (`ElementTree.parse`, checking for
#: SVG) raises an uncaught `xml.etree.ElementTree.ParseError` instead of
#: reporting "not an image" — which would otherwise take the whole post
#: down with it. So every local file is checked against a real image
#: magic-byte signature *before* it is ever handed to Wagtail; anything
#: that isn't recognised is treated as a per-image failure (logged,
#: skipped, the rest of the post still imports) rather than letting
#: Willow's exception propagate.
_IMAGE_SIGNATURES: list[bytes] = [
    b"GIF87a",
    b"GIF89a",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",  # JPEG
    b"BM",  # BMP
]


def _looks_like_a_real_image(data: bytes) -> bool:
    if any(data.startswith(sig) for sig in _IMAGE_SIGNATURES):
        return True
    # WEBP: "RIFF"<4-byte size>"WEBP"
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


class ImportAborted(Exception):
    """A whole-run problem (no BlogIndexPage, unreadable archive path) —
    distinct from a single entry failing. Stops the run before anything
    is written."""


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    images_copied: int = 0
    images_reused: int = 0
    images_failed: list[tuple[str, str]] = field(default_factory=list)
    redirects_created: int = 0
    redirects_updated: int = 0
    uncategorised_no_label: int = 0

    def write_summary(self, out) -> None:
        out(f"Imported (new posts):     {len(self.imported)}")
        out(f"Updated (changed):        {len(self.updated)}")
        out(f"Unchanged (no-op):        {len(self.unchanged)}")
        out(f"Skipped:                  {len(self.skipped)}")
        out(f"Failed:                   {len(self.failed)}")
        out(f"Images copied (new):      {self.images_copied}")
        out(f"Images reused (existing): {self.images_reused}")
        out(f"Images failed:            {len(self.images_failed)}")
        out(f"Redirects created:        {self.redirects_created}")
        out(f"Redirects updated:        {self.redirects_updated}")
        out(f"Posts with no label at all (imports uncategorised): {self.uncategorised_no_label}")

        if self.skipped:
            out("")
            out("Skipped, with reasons:")
            for identifier, reason in self.skipped:
                out(f"  - {identifier}: {reason}")

        if self.failed:
            out("")
            out("Failed, with reasons:")
            for identifier, reason in self.failed:
                out(f"  - {identifier}: {reason}")

        if self.images_failed:
            out("")
            out("Images that failed to copy:")
            for identifier, reason in self.images_failed:
                out(f"  - {identifier}: {reason}")

        if self.notes:
            out("")
            out("Content review notes (accessibility, categorisation, formatting):")
            for note in self.notes:
                out(f"  - {note}")


class KeenImporter:
    """
    One instance per invocation of the management command. Holds the
    run's configuration; `run(archive_path)` does the work and returns an
    `ImportReport`.
    """

    def __init__(
        self,
        *,
        write: bool,
        limit: int | None = None,
        index_page=None,
    ):
        self.write = write
        self.limit = limit
        self.index_page = index_page
        self._category_cache: dict[str, object | None] = {}
        #: filename (as it appears in the archive's images/ directory) ->
        #: already-saved wagtail Image, built once per run so a file
        #: referenced by many posts is only ever copied once, and so a
        #: second run over the same archive finds everything already
        #: copied in run 1 and copies nothing again.
        self._image_cache: dict[str, object] | None = None

    # -- top level ---------------------------------------------------

    def run(self, archive_path: str) -> ImportReport:
        report = ImportReport()
        index_page = self._resolve_index_page()
        archive = Path(archive_path)

        entries, parse_errors = parse_archive(archive)
        for filename, reason in parse_errors:
            report.skipped.append((filename, reason))

        if self.limit is not None:
            entries = entries[: self.limit]

        if self.write:
            self._image_cache = self._build_image_cache()

        for entry in entries:
            identifier = f"{entry.title!r} ({entry.keen_post_id})"
            try:
                self._process_entry(entry, index_page, archive, report, identifier)
            except Exception as exc:  # noqa: BLE001 - one bad post must not stop the run
                report.failed.append((identifier, f"{exc.__class__.__name__}: {exc}"))

        return report

    def _resolve_index_page(self):
        from apps.blog.models import BlogIndexPage

        if self.index_page is not None:
            return self.index_page

        index_page = BlogIndexPage.objects.first()
        if index_page is None:
            raise ImportAborted(
                "No BlogIndexPage exists yet. Create the Blog index page in "
                "Wagtail admin (under Home) first, then re-run the import — "
                "the importer never guesses where to file imported posts."
            )
        return index_page

    def _build_image_cache(self) -> dict[str, object]:
        from wagtail.images import get_image_model
        import os

        ImageModel = get_image_model()
        cache: dict[str, object] = {}
        for image in ImageModel.objects.all():
            cache[os.path.basename(image.file.name)] = image
        return cache

    # -- per entry -----------------------------------------------------

    def _process_entry(self, entry: KeenEntry, index_page, archive: Path, report: ImportReport, identifier: str) -> None:
        from apps.blog.models import BlogPost

        title = (entry.title or "").strip()[:255] or "(untitled)"
        published = _ensure_aware(entry.published)
        author_name = (entry.author or "").strip() or DEFAULT_AUTHOR

        existing = BlogPost.objects.filter(keen_post_id=entry.keen_post_id).first()

        sanitized = sanitize_content(entry.content_html)
        local_images, external_image_count = _split_local_images(sanitized.images, archive)

        if not entry.labels:
            report.uncategorised_no_label += 1
        category, category_note = self._resolve_category(entry.labels)
        if category_note:
            report.notes.append(f"{identifier}: {category_note}")

        excerpt = _derive_excerpt(sanitized)

        content_hash = _compute_hash(
            title=title,
            entry=entry,
            published=published,
            category=category,
            excerpt=excerpt,
            author_name=author_name,
            sanitized=sanitized,
            local_image_filenames=[img.filename for img in local_images],
        )

        if existing is not None and existing.keen_content_hash == content_hash:
            report.unchanged.append(identifier)
            return

        if external_image_count:
            report.notes.append(
                f"{identifier}: {external_image_count} image(s) pointed at an external address "
                "(not in the archive's local images/ folder) — not imported (out of scope: a "
                "file copy, not a network download) and dropped from the post body. Review the "
                f"original at {entry.source_file!r} for anything that needs re-adding by hand."
            )

        if not self.write:
            from wagtail.contrib.redirects.models import Redirect

            action = "update" if existing is not None else "create"
            redirect_preview = f"redirect {Redirect.normalise_path(entry.original_url)!r} -> this post"
            report.notes.append(
                f"{identifier}: DRY RUN would {action} — category="
                f"{category.name if category else 'none (needs manual categorisation)'}, "
                f"{len(local_images)} local image(s) to copy, {redirect_preview}"
            )
            self._append_content_notes(identifier, sanitized, report)
            if existing is not None:
                report.updated.append(identifier)
            else:
                report.imported.append(identifier)
            return

        # -- write mode from here ------------------------------------

        copied_images: list[object | None] = []
        for image in local_images:
            was_cached = image.filename in self._image_cache
            wagtail_image, err = self._copy_image(image, archive)
            if err:
                report.images_failed.append((f"{identifier}: {image.filename}", err))
                copied_images.append(None)
            else:
                copied_images.append(wagtail_image)
                if was_cached:
                    report.images_reused += 1
                else:
                    report.images_copied += 1

        body = _build_streamfield_body(sanitized.blocks, local_images, copied_images)
        if not body:
            report.skipped.append(
                (identifier, "sanitised content was empty (no text survived cleanup and no "
                 "image copied successfully) — review the original Keen post manually")
            )
            return

        featured_image = next((img for img in copied_images if img is not None), None)

        if existing is not None:
            post = existing
            post.title = title
            post.published_date = published
            post.excerpt = excerpt
            post.featured_image = featured_image or post.featured_image
            post.category = category or post.category
            post.original_category_label = entry.raw_label_text
            post.body = body
            post.author_name = author_name
            post.source_url = entry.original_url or post.source_url
            post.keen_content_hash = content_hash
            post.first_published_at = post.first_published_at or published
            post.last_published_at = published
            post.save()
            post.save_revision(log_action=False)
            report.updated.append(identifier)
        else:
            post = self._new_post(
                index_page=index_page,
                entry=entry,
                title=title,
                published=published,
                excerpt=excerpt,
                featured_image=featured_image,
                category=category,
                body=body,
                author_name=author_name,
                content_hash=content_hash,
            )
            report.imported.append(identifier)

        self._append_content_notes(identifier, sanitized, report)
        self._upsert_redirect(entry, post, report)

    def _new_post(
        self,
        *,
        index_page,
        entry: KeenEntry,
        title: str,
        published,
        excerpt,
        featured_image,
        category,
        body,
        author_name,
        content_hash,
    ):
        from wagtail.models import Page

        from apps.blog.models import BlogPost

        base_slug = slugify(title)[:50] or "post"
        slug = base_slug
        suffix = 2
        while Page.objects.child_of(index_page).filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        post = BlogPost(
            title=title,
            slug=slug,
            published_date=published,
            excerpt=excerpt,
            featured_image=featured_image,
            category=category,
            original_category_label=entry.raw_label_text,
            body=body,
            author_name=author_name,
            source_url=entry.original_url,
            keen_post_id=entry.keen_post_id,
            keen_content_hash=content_hash,
            live=True,
            first_published_at=published,
            last_published_at=published,
        )
        index_page.add_child(instance=post)
        post.save_revision(log_action=False)
        return post

    # -- categorisation --------------------------------------------------

    def _resolve_category(self, labels: list[str]):
        from apps.blog.models import BlogCategory

        slug, unmapped = resolve_bucket_slug(labels)

        note = None
        if unmapped:
            note = (
                "label(s) " + ", ".join(repr(label) for label in unmapped) + " are not in the "
                "known Keen label -> category mapping (apps.blog.keen_import.categories) — "
                "left out of automatic categorisation. The original text is still preserved on "
                "the post's 'Original category label' field."
            )

        if slug is None:
            return None, note

        if slug not in self._category_cache:
            self._category_cache[slug] = BlogCategory.objects.filter(slug=slug).first()
        category = self._category_cache[slug]

        if category is None:
            missing_note = (
                f"mapped to category slug {slug!r}, which does not exist yet in "
                "BlogCategory — run the category-seeding migration first. Left uncategorised."
            )
            note = f"{note} " + missing_note if note else missing_note

        return category, note

    # -- images ------------------------------------------------------

    def _copy_image(self, image: "_LocalImage", archive: Path):
        from wagtail.images import get_image_model

        assert self._image_cache is not None

        cached = self._image_cache.get(image.filename)
        if cached is not None:
            return cached, None

        file_path = archive / "images" / image.filename
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return None, f"could not read {file_path}: {exc}"

        if not data:
            return None, "empty file on disk"
        if len(data) > MAX_IMAGE_BYTES:
            return None, f"exceeds the {MAX_IMAGE_BYTES}-byte safety limit for a single image"
        if not _looks_like_a_real_image(data):
            return None, (
                "not a valid image file (its content doesn't match any known image format — "
                "looks like an archived error page saved under an image filename, most likely "
                "a dead external image link at the time this archive was made)"
            )

        filename = _corrected_filename(image.filename, data)

        # Alt text is never invented (alt-text-design skill): if the
        # archive's <img> supplied one, it becomes the image's title
        # (Wagtail's default alt source); otherwise the title is just the
        # filename, and the report flags this image as needing a real one
        # written by Leslie.
        title = image.alt or _title_from_filename(filename)

        ImageModel = get_image_model()
        try:
            wagtail_image = ImageModel(title=title, file=ContentFile(data, name=filename))
            wagtail_image.save()
        except Exception as exc:  # noqa: BLE001 - a bad single image must not fail the whole post
            return None, f"could not save into Wagtail: {exc.__class__.__name__}: {exc}"

        self._image_cache[image.filename] = wagtail_image
        return wagtail_image, None

    # -- redirects -----------------------------------------------------

    def _upsert_redirect(self, entry: KeenEntry, post, report: ImportReport) -> None:
        from wagtail.contrib.redirects.models import Redirect

        old_path = Redirect.normalise_path(entry.original_url)
        if old_path in ("", "/"):
            report.notes.append(
                f"{post.title!r}: original URL normalised to the site root — skipped, no "
                "redirect created for '/'."
            )
            return

        # A redirect is only ever consulted for a response that already
        # came back 404 (wagtail.contrib.redirects.middleware.
        # RedirectMiddleware.process_response checks response.status_code
        # first) — so even in the unlikely case old_path coincides with a
        # real page on this site, that page still serves normally and this
        # redirect simply never fires. No collision check is needed.
        _, created = Redirect.objects.update_or_create(
            old_path=old_path,
            site=None,
            defaults={
                "redirect_page": post,
                "redirect_link": "",
                "is_permanent": True,
            },
        )
        if created:
            report.redirects_created += 1
        else:
            report.redirects_updated += 1

    # -- reporting -------------------------------------------------------

    def _append_content_notes(self, identifier: str, sanitized, report: ImportReport) -> None:
        if sanitized.heading_fixups:
            report.notes.append(
                f"{identifier}: {sanitized.heading_fixups} heading(s) normalised to <h3>/<h4> "
                "(some inferred from bold/styled text, not real heading tags) — check heading "
                "structure and order against the original post."
            )
        for image in sanitized.images:
            if _local_image_filename(image.src) is None:
                # External source, dropped entirely (see the module
                # docstring) — no point flagging alt text on an image
                # that was never imported.
                continue
            if not image.alt:
                report.notes.append(
                    f"{identifier}: image {image.src!r} has no alt text — add one in Wagtail "
                    "admin before publishing (not invented by the importer)."
                )
        if sanitized.generic_links:
            joined = "; ".join(sanitized.generic_links)
            report.notes.append(
                f"{identifier}: generic link text found ({joined}) — rewrite to describe the "
                "destination (e.g. not 'click here')."
            )
        if sanitized.dropped_inline_images:
            report.notes.append(
                f"{identifier}: {sanitized.dropped_inline_images} image(s) nested inside a "
                "link alongside other text were dropped rather than imported — review the "
                "original post for images that may be missing."
            )


# ---------------------------------------------------------------------------
# Free functions — no state, easy to test on their own.
# ---------------------------------------------------------------------------


@dataclass
class _LocalImage:
    filename: str
    alt: str


def _split_local_images(images: list[ExtractedImage], archive: Path) -> tuple[list[_LocalImage], int]:
    """
    Archive-local image references look like `../images/<filename>`
    (confirmed: every one of the 779 distinct local image references in
    the real archive resolves to a real file under `images/`, with no
    exceptions). Anything else is an external address, out of this
    import's scope (see the module docstring) — counted, not copied.
    """
    local: list[_LocalImage] = []
    external_count = 0
    for image in images:
        filename = _local_image_filename(image.src)
        if filename is None:
            external_count += 1
            continue
        local.append(_LocalImage(filename=filename, alt=image.alt))
    return local, external_count


def _local_image_filename(src: str) -> str | None:
    prefix = "../images/"
    if not src.startswith(prefix):
        return None
    filename = src[len(prefix):].strip()
    # Defensive: reject anything that would escape the images/ directory
    # or carry a query string / fragment — the real archive's local
    # references are always a bare filename, never any of this.
    if not filename or "/" in filename or "\\" in filename or "?" in filename or "#" in filename:
        return None
    return filename


def _corrected_filename(filename: str, data: bytes) -> str:
    """
    One file in the real archive (`51c65241f051eeb4.aspx`) is a real GIF
    saved under a non-image extension (evidently inherited from a
    dynamically-generated source URL) — Wagtail's image field validates
    the file's extension, so a mismatch would otherwise fail to import a
    real, present image for no content reason. Sniffed from the file's
    own magic bytes, applied only when it disagrees with the extension
    already on disk; the bytes themselves are copied unmodified either
    way.
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    current_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    for signature, ext in _MAGIC_SIGNATURES:
        if data.startswith(signature):
            if current_ext != ext:
                return f"{stem}.{ext}"
            return filename

    return filename


def _ensure_aware(value):
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value)


def _build_streamfield_body(blocks, local_images: list[_LocalImage], copied_images: list[object | None]):
    """
    Mirrors `apps.blog.blogger_import.importer._build_streamfield_body`,
    adapted for the fact that `sanitized.images` here may include external
    (out-of-scope, never copied) images interleaved with local ones —
    `local_images`/`copied_images` only cover the local subset, so each
    "image" block is matched against `local_images` by source-image
    identity rather than assumed to line up 1:1 with `sanitized.blocks`.
    """
    # Positional queue: `local_images`/`copied_images` were derived from
    # `sanitized.images` by filtering out external ones in document order
    # (see `_split_local_images`), so walking `blocks` and advancing this
    # queue only on a *local* image placeholder keeps the two in step.
    local_iter = iter(zip(local_images, copied_images))
    body = []
    for kind, value in blocks:
        if kind == "text":
            body.append(("text", value))
        elif kind == "image":
            extracted: ExtractedImage = value
            if _local_image_filename(extracted.src) is None:
                # External image, out of scope — already logged in the
                # per-entry notes; drop just this block.
                continue
            try:
                local, wagtail_image = next(local_iter)
            except StopIteration:
                continue
            if wagtail_image is None:
                # Copy failed — already logged in images_failed; drop
                # just this block rather than fail the whole post.
                continue
            body.append(("image", {"image": wagtail_image, "caption": ""}))
    return body


def _compute_hash(*, title, entry: KeenEntry, published, category, excerpt, author_name, sanitized, local_image_filenames) -> str:
    text_blocks = [value for kind, value in sanitized.blocks if kind == "text"]
    payload = json.dumps(
        {
            "title": title,
            "author": author_name,
            "published": published.isoformat(),
            "category": category.slug if category else None,
            "original_labels": entry.raw_label_text,
            "excerpt": excerpt,
            "text_blocks": text_blocks,
            "local_image_filenames": local_image_filenames,
            "source_url": entry.original_url,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

"""
Orchestrate the Blogger import against the real database.

This is the only module in `apps.blog.blogger_import` that writes
anything. Everything it depends on for fetching (`feed.py`) and cleaning
(`sanitize.py`) is Django/Wagtail-light and already tested in isolation;
this module's job is narrower and higher-stakes: decide, for each parsed
entry, whether it is new/changed/unchanged, and — only when `write=True` —
create or update exactly one `BlogPost`, download its images, and record a
redirect from its old Blogger address.

Idempotency (binding, per the migration rules this app operates under):

- Matching is on `BlogPost.blogger_post_id`, never on title or slug.
- A content fingerprint (`BlogPost.blogger_content_hash`) is compared
  *before* any write or image download, so a second run over an unchanged
  export does nothing at all to that post beyond confirming it is
  unchanged — reported separately as "unchanged", not "updated".
- A post whose upstream content genuinely changed is updated in place —
  same page, same URL, same `blogger_post_id` — never duplicated.
- Nothing already in the database is ever deleted. A post/image/redirect
  that cannot be reconciled is logged (`failed`/`skipped`/`notes`) and the
  run moves on to the next entry.
- `_build_streamfield_body` never leaves the image promoted to
  `featured_image` also sitting in the body (see that function's own
  docstring) — this importer was never run against real content (the
  live import path is `apps.blog.keen_import`, see
  `apps/blog/models.py`'s module docstring), so there is no equivalent
  "repair posts already written with the duplicate" mechanism here the
  way `apps.blog.keen_import.importer` has one: nothing has ever written
  that duplicate through this path for a repair mechanism to fix.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from apps.blog.blogger_import.feed import BloggerEntry
from apps.blog.blogger_import.sanitize import ExtractedImage, sanitize_content

DEFAULT_TIMEOUT = 20
DEFAULT_USER_AGENT = "LeslieHaleAstrology-BloggerImporter/1.0 (+wagtail import command)"
ALLOWED_IMAGE_SCHEMES = {"http", "https"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
EXCERPT_MAX_LENGTH = 300
DEFAULT_AUTHOR = "Leslie Hale"  # matches BlogPost.author_name's own model default


class ImportAborted(Exception):
    """A whole-run problem (no BlogIndexPage, unreadable source, bad
    category map) — distinct from a single entry failing. Stops the run
    before anything is written."""


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    images_downloaded: int = 0
    images_failed: list[tuple[str, str]] = field(default_factory=list)
    redirects_created: int = 0
    redirects_updated: int = 0

    def write_summary(self, out) -> None:
        out(f"Imported (new posts):   {len(self.imported)}")
        out(f"Updated (changed):      {len(self.updated)}")
        out(f"Unchanged (no-op):      {len(self.unchanged)}")
        out(f"Skipped:                {len(self.skipped)}")
        out(f"Failed:                 {len(self.failed)}")
        out(f"Images downloaded:      {self.images_downloaded}")
        out(f"Images failed:          {len(self.images_failed)}")
        out(f"Redirects created:      {self.redirects_created}")
        out(f"Redirects updated:      {self.redirects_updated}")

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
            out("Images that failed to download:")
            for identifier, reason in self.images_failed:
                out(f"  - {identifier}: {reason}")

        if self.notes:
            out("")
            out("Content review notes (accessibility, categorisation, formatting):")
            for note in self.notes:
                out(f"  - {note}")


class BloggerImporter:
    """
    One instance per invocation of the management command. Holds the
    run's configuration; `run(source)` does the work and returns an
    `ImportReport`.
    """

    def __init__(
        self,
        *,
        write: bool,
        limit: int | None = None,
        category_map: dict[str, str] | None = None,
        index_page=None,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pages: int = 200,
        max_bytes: int = 100 * 1024 * 1024,
    ):
        self.write = write
        self.limit = limit
        self.category_map = category_map or {}
        self.index_page = index_page
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.max_bytes = max_bytes
        self._category_cache: dict[str, object | None] = {}

    # -- top level ---------------------------------------------------

    def run(self, source: str) -> ImportReport:
        from apps.blog.blogger_import import feed as feed_module

        report = ImportReport()

        index_page = self._resolve_index_page()

        try:
            documents = feed_module.fetch_documents(
                source,
                timeout=self.timeout,
                user_agent=self.user_agent,
                max_pages=self.max_pages,
                max_bytes=self.max_bytes,
            )
        except feed_module.FeedFetchError as exc:
            raise ImportAborted(str(exc)) from exc

        entries, parse_errors = feed_module.parse_documents(documents)
        for err in parse_errors:
            report.skipped.append((err, "could not be parsed from the feed"))

        if self.limit is not None:
            entries = entries[: self.limit]

        for entry in entries:
            identifier = f"{entry.title!r} ({entry.blogger_id})"
            try:
                self._process_entry(entry, index_page, report, identifier)
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

    # -- per entry -----------------------------------------------------

    def _process_entry(self, entry: BloggerEntry, index_page, report: ImportReport, identifier: str) -> None:
        from apps.blog.models import BlogPost

        # Page.title has a max_length (255); a Blogger title is very
        # unlikely to exceed it, but truncating defensively here beats a
        # ValidationError aborting an otherwise-good post.
        title = (entry.title or "").strip()[:255] or "(untitled)"

        published = _ensure_aware(entry.published)
        updated = _ensure_aware(entry.updated) if entry.updated else None

        existing = BlogPost.objects.filter(blogger_post_id=entry.blogger_id).first()

        sanitized = sanitize_content(entry.content_html)
        category, category_note = self._resolve_category(entry.labels)
        if category_note:
            report.notes.append(f"{identifier}: {category_note}")

        excerpt = _derive_excerpt(sanitized)
        author_name = entry.author_name.strip() or DEFAULT_AUTHOR

        content_hash = _compute_hash(
            title=title,
            entry=entry,
            published=published,
            updated=updated,
            category=category,
            excerpt=excerpt,
            author_name=author_name,
            sanitized=sanitized,
        )

        if existing is not None and existing.blogger_content_hash == content_hash:
            report.unchanged.append(identifier)
            return

        if not self.write:
            from wagtail.contrib.redirects.models import Redirect

            action = "update" if existing is not None else "create"
            image_count = len(sanitized.images)
            redirect_preview = (
                f"redirect {Redirect.normalise_path(entry.original_url)!r} -> this post"
                if entry.original_url
                else "no redirect (no original URL in export)"
            )
            report.notes.append(
                f"{identifier}: DRY RUN would {action} — category="
                f"{category.name if category else 'none (needs manual categorisation)'}, "
                f"{image_count} image(s) to download, live={not entry.is_draft}, {redirect_preview}"
            )
            self._append_content_notes(identifier, sanitized, report)
            if existing is not None:
                report.updated.append(identifier)
            else:
                report.imported.append(identifier)
            return

        # -- write mode from here ------------------------------------

        downloaded_images: list[object | None] = []
        for image in sanitized.images:
            wagtail_image, err = self._download_image(image, post_title=title)
            if err:
                report.images_failed.append((f"{identifier}: {image.src}", err))
                downloaded_images.append(None)
            else:
                report.images_downloaded += 1
                downloaded_images.append(wagtail_image)

        body = _build_streamfield_body(sanitized.blocks, downloaded_images)
        if not body:
            report.skipped.append(
                (identifier, "sanitised content was empty (no text survived cleanup and no "
                 "image downloaded successfully) — review the original Blogger post manually")
            )
            return

        featured_image = next((img for img in downloaded_images if img is not None), None)
        is_live = not entry.is_draft

        if existing is not None:
            post = existing
            post.title = title
            post.published_date = published
            post.excerpt = excerpt
            post.featured_image = featured_image or post.featured_image
            post.category = category or post.category
            post.body = body
            post.author_name = author_name
            post.source_url = entry.original_url or post.source_url
            post.blogger_content_hash = content_hash
            post.live = is_live
            post.first_published_at = post.first_published_at or published
            post.last_published_at = updated or published
            post.save()
            post.save_revision(log_action=False)
            report.updated.append(identifier)
        else:
            post = self._new_post(
                index_page=index_page,
                entry=entry,
                title=title,
                published=published,
                updated=updated,
                excerpt=excerpt,
                featured_image=featured_image,
                category=category,
                body=body,
                author_name=author_name,
                content_hash=content_hash,
                is_live=is_live,
            )
            report.imported.append(identifier)

        self._append_content_notes(identifier, sanitized, report)
        self._upsert_redirect(entry, post, report)

    def _new_post(
        self,
        *,
        index_page,
        entry: BloggerEntry,
        title: str,
        published,
        updated,
        excerpt,
        featured_image,
        category,
        body,
        author_name,
        content_hash,
        is_live,
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
            body=body,
            author_name=author_name,
            source_url=entry.original_url,
            blogger_post_id=entry.blogger_id,
            blogger_content_hash=content_hash,
            live=is_live,
            first_published_at=published,
            last_published_at=updated or published,
        )
        index_page.add_child(instance=post)
        post.save_revision(log_action=False)
        return post

    # -- categorisation --------------------------------------------------

    def _resolve_category(self, labels: list[str]):
        """
        Never invents a taxonomy. `BlogCategory` is a small, editor-curated
        list (apps/blog/models.py) — this only ever maps to a category that
        already exists, via an explicit `--category-map` the operator
        supplies. With no map, or no match, the post is left uncategorised
        (the model supports this deliberately) and the original Blogger
        label(s) are surfaced in the report for a human to act on.
        """
        from apps.blog.models import BlogCategory

        if not labels:
            return None, None

        if self.category_map:
            for label in labels:
                slug = self.category_map.get(label) or self.category_map.get(label.lower())
                if not slug:
                    continue
                if slug not in self._category_cache:
                    self._category_cache[slug] = BlogCategory.objects.filter(slug=slug).first()
                category = self._category_cache[slug]
                if category is not None:
                    return category, None
                return (
                    None,
                    f"--category-map maps Blogger label {label!r} to category slug "
                    f"{slug!r}, which does not exist — left uncategorised.",
                )

        return (
            None,
            "Blogger label(s) " + ", ".join(repr(l) for l in labels) + " were not "
            "categorised automatically — set a category in Wagtail admin, or pass "
            "--category-map to map Blogger labels to existing categories.",
        )

    # -- images ------------------------------------------------------

    def _download_image(self, image: ExtractedImage, *, post_title: str):
        from wagtail.images import get_image_model

        parsed = urlparse(image.src)
        if parsed.scheme not in ALLOWED_IMAGE_SCHEMES:
            return None, f"unsupported URL scheme {parsed.scheme!r} — not downloaded"

        request = urllib.request.Request(image.src, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read(MAX_IMAGE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            return None, f"download failed: {exc}"

        if len(data) > MAX_IMAGE_BYTES:
            return None, f"exceeds the {MAX_IMAGE_BYTES}-byte safety limit for a single image"
        if content_type and not content_type.startswith("image/"):
            return None, f"unexpected content type {content_type!r} (not an image)"
        if not data:
            return None, "empty response body"

        filename = _filename_from_url(image.src)
        # Alt text is never invented (alt-text-design skill): if Blogger
        # supplied one, it becomes the image's title (Wagtail's default alt
        # source); otherwise the title is just the filename, and the
        # report flags this image as needing a real one written by Leslie.
        title = image.alt or _title_from_filename(filename)

        ImageModel = get_image_model()
        wagtail_image = ImageModel(title=title, file=ContentFile(data, name=filename))
        wagtail_image.save()
        return wagtail_image, None

    # -- redirects -----------------------------------------------------

    def _upsert_redirect(self, entry: BloggerEntry, post, report: ImportReport) -> None:
        from wagtail.contrib.redirects.models import Redirect

        if not entry.original_url:
            report.notes.append(
                f"{post.title!r}: no original Blogger URL in the export — no redirect created."
            )
            return

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


def _ensure_aware(value: datetime) -> datetime:
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value)


def _derive_excerpt(sanitized) -> str:
    """
    Derived from the post's own first paragraph of real text, never
    fabricated — matches BlogPost.excerpt's own help text ("Leave blank to
    use the start of the post instead"): this *is* the start of the post.
    """
    for kind, value in sanitized.blocks:
        if kind != "text":
            continue
        plain = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
        if plain:
            return _truncate(plain, EXCERPT_MAX_LENGTH - 3)
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0]
    return f"{truncated}…"


def _build_streamfield_body(blocks, downloaded_images):
    """
    The *first* successfully downloaded image is the one `_process_entry`
    promotes to `BlogPost.featured_image` (`next((img for img in
    downloaded_images if img is not None), None)`, aligned with this
    function's own walk over `downloaded_images` in the same document
    order). That image is deliberately left OUT of the body here:
    templates/blog/post.html renders `featured_image` as
    `figure.article-hero` and then the body with `{% include_block %}`,
    so leaving it in the body too printed the same photo twice on every
    post that had one (see apps.blog.keen_import.importer's identical
    fix, which this mirrors). Only the first occurrence of the promoted
    image is skipped — a post that legitimately repeats its own hero
    image further down the article keeps that later occurrence.
    """
    image_iter = iter(downloaded_images)
    body = []
    promoted_to_hero_already_skipped = False
    for kind, value in blocks:
        if kind == "text":
            body.append(("text", value))
        elif kind == "image":
            wagtail_image = next(image_iter)
            if wagtail_image is None:
                # Download failed — already logged in images_failed; drop
                # just this block rather than fail the whole post.
                continue
            if not promoted_to_hero_already_skipped:
                promoted_to_hero_already_skipped = True
                continue
            body.append(("image", {"image": wagtail_image, "caption": ""}))
    return body


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = unquote(os.path.basename(path)) or "image"
    if "." not in name:
        name += ".jpg"
    return name[:100]


def _title_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    return stem.replace("-", " ").replace("_", " ").strip() or "Imported image"


def _compute_hash(*, title: str, entry: BloggerEntry, published, updated, category, excerpt, author_name, sanitized) -> str:
    text_blocks = [value for kind, value in sanitized.blocks if kind == "text"]
    image_srcs = [image.src for image in sanitized.images]
    payload = json.dumps(
        {
            "title": title,
            "author": author_name,
            "published": published.isoformat(),
            "updated": updated.isoformat() if updated else None,
            "is_draft": entry.is_draft,
            "category": category.slug if category else None,
            "excerpt": excerpt,
            "text_blocks": text_blocks,
            "image_srcs": image_srcs,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_category_map(path: str) -> dict[str, str]:
    """
    Load an operator-supplied `--category-map` JSON file: a flat
    `{"Blogger label": "existing-category-slug"}` mapping. Never
    auto-generated — the importer does not invent a category taxonomy
    (content-strategy skill / apps/blog/models.py's own design intent);
    this is a human decision fed in as configuration.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ImportAborted(f"Could not read --category-map file {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ImportAborted(f"--category-map file {path!r} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ImportAborted(
            f"--category-map file {path!r} must be a flat JSON object of "
            '"Blogger label": "category-slug" string pairs.'
        )
    return data

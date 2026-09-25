"""
One-time backfill for `blog.KeenImportedImage`.

That table is the fix for a real defect (see
`apps.blog.keen_import.importer`'s module docstring, "Idempotency"
section, and `KeenImportedImage`'s own docstring for the full story): a
re-run of the Keen import needs a reliable way to tell "this archive
image was already copied in" apart from "never copied", and it turns out
Wagtail's own storage filename can't be trusted for that (it renames on
a storage-name collision, and the importer itself corrects one archived
file's extension) — so the importer now keeps its own map instead.

That map starts *empty* the moment this migration ships. A database that
already has Keen-imported posts from *before* `KeenImportedImage`
existed has, from the importer's point of view, zero images on record —
meaning the very next `import_keen --write` run would see every
already-correct image as missing and re-copy every one of them, each as
a brand new duplicate Wagtail Image. This command exists purely to avoid
that: it populates the map from what's already there, once, so the next
import run only repairs what's actually missing.

Deliberately conservative, in keeping with this app's own "never invent"
rule: an image whose stored filename doesn't look like an untouched
archive filename (Wagtail applies a random suffix on an actual
storage-name collision) is left alone and reported rather than guessed
at. A wrong guess here would make a later import silently attach the
wrong image to a filename; a gap just costs one redundant, harmless
re-copy from the archive next run. In real production data this should
be rare to nonexistent — Keen's archive filenames are content-hash-like
and effectively unique, so a genuine storage collision between two
different archived images isn't expected to happen.

Safe to re-run: `get_or_create` on `archive_filename`, and it only ever
fills gaps, never overwrites a row a real import run already wrote.
"""

from __future__ import annotations

import os
import re

from django.core.management.base import BaseCommand

_WAGTAIL_COLLISION_SUFFIX = re.compile(r"^.+_[A-Za-z0-9]{7}$")

# The one archived file (see importer.py's `_corrected_filename`) known
# to be stored under a different extension than its archive name.
_KNOWN_EXTENSION_CORRECTIONS = {
    "51c65241f051eeb4.gif": "51c65241f051eeb4.aspx",
}


class Command(BaseCommand):
    help = (
        "One-time backfill of blog.KeenImportedImage from already-imported Keen "
        "posts' images, for a database that had Keen content imported before that "
        "table existed. Safe to re-run; only fills gaps."
    )

    def handle(self, *args, **options):
        from apps.blog.models import BlogPost, KeenImportedImage

        created = 0
        already_mapped = 0
        skipped: list[tuple[int, str]] = []
        seen_image_ids: set[int] = set()

        posts = BlogPost.objects.filter(keen_post_id__isnull=False).select_related("featured_image")
        for post in posts:
            images = []
            if post.featured_image_id:
                images.append(post.featured_image)
            for block in post.body:
                if block.block_type == "image":
                    image = block.value.get("image")
                    if image is not None:
                        images.append(image)

            for image in images:
                if image.id in seen_image_ids:
                    continue
                seen_image_ids.add(image.id)

                basename = os.path.basename(image.file.name)
                if basename in _KNOWN_EXTENSION_CORRECTIONS:
                    archive_filename = _KNOWN_EXTENSION_CORRECTIONS[basename]
                elif _WAGTAIL_COLLISION_SUFFIX.match(basename):
                    skipped.append((image.id, basename))
                    continue
                else:
                    archive_filename = basename

                _, was_created = KeenImportedImage.objects.get_or_create(
                    archive_filename=archive_filename,
                    defaults={"image": image},
                )
                if was_created:
                    created += 1
                else:
                    already_mapped += 1

        self.stdout.write(self.style.MIGRATE_HEADING("Keen image map backfill — results"))
        self.stdout.write(f"Mappings created:        {created}")
        self.stdout.write(f"Already mapped (no-op):  {already_mapped}")
        self.stdout.write(f"Skipped (needs review):  {len(skipped)}")

        if skipped:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "These images' stored filenames look like Wagtail renamed them to avoid a "
                    "storage-name collision, so this command can't safely recover their original "
                    "archive filename — the next import run will treat them as missing and "
                    "re-copy them from the archive (one harmless extra copy, not data loss). "
                    "Review by hand if that's not acceptable:"
                )
            )
            for image_id, basename in skipped:
                self.stdout.write(f"  - image id={image_id}: {basename!r}")

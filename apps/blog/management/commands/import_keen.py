"""
Import blog posts from Leslie's local Keen.com archive export (§5,
corrected: the old blog was never on Blogger — see apps/blog/models.py's
module docstring for that correction).

The archive path is a required argument, never hard-coded or guessed —
this command expects the directory that directly contains `index.html`,
`articles/` and `images/` (e.g. `keen_blog_archive/` at the repo root).

See `apps.blog.keen_import` for the actual parse/sanitise/import logic;
this file is deliberately thin — argument parsing and console reporting,
mirroring `import_blogger`'s own shape.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.blog.keen_import.importer import ImportAborted, KeenImporter
from apps.blog.keen_import.parser import KeenParseError


class Command(BaseCommand):
    help = (
        "Import blog posts from a local Keen.com archive export (a directory "
        "containing index.html, articles/*.html and images/). Prints a dry-run "
        "preview by default; pass --write to actually create/update posts. Safe "
        "to re-run: posts are matched on the numeric post ID in their original "
        "keen.com URL, never duplicated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "archive_path",
            help=(
                "Path to the Keen archive directory (contains index.html, "
                "articles/, images/) — e.g. keen_blog_archive/. Never guessed — "
                "always supplied explicitly."
            ),
        )
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help=(
                "Actually create/update posts, copy images, and create redirects. "
                "Without this flag the command only prints what it would do — this "
                "is the default, not an opt-in."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N articles found (sorted by Keen post ID). "
            "Useful for a quick test before a full run.",
        )
        parser.add_argument(
            "--index-page-id",
            dest="index_page_id",
            type=int,
            default=None,
            help="Wagtail page ID of the BlogIndexPage to import posts under. "
            "Defaults to the site's one BlogIndexPage (there can only be one — "
            "see apps/blog/models.py). Only needed to override that default.",
        )

    def handle(self, *args, **options):
        from apps.blog.models import BlogIndexPage

        archive_path = options["archive_path"]
        write = options["write"]

        index_page = None
        if options["index_page_id"] is not None:
            try:
                index_page = BlogIndexPage.objects.get(pk=options["index_page_id"])
            except BlogIndexPage.DoesNotExist as exc:
                raise CommandError(
                    f"No BlogIndexPage with id={options['index_page_id']!r}."
                ) from exc

        importer = KeenImporter(write=write, limit=options["limit"], index_page=index_page)

        mode = "WRITE" if write else "DRY RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Keen archive import — {mode} — source: {archive_path}"))
        if not write:
            self.stdout.write(
                "No changes will be made. Re-run with --write once this preview looks right."
            )
        self.stdout.write("")

        try:
            report = importer.run(archive_path)
        except (ImportAborted, KeenParseError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Keen archive import — {mode} — results"))
        report.write_summary(self.stdout.write)

        if not write and (report.imported or report.updated):
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "This was a dry run — nothing above was actually written. "
                    "Re-run with --write to apply it."
                )
            )

        if report.failed:
            raise CommandError(
                f"{len(report.failed)} post(s) failed to import — see the reasons above. "
                "Everything else in this run still completed; re-running is safe and will "
                "retry the failed ones without duplicating what already succeeded."
            )

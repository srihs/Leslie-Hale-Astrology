"""
Import blog posts from a Blogger export (§5).

The Blogger URL is an unconfirmed §8 item — this command takes its source
as a required argument and never hard-codes or guesses at one. It accepts
either the live export URL Leslie/the agency eventually confirm, or a
local export file, so it can be exercised without network access.

See `apps.blog.blogger_import` for the actual fetch/sanitise/import logic;
this file is deliberately thin — argument parsing and console reporting.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.blog.blogger_import.importer import BloggerImporter, ImportAborted, load_category_map


class Command(BaseCommand):
    help = (
        "Import blog posts from a Blogger Atom or RSS export — either the live "
        "export URL or a local export file. Prints a dry-run preview by default; "
        "pass --write to actually create/update posts. Safe to re-run: posts are "
        "matched on their Blogger post ID, never duplicated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            help=(
                "Where to read the export from: either the Blogger export/feed URL "
                "(http:// or https://) or the path to a local export XML file. "
                "Never guessed — always supplied explicitly."
            ),
        )
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help=(
                "Actually create/update posts, download images, and create redirects. "
                "Without this flag the command only prints what it would do — this is "
                "the default, not an opt-in."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N post entries found (after filtering to "
            "actual posts). Useful for a quick test before a full run.",
        )
        parser.add_argument(
            "--category-map",
            dest="category_map",
            default=None,
            help=(
                "Path to a JSON file mapping Blogger label -> existing Wagtail "
                'BlogCategory slug, e.g. {"Transits": "transits"}. Without this, '
                "imported posts are left uncategorised (Blogger's labels are logged "
                "in the report) — the importer never invents a category taxonomy."
            ),
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
        parser.add_argument(
            "--timeout",
            type=int,
            default=20,
            help="Timeout in seconds for each network request (feed pages and "
            "image downloads). Default: 20.",
        )
        parser.add_argument(
            "--user-agent",
            dest="user_agent",
            default=None,
            help="Override the User-Agent header sent when fetching the feed or "
            "downloading images.",
        )
        parser.add_argument(
            "--max-pages",
            dest="max_pages",
            type=int,
            default=200,
            help="Safety cap on how many paginated feed pages to follow when "
            "--source is a URL. Default: 200.",
        )
        parser.add_argument(
            "--max-bytes",
            dest="max_bytes",
            type=int,
            default=100 * 1024 * 1024,
            help="Safety cap, in bytes, on the size of a single feed response or "
            "local export file. Default: 100MB.",
        )

    def handle(self, *args, **options):
        from apps.blog.blogger_import import feed as feed_module
        from apps.blog.models import BlogIndexPage

        source = options["source"]
        write = options["write"]

        category_map = None
        if options["category_map"]:
            try:
                category_map = load_category_map(options["category_map"])
            except ImportAborted as exc:
                raise CommandError(str(exc)) from exc

        index_page = None
        if options["index_page_id"] is not None:
            try:
                index_page = BlogIndexPage.objects.get(pk=options["index_page_id"])
            except BlogIndexPage.DoesNotExist as exc:
                raise CommandError(
                    f"No BlogIndexPage with id={options['index_page_id']!r}."
                ) from exc

        kwargs = dict(
            write=write,
            limit=options["limit"],
            category_map=category_map,
            index_page=index_page,
            timeout=options["timeout"],
            max_pages=options["max_pages"],
            max_bytes=options["max_bytes"],
        )
        if options["user_agent"]:
            kwargs["user_agent"] = options["user_agent"]

        importer = BloggerImporter(**kwargs)

        mode = "WRITE" if write else "DRY RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Blogger import — {mode} — source: {source}"))
        if not write:
            self.stdout.write(
                "No changes will be made. Re-run with --write once this preview looks right."
            )
        self.stdout.write("")

        try:
            report = importer.run(source)
        except ImportAborted as exc:
            raise CommandError(str(exc)) from exc
        except feed_module.FeedFetchError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Blogger import — {mode} — results"))
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

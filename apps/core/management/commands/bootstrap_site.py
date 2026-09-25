"""
Build the initial site structure (PROJECT-SCOPE.md §4) so a freshly
migrated, empty database serves the real site instead of Wagtail's own
"Welcome to your new Wagtail site!" placeholder at "/".

See `apps.core.site_bootstrap` for what this actually does and why; this
file is deliberately thin — argument parsing and console reporting,
mirroring `import_keen`'s own shape (apps/blog/management/commands/
import_keen.py).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.site_bootstrap import SiteBootstrapper


class Command(BaseCommand):
    help = (
        "Create HomePage and its five §4 children (About, Readings, Booking, Blog, "
        "Contact) if they don't already exist, and point Wagtail's Site record at "
        "HomePage. Prints a dry-run preview by default; pass --write to actually "
        "create anything. Safe to re-run on a database that already has some or all "
        "of this: existing pages are never modified, re-parented or deleted."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help=(
                "Actually create the page tree and repoint the Site record. Without "
                "this flag the command only prints what it would do — this is the "
                "default, not an opt-in."
            ),
        )

    def handle(self, *args, **options):
        write = options["write"]
        mode = "WRITE" if write else "DRY RUN"

        self.stdout.write(self.style.MIGRATE_HEADING(f"Site bootstrap — {mode}"))
        if not write:
            self.stdout.write(
                "No changes will be made. Re-run with --write once this preview looks right."
            )
        self.stdout.write("")

        report = SiteBootstrapper(write=write).run()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Site bootstrap — {mode} — results"))
        report.write_summary(self.stdout.write)

        if not write and report.created:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "This was a dry run — nothing above was actually written. "
                    "Re-run with --write to apply it."
                )
            )

"""
Remove the placeholder "Sample post N" blog pages seeded during the
build, so only the real Keen archive import populates the blog (this
task's explicit instruction).

Deliberately its own command, not a step folded silently into
`import_keen`: deleting content is exactly the one thing that command's
migration rules say an importer must never do, so cleaning up seed data
gets its own separate, explicit, dry-run-by-default action instead of
living inside an importer that is bound to never delete anything.

Matches on title only (`^Sample post \\d+$`), scoped to `BlogPost` —
never touches any other page type or app. Dry run by default, same as
`import_keen`, even though this is deleting synthetic placeholder pages
rather than irreplaceable source content: a bulk delete based on a
pattern match is still worth previewing before it runs for real.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand

SAMPLE_POST_TITLE_RE = re.compile(r"^Sample post \d+$")


class Command(BaseCommand):
    help = (
        "Delete the placeholder 'Sample post N' pages seeded during the build "
        "(title matches exactly, e.g. 'Sample post 1', 'Sample post 11'). Prints "
        "what would be deleted by default; pass --write to actually delete."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help="Actually delete the matching pages. Without this flag the "
            "command only lists what it would delete — this is the default, "
            "not an opt-in.",
        )

    def handle(self, *args, **options):
        from apps.blog.models import BlogPost

        write = options["write"]

        candidates = [
            post for post in BlogPost.objects.all().order_by("id")
            if SAMPLE_POST_TITLE_RE.match(post.title)
        ]

        mode = "WRITE" if write else "DRY RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Remove sample blog posts — {mode}"))
        self.stdout.write("")

        if not candidates:
            self.stdout.write("No 'Sample post N' pages found — nothing to do.")
            return

        for post in candidates:
            self.stdout.write(f"  - [{post.id}] {post.title!r} (slug: {post.slug})")

        self.stdout.write("")
        if write:
            deleted_count = 0
            for post in candidates:
                post.delete()
                deleted_count += 1
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} sample post(s)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"This was a dry run — {len(candidates)} page(s) listed above would be "
                    "deleted. Re-run with --write to actually delete them."
                )
            )

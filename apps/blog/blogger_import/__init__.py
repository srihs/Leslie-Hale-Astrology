"""
The Blogger import (§5). Owned by blog-migration.

This package is deliberately separate from the `import_blogger` management
command itself: the command (apps/blog/management/commands/import_blogger.py)
is a thin CLI wrapper — argument parsing and console reporting only — over
the pieces here, so each piece can be exercised and tested on its own
without spinning up a full management command / database:

- `feed.py`    — fetch a Blogger Atom/RSS export (URL or local file) and
                 parse it into plain `BloggerEntry` data. No Django/Wagtail
                 imports; safe to unit test with static XML fixtures.
- `sanitize.py` — turn one entry's raw Blogger HTML into the site's own
                 StreamField block shape, stripped to a safe allowlist, with
                 images extracted for separate download. No Django ORM
                 writes; returns data plus human-readable notes.
- `importer.py` — orchestrates the above against the database: dry-run
                 preview, idempotent match-and-write, image download,
                 redirect creation, and the final counts report. This is
                 the only module in this package that touches the database.

See the module docstrings in each file, and the `import_blogger` management
command's help text, for the full picture.
"""

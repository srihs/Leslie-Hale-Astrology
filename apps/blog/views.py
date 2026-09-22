"""
BlogIndexPage and BlogPost are served by Wagtail's normal page-serving
mechanism (get_context + templates) — no custom views are needed for the
structural skeleton.

The Blogger import itself (reading the old feed/export and creating
BlogPost instances) is a management command owned by blog-migration, not
a view, and does not belong in this file.
"""

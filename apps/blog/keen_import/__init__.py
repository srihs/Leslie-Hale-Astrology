"""
Import Leslie's real blog archive — a local export of her old Keen.com
blog (`keen_blog_archive/`, 1460 posts, 2009-2026) — replacing the
now-corrected §8 assumption that the old blog was on Blogger.

See `apps.blog.keen_import.parser` (reads the archive), `.categories`
(the ~66 original "Filed Under" labels -> 8 curated BlogCategory
buckets) and `.importer` (the only module here that writes anything).
`apps.blog.blogger_import` is untouched by this package — it was built,
reviewed and tested against the Blogger assumption and is left in place
rather than deleted on a corrected guess — but it is no longer the live
import path; `manage.py import_keen` is.
"""

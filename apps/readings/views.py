"""
ReadingsIndexPage and ReadingDetailPage are served by Wagtail's normal
page-serving mechanism (Page.get_context + their templates) — no custom
views are needed for the structural skeleton.

Any htmx partial (e.g. filtering the readings list) is htmx-frontend's to
add here.
"""

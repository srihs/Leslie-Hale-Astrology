"""
apps.core has no routed views of its own — it supplies settings, snippets
and shared StreamField blocks consumed by other apps' pages and templates.

If a shared, non-page view (e.g. a small htmx partial reused across
sections) is ever needed, it belongs here, but that is htmx-frontend's
call to make, not wagtail-backend's.
"""

"""
apps.core has no routed *page* views of its own — it supplies settings,
snippets and shared StreamField blocks consumed by other apps' pages and
templates.

`robots_txt` is the one exception: a small, settings-driven view (not a
page, and not a static file — see its own docstring and
config/settings/base.py:SEARCH_ENGINE_INDEXING_ALLOWED) that seo-analytics
owns, wired directly in config/urls.py.

If a shared, non-page view (e.g. a small htmx partial reused across
sections) is ever needed, it belongs here, but that is htmx-frontend's
call to make, not wagtail-backend's.
"""

from django.conf import settings
from django.http import HttpResponse


def robots_txt(request):
    """
    Driven entirely from settings.SEARCH_ENGINE_INDEXING_ALLOWED, never a
    static file, so one environment variable controls it rather than a
    text file someone has to remember to swap per deploy. See that
    setting's own comment (config/settings/base.py) for why DEBUG alone
    can't be used to tell a Prohosting staging host apart from production
    — both are expected to run config.settings.prod.

    Defaults to disallowing every user agent everywhere. Only when the
    flag is explicitly set does this permit indexing and point crawlers at
    the sitemap.
    """
    if getattr(settings, "SEARCH_ENGINE_INDEXING_ALLOWED", False):
        lines = [
            "User-agent: *",
            "Allow: /",
            "",
            f"Sitemap: https://{settings.CANONICAL_DOMAIN}/sitemap.xml",
        ]
    else:
        lines = ["User-agent: *", "Disallow: /"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")

"""
Site-wide SEO context: the canonical URL for the current request, the
site's canonical origin (for building other absolute URLs, e.g. an
og:image rendition), and the sitewide default share image.

Deliberately independent of Wagtail's own Site model (Sites -> hostname,
editable in Wagtail admin): that field is decided by whoever configures
the Wagtail Site record, and if it's ever left at Wagtail's own
"localhost" default, or pointed at a staging host, every page's canonical
URL and Open Graph links would silently follow it. `settings.CANONICAL_DOMAIN`
(config/settings/base.py) is instead one deliberate, environment-backed
value seo-analytics owns — see that setting's own comment.
"""

from django.conf import settings

# The homepage hero's own photo (Unsplash License, photo-1462331940025-
# 496dfbfc7564 — see templates/home/index.html for the same credit) is the
# one real, already-approved image every visitor sees regardless of which
# page they land on. Reused here as the sitewide default Open Graph/Twitter
# share image rather than commissioning or inventing a new "social card"
# asset — design-system was never asked for one, and §5 is basic on-page
# SEO, not a new visual asset. Pages with a real image of their own
# (a blog post's featured image, Leslie's portrait, a reading's photo)
# override this per-page — see each template's `og_image` block.
DEFAULT_OG_IMAGE = (
    "https://images.unsplash.com/photo-1462331940025-496dfbfc7564"
    "?w=1200&h=630&fit=crop&q=75&auto=format"
)


def seo(request):
    origin = f"https://{settings.CANONICAL_DOMAIN}" if settings.CANONICAL_DOMAIN else request.build_absolute_uri("/").rstrip("/")
    return {
        "canonical_url": f"{origin}{request.path}",
        "seo_site_origin": origin,
        "default_og_image": DEFAULT_OG_IMAGE,
    }

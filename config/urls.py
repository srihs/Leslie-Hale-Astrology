from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from apps.blog.feeds import BlogFeed


def healthz(request):
    """
    Liveness/readiness probe for the web service's Docker HEALTHCHECK and
    any compose/orchestrator healthcheck. Deliberately outside apps/ — this
    is infra plumbing, not a page any agent owns.
    """
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("sitemap.xml", sitemap),
    # Fixed address, independent of whatever slug the Blog index page ends
    # up with, and ahead of the wagtail_urls catch-all below so it can
    # never be shadowed by a page Leslie creates (apps/blog/feeds.py).
    path("blog/rss/", BlogFeed(), name="blog_rss"),
    # Non-page htmx/no-JS form endpoints only (FINDING 1, reviews/
    # 2026-09-22-project-structure-scaffold.md). Wagtail pages (Home,
    # About, Readings, Blog, Booking, Contact) are all served by the
    # wagtail_urls catch-all below and are addressed with {% pageurl %},
    # not a name here. "forms/" keeps these off the same path space as
    # Leslie's page slugs, so a page she creates can never be shadowed by
    # one of these endpoints.
    path("forms/contact/", include("apps.contact.urls")),
    path("forms/booking/", include("apps.bookings.urls")),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page-serving catch-all goes last.
urlpatterns += [
    path("", include(wagtail_urls)),
]

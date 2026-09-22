from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls


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
    # apps.contact, apps.bookings and apps.blog register their own url
    # patterns here once those packages exist (wagtail-backend /
    # booking-payments / blog-migration / htmx-frontend own that include()).
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page-serving catch-all goes last.
urlpatterns += [
    path("", include(wagtail_urls)),
]

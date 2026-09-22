from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    Shared, cross-cutting building blocks: Wagtail settings (contact details,
    analytics), the Testimonial snippet, and StreamField blocks reused by
    other apps' pages. This app owns no page type of its own except the
    About page, which has no more natural home in the six-app split.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Site-wide settings and shared content"

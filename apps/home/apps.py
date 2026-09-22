from django.apps import AppConfig


class HomeConfig(AppConfig):
    """The homepage: a single StreamField-driven page in the fixed §7 order."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.home"
    label = "home"
    verbose_name = "Homepage"

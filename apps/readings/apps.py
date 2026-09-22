from django.apps import AppConfig


class ReadingsConfig(AppConfig):
    """Readings (§4 'Services'): the Reading snippet, and the Services index
    and per-reading detail pages that present it."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.readings"
    label = "readings"
    verbose_name = "Readings & Services"

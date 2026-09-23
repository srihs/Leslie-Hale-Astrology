from django.apps import AppConfig


class BackofficeConfig(AppConfig):
    """
    The bespoke admin at /manage/ (task brief: "Wagtail's own admin is
    too complex for the client, so she will never see it"). This app
    owns no content of its own — every screen reads and writes models
    defined in apps.readings / apps.bookings / apps.core / apps.contact /
    apps.blog. See apps/backoffice/models.py for the one thing it does
    define: a marker permission, not a content model.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backoffice"
    label = "backoffice"
    verbose_name = "Management dashboard"

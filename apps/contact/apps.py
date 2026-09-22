from django.apps import AppConfig


class ContactConfig(AppConfig):
    """The Contact page, plus local storage for contact form submissions
    and newsletter signups. No email-marketing platform is wired in here —
    §8 leaves that choice open."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contact"
    label = "contact"
    verbose_name = "Contact & Newsletter"

from django.apps import AppConfig


class BlogConfig(AppConfig):
    """The blog: index page and post page, including the fields the
    Blogger migration needs to preserve original URLs and dates."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.blog"
    label = "blog"
    verbose_name = "Blog"

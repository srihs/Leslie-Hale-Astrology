from __future__ import annotations

import factory
from django.utils import timezone

from apps.blog.models import BlogCategory, BlogIndexPage, BlogPost


class BlogCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BlogCategory

    name = factory.Sequence(lambda n: f"Category {n}")


def make_blog_index_page(home_page, **overrides):
    field_defaults = dict(title="Blog", slug=overrides.pop("slug", "blog-test"))
    field_defaults.update(overrides)
    index = BlogIndexPage(**field_defaults)
    home_page.add_child(instance=index)
    return index


def make_blog_post(index_page, **overrides):
    field_defaults = dict(
        title=overrides.pop("title", "A test post"),
        slug=overrides.pop("slug", None),
        published_date=overrides.pop("published_date", timezone.now()),
        excerpt="A short excerpt.",
        body=[("text", "<p>Body copy.</p>")],
        live=True,
    )
    if field_defaults["slug"] is None:
        from django.utils.text import slugify

        field_defaults["slug"] = slugify(field_defaults["title"])
    field_defaults.update(overrides)
    post = BlogPost(**field_defaults)
    index_page.add_child(instance=post)
    return post

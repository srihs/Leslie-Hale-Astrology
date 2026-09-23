"""
Blog posts screen (task item 6): CRUD over `blog.BlogPost` (a Wagtail
Page) through plain fields only — title, post text, excerpt, featured
image, category, published date, draft/live.

Does NOT touch apps/blog/*.py (blog-migration owns that concurrently);
BlogPost/BlogCategory/BlogIndexPage are imported here only as read/write
models, never redefined or altered.

Wagtail Page creation/publishing (`add_child`, `save_revision`,
`publish`/`unpublish`) doesn't map onto Django's generic CreateView/
UpdateView, which assume a plain `Model.save()` — so create and edit
share one hand-written view instead. No revision/moderation workflow is
exposed to Leslie: "draft/live" is the one control the task brief asked
for, implemented as directly as Wagtail allows (`revision.publish()` to
go live, `page.unpublish()` to go back to draft). Wagtail's own revision
history still records every save, even though Leslie never sees it.

A post's slug (and so its URL) is set once, at creation, from its title,
and is never recomputed on edit — changing a title later must not
silently break an already-published link or the RSS feed
(apps/blog/feeds.py) pointing at it.
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView

from apps.backoffice.content import (
    body_from_story_text,
    create_image_from_upload,
    story_text_from_body,
)
from apps.backoffice.forms import BlogPostForm
from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.blog.models import BlogIndexPage, BlogPost

PAGE_SIZE = 20


def _unique_slug(parent, title: str) -> str:
    base = slugify(title) or "post"
    slug = base
    n = 2
    while parent.get_children().filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class BlogPostListView(BackofficeAccessRequiredMixin, ListView):
    template_name = "backoffice/blog_list.html"
    context_object_name = "posts"
    paginate_by = PAGE_SIZE
    queryset = BlogPost.objects.select_related("featured_image", "category").order_by("-published_date")


class BlogPostFormView(BackofficeAccessRequiredMixin, View):
    """Shared create/edit view — see the module docstring for why."""

    template_name = "backoffice/blog_form.html"

    def get_object(self, pk):
        return get_object_or_404(BlogPost, pk=pk) if pk else None

    def get(self, request, pk=None):
        post = self.get_object(pk)
        initial = {}
        if post is not None:
            initial = {
                "title": post.title,
                "excerpt": post.excerpt,
                "body_text": story_text_from_body(post.body),
                "category": post.category,
                "published_date": post.published_date,
                "is_live": post.live,
            }
        form = BlogPostForm(initial=initial)
        return render(request, self.template_name, {"form": form, "post": post})

    def post(self, request, pk=None):
        post = self.get_object(pk)
        creating = post is None
        form = BlogPostForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "post": post})

        data = form.cleaned_data
        if creating:
            post = BlogPost(title=data["title"])

        post.title = data["title"]
        post.excerpt = data["excerpt"]
        existing_body = [] if creating else post.body
        post.body = body_from_story_text(existing_body, data["body_text"])
        post.category = data["category"]
        post.published_date = data["published_date"]

        upload = data.get("featured_image_upload")
        if upload:
            post.featured_image = create_image_from_upload(upload, title=data["title"])
        elif data.get("remove_featured_image"):
            post.featured_image = None

        if creating:
            parent = BlogIndexPage.objects.first()
            if parent is None:
                messages.error(
                    request, "No blog page exists yet — ask your developer to set one up."
                )
                return redirect(reverse("backoffice:blog_list"))
            post.slug = _unique_slug(parent, data["title"])
            parent.add_child(instance=post)
        else:
            post.save()

        revision = post.save_revision()
        if data["is_live"]:
            revision.publish()
        elif post.live:
            post.unpublish()

        messages.success(request, f"'{post.title}' saved.")
        return redirect(reverse("backoffice:blog_list"))


class BlogPostDeleteView(BackofficeAccessRequiredMixin, View):
    def get(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        return render(request, "backoffice/blog_confirm_delete.html", {"post": post})

    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        title = post.title
        post.delete()
        messages.success(request, f"'{title}' deleted.")
        return redirect(reverse("backoffice:blog_list"))

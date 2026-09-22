"""
The blog (§4/§5): index page, post page, and categorisation via tags.

`source_url` and the ability to set `published_date` explicitly exist so
the eventual Blogger migration (owned by blog-migration; the Blogger URL
itself is unconfirmed per §8) can preserve each post's original address
(for redirects) and original publish date, rather than every migrated
post appearing to have been written today.
"""

from django.db import models
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from apps.core.blocks import BodyTextBlock, CaptionedImageBlock


class BlogIndexPage(Page):
    """The blog listing page."""

    # templates/blog/index.html is the real file (FINDING 3).
    template = "blog/index.html"

    intro = models.TextField(
        blank=True,
        help_text="Optional introduction shown above the list of posts.",
    )

    content_panels = Page.content_panels + [FieldPanel("intro")]

    parent_page_types = ["home.HomePage"]
    subpage_types = ["blog.BlogPost"]
    max_count = 1

    class Meta:
        verbose_name = "Blog index page"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 note: `posts` is a queryset of real `BlogPost` pages —
        each has `.title`, `.url` (both from Page), `.published_date` (not
        `date`), `.excerpt`, `.featured_image` (an Image object, not
        `image_url` — render with {% image %}), and `.tags` (a taggable
        manager; there is no single `category` field on this model, only
        tags — see the module docstring). The queryset itself was already
        correctly scoped and prefetched; nothing here needed to change,
        only the field names templates read off each post.

        The category-filter/pagination htmx contract documented in
        templates/blog/partials/_post_list.html (`categories`, `pager`) is
        out of scope for this fix — it needs a decision about mapping tags
        to "categories" and paginating this same queryset, which belongs
        with whoever builds that htmx endpoint against this page's own
        URL, not a model/context change.
        """
        context = super().get_context(request, *args, **kwargs)
        context["posts"] = (
            BlogPost.objects.child_of(self)
            .live()
            .public()
            .order_by("-published_date")
            .select_related("featured_image")
            .prefetch_related("tags")
        )
        return context


class BlogPostTag(TaggedItemBase):
    """Through model connecting BlogPost to taggit's shared Tag table."""

    content_object = ParentalKey(
        "blog.BlogPost", on_delete=models.CASCADE, related_name="tagged_items"
    )


class BlogPost(Page):
    """A single blog article."""

    published_date = models.DateTimeField(
        help_text="When this post should appear as published. Backdate this "
        "for posts migrated from the old Blogger blog so they keep their "
        "original date.",
    )
    excerpt = models.CharField(
        max_length=300,
        blank=True,
        help_text="Short summary shown on the blog index and homepage. Leave "
        "blank to use the start of the post instead.",
    )
    featured_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Image shown with this post on the blog index and homepage.",
    )
    body = StreamField(
        [
            ("text", BodyTextBlock()),
            ("image", CaptionedImageBlock()),
        ],
        help_text="The post itself. Add as many text and image sections as "
        "you like, in whatever order reads best.",
    )
    author_name = models.CharField(
        max_length=100,
        default="Leslie Hale",
        help_text="Shown as this post's author. Change only for a guest post.",
    )
    source_url = models.URLField(
        blank=True,
        help_text="If this post was migrated from the old Blogger blog, paste "
        "its original address here so old links can be redirected to this page.",
    )
    tags = ClusterTaggableManager(
        through=BlogPostTag,
        blank=True,
        help_text="Categories/tags for this post, e.g. 'Mercury Retrograde', "
        "'Relationships'. Used to group related posts.",
    )

    # templates/blog/post.html is the real file (FINDING 3).
    template = "blog/post.html"

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("published_date"), FieldPanel("excerpt"), FieldPanel("featured_image")],
            heading="Post details",
        ),
        FieldPanel("body"),
        FieldPanel("author_name"),
    ]

    promote_panels = Page.promote_panels + [FieldPanel("tags")]

    settings_panels = Page.settings_panels + [FieldPanel("source_url")]

    parent_page_types = ["blog.BlogIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "Blog post"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 fix: this post's own fields are already on `page`
        (title, published_date, author_name, featured_image, tags, body —
        Wagtail puts `self` there automatically); no shadow context is
        added for those. `related_posts` is the one thing the template
        can't get any other way.
        """
        context = super().get_context(request, *args, **kwargs)
        context["related_posts"] = (
            BlogPost.objects.live()
            .public()
            .exclude(pk=self.pk)
            .order_by("-published_date")
            .select_related("featured_image")
            .prefetch_related("tags")[:2]
        )
        return context

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

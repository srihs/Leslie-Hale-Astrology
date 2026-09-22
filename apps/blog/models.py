"""
The blog (§4/§5): index page, post page, and categorisation.

Tags vs categories (2026-09-22 gap-closure task): §5 explicitly names
"categories" as an in-scope feature ("Blog (articles database, categories,
Blogger import)"), and the locked design (versions/v1-ephemeris/blog.html,
post.html) shows exactly one category per post — a single eyebrow tag
("Transits", "Everyday astrology", ...) and a single-select filter bar
("All / Transits / Everyday astrology / Signs / ..."), never a
comma-separated list. That is a categories model, not a tags model: one
value per post, editor-curated, filterable. The previous `tags`
(django-taggit ClusterTaggableManager) implementation let a post carry
any number of free-typed labels, which doesn't match that single-select
filter bar and isn't what §5 asked for, so it is replaced here with a
`BlogCategory` snippet and a single ForeignKey on BlogPost. `category` is
left optional (null/blank) rather than required, so blog-migration can
import Blogger posts in bulk before every one has been individually
categorised.

`source_url` and the ability to set `published_date` explicitly exist so
the eventual Blogger migration (owned by blog-migration; the Blogger URL
itself is unconfirmed per §8) can preserve each post's original address
(for redirects) and original publish date, rather than every migrated
post appearing to have been written today.

`blogger_post_id` and `blogger_content_hash` (2026-09-22, blog-migration)
back the importer's idempotency: `blogger_post_id` is the stable external
identifier the importer matches on so a second run over the same export
updates existing posts instead of duplicating them; `blogger_content_hash`
is an internal-only fingerprint of what the importer last wrote, so an
unchanged post can be recognised as unchanged and left untouched (no
redundant writes or image re-downloads) rather than every re-run being
treated as an update.
"""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.utils.text import slugify
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

from apps.core.blocks import BodyTextBlock, CaptionedImageBlock


@register_snippet
class BlogCategory(models.Model):
    """
    A blog category (§5), e.g. 'Transits' or 'Everyday astrology'. Kept as
    a snippet — rather than a free-text field on each post — so the
    category filter on the blog index always shows a short, curated list
    Leslie controls, instead of growing one entry per typo.
    """

    name = models.CharField(
        max_length=60,
        unique=True,
        help_text="The category name as visitors will see it, e.g. 'Transits'.",
    )
    slug = models.SlugField(
        max_length=60,
        unique=True,
        blank=True,
        help_text="Used in the category filter's web address. Leave blank to "
        "generate this automatically from the name.",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls the order categories appear in the filter bar. "
        "Lower numbers show first.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("order"),
    ]

    class Meta:
        verbose_name = "Blog category"
        verbose_name_plural = "Blog categories"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class BlogIndexPage(Page):
    """The blog listing page."""

    # templates/blog/index.html is the real file (FINDING 3).
    template = "blog/index.html"

    #: A technical display default, not a §8 business fact — chosen to
    #: read comfortably as three rows of the design's 3-up post grid.
    #: Safe for htmx-frontend to change without touching this model.
    POSTS_PER_PAGE = 9

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
        Supplies everything templates/blog/partials/_post_list.html needs
        for category filtering and pagination (both deferred pending the
        tags-vs-categories decision — see the module docstring; that
        decision is now made).

        `posts` is a queryset of real `BlogPost` pages — each has
        `.title`, `.url` (both from Page), `.published_date` (not
        `.date`), `.excerpt`, `.featured_image` (an Image object, not
        `.image_url` — render with {% image %}), and `.category` (a
        BlogCategory or None, with `.name` / `.slug` — there is no
        `.tags` any more, see the module docstring).

        Read from the query string:
          ?category=<slug>  filters to that category, if it exists
          ?page=<n>         which page of results to show

          categories        every BlogCategory, for the filter bar
          active_category   the BlogCategory matching ?category=, or None
                             (compare `category.slug == active_category.slug`
                             for aria-current, guarding for None)
          posts_page        a django.core.paginator Page: `.object_list`,
                             `.has_previous`/`.has_next`,
                             `.previous_page_number`/`.next_page_number`,
                             `.number`, `.paginator.num_pages`,
                             `.paginator.page_range`
          posts             convenience alias for `posts_page.object_list`,
                             for anywhere that only needs the post list and
                             not the pager controls
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "blog"

        posts = (
            BlogPost.objects.child_of(self)
            .live()
            .public()
            .select_related("featured_image", "category")
            .order_by("-published_date")
        )

        categories = BlogCategory.objects.all().order_by("order", "name")
        active_category = None
        category_slug = request.GET.get("category", "").strip()
        if category_slug:
            active_category = categories.filter(slug=category_slug).first()
            if active_category:
                posts = posts.filter(category=active_category)

        paginator = Paginator(posts, self.POSTS_PER_PAGE)
        try:
            posts_page = paginator.page(request.GET.get("page", 1))
        except PageNotAnInteger:
            posts_page = paginator.page(1)
        except EmptyPage:
            posts_page = paginator.page(paginator.num_pages)

        context["categories"] = categories
        context["active_category"] = active_category
        context["posts_page"] = posts_page
        context["posts"] = posts_page.object_list
        return context


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
    category = models.ForeignKey(
        "blog.BlogCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posts",
        help_text="Which category this post belongs to — shown as its tag "
        "and used by the blog's category filter. Set the category up first "
        "in Snippets → Blog categories, then choose it here.",
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
    blogger_post_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Set automatically by the Blogger importer (blog-migration). "
        "The stable ID of this post in the old Blogger export, used to match it "
        "on re-import so re-running the import updates this post instead of "
        "creating a duplicate. Leave blank for posts written directly in "
        "Wagtail — it is never required for a normal post.",
    )
    blogger_content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        help_text="Internal checksum of the content last written by the "
        "Blogger importer, used to detect whether a post changed upstream "
        "since the last import run. Not shown in the editor.",
    )

    # templates/blog/post.html is the real file (FINDING 3).
    template = "blog/post.html"

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("published_date"),
                FieldPanel("category"),
                FieldPanel("excerpt"),
                FieldPanel("featured_image"),
            ],
            heading="Post details",
        ),
        FieldPanel("body"),
        FieldPanel("author_name"),
    ]

    settings_panels = Page.settings_panels + [
        FieldPanel("source_url"),
        FieldPanel("blogger_post_id"),
    ]

    parent_page_types = ["blog.BlogIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "Blog post"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 fix: this post's own fields are already on `page`
        (title, published_date, author_name, featured_image, category,
        body — Wagtail puts `self` there automatically); no shadow
        context is added for those. `related_posts` is the one thing the
        template can't get any other way.
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "blog"
        context["related_posts"] = (
            BlogPost.objects.live()
            .public()
            .exclude(pk=self.pk)
            .order_by("-published_date")
            .select_related("featured_image", "category")[:2]
        )
        return context

"""
Readings (§4 "Services").

`Reading` is a snippet, not a page: it is the single source of truth for a
reading's name, summary and price, and it is reused in more than one
place — the homepage services teaser, the Services index grid, and the
booking form's choice of reading. Keeping it a snippet means Leslie edits
a price once and it updates everywhere it's shown, rather than hunting
down every page that mentions it.

`ReadingsIndexPage` is the Services page: a list of active readings.
`ReadingDetailPage` gives an individual reading its own URL, for a longer
description and for direct linking (SEO, booking deep-links) — its
short summary and price still come from the linked `Reading` snippet.
"""

from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

from apps.core.blocks import BodyTextBlock, CaptionedImageBlock, FAQListBlock


@register_snippet
class Reading(models.Model):
    """
    A single type of reading Leslie offers, e.g. "Natal Chart Reading".
    The final list of readings and their prices is unconfirmed (§8) —
    price is left blank until confirmed rather than guessed, and
    `price_note` lets Leslie show words instead of a number (e.g. "Price
    on enquiry") for as long as she needs to.
    """

    name = models.CharField(
        max_length=100,
        help_text="The name of this reading as visitors will see it, e.g. "
        "'Natal Chart Reading'.",
    )
    summary = models.CharField(
        max_length=220,
        help_text="A one- or two-sentence description shown on cards on the "
        "homepage and Services page.",
    )
    description = models.TextField(
        blank=True,
        help_text="A longer description for this reading's own page. Leave "
        "blank to show just the summary above.",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How long this reading usually takes, in minutes. Leave "
        "blank if it varies.",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price in NZD. Leave blank until pricing is confirmed — the "
        "note below will be shown instead of a number.",
    )
    price_note = models.CharField(
        max_length=60,
        blank=True,
        default="Price on enquiry",
        help_text="Shown instead of, or alongside, the price — e.g. 'From "
        "$150' or 'Price on enquiry'. Leave as-is until pricing is confirmed.",
    )
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image or icon representing this reading.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Untick to hide this reading from the site without "
        "deleting it (e.g. while it's temporarily unavailable).",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls the order readings are listed in. Lower numbers "
        "show first.",
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("name"), FieldPanel("summary"), FieldPanel("image")],
            heading="Basics",
        ),
        MultiFieldPanel([FieldPanel("description"), FieldPanel("duration_minutes")], heading="Details"),
        MultiFieldPanel([FieldPanel("price"), FieldPanel("price_note")], heading="Pricing"),
        MultiFieldPanel([FieldPanel("order"), FieldPanel("is_active")], heading="Display"),
    ]

    class Meta:
        verbose_name = "Reading"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ReadingsIndexPage(Page):
    """The Services page: an introduction plus the list of active readings."""

    # templates/readings/index.html is the real file (FINDING 3).
    template = "readings/index.html"

    intro = models.TextField(
        blank=True,
        help_text="Optional introduction shown above the list of readings.",
    )

    content_panels = Page.content_panels + [FieldPanel("intro")]

    parent_page_types = ["home.HomePage"]
    subpage_types = ["readings.ReadingDetailPage"]
    max_count = 1

    class Meta:
        verbose_name = "Services page"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 fix: `readings` is a queryset of `Reading` snippets, not
        Page objects — a Reading has no `slug`, `title`, `bullets` or
        `image_url` (see the model above). The real fields are `name`,
        `summary`, `description`, `duration_minutes`, `price`,
        `price_note`, `image` (a wagtailimages.Image, render with
        {% image %}, not a bare URL). For linking to a reading's own page,
        use `reading.detail_page.url` / `.title` (the reverse side of
        ReadingDetailPage.reading) — `select_related("detail_page")` below
        avoids a query per card for that lookup; it will be None for any
        reading that doesn't have its own detail page yet.
        """
        context = super().get_context(request, *args, **kwargs)
        context["readings"] = (
            Reading.objects.filter(is_active=True)
            .select_related("image", "detail_page")
            .order_by("order", "name")
        )
        return context


class ReadingDetailPage(Page):
    """
    An individual reading's own page — its own URL for SEO and for direct
    links from booking confirmations, on top of what the Services grid
    shows. The name, summary and price always come from the linked
    Reading snippet so they never drift out of sync.
    """

    reading = models.OneToOneField(
        Reading,
        on_delete=models.PROTECT,
        related_name="detail_page",
        help_text="Which reading this page is about. Set the reading up in "
        "Snippets → Readings first, then choose it here.",
    )
    body = StreamField(
        [
            ("text", BodyTextBlock()),
            ("image", CaptionedImageBlock()),
            ("faq", FAQListBlock()),
        ],
        blank=True,
        help_text="Extra detail for this reading beyond its short summary — "
        "what to expect, how to prepare, or a short FAQ.",
    )

    # templates/readings/detail.html is the real file (FINDING 3).
    template = "readings/detail.html"

    content_panels = Page.content_panels + [
        FieldPanel("reading"),
        FieldPanel("body", heading="Extra detail"),
    ]

    parent_page_types = ["readings.ReadingsIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "Reading detail page"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 fix: this page's own title/url/body are already on
        `page` (Wagtail puts `self` there automatically) and its reading's
        name/summary/price/etc are on `page.reading` — neither needs
        duplicating into context under guessed names. What the template
        can't get any other way is the "other readings" list, so that's
        the only thing added here, in the same shape as
        ReadingsIndexPage.get_context above.
        """
        context = super().get_context(request, *args, **kwargs)
        context["other_readings"] = (
            Reading.objects.filter(is_active=True)
            .exclude(pk=self.reading_id)
            .select_related("image", "detail_page")
            .order_by("order", "name")
        )
        return context

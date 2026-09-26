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

from django.conf import settings
from django.db import models
from wagtail import blocks
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
    tag_label = models.CharField(
        max_length=40,
        blank=True,
        help_text="A short category tag shown next to this reading's number "
        "on the Services and Readings pages, e.g. 'Natal chart' or 'Year "
        "ahead'. Leave blank to show just the number.",
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
    features = StreamField(
        [("item", blocks.CharBlock(max_length=150, label="Feature"))],
        blank=True,
        help_text="Short bullet points describing what's included, e.g. '60 "
        "minutes, online or by phone' or 'Recording sent afterwards'. Shown "
        "as a checklist on this reading's own page.",
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
        # No currency named here deliberately: this string is frozen into a
        # migration the moment it's written, but `settings.BOOKING_CURRENCY`
        # (config/settings/base.py, env-backed) is exactly the kind of value
        # that can change without a schema change, and a literal here would
        # go stale the same way the old "Price in NZD" wording did (that was
        # the agency's own country leaking into what Leslie reads while
        # typing a price — see apps/bookings/models.py's CURRENCY comment
        # for the sibling fix on the booking side). The currency Leslie
        # actually sees while editing is supplied below, on the FieldPanel,
        # which reads the same setting when this module is imported (once,
        # at process startup, same as any other settings-derived constant)
        # but is never serialised into migration state the way this field's
        # own kwargs are — so a currency change is a one-line config edit
        # and a restart, not a migration.
        help_text="Leave blank until pricing is confirmed — the note below "
        "will be shown instead of a number.",
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
    is_most_booked = models.BooleanField(
        default=False,
        help_text="Tick to show a 'Most booked' highlight on this reading's "
        "card. Only tick this for one reading at a time.",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls the order readings are listed in. Lower numbers "
        "show first.",
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("name"), FieldPanel("tag_label"), FieldPanel("summary"), FieldPanel("image")],
            heading="Basics",
        ),
        MultiFieldPanel(
            [FieldPanel("description"), FieldPanel("features"), FieldPanel("duration_minutes")],
            heading="Details",
        ),
        MultiFieldPanel(
            [
                FieldPanel(
                    "price",
                    help_text=f"Price in {settings.BOOKING_CURRENCY}. Leave "
                    "blank until pricing is confirmed — the note below will "
                    "be shown instead of a number.",
                ),
                FieldPanel("price_note"),
            ],
            heading="Pricing",
        ),
        MultiFieldPanel(
            [FieldPanel("order"), FieldPanel("is_active"), FieldPanel("is_most_booked")],
            heading="Display",
        ),
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
    faq = StreamField(
        [("faq", FAQListBlock())],
        blank=True,
        max_num=1,
        help_text="Optional FAQ section shown below the list of readings "
        "(§7 includes FAQ as content that supports bookings).",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("faq", heading="FAQ"),
    ]

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
        `tag_label`, `summary`, `description`, `features` (a StreamField
        of short bullet strings), `duration_minutes`, `price`,
        `price_note`, `image` (a wagtailimages.Image, render with
        {% image %}, not a bare URL), `is_most_booked`. For linking to a
        reading's own page, use `reading.detail_page.url` / `.title` (the
        reverse side of ReadingDetailPage.reading) — `select_related
        ("detail_page")` below avoids a query per card for that lookup;
        it will be None for any reading that doesn't have its own detail
        page yet. The card's number label is this queryset's own
        position (e.g. `{{ forloop.counter }}`), not stored data.

        `page.faq` (this page's own StreamField) is already on `page` —
        no separate context entry is added for it.
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "readings"
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
    # FAQListBlock is deliberately NOT offered here. It already has a
    # working home on ReadingsIndexPage.faq (rendered field-by-field —
    # see that page's get_context docstring), and PROJECT-SCOPE.md never
    # asks for a *per-reading* FAQ, only a site-wide one (§4, §7
    # adaptations). Offering the same StructBlock in two places with two
    # different rendering paths — one field-by-field, one via
    # {% include_block %} with no Meta.template — is how it stayed a
    # latent defect here: nothing rendered wrong until someone actually
    # used it in this position. If a per-reading FAQ is ever wanted,
    # that's a deliberate decision to reintroduce it here *with* a
    # Meta.template, not a default.
    body = StreamField(
        [
            ("text", BodyTextBlock()),
            ("image", CaptionedImageBlock()),
        ],
        blank=True,
        help_text="Extra detail for this reading beyond its short summary — "
        "what to expect or how to prepare.",
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
        can't get any other way is the "other readings" list and this
        reading's own number (its position among active readings, matching
        the number ReadingsIndexPage shows for the same reading — computed
        here rather than stored, so it can never drift out of sync with
        that page's own ordering).
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "readings"

        active_reading_ids = list(
            Reading.objects.filter(is_active=True)
            .order_by("order", "name")
            .values_list("pk", flat=True)
        )
        context["reading_number"] = (
            active_reading_ids.index(self.reading_id) + 1
            if self.reading_id in active_reading_ids
            else None
        )
        context["other_readings"] = (
            Reading.objects.filter(is_active=True)
            .exclude(pk=self.reading_id)
            .select_related("image", "detail_page")
            .order_by("order", "name")
        )
        return context

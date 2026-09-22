"""
Shared, cross-cutting models.

This module holds three kinds of thing, each picked deliberately:

- Wagtail *settings* (`ContactSettings`, `AnalyticsSettings`) for values
  that are true once for the whole site and must never be duplicated
  across pages: contact details, social links, the years-of-experience
  figure, and the GA4 ID. Editing one field in one place updates every
  page that uses it.
- The `Testimonial` *snippet*, because testimonials are reused (the
  homepage picks a curated few; a future page could reuse the same pool)
  and Leslie should only ever have to write one down once.
- `AboutPage`, the one page in the site map (§4 "About / Bio") that has
  no more specific owning app among the six requested. It lives here
  rather than getting a seventh app for a single page.

§8 is explicit that contact details, the years-of-experience figure,
prices and testimonials are all unconfirmed. Nothing here guesses at
real-looking values: email/phone default to empty, and the only default
text used is copy that is obviously a placeholder (e.g. "Experience
details coming soon"), never a specific invented number.
"""

from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

from apps.core.blocks import BodyTextBlock, CaptionedImageBlock, CTALinkBlock


@register_setting(icon="mail")
class ContactSettings(BaseGenericSetting):
    """
    The contact details and social links shown across the site (nav,
    footer, Contact page, booking confirmations). Fill these in once here
    rather than typing them onto individual pages — if a phone number or
    social handle changes, it only needs to change in this one place.
    """

    contact_email = models.EmailField(
        blank=True,
        default="",
        help_text="The email address clients should use to reach you, and the "
        "one the contact form and booking notifications will use. Nothing will "
        "be shown on the site until this is filled in.",
    )
    contact_phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Optional phone number shown on the Contact page. Leave blank "
        "if you'd rather clients only reach you by email or the booking form.",
    )
    studio_address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional. Only fill this in if you see clients in person and "
        "want the address shown on the Contact page.",
    )
    instagram_url = models.URLField(
        blank=True, default="", help_text="Full web address of your Instagram profile, if you have one."
    )
    facebook_url = models.URLField(
        blank=True, default="", help_text="Full web address of your Facebook page, if you have one."
    )
    years_experience_label = models.CharField(
        max_length=60,
        default="Experience details coming soon",
        help_text="How your experience is described around the site, e.g. "
        "'12+ years'. Shown on the homepage and About page. Update this once "
        "here and it changes everywhere.",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("contact_email"),
                FieldPanel("contact_phone"),
                FieldPanel("studio_address"),
            ],
            heading="How clients reach you",
        ),
        MultiFieldPanel(
            [FieldPanel("instagram_url"), FieldPanel("facebook_url")],
            heading="Social links",
        ),
        MultiFieldPanel(
            [FieldPanel("years_experience_label")],
            heading="Experience",
        ),
    ]

    class Meta:
        verbose_name = "Contact details"


@register_setting(icon="cog")
class AnalyticsSettings(BaseGenericSetting):
    """
    Analytics configuration. Kept separate from contact details so this
    screen stays short and is easy to hand to whoever manages analytics
    without giving them access to contact information.
    """

    google_analytics_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Your Google Analytics measurement ID (looks like "
        "'G-XXXXXXXXXX'). Leave blank to disable analytics tracking.",
    )

    panels = [FieldPanel("google_analytics_id")]

    class Meta:
        verbose_name = "Analytics"


@register_snippet
class Testimonial(models.Model):
    """
    A single client testimonial. Kept as a snippet (rather than fields on
    the homepage) so the same testimonial can be reused wherever it's
    needed without retyping it, and so old ones can be kept on file even
    when they're not currently featured anywhere.
    """

    quote = models.TextField(
        help_text="The testimonial itself, in the client's own words. Keep "
        "identifying details out unless the client is happy to be named."
    )
    author_name = models.CharField(
        max_length=100,
        help_text="Who this is from, e.g. 'Sarah M.' First name and last "
        "initial is usually enough to feel genuine while protecting privacy.",
    )
    author_descriptor = models.CharField(
        max_length=150,
        blank=True,
        help_text="Optional short context under the name, e.g. 'Natal Chart "
        "Reading' or 'Auckland'.",
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Tick to make this testimonial available to pick for the "
        "homepage. Untick to keep it on file without showing it anywhere.",
    )

    panels = [
        FieldPanel("quote"),
        MultiFieldPanel(
            [FieldPanel("author_name"), FieldPanel("author_descriptor")],
            heading="Attribution",
        ),
        FieldPanel("is_featured"),
    ]

    class Meta:
        verbose_name = "Testimonial"
        ordering = ["-is_featured", "author_name"]

    def __str__(self):
        return f"{self.author_name} — {self.quote[:40]}"


class AboutPage(Page):
    """
    The About / Bio page (§4): portrait, story, philosophy and a closing
    call to action. The years-of-experience figure lives in
    ContactSettings, not here, so it only has to be kept accurate once.
    """

    # No template file exists for this page yet — templates/core/about.html
    # is not present in the repo (confirmed by FINDING 3; PROJECT-SCOPE.md
    # §4 "About / Bio" is in scope, but no one has built its markup). This
    # attribute is set now, matching this app's other single-purpose-page
    # naming (bookings/booking.html, contact/contact.html), so htmx-frontend
    # has an unambiguous file to create rather than inheriting Wagtail's
    # default "core/about_page.html" guess.
    template = "core/about.html"

    portrait = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Your portrait photo. A vertical black-and-white photo works "
        "best with this design.",
    )
    intro = models.TextField(
        blank=True,
        help_text="A short introduction shown near the top of the page, above "
        "your full story.",
    )
    body = StreamField(
        [
            ("text", BodyTextBlock()),
            ("image", CaptionedImageBlock()),
        ],
        blank=True,
        help_text="Your story and philosophy. Add as many text and image "
        "sections as you like, in whatever order reads best.",
    )
    pull_quote = models.CharField(
        max_length=300,
        blank=True,
        help_text="A short line pulled out and shown in large italic type, "
        "e.g. your guiding philosophy in one sentence.",
    )
    cta = StreamField(
        [("button", CTALinkBlock())],
        max_num=1,
        blank=True,
        help_text="An optional button at the end of the page, e.g. inviting "
        "visitors to book a reading.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("portrait"), FieldPanel("intro")],
            heading="Portrait & introduction",
        ),
        FieldPanel("body", heading="Your story"),
        FieldPanel("pull_quote", heading="Pull quote"),
        FieldPanel("cta", heading="Call to action"),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1

    class Meta:
        verbose_name = "About page"

"""
StreamField blocks for the homepage's six fixed sections (§7).

Each block below corresponds to exactly one numbered section in the
locked design order: Hero, Services, About, Testimonials, Blog, Final
CTA. They are deliberately not interchangeable or reusable outside their
section — the homepage's field-per-section layout (see home/models.py)
is what keeps that order fixed, not anything in these block
definitions.
"""

from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock

from apps.core.blocks import CTALinkBlock


class HeroBlock(blocks.StructBlock):
    """The homepage hero: tag, headline, subhead and one or two buttons."""

    eyebrow = blocks.CharBlock(
        max_length=60,
        required=False,
        help_text="Small label above the headline, e.g. 'PERSONAL ASTROLOGY "
        "READINGS'. Usually shown in capitals.",
    )
    headline = blocks.CharBlock(
        max_length=120,
        help_text="The large headline. Keep it to one short sentence or phrase.",
    )
    subheading = blocks.CharBlock(
        max_length=200,
        required=False,
        help_text="One line under the headline expanding on it.",
    )
    primary_button = CTALinkBlock(help_text="The main button, e.g. 'Book a Reading'.")
    secondary_button = CTALinkBlock(
        required=False,
        help_text="An optional second, lower-emphasis button, e.g. 'View Services'.",
    )

    class Meta:
        label = "Hero"
        icon = "home"


class ServicesTeaserBlock(blocks.StructBlock):
    """
    The homepage services section.

    PROJECT-SCOPE.md §7 describes this section as a "2-up grid: bordered
    card (number label, title, description, price, arrow) + image-backed
    card (astrolabe/celestial imagery)". The built v1-ephemeris homepage
    mockup (versions/v1-ephemeris/index.html) instead renders three
    bordered reading cards side by side and has no image card at all —
    the two disagree. Per instruction this block follows the written §7
    spec, not the mockup: it keeps a single image-backed card, and lets
    Leslie feature more than one reading as bordered cards (the mockup's
    three-reading grid was the signal that one reading was too few — see
    this task's final report for the full reasoning).

    The "number label" and "arrow" §7 mentions for each bordered card are
    not stored here: the number is each card's position in this list
    (rendered by the template, e.g. "01", "02"), and the arrow is just a
    "Book" link to the booking page — neither is content Leslie edits.
    """

    heading = blocks.CharBlock(max_length=100, default="Services")
    subline = blocks.TextBlock(
        max_length=200,
        required=False,
        help_text="A line under the heading introducing your services.",
    )
    featured_readings = blocks.ListBlock(
        SnippetChooserBlock("readings.Reading"),
        min_num=1,
        max_num=3,
        help_text="Choose 1–3 readings to feature here as bordered cards, in "
        "the order they should appear. Each card's name, summary and price "
        "come from the reading itself — edit those in Snippets → Readings.",
    )
    image = ImageChooserBlock(
        help_text="Image for the supporting card, e.g. an astrolabe or night-sky photo."
    )
    image_caption = blocks.CharBlock(
        max_length=100,
        required=False,
        help_text="Optional short caption over the image.",
    )
    image_link = CTALinkBlock(
        required=False,
        help_text="Optional — make the image card clickable, e.g. through to "
        "the Services page. Leave blank for a decorative, non-clickable image.",
    )

    class Meta:
        label = "Services"
        icon = "list-ul"


class AboutTeaserBlock(blocks.StructBlock):
    """The homepage About teaser: portrait, short story and a link to the full About page."""

    portrait = ImageChooserBlock(help_text="Your portrait photo for the homepage.")
    story = blocks.RichTextBlock(
        features=["bold", "italic"],
        help_text="A short passage introducing yourself. The full story lives "
        "on the About page — this is a taste of it.",
    )
    pull_quote = blocks.CharBlock(
        max_length=300,
        required=False,
        help_text="A short line shown in large italic type.",
    )
    link_text = blocks.CharBlock(max_length=40, default="Read my story")
    link_page = blocks.PageChooserBlock(
        required=False, help_text="Usually your About page."
    )

    class Meta:
        label = "About Teaser"
        icon = "user"


class TestimonialsTeaserBlock(blocks.StructBlock):
    """Up to three chosen testimonials, in the order they should appear."""

    heading = blocks.CharBlock(max_length=100, default="What clients say")
    testimonials = blocks.ListBlock(
        SnippetChooserBlock("core.Testimonial"),
        help_text="Choose up to three testimonials to feature here, in order. "
        "Add and edit testimonials in Snippets → Testimonials.",
    )

    class Meta:
        label = "Testimonials"
        icon = "openquote"


class LatestBlogTeaserBlock(blocks.StructBlock):
    """
    Heading only — the two posts shown here are always the most recently
    published blog posts, so this section never needs updating by hand
    and can never point at a post that's been unpublished.
    """

    heading = blocks.CharBlock(max_length=100, default="From the Blog")
    subline = blocks.CharBlock(max_length=200, required=False)
    view_all_link_text = blocks.CharBlock(max_length=40, default="View all posts")

    class Meta:
        label = "Latest Blog Posts"
        icon = "doc-full"


class FinalCTABlock(blocks.StructBlock):
    """The closing call-to-action band at the bottom of the homepage."""

    headline = blocks.CharBlock(max_length=120)
    subline = blocks.CharBlock(max_length=200, required=False)
    button = CTALinkBlock(help_text="The button in the closing band, e.g. 'Book a Reading'.")

    class Meta:
        label = "Final Call to Action"
        icon = "success"

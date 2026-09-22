"""
Shared StreamField blocks.

These are the building blocks other apps' pages assemble into StreamFields.
Keeping them here means a reading's price, a call-to-action button or an
FAQ entry looks and behaves the same wherever Leslie adds one.

Block class names are internal (developer-facing); every block also carries
a Meta.label, which is the name Leslie actually sees in the "choose a
block" chooser, so those labels are written as client-facing copy, not
developer shorthand.
"""

from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock


class CTALinkBlock(blocks.StructBlock):
    """
    A single call-to-action button: its label, and where it goes. Reused by
    the hero, the final call-to-action band, and anywhere else a page needs
    a "Book a Reading"-style button.
    """

    text = blocks.CharBlock(
        max_length=40,
        default="Book a Reading",
        help_text="The words on the button, e.g. 'Book a Reading'. Keep it short "
        "so it fits on one line.",
    )
    page = blocks.PageChooserBlock(
        required=False,
        help_text="Choose a page on this site for the button to open. Use this "
        "instead of the web address below whenever you can — it keeps working "
        "even if the page's URL changes.",
    )
    url = blocks.URLBlock(
        required=False,
        label="Or a web address",
        help_text="Only fill this in if the button should go somewhere outside "
        "this site (e.g. an external booking tool). Leave blank if you chose a "
        "page above.",
    )

    class Meta:
        label = "Button"
        icon = "link"


class FAQEntryBlock(blocks.StructBlock):
    """One question-and-answer pair for an FAQ list."""

    question = blocks.CharBlock(
        max_length=200,
        help_text="The question, written the way a visitor would ask it.",
    )
    answer = blocks.RichTextBlock(
        features=["bold", "italic", "link", "ol", "ul"],
        help_text="Your answer. Keep it plain and reassuring.",
    )

    class Meta:
        label = "Question & Answer"
        icon = "help"


class FAQListBlock(blocks.StructBlock):
    """A titled group of frequently asked questions."""

    heading = blocks.CharBlock(
        max_length=100,
        default="Frequently Asked Questions",
        help_text="The heading shown above this list of questions.",
    )
    questions = blocks.ListBlock(FAQEntryBlock())

    class Meta:
        label = "FAQ List"
        icon = "help"


class CaptionedImageBlock(blocks.StructBlock):
    """A single image with an optional caption, for use inside page body copy."""

    image = ImageChooserBlock(help_text="Choose an image from the image library.")
    caption = blocks.CharBlock(
        required=False,
        max_length=200,
        help_text="Optional line of text shown under the image, e.g. a photo credit.",
    )

    class Meta:
        label = "Image"
        icon = "image"


class BodyTextBlock(blocks.RichTextBlock):
    """A block of formatted paragraph copy for use inside longer page bodies."""

    def __init__(self, **kwargs):
        kwargs.setdefault(
            "features", ["bold", "italic", "link", "ol", "ul", "h3", "h4", "blockquote"]
        )
        super().__init__(**kwargs)

    class Meta:
        label = "Paragraph Text"
        icon = "pilcrow"


class PromiseBlock(blocks.StructBlock):
    """One of the About page's 'Three promises' — a short claim plus what it means."""

    title = blocks.CharBlock(
        max_length=60,
        help_text="A short promise, e.g. 'No judgement'.",
    )
    description = blocks.TextBlock(
        max_length=250,
        help_text="One or two sentences explaining what this promise means for a client.",
    )

    class Meta:
        label = "Promise"
        icon = "success"


class ThreePromisesBlock(blocks.StructBlock):
    """
    The About page's 'Three promises' section (versions/v1-ephemeris/about.html):
    a heading plus exactly three promises. The list is fixed at three (not a
    free-for-all repeatable list) because the design is a fixed 3-column
    row — a fourth promise would have nowhere to go.
    """

    eyebrow = blocks.CharBlock(
        max_length=60,
        default="What you can expect",
        help_text="Small label shown above the heading.",
    )
    heading = blocks.CharBlock(max_length=100, default="Three promises")
    promises = blocks.ListBlock(
        PromiseBlock(),
        min_num=3,
        max_num=3,
        help_text="Exactly three promises, in the order they should appear.",
    )

    class Meta:
        label = "Three Promises"
        icon = "success"


class TrainingBackgroundBlock(blocks.StructBlock):
    """
    The About page's 'Training & background' section
    (versions/v1-ephemeris/about.html): qualifications, study and
    experience, in Leslie's own words — never invented here (§8).
    """

    eyebrow = blocks.CharBlock(
        max_length=60,
        default="Training & background",
        help_text="Small label shown above the heading.",
    )
    heading = blocks.CharBlock(
        max_length=100,
        default="Where the knowledge comes from",
        help_text="Heading for this section.",
    )
    body = blocks.RichTextBlock(
        features=["bold", "italic", "link", "ol", "ul"],
        help_text="Your training, qualifications and background as an astrologer.",
    )
    link = CTALinkBlock(
        required=False,
        help_text="Optional link at the end of this section, e.g. through to the Readings page.",
    )

    class Meta:
        label = "Training & Background"
        icon = "form"

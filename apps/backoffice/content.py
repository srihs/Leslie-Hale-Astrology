"""
Conversions between "one plain field Leslie can type into" and the
StreamField/StructBlock shapes the underlying Wagtail models actually
store (see apps/home/blocks.py, apps/core/blocks.py). Used by exactly two
screens — Website text (apps/backoffice/views/website_text.py) and Blog
posts (apps/backoffice/views/blog.py) — plus Readings & prices'
`features` list (apps/backoffice/forms.py:ReadingForm) — so those never
construct raw StreamField dicts inline, and this project's block-name
conventions (block type "hero", ListBlock children named "item", etc. —
confirmed against real StreamField data, not assumed) live in one place.

IMPORTANT trade-off — `richtext_to_plain` / `plain_to_richtext` round-trip
PLAIN TEXT only: paragraphs (blank-line separated), nothing else. Any
bold/italic/link markup a page already carries from before this admin
existed is DISCARDED the first time that field is re-saved through
/manage/. This was a deliberate choice, not an oversight — see this
task's final report for the alternative considered (a rich-text control
in the bespoke admin) and why it was rejected for a "plain fields, no
StreamField UI" tool Leslie will use going forward.
"""

from __future__ import annotations

import re
from uuid import uuid4

from django.utils.html import escape, strip_tags

_PARAGRAPH_BREAK_RE = re.compile(r"</p>\s*<p[^>]*>", re.IGNORECASE)
_LINE_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Plain text <-> RichTextBlock HTML
# ---------------------------------------------------------------------------


def richtext_to_plain(html: str) -> str:
    """A RichTextBlock's stored HTML -> plain text, blank-line-separated
    paragraphs. See the module docstring: formatting is discarded."""
    if not html:
        return ""
    text = _PARAGRAPH_BREAK_RE.sub("\n\n", html)
    text = _LINE_BREAK_RE.sub("\n", text)
    return strip_tags(text).strip()


def plain_to_richtext(text: str) -> str:
    """The inverse of `richtext_to_plain`, for content authored entirely
    through this admin. Each blank-line-separated paragraph becomes its
    own `<p>`, HTML-escaped."""
    text = (text or "").replace("\r\n", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return "<p></p>"
    return "".join(f"<p>{escape(p)}</p>" for p in paragraphs)


# ---------------------------------------------------------------------------
# AboutPage.body / BlogPost.body — a StreamField of "text"/"image" blocks
# ---------------------------------------------------------------------------


def story_text_from_body(body) -> str:
    """`body` (AboutPage.body or BlogPost.body — see apps/core/models.py,
    apps/blog/models.py) -> the plain text Leslie edits as one field.
    Every "text" block's content is concatenated, in order; "image"
    blocks aren't representable in a plain-text field and are left out of
    this value — see `body_from_story_text` for how they survive a save
    regardless."""
    parts = []
    for block in body:
        if block.block_type == "text":
            plain = richtext_to_plain(str(block.value))
            if plain:
                parts.append(plain)
    return "\n\n".join(parts)


def body_from_story_text(body, story_text: str) -> list[dict]:
    """
    The inverse of `story_text_from_body`, applied as an update: every
    existing "text" block is replaced by exactly one new "text" block
    holding `story_text`, placed first; any "image" blocks already in the
    StreamField (added, before this admin existed, through Wagtail
    itself) are carried over unchanged and keep their original relative
    order, after it.

    This is a deliberate, documented simplification, not an oversight —
    see this task's final report. A client editing through a single
    "your story"/"post text" box has no way to say *where* among several
    paragraphs an inline image should sit, so images are kept (never
    silently dropped) but always moved after the one text block.
    """
    images = []
    for block in body:
        if block.block_type != "image":
            continue
        image = block.value.get("image")
        if image is None:
            continue
        images.append(
            {"type": "image", "value": {"image": image.id, "caption": block.value.get("caption", "")}}
        )
    return [{"type": "text", "value": plain_to_richtext(story_text)}] + images


# ---------------------------------------------------------------------------
# A ListBlock of plain CharBlocks (Reading.features) — one line per item.
# Wagtail names an unnamed ListBlock child "item" (confirmed against real
# StreamField data — see this task's final report).
# ---------------------------------------------------------------------------


def charlist_to_lines(stream) -> str:
    return "\n".join(str(block.value) for block in stream if str(block.value).strip())


def lines_to_charlist(text: str) -> list[dict]:
    return [{"type": "item", "value": line.strip()} for line in (text or "").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# HomePage.hero — a StreamField restricted to exactly one HeroBlock
# (min_num=1, max_num=1 — see apps/home/models.py)
# ---------------------------------------------------------------------------


def hero_value(hero_stream) -> dict:
    """The hero StreamField's single StructValue, or sensible blanks if
    the field is somehow empty (min_num=1 is editor-form validation, not
    a database constraint — a HomePage built outside the admin could
    still have an empty StreamField)."""
    if hero_stream:
        return hero_stream[0].value
    return {
        "eyebrow": "",
        "headline": "",
        "subheading": "",
        "primary_button": {"text": "Book a Reading", "page": None, "url": ""},
        "secondary_button": {"text": "", "page": None, "url": ""},
    }


def _cta_to_dict(value) -> dict:
    if not value:
        return {"text": "", "page": None, "url": ""}
    page = value.get("page")
    return {
        "text": value.get("text", ""),
        "page": page.id if page else None,
        "url": value.get("url", ""),
    }


def hero_stream_with_text(hero_stream, *, headline: str, subheading: str) -> list[dict]:
    """Rebuilds HomePage.hero with a new headline/subheading, carrying
    the eyebrow and both buttons over UNCHANGED — the Website text screen
    only ever edits "hero heading and intro" (task brief), never the
    buttons, which point at the booking/services pages and aren't safe to
    reconstruct from a flat text field."""
    current = hero_value(hero_stream)
    return [
        {
            "type": "hero",
            "value": {
                "eyebrow": current.get("eyebrow", ""),
                "headline": headline,
                "subheading": subheading,
                "primary_button": _cta_to_dict(current.get("primary_button")),
                "secondary_button": _cta_to_dict(current.get("secondary_button")),
            },
        }
    ]


# ---------------------------------------------------------------------------
# AboutPage.three_promises — a StreamField restricted to exactly one
# ThreePromisesBlock, itself containing exactly three PromiseBlocks
# (min_num=max_num=1 and =3 respectively — see apps/core/blocks.py)
# ---------------------------------------------------------------------------


def three_promises_value(stream) -> dict | None:
    return stream[0].value if stream else None


def three_promises_stream(*, eyebrow: str, heading: str, promises: list[tuple[str, str]]) -> list[dict]:
    """Rebuilds AboutPage.three_promises from three plain (title,
    description) pairs, in order.

    Every "item" dict below carries its own "id" (a fresh UUID4),
    confirmed necessary against real StreamField data (see this task's
    final report): a top-level StreamField block missing "id" gets one
    generated for it automatically on save (`hero_stream_with_text`,
    `body_from_story_text` above both rely on exactly that, and both were
    round-tripped against real data to confirm it), but a `ListBlock`
    child nested inside a StructBlock — `promises` here — does not get
    the same treatment: omitting "id" silently produced
    `StructValue({'title': None, 'description': None})` on read-back
    after a real save, with no exception at save or load time. That
    silent corruption, not a missing field, is why this is written out
    explicitly rather than left to chance a second time.
    """
    return [
        {
            "type": "section",
            "value": {
                "eyebrow": eyebrow,
                "heading": heading,
                "promises": [
                    {
                        "id": str(uuid4()),
                        "type": "item",
                        "value": {"title": title, "description": description},
                    }
                    for title, description in promises
                ],
            },
        }
    ]


# ---------------------------------------------------------------------------
# Image uploads — lets Leslie attach a photo without ever touching
# Wagtail's own image library UI (which lives behind /admin/, closed to
# her — see apps/backoffice/middleware.py).
# ---------------------------------------------------------------------------


def create_image_from_upload(uploaded_file, *, title: str):
    """Creates a real `wagtailimages.Image` from a plain file upload.
    Uses `wagtail.images.get_image_model()` (not a hardcoded import),
    matching this project's own test helper (tests/images.py) — future-
    proof against a custom image model, though none is configured here."""
    from wagtail.images import get_image_model

    ImageModel = get_image_model()
    return ImageModel.objects.create(title=title or uploaded_file.name, file=uploaded_file)

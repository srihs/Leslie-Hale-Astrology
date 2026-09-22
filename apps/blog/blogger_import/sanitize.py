"""
Turn one Blogger post's raw HTML into safe, structured content.

This is the file the security review (reviews/ — the importer is flagged
as the site's single most likely XSS vector: raw Blogger HTML written into
a rich text field) is really about, so the approach is deliberately an
**allowlist**, not a denylist, and it is Wagtail's own allowlist, not a
hand-rolled one:

1. Dangerous elements (`<script>`, `<style>`, `<iframe>`, forms, embeds,
   …) are decomposed — removed *with* their content — before anything
   else runs, so their text never leaks into the page as inert-looking
   body copy.
2. Headings are normalised. The site's body rich text field
   (`apps.core.blocks.BodyTextBlock`) only enables the `h3`/`h4` features
   (the post's own `<h1>` is the page title, rendered outside this field)
   — so any Blogger `<h1>`–`<h6>` is remapped onto that two-level scheme,
   and Blogger's common "styled `<div>` posing as a heading" pattern
   (a `<div>`/`<p>` whose entire text is one bold/large-font span) is
   heuristically promoted to a real `<h3>` too. This is a heuristic, not
   a guarantee — see `SanitizeResult.heading_fixups`, which the importer
   surfaces in its report so a human checks the result rather than
   trusting it silently.
3. Images are extracted out of the flow entirely — they become separate
   `image` StreamField blocks (downloaded locally by the importer, never
   hotlinked), not inline `<img>` tags surviving into the rich text.
4. Everything else — inline `style=`, `class=`, `<font>` tags, and any
   other element outside the allowlist — is stripped or unwrapped by
   handing the remaining text through a `wagtail.whitelist.Whitelister`
   (the exact engine Wagtail's own rich text editor uses to turn pasted
   HTML into the pseudo-HTML stored in the database) configured with an
   element allowlist matching `BodyTextBlock`'s enabled features exactly:
   `b`/`strong`, `i`/`em`, `a[href]`, `ol`/`ul`/`li`, `h3`, `h4`,
   `blockquote`, plus the baseline `p`/`br`/`div` Wagtail always allows.
   Link `href`s are scheme-checked (`javascript:` etc. rejected) by
   Wagtail's own `check_url`. Deliberately *not* the higher-level
   `wagtail.admin.rich_text.converters.editor_html.EditorHTMLConverter`
   this module used at first: that indirection resolves each enabled
   *feature* to a tag rule via Wagtail's legacy "editorhtml" converter
   registry (the pre-Draftail rich text editor's format), and that
   registry has a real gap — core Wagtail never registered an
   "editorhtml" rule for `blockquote` (only its modern Draftail
   "contentstate" rule), so a feature that is genuinely enabled and
   genuinely round-trips fine through the real admin editor was silently
   stripped here. Building the element allowlist directly, with the same
   `Whitelister`/`attribute_rule`/`check_url` primitives Wagtail's own
   allowlisting is built from, avoids that gap.
5. Alt text is never invented. Every extracted image is flagged in
   `SanitizeResult` (`images`); the importer reports every one of them as
   needing a human-written description, per the alt-text-design skill —
   an imported image with no alt text is left with none, not guessed at.
6. Generic link text ("click here", "read more", …) is flagged, not
   rewritten — rewriting it well requires knowing what the link is *for*
   in a way sanitisation code cannot, so it is surfaced for a human to fix
   instead (link-text-design skill).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from wagtail.whitelist import Whitelister, allow_without_attributes, attribute_rule, check_url

# BodyTextBlock's enabled features (apps/core/blocks.py) — kept in sync
# manually since that block is owned by apps.core, not apps.blog; blog
# posts use exactly this StreamField, so the importer's rich text output
# must be sanitised to the same allowlist or the editor would immediately
# strip on next save what the importer just wrote.
#
# One tag per enabled feature (bold->b/strong, italic->i/em, link->a,
# ol/ul->ol/ul/li, h3/h4, blockquote), plus the baseline p/br/div Wagtail
# always allows regardless of feature configuration (wagtail.admin.
# rich_text.converters.editor_html.BASE_WHITELIST_RULES) — kept here too
# since we don't use that module (see the module docstring for why).
BODY_TEXT_ELEMENT_RULES = {
    "[document]": allow_without_attributes,
    "p": allow_without_attributes,
    "div": allow_without_attributes,
    "br": allow_without_attributes,
    "b": allow_without_attributes,
    "strong": allow_without_attributes,
    "i": allow_without_attributes,
    "em": allow_without_attributes,
    "a": attribute_rule({"href": check_url}),
    "ol": allow_without_attributes,
    "ul": allow_without_attributes,
    "li": allow_without_attributes,
    "h3": allow_without_attributes,
    "h4": allow_without_attributes,
    "blockquote": allow_without_attributes,
}


class BodyTextWhitelister(Whitelister):
    """
    `wagtail.whitelist.Whitelister` configured for `BodyTextBlock`'s exact
    feature set. Any element not in `BODY_TEXT_ELEMENT_RULES` is unwrapped
    (content kept, tag dropped) by the base class — safe by construction,
    since `_remove_dangerous` has already fully removed (tag *and*
    content) anything actually dangerous before this ever runs.
    """

    element_rules = BODY_TEXT_ELEMENT_RULES

    def clean_tag_node(self, doc, tag):
        # Matches wagtail.admin.rich_text.converters.editor_html.
        # DbWhitelister's own behaviour: Blogger's <div>-heavy structure
        # (e.g. <div class="separator">) reads as a paragraph, not a
        # meaningless wrapper, once its attributes are already stripped.
        if tag.name == "div":
            tag.name = "p"
        super().clean_tag_node(doc, tag)


# Removed *with* their content — never merely unwrapped, or their text
# (script source, CSS rules, form fields...) would survive as visible body
# copy even once the tags themselves are gone.
DANGEROUS_TAGS = {
    "script", "style", "noscript", "iframe", "object", "embed", "form",
    "input", "button", "select", "textarea", "svg", "canvas", "video",
    "audio", "applet", "meta", "base", "link",
}

GENERIC_LINK_TEXT = {
    "click here", "here", "this", "this link", "read more", "learn more",
    "more", "link", "click",
}

# A styled div/p is only ever promoted to a heading if its whole visible
# text is short enough to plausibly be a heading, not a paragraph that
# happens to be entirely bold.
HEADING_HEURISTIC_MAX_CHARS = 120

_PLACEHOLDER_RE = re.compile(r"\x00IMG(\d+)\x00")


@dataclass
class ExtractedImage:
    src: str
    alt: str


@dataclass
class SanitizeResult:
    #: In document order: ("text", html) or ("image", ExtractedImage)
    blocks: list[tuple[str, object]] = field(default_factory=list)
    heading_fixups: int = 0
    generic_links: list[str] = field(default_factory=list)
    #: Images that appeared inline inside a link alongside other real
    #: content (not just linking straight to the image itself) — these are
    #: dropped rather than extracted, to avoid splitting the enclosing
    #: <a> tag apart at the wrong place. Rare in practice; see
    #: `_extract_images` for why.
    dropped_inline_images: int = 0

    @property
    def images(self) -> list[ExtractedImage]:
        return [value for kind, value in self.blocks if kind == "image"]


def sanitize_content(content_html: str) -> SanitizeResult:
    soup = BeautifulSoup(content_html or "", "html.parser")

    _strip_comments(soup)
    _remove_dangerous(soup)
    heading_fixups = _normalise_headings(soup)
    images, dropped_inline_images = _extract_images(soup)
    generic_links = _flag_generic_links(soup)
    _strip_attributes(soup)

    blocks = _build_blocks(soup, images)

    return SanitizeResult(
        blocks=blocks,
        heading_fixups=heading_fixups,
        generic_links=generic_links,
        dropped_inline_images=dropped_inline_images,
    )


def _strip_comments(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()


def _remove_dangerous(soup: BeautifulSoup) -> None:
    for tag_name in DANGEROUS_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()


def _normalise_headings(soup: BeautifulSoup) -> int:
    fixups = 0

    # Genuine heading tags: h1-h3 -> h3 (top level available in the body;
    # the post's real <h1> is the page title, outside this field),
    # h4-h6 -> h4 (one level of nesting is all the field supports).
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        new_name = "h3" if element.name in ("h1", "h2", "h3") else "h4"
        if element.name != new_name:
            fixups += 1
        element.name = new_name

    # Heuristic: a <div>/<p> whose entire visible text is wrapped in a
    # single <b>/<strong> — Blogger's common "styled div posing as a
    # heading" pattern — short enough to plausibly be a heading, not
    # already inside a blockquote, and not itself an image caption.
    for element in soup.find_all(["div", "p"]):
        if element.find("img"):
            continue
        if element.find_parent("blockquote"):
            continue
        text = element.get_text(strip=True)
        if not text or len(text) > HEADING_HEURISTIC_MAX_CHARS:
            continue

        emphasis = element.find(["b", "strong"])
        if emphasis is not None and emphasis.get_text(strip=True) == text:
            element.name = "h3"
            fixups += 1

    return fixups


def _extract_images(soup: BeautifulSoup) -> tuple[list[ExtractedImage], int]:
    """
    Pull every `<img>` out of the flow and replace it with a placeholder
    text token marking where it goes, so `_build_blocks` can later split
    the serialised HTML into text/image StreamField blocks at exactly
    those points.

    Splitting happens on the final *string*, not the parse tree, so a
    placeholder must never land inside a tag that would otherwise still
    have open content either side of it — that would cut an opening tag
    on one side and leave a stray closing tag on the other. Two cases are
    structurally safe to replace in place:

    - a bare `<img>` with no enclosing `<a>` (a leaf node — nothing to
      cut through), and
    - an `<a>` whose *entire* content is that one image (Blogger's
      standard "click image for full size" lightbox pattern) — the whole
      `<a>` is replaced, not just the `<img>` inside it, so no partial
      anchor survives on either side of the split.

    An `<img>` that shares an `<a>` with other real content (rare — a
    link that is also, incidentally, an image alongside some caption
    text) is dropped rather than extracted: preserving the image there
    would require splitting the anchor's markup mid-tag. Counted in the
    second return value so the caller can flag it for manual review.
    """
    images: list[ExtractedImage] = []
    dropped_inline = 0

    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            # No usable source at all — nothing to download or preserve.
            img.decompose()
            continue

        enclosing_link = img.find_parent("a")
        if enclosing_link is not None:
            wraps_only_this_image = (
                enclosing_link.get_text(strip=True) == ""
                and list(enclosing_link.find_all(True)) == [img]
            )
            if not wraps_only_this_image:
                dropped_inline += 1
                img.decompose()
                continue
            target: Tag = enclosing_link
        else:
            target = img

        alt = (img.get("alt") or "").strip()
        placeholder = f"\x00IMG{len(images)}\x00"
        images.append(ExtractedImage(src=src, alt=alt))
        target.replace_with(NavigableString(placeholder))

    return images, dropped_inline


def _flag_generic_links(soup: BeautifulSoup) -> list[str]:
    flagged = []
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        if text.lower() in GENERIC_LINK_TEXT:
            href = a.get("href") or "(no href)"
            flagged.append(f"{text!r} -> {href}")
    return flagged


def _strip_attributes(soup: BeautifulSoup) -> None:
    """
    Drop every attribute except `href` on `<a>`. Everything else —
    `style`, `class`, `<font color>`, event handlers, and so on — is gone
    before this content ever reaches Wagtail's own allowlist converter,
    which then also independently drops anything it doesn't recognise
    (belt and braces, not a substitute for it: this pass removes styling
    cruft even from tags the converter *does* keep, like `<b style=...>`).
    """
    for tag in soup.find_all(True):
        if tag.name == "a":
            href = tag.get("href")
            tag.attrs = {"href": href} if href else {}
        else:
            tag.attrs = {}


def _build_blocks(soup: BeautifulSoup, images: list[ExtractedImage]) -> list[tuple[str, object]]:
    raw_html = str(soup)
    segments = _PLACEHOLDER_RE.split(raw_html)
    # re.split with a capturing group interleaves [text, index, text, index, ..., text]
    blocks: list[tuple[str, object]] = []
    for position, segment in enumerate(segments):
        if position % 2 == 1:
            # This is a captured placeholder index, not markup.
            image_index = int(segment)
            blocks.append(("image", images[image_index]))
            continue

        fragment = BeautifulSoup(segment, "html.parser")
        if not fragment.get_text(strip=True):
            continue
        # A fresh Whitelister per segment: Whitelister carries no state
        # worth reusing, and this keeps _build_blocks safe to call
        # concurrently / repeatedly without any shared-instance surprises.
        cleaned = BodyTextWhitelister().clean(segment)
        blocks.append(("text", cleaned))

    return blocks

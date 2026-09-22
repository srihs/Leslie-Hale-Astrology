"""
`apps.blog.blogger_import.sanitize` — the allowlist that turns raw
Blogger HTML into safe rich text. Security-critical (see that module's
own docstring: this is the site's single most likely XSS vector), so
these tests assert both halves of an allowlist: dangerous content is
actually removed, and the specific feature the first implementation
silently broke (blockquote) actually survives.
"""

from __future__ import annotations

from apps.blog.blogger_import.sanitize import sanitize_content


def _text_html(result) -> str:
    return "".join(value for kind, value in result.blocks if kind == "text")


def test_script_elements_are_removed_with_their_content():
    result = sanitize_content('<p>Hello</p><script>alert("xss")</script><p>World</p>')

    html = _text_html(result)
    assert "<script" not in html
    assert "alert" not in html
    assert "Hello" in html
    assert "World" in html


def test_javascript_href_is_stripped_from_a_link():
    result = sanitize_content('<p>Click <a href="javascript:alert(1)">here-ish</a></p>')

    html = _text_html(result)
    assert "javascript:" not in html
    # The link text survives (Wagtail's check_url drops just the bad href,
    # matching wagtail.whitelist's own attribute_rule/check_url behaviour).
    assert "here-ish" in html


def test_iframe_and_its_content_are_removed():
    result = sanitize_content('<p>Before</p><iframe src="https://evil.example/"></iframe><p>After</p>')

    html = _text_html(result)
    assert "<iframe" not in html
    assert "evil.example" not in html


def test_onerror_style_event_handler_attributes_are_stripped():
    """Every attribute except `href` on `<a>` is dropped outright
    (`_strip_attributes`) — this covers the classic img/onerror vector,
    even though the `<img>` itself is extracted separately, not left
    inline."""
    result = sanitize_content('<p onclick="doEvil()">Text</p>')

    html = _text_html(result)
    assert "onclick" not in html
    assert "doEvil" not in html


def test_blockquote_is_preserved():
    """Regression test for the bug named directly in this task: the first
    sanitizer implementation (routed through Wagtail's legacy
    "editorhtml" converter registry) silently stripped blockquote even
    though it is a genuinely enabled BodyTextBlock feature. This must
    never regress."""
    result = sanitize_content("<blockquote>A wise quote.</blockquote>")

    html = _text_html(result)
    assert "<blockquote>" in html
    assert "A wise quote." in html


def test_style_and_class_attributes_are_stripped_but_content_kept():
    result = sanitize_content('<p style="color:red" class="fancy">Styled text</p>')

    html = _text_html(result)
    assert "style=" not in html
    assert "class=" not in html
    assert "Styled text" in html


def test_allowed_formatting_elements_survive():
    result = sanitize_content("<p><b>bold</b> and <i>italic</i> and <a href='https://example.com'>a link</a></p>")

    html = _text_html(result)
    assert "<b>bold</b>" in html
    assert "<i>italic</i>" in html
    assert 'href="https://example.com"' in html


def test_headings_are_normalised_to_h3_and_h4():
    result = sanitize_content("<h1>Top</h1><h2>Second</h2><h4>Sub</h4><h6>Deep</h6>")

    html = _text_html(result)
    assert "<h3>Top</h3>" in html
    assert "<h3>Second</h3>" in html
    assert "<h4>Sub</h4>" in html
    assert "<h4>Deep</h4>" in html
    assert result.heading_fixups >= 3


def test_images_are_extracted_out_of_the_text_flow():
    result = sanitize_content('<p>Before</p><img src="https://example.com/a.jpg" alt="A cat"><p>After</p>')

    assert len(result.images) == 1
    assert result.images[0].src == "https://example.com/a.jpg"
    assert result.images[0].alt == "A cat"
    # The image must not still be sitting inline as an <img> tag in any
    # text block.
    assert "<img" not in _text_html(result)


def test_generic_link_text_is_flagged_not_silently_rewritten():
    result = sanitize_content('<p><a href="https://example.com/post">click here</a></p>')

    assert any("click here" in flag for flag in result.generic_links)
    # Not rewritten — the link text itself is left exactly as authored.
    assert "click here" in _text_html(result)


def test_empty_content_produces_no_blocks():
    result = sanitize_content("")
    assert result.blocks == []


def test_none_content_does_not_raise():
    result = sanitize_content(None)
    assert result.blocks == []

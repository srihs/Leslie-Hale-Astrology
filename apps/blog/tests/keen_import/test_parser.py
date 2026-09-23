"""
`apps.blog.keen_import.parser` — turning a Keen archive directory into
`KeenEntry` records. No database involved.

The date format tested here is deliberately the exact one this task's
brief calls out as a trap: an hour that runs 0-23 (not a normal 12-hour
hour) with an AM/PM suffix that simply mirrors that 24-hour value, not a
real 12-hour clock — including the brief's own example, "0:51 AM".
"""

from __future__ import annotations

from apps.blog.keen_import.parser import KeenParseError, parse_archive

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><title>{title}</title></head>
<body>
<main class="article">
  <h1>{title}</h1>
  <div class="date">{date_line}</div>
  <div class="source"><a href="{url}" target="_blank" rel="noopener">view original on keen.com</a></div>
  <article class="content">
    <div class="col-sm-12 blog-body">{body}</div>
  </article>
</main>
</body>
</html>
"""


def _write_article(tmp_path, filename, *, title="A Test Post", date_line=None, url=None, body="<p>Hello.</p>"):
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir(exist_ok=True)
    (tmp_path / "images").mkdir(exist_ok=True)
    date_line = date_line or (
        "posted Wed, Apr 15, 2020 15:11 PM by Astrology readings Leslie Hale "
        "Filed Under: Saturn , Eclipses 3 Comments"
    )
    url = url or "https://www.keen.com/CommunityServer/UserBlogPosts/Astrology_readings_Leslie_Hale/A-Test-Post/123456.aspx"
    html = ARTICLE_TEMPLATE.format(title=title, date_line=date_line, url=url, body=body)
    (articles_dir / filename).write_text(html, encoding="utf-8")


def test_parses_title_url_id_date_labels_and_body(tmp_path):
    _write_article(tmp_path, "001-a-test-post.html")

    entries, errors = parse_archive(tmp_path)

    assert errors == []
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "A Test Post"
    assert entry.keen_post_id == "123456"
    assert entry.original_url.endswith("/123456.aspx")
    assert entry.author == "Astrology readings Leslie Hale"
    assert entry.labels == ["Saturn", "Eclipses"]
    assert entry.raw_label_text == "Saturn , Eclipses"
    assert "Hello." in entry.content_html


def test_hour_0_am_is_parsed_as_midnight_not_rejected(tmp_path):
    """The brief's own trap case, verbatim: "0:51 AM" is a 24-hour hour of
    0 (midnight), not an invalid 12-hour hour."""
    _write_article(
        tmp_path, "001-midnight.html",
        date_line="posted Tue, Sep 10, 2013 0:51 AM by Astrology readings Leslie Hale Filed Under: Neptune 9 Comments",
    )

    entries, errors = parse_archive(tmp_path)

    assert errors == []
    entry = entries[0]
    assert entry.published.year == 2013
    assert entry.published.month == 9
    assert entry.published.day == 10
    assert entry.published.hour == 0
    assert entry.published.minute == 51


def test_afternoon_hour_is_parsed_as_24_hour_not_shifted_by_12(tmp_path):
    """"15:11 PM" (this task's other worked example) means 15:11, not
    15:11 + 12h — a naive 12-hour parse would corrupt this."""
    _write_article(
        tmp_path, "001-afternoon.html",
        date_line="posted Wed, Apr 15, 2020 15:11 PM by Astrology readings Leslie Hale Filed Under: Saturn 7 Comments",
    )

    entries, _ = parse_archive(tmp_path)

    assert entries[0].published.hour == 15
    assert entries[0].published.minute == 11


def test_post_with_no_filed_under_has_empty_labels(tmp_path):
    _write_article(
        tmp_path, "001-no-label.html",
        date_line="posted Wed, Apr 15, 2020 15:11 PM by Astrology readings Leslie Hale 0 Comments",
    )

    entries, errors = parse_archive(tmp_path)

    assert errors == []
    entry = entries[0]
    assert entry.labels == []
    assert entry.raw_label_text == ""


def test_keen_post_id_is_the_trailing_numeric_segment_of_the_source_url(tmp_path):
    _write_article(
        tmp_path, "001-post.html",
        url="https://www.keen.com/CommunityServer/UserBlogPosts/Astrology_readings_Leslie_Hale/Some-Slug/998877.aspx",
    )

    entries, _ = parse_archive(tmp_path)

    assert entries[0].keen_post_id == "998877"


def test_original_label_text_preserves_exact_source_spacing(tmp_path):
    """`raw_label_text` is the un-normalised substring, not a
    reconstruction from the split label list — so an oddity like the real
    archive's double space in "2014  monthly updates" is never silently
    tidied away."""
    _write_article(
        tmp_path, "001-spacing.html",
        date_line=(
            "posted Wed, Apr 15, 2020 15:11 PM by Astrology readings Leslie Hale "
            "Filed Under: 2014  monthly updates , Grand Cross of 2014 5 Comments"
        ),
    )

    entries, _ = parse_archive(tmp_path)

    assert entries[0].raw_label_text == "2014  monthly updates , Grand Cross of 2014"
    assert entries[0].labels == ["2014  monthly updates", "Grand Cross of 2014"]


def test_a_malformed_file_is_reported_as_an_error_not_raised(tmp_path):
    """One bad file must not stop the rest of the archive being read."""
    _write_article(tmp_path, "001-good.html")
    (tmp_path / "articles" / "002-bad.html").write_text(
        "<html><body><main class='article'><h1>Broken</h1></main></body></html>",
        encoding="utf-8",
    )

    entries, errors = parse_archive(tmp_path)

    assert len(entries) == 1
    assert entries[0].title == "A Test Post"
    assert len(errors) == 1
    assert errors[0][0] == "002-bad.html"


def test_missing_articles_directory_raises_a_clear_error(tmp_path):
    try:
        parse_archive(tmp_path)
        assert False, "expected KeenParseError"
    except KeenParseError as exc:
        assert "articles" in str(exc)


def test_entries_are_sorted_by_keen_post_id(tmp_path):
    _write_article(
        tmp_path, "001-second.html", title="Second",
        url="https://www.keen.com/.../Second/222222.aspx",
    )
    _write_article(
        tmp_path, "002-first.html", title="First",
        url="https://www.keen.com/.../First/111111.aspx",
    )

    entries, _ = parse_archive(tmp_path)

    assert [e.keen_post_id for e in entries] == ["111111", "222222"]

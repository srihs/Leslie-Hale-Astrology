"""
Read the Keen archive on disk into plain `KeenEntry` records.

No writing happens here and nothing is sanitised — this module's only job
is turning `keen_blog_archive/articles/*.html` into structured data, so it
can be tested on its own against real sample files without touching the
database. `apps.blog.keen_import.importer` does the sanitising (via the
same `apps.blog.blogger_import.sanitize` allowlist the Blogger importer
uses) and the writing.

Every one of the 1460 real archive files was confirmed (by directly
reading a sample across the full 2009-2026 range, and by scripted checks
against the whole archive before this was written) to share exactly one
`<div class="date">` format:

    posted <Weekday>, <Mon> <D>, <YYYY> <H>:<MM> <AM|PM> by <author>[ Filed
    Under: <label>[, <label>...]] <N> Comment[s]

The `<H>` hour is **not** a normal 12-hour hour: it runs 0-23 (e.g. "15:11
PM", "0:51 AM") with an AM/PM suffix that simply mirrors whether the
24-hour hour is below/at-or-above 12 — confirmed across the full archive
(every AM row has hour 0-11, every PM row has hour 12-23, with zero
exceptions). So `<H>:<MM>` is parsed directly as a 24-hour clock time and
the AM/PM suffix is not used for arithmetic; a naive "12-hour" parse of
this format (treating hour 0 as invalid, or converting "PM" hours by
adding 12) would silently corrupt every afternoon/evening timestamp in
the archive.

The archive carries no timezone information at all, so parsed
date/times are localised to Django's configured `TIME_ZONE` — the only
way to "preserve the original publication date exactly" when no offset
was ever recorded is to preserve the literal date/time text as written,
which is what this does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Deliberately not using strptime's locale-sensitive %b: MONTHS above is
# the exact closed set of three-letter abbreviations confirmed present in
# the real archive, checked independently of this parser.
_DATE_RE = re.compile(
    r"""^posted\s+
        \w{3},\s+                       # weekday name, e.g. "Wed," — unused, the date fields below are authoritative
        (?P<month>[A-Za-z]{3}),?\s*      # "Apr"
        \s*(?P<day>\d{1,2}),\s+
        (?P<year>\d{4})\s+
        (?P<hour>\d{1,2}):(?P<minute>\d{2})\s+
        (?P<ampm>AM|PM)\s+
        by\s+
        (?P<rest>.*)$
    """,
    re.VERBOSE | re.DOTALL,
)

_COMMENTS_SUFFIX_RE = re.compile(r"\s+\d+\s+Comments?\s*$")

_KEEN_ID_RE = re.compile(r"/(\d+)\.aspx\s*$")


class KeenParseError(Exception):
    """One article file could not be parsed. Carries enough context for
    the importer to log it and move on to the next file, never aborting
    the whole run over a single bad file."""


@dataclass
class KeenEntry:
    keen_post_id: str
    title: str
    original_url: str
    published: datetime  # naive; the importer localises it
    author: str
    labels: list[str]
    #: The raw "Filed Under: ..." text, exactly as it appeared (original
    #: spacing/punctuation kept), or "" if the post had no "Filed Under"
    #: at all. Distinct from `labels` (parsed/whitespace-trimmed, used
    #: for category-bucket matching) so nothing from the source is lost.
    raw_label_text: str
    content_html: str
    source_file: str


def parse_archive(archive_path: str | Path) -> tuple[list[KeenEntry], list[tuple[str, str]]]:
    """
    Parse every `articles/*.html` file under `archive_path`. Returns
    `(entries, errors)` — `errors` is `[(filename, reason), ...]` for any
    file that could not be parsed; one bad file never stops the rest of
    the archive from being read.

    Entries are returned sorted by `keen_post_id` (numeric) so the
    importer's behaviour — and any `--limit` cutoff — is stable and
    reproducible across runs and across platforms' directory-listing
    order, rather than depending on filesystem iteration order.
    """
    archive_path = Path(archive_path)
    articles_dir = archive_path / "articles"
    if not articles_dir.is_dir():
        raise KeenParseError(
            f"{articles_dir} does not exist or is not a directory — expected "
            "<archive>/articles/*.html (see the archive's own index.html)."
        )

    entries: list[KeenEntry] = []
    errors: list[tuple[str, str]] = []

    for file_path in sorted(articles_dir.glob("*.html")):
        try:
            entries.append(_parse_article(file_path))
        except KeenParseError as exc:
            errors.append((file_path.name, str(exc)))
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            errors.append((file_path.name, f"{exc.__class__.__name__}: {exc}"))

    entries.sort(key=lambda e: int(e.keen_post_id))
    return entries, errors


def _parse_article(file_path: Path) -> KeenEntry:
    html = file_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        raise KeenParseError("no <h1> or <title> found")

    source_a = soup.select_one("div.source a[href]")
    if source_a is None or not source_a.get("href", "").strip():
        raise KeenParseError("no div.source > a[href] (original keen.com URL) found")
    original_url = source_a["href"].strip()

    id_match = _KEEN_ID_RE.search(original_url)
    if not id_match:
        raise KeenParseError(
            f"could not extract a numeric post ID from original URL {original_url!r} "
            "(expected it to end .../<digits>.aspx)"
        )
    keen_post_id = id_match.group(1)

    date_div = soup.select_one("div.date")
    if date_div is None:
        raise KeenParseError("no div.date found")
    published, author, labels, raw_label_text = _parse_date_div(date_div.get_text(" ", strip=True))

    content_div = soup.select_one("div.blog-body") or soup.select_one("article.content")
    if content_div is None:
        raise KeenParseError("no div.blog-body / article.content found")
    content_html = content_div.decode_contents()

    return KeenEntry(
        keen_post_id=keen_post_id,
        title=title,
        original_url=original_url,
        published=published,
        author=author,
        labels=labels,
        raw_label_text=raw_label_text,
        content_html=content_html,
        source_file=str(file_path),
    )


def _parse_date_div(text: str) -> tuple[datetime, str, list[str], str]:
    match = _DATE_RE.match(text)
    if not match:
        raise KeenParseError(f"div.date text did not match the expected format: {text!r}")

    month = MONTHS.get(match.group("month"))
    if month is None:
        raise KeenParseError(f"unrecognised month abbreviation {match.group('month')!r} in {text!r}")

    day = int(match.group("day"))
    year = int(match.group("year"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    ampm = match.group("ampm")

    # Sanity check, not a correction: this format's hour is a 24-hour
    # value (0-23), and AM/PM should always agree with that (AM <-> hour
    # < 12). A mismatch would mean this specific post's date text doesn't
    # follow the pattern the rest of the archive does — surfaced as a
    # parse error rather than silently guessed at, per this project's
    # "never invent" rule.
    if hour > 23 or minute > 59:
        raise KeenParseError(f"hour/minute out of range in {text!r}")
    expected_ampm = "AM" if hour < 12 else "PM"
    if ampm != expected_ampm:
        raise KeenParseError(
            f"AM/PM ({ampm}) does not match 24-hour hour {hour} in {text!r} — "
            "this post's date does not follow the archive's usual format; not guessing."
        )

    try:
        published = datetime(year, month, day, hour, minute)
    except ValueError as exc:
        raise KeenParseError(f"invalid calendar date in {text!r}: {exc}") from exc

    rest = match.group("rest")
    if " Filed Under: " in rest:
        author_part, labels_part = rest.split(" Filed Under: ", 1)
        raw_label_text = _COMMENTS_SUFFIX_RE.sub("", labels_part).strip()
        labels = [label.strip() for label in raw_label_text.split(",") if label.strip()]
    else:
        author_part = _COMMENTS_SUFFIX_RE.sub("", rest)
        raw_label_text = ""
        labels = []

    author = author_part.strip()
    return published, author, labels, raw_label_text

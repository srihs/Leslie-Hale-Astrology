"""
Fetch and parse a Blogger export.

Deliberately dependency-light and Django/Wagtail-free: this module only
knows how to turn "a URL or a local file" into a flat list of
`BloggerEntry` objects. It never touches the database, so it can be
exercised directly against a static XML fixture (see the importer's dry
run and the tests this module was built to support).

Two source shapes are supported, because both are "the documented Blogger
export format" depending on which export Leslie/the agency ends up with:

- **Atom** — what Blogger's own "Back up content" (Settings → Manage blog →
  Back up content) produces, and what the live `.../feeds/posts/default`
  endpoint serves by default. This is the primary, best-supported path: it
  is the only shape that carries draft status (`<app:control><app:draft>`)
  and Blogger's per-post labels with an unambiguous `#kind` marker
  separating actual posts from pages/comments/settings/template entries
  that can appear in the same export.
- **RSS 2.0** — what `.../feeds/posts/default?alt=rss` serves. Supported as
  a fallback since it is also a real, documented Blogger export shape, but
  it does not expose draft status, so every RSS-sourced entry is treated
  as published (see `BloggerEntry.is_draft` below).

Nothing here hard-codes a Blogger URL or guesses at a feed location (§8);
the caller always supplies `source` explicitly.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://purl.org/atom/app#"
GKIND_SCHEME = "http://schemas.google.com/g/2005#kind"
BLOGGER_KIND_POST = "http://schemas.google.com/blogger/2008/kind#post"
BLOGGER_LABEL_SCHEME = "http://www.blogger.com/atom/ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

#: Refuse to read a response/file larger than this. A Blogger export full
#: of years of posts is realistically a few MB of text; this is a generous
#: ceiling against a runaway or hostile response, not a tuned production
#: limit — see the importer's final report for this as a known limitation
#: (no XML entity-expansion hardening beyond this size cap; that needs
#: `defusedxml`, which is outside this app's allowed dependency set).
DEFAULT_MAX_BYTES = 100 * 1024 * 1024

DEFAULT_TIMEOUT = 20
DEFAULT_USER_AGENT = "LeslieHaleAstrology-BloggerImporter/1.0 (+wagtail import command)"

#: Safety cap on how many paginated feed pages we will follow for a single
#: run, independent of whatever `--limit` the operator passed. Prevents an
#: unbounded loop if a feed's "next" link is ever malformed into pointing
#: at itself.
MAX_FEED_PAGES = 200


class FeedFetchError(Exception):
    """The source could not be read at all (bad URL, missing file, network
    failure, response too large). Distinct from a per-entry parse problem —
    this one stops the whole run, because there is nothing to import."""


@dataclass
class BloggerEntry:
    """One Blogger post, in plain data — no Django/Wagtail types."""

    blogger_id: str
    title: str
    content_html: str
    published: datetime
    updated: datetime | None
    author_name: str
    original_url: str
    is_draft: bool
    labels: list[str] = field(default_factory=list)


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def fetch_documents(
    source: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    max_pages: int = MAX_FEED_PAGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[bytes]:
    """
    Return a list of raw XML documents making up the whole export.

    A local file is always exactly one document (a full backup export is a
    single XML file). A URL may be paginated — Blogger's live feed serves
    a fixed page size and links to the next page via an Atom `<link
    rel="next">` — so we follow those links, capped at `max_pages`, until
    there is no next link or a page comes back empty.
    """
    if is_url(source):
        return _fetch_paginated_url(
            source, timeout=timeout, user_agent=user_agent, max_pages=max_pages, max_bytes=max_bytes
        )

    if not os.path.isfile(source):
        raise FeedFetchError(
            f"{source!r} is neither a URL (http:// or https://) nor an existing "
            "local file. Pass the Blogger export URL or the path to a downloaded "
            "export file."
        )
    size = os.path.getsize(source)
    if size > max_bytes:
        raise FeedFetchError(
            f"{source!r} is {size} bytes, over the {max_bytes} byte safety limit "
            "for this command. Increase --max-bytes if this file is genuinely "
            "that large."
        )
    with open(source, "rb") as fh:
        return [fh.read()]


def _fetch_paginated_url(
    url: str, *, timeout: int, user_agent: str, max_pages: int, max_bytes: int
) -> list[bytes]:
    documents: list[bytes] = []
    next_url: str | None = url
    seen_urls: set[str] = set()

    while next_url and len(documents) < max_pages:
        if next_url in seen_urls:
            # A malformed or self-referential "next" link — stop rather
            # than loop forever.
            break
        seen_urls.add(next_url)

        body = _fetch_url(next_url, timeout=timeout, user_agent=user_agent, max_bytes=max_bytes)
        documents.append(body)
        next_url = _find_next_link(body)

    return documents


def _fetch_url(url: str, *, timeout: int, user_agent: str, max_bytes: int) -> bytes:
    if not is_url(url):
        raise FeedFetchError(f"Refusing to fetch non-http(s) URL: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise FeedFetchError(f"Could not fetch {url!r}: {exc}") from exc

    if len(body) > max_bytes:
        raise FeedFetchError(
            f"Response from {url!r} exceeded the {max_bytes} byte safety limit "
            "for this command."
        )
    return body


def _find_next_link(xml_bytes: bytes) -> str | None:
    """Look for an Atom `<link rel="next" href="...">` at the feed/channel
    level, whether the document is Atom or Blogger's atom-namespaced-RSS."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    for link in root.iter(f"{{{ATOM_NS}}}link"):
        if link.get("rel") == "next" and link.get("href"):
            return link.get("href")
    # RSS root's <channel> is a direct child; atom:link may live there too.
    for link in root.iter("link"):
        if link.get("rel") == "next" and link.get("href"):
            return link.get("href")
    return None


def parse_documents(documents: list[bytes]) -> tuple[list[BloggerEntry], list[str]]:
    """
    Parse every document and return `(entries, errors)`.

    A malformed *document* (the whole page failed to parse as XML) is
    reported as one error and skipped — its entries are simply unavailable,
    same as if that page had never been fetched. A malformed *entry* within
    an otherwise-valid document is reported as one error per entry and
    skipped; the rest of that document's entries still import. Nothing
    here raises past a single document/entry — one bad page or post must
    never abort the whole run.
    """
    entries: list[BloggerEntry] = []
    errors: list[str] = []

    for index, doc in enumerate(documents):
        try:
            root = ET.fromstring(doc)
        except ET.ParseError as exc:
            errors.append(f"document {index + 1}: not valid XML ({exc})")
            continue

        tag = root.tag
        if tag == f"{{{ATOM_NS}}}feed":
            doc_entries, doc_errors = _parse_atom(root)
        elif tag == "rss":
            doc_entries, doc_errors = _parse_rss(root)
        else:
            errors.append(
                f"document {index + 1}: unrecognised root element {tag!r} — "
                "expected an Atom <feed> or an RSS <rss> document."
            )
            continue

        entries.extend(doc_entries)
        errors.extend(f"document {index + 1}, {e}" for e in doc_errors)

    return entries, errors


def _parse_atom(root: ET.Element) -> tuple[list[BloggerEntry], list[str]]:
    entries: list[BloggerEntry] = []
    errors: list[str] = []

    for position, entry_el in enumerate(root.findall(f"{{{ATOM_NS}}}entry")):
        label = f"entry {position + 1}"
        try:
            categories = entry_el.findall(f"{{{ATOM_NS}}}category")
            kind_terms = {
                c.get("term") for c in categories if c.get("scheme") == GKIND_SCHEME
            }
            if BLOGGER_KIND_POST not in kind_terms:
                # Not a post (a page, comment, settings or template entry
                # sharing the same export) — not an error, just not ours.
                continue

            entry_id = _text(entry_el, f"{{{ATOM_NS}}}id")
            title = _text(entry_el, f"{{{ATOM_NS}}}title") or "(untitled)"
            content_el = entry_el.find(f"{{{ATOM_NS}}}content")
            content_html = (content_el.text or "") if content_el is not None else ""
            published_raw = _text(entry_el, f"{{{ATOM_NS}}}published")
            updated_raw = _text(entry_el, f"{{{ATOM_NS}}}updated")

            if not entry_id:
                errors.append(f"{label}: has no <id> — cannot be matched on re-import, skipped")
                continue
            if not published_raw:
                errors.append(f"{label} ({entry_id}): has no <published> date, skipped")
                continue

            published = _parse_iso8601(published_raw)
            updated = _parse_iso8601(updated_raw) if updated_raw else None

            author_el = entry_el.find(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name")
            author_name = (author_el.text or "").strip() if author_el is not None else ""

            original_url = ""
            for link_el in entry_el.findall(f"{{{ATOM_NS}}}link"):
                if link_el.get("rel") == "alternate" and link_el.get("href"):
                    original_url = link_el.get("href")
                    break

            draft_el = entry_el.find(f"{{{APP_NS}}}control/{{{APP_NS}}}draft")
            is_draft = draft_el is not None and (draft_el.text or "").strip().lower() == "yes"

            labels = [
                c.get("term")
                for c in categories
                if c.get("scheme") == BLOGGER_LABEL_SCHEME and c.get("term")
            ]

            entries.append(
                BloggerEntry(
                    blogger_id=_compact_blogger_id(entry_id),
                    title=title.strip(),
                    content_html=content_html,
                    published=published,
                    updated=updated,
                    author_name=author_name,
                    original_url=original_url,
                    is_draft=is_draft,
                    labels=labels,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one bad entry must not stop the run
            errors.append(f"{label}: could not be parsed ({exc.__class__.__name__}: {exc})")

    return entries, errors


def _parse_rss(root: ET.Element) -> tuple[list[BloggerEntry], list[str]]:
    entries: list[BloggerEntry] = []
    errors: list[str] = []

    channel = root.find("channel")
    if channel is None:
        return entries, ["RSS document has no <channel>"]

    for position, item_el in enumerate(channel.findall("item")):
        label = f"item {position + 1}"
        try:
            guid_el = item_el.find("guid")
            guid = (guid_el.text or "").strip() if guid_el is not None else ""
            title = _text(item_el, "title") or "(untitled)"
            link = _text(item_el, "link") or ""

            content_el = item_el.find(f"{{{CONTENT_NS}}}encoded")
            if content_el is None or not (content_el.text or "").strip():
                content_el = item_el.find("description")
            content_html = (content_el.text or "") if content_el is not None else ""

            pub_date_raw = _text(item_el, "pubDate")
            if not guid and not link:
                errors.append(f"{label}: has no <guid> or <link> — cannot be matched on re-import, skipped")
                continue
            if not pub_date_raw:
                errors.append(f"{label} ({guid or link}): has no <pubDate>, skipped")
                continue

            published = parsedate_to_datetime(pub_date_raw)

            creator_el = item_el.find(f"{{{DC_NS}}}creator")
            author_name = (creator_el.text or "").strip() if creator_el is not None else ""

            labels = [c.text.strip() for c in item_el.findall("category") if c.text and c.text.strip()]

            entries.append(
                BloggerEntry(
                    blogger_id=_compact_blogger_id(guid or link),
                    title=title.strip(),
                    content_html=content_html,
                    published=published,
                    updated=None,
                    author_name=author_name,
                    original_url=link,
                    # Blogger's RSS export does not expose draft status —
                    # only published posts are normally syndicated to it.
                    # Documented as a known limitation in the importer's
                    # final report rather than silently assumed correct.
                    is_draft=False,
                    labels=labels,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: could not be parsed ({exc.__class__.__name__}: {exc})")

    return entries, errors


_POST_ID_RE = re.compile(r"post-(\d+)$")


def _compact_blogger_id(raw_id: str) -> str:
    """
    Blogger's Atom `<id>` looks like `tag:blogger.com,1999:blog-123.post-456`.
    Prefer the compact `post-456` form for readability in the admin and in
    reports; fall back to the raw id verbatim (still unique and stable) for
    anything that doesn't match, including RSS guids/links.
    """
    match = _POST_ID_RE.search(raw_id)
    if match:
        return f"post-{match.group(1)}"
    return raw_id.strip()[:100]


def _text(el: ET.Element, path: str) -> str | None:
    found = el.find(path)
    if found is None or found.text is None:
        return None
    return found.text


def _parse_iso8601(raw: str) -> datetime:
    # Blogger's Atom dates look like 2026-09-12T08:00:00.000-07:00 —
    # Python's fromisoformat (3.11+) handles arbitrary fractional-second
    # precision and a colon-separated UTC offset directly.
    return datetime.fromisoformat(raw.strip())

"""
`apps.blog.blogger_import.feed` — fetching and parsing a Blogger export.
No network calls: `fetch_documents` is exercised only against local files
(one of its two documented supported source shapes), never a URL, so
nothing here ever calls out.

The defusedxml tests are the security-critical ones: a hostile export
(entity-expansion "billion laughs", or an XXE payload trying to read a
local file or reach an external URL) must be refused for that one
document, and the run must carry on rather than aborting entirely — see
`parse_documents`'s own docstring on why a bad document is one skipped
error, not a fatal one.
"""

from __future__ import annotations

import pytest

from apps.blog.blogger_import import feed

ATOM_NS = "http://www.w3.org/2005/Atom"


def _atom_entry(entry_id="tag:blogger.com,1999:blog-1.post-42", title="Hello", content="<p>Body</p>", published="2020-01-01T00:00:00.000-08:00", labels=""):
    label_xml = "".join(
        f'<category scheme="http://www.blogger.com/atom/ns#" term="{l}"/>' for l in ([labels] if labels else [])
    )
    return f"""
  <entry>
    <id>{entry_id}</id>
    <published>{published}</published>
    <updated>{published}</updated>
    <title type="text">{title}</title>
    <content type="html">{content}</content>
    <author><name>Leslie Hale</name></author>
    <link rel="alternate" type="text/html" href="https://old-blog.example.com/2020/01/{title.lower()}.html"/>
    <category scheme="http://schemas.google.com/g/2005#kind" term="http://schemas.google.com/blogger/2008/kind#post"/>
    {label_xml}
  </entry>
"""


def _atom_feed(*entries: str) -> bytes:
    body = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}">
{body}
</feed>""".encode("utf-8")


def test_valid_atom_feed_parses_into_entries():
    doc = _atom_feed(_atom_entry())
    entries, errors = feed.parse_documents([doc])

    assert errors == []
    assert len(entries) == 1
    assert entries[0].blogger_id == "post-42"
    assert entries[0].title == "Hello"
    assert entries[0].is_draft is False


def test_billion_laughs_entity_expansion_is_refused_and_the_run_continues():
    """A classic entity-expansion bomb — defusedxml must refuse it (never
    silently parse and expand it), and `parse_documents` must record one
    error for that document and still process whatever came after it, not
    raise past the caller."""
    billion_laughs = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<feed xmlns="http://www.w3.org/2005/Atom"><title>&lol2;</title></feed>"""

    good_doc = _atom_feed(_atom_entry(entry_id="tag:blogger.com,1999:blog-1.post-99", title="Safe Post"))

    entries, errors = feed.parse_documents([billion_laughs, good_doc])

    assert len(errors) == 1
    assert "document 1" in errors[0]
    assert len(entries) == 1
    assert entries[0].title == "Safe Post"


def test_xxe_external_entity_is_refused_and_the_run_continues():
    """An XXE payload attempting to read a local file. Even though this
    process never has a file at that exact path, the point is that
    defusedxml must reject the *DOCTYPE with an external entity
    declaration itself* — a working exploit must never depend on this
    environment happening to lack the file it targets."""
    xxe = b"""<?xml version="1.0"?>
<!DOCTYPE feed [
 <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<feed xmlns="http://www.w3.org/2005/Atom"><title>&xxe;</title></feed>"""

    good_doc = _atom_feed(_atom_entry(entry_id="tag:blogger.com,1999:blog-1.post-100", title="Still Safe"))

    entries, errors = feed.parse_documents([xxe, good_doc])

    assert len(errors) == 1
    assert len(entries) == 1
    assert entries[0].title == "Still Safe"
    # Nothing from /etc/passwd leaked into any parsed entry.
    assert not any("root:" in e.title for e in entries)


def test_xxe_in_the_next_link_lookup_does_not_raise():
    """`_find_next_link` also parses untrusted bytes (used while paginating
    a live URL) — same hostile payload, different entry point, must
    degrade to "no next link" rather than raising."""
    xxe = b"""<?xml version="1.0"?>
<!DOCTYPE feed [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<feed xmlns="http://www.w3.org/2005/Atom"><title>&xxe;</title></feed>"""

    assert feed._find_next_link(xxe) is None


def test_malformed_xml_is_one_skipped_error_not_a_crash():
    entries, errors = feed.parse_documents([b"<feed><not-closed>"])

    assert entries == []
    assert len(errors) == 1
    assert "not valid XML" in errors[0]


def test_rss_source_entries_are_never_treated_as_drafts():
    """RSS does not expose draft status (feed.py's own documented
    limitation) — every RSS-sourced entry must come back `is_draft=False`,
    never guessed True."""
    rss = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>An RSS post</title>
  <link>https://old-blog.example.com/rss-post.html</link>
  <guid>https://old-blog.example.com/rss-post.html</guid>
  <pubDate>Mon, 01 Jan 2020 00:00:00 GMT</pubDate>
  <description>&lt;p&gt;Body&lt;/p&gt;</description>
</item>
</channel></rss>"""

    entries, errors = feed.parse_documents([rss])

    assert errors == []
    assert len(entries) == 1
    assert entries[0].is_draft is False


def test_fetch_documents_rejects_a_missing_local_file(tmp_path):
    missing = tmp_path / "does-not-exist.xml"
    with pytest.raises(feed.FeedFetchError):
        feed.fetch_documents(str(missing))


def test_fetch_documents_enforces_the_max_bytes_limit(tmp_path):
    big_file = tmp_path / "export.xml"
    big_file.write_bytes(b"<feed></feed>" + b" " * 100)

    with pytest.raises(feed.FeedFetchError):
        feed.fetch_documents(str(big_file), max_bytes=10)


def test_fetch_documents_reads_a_local_file_as_one_document(tmp_path):
    export = tmp_path / "export.xml"
    export.write_bytes(_atom_feed(_atom_entry()))

    documents = feed.fetch_documents(str(export))

    assert len(documents) == 1

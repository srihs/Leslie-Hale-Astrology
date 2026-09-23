"""
Map the Keen archive's ~66 free-text "Filed Under" labels onto a small,
editor-curated set of `BlogCategory` buckets.

This mapping was built by reading a sample of posts across the full
2009-2026 date range and counting every distinct label across all 1460
articles (not by guessing at a taxonomy from the label text alone — see
the `ux-strategy:content-strategy` skill this task was built under). Two
buckets — "Transits" (slug `transits`) and "Everyday astrology" (slug
`everyday-astrology`) — already existed as `BlogCategory` snippets,
seeded to match the locked design's filter-bar mockup
(`versions/v1-ephemeris/blog.html`); this mapping reuses those two by
slug rather than creating near-duplicates, and adds six more that the
mockup's placeholder categories ("Signs", "Q&A") don't cover but the real
archive clearly needs.

The eight buckets, and roughly why:

- `transits` ("Transits") — by far the largest group: every post tagged
  with a bare planet name (Jupiter, Saturn, Pluto, ...) or a named
  transit/aspect event (a square, conjunction, a planet changing sign).
  This is the technical astrology writing that is the backbone of the
  blog.
- `yearly-forecasts` ("Yearly & monthly forecasts") — the "Astrology of
  20XX" / "20XX astrology" / "20XX monthly updates" round-up posts. Almost
  one per year of the archive's 17-year span, plus a handful of explicit
  monthly-update labels.
- `eclipses` ("Eclipses") — eclipses are common enough (three separate
  labels, the plain "Eclipses" label alone appears on well over a hundred
  posts) and distinct enough from routine transit commentary to earn
  their own bucket rather than being folded into `transits`.
- `politics-elections` ("Politics & elections") — political figures,
  politics generally, and election-specific posts.
- `public-figures` ("Public figures & celebrities") — celebrities,
  royalty, and other named public figures who are not primarily written
  about as politicians.
- `disasters-history` ("Disasters & historic events") — disasters and
  posts about historic figures/events (often the same post covers both,
  e.g. an assassination).
- `relationships` ("Relationships") — the single "Relationships and love"
  label, common enough (48 posts) and distinct enough in subject to stand
  alone rather than folding into `everyday-astrology`.
- `everyday-astrology` ("Everyday astrology") — basic-astrology
  explainers, advice/"words of wisdom" posts, personal true-story/
  reflection posts (including the "Leslie's favorite blogs" label, which
  in practice tags the same kind of personal-anecdote post as "True
  stories", not a links roundup), holidays, and anything genuinely
  miscellaneous.

A post's original label text is never discarded even though only one
bucket can be chosen per post (`BlogPost.category` is a single
ForeignKey, matching the locked design's single-select filter bar) — the
importer writes the full original "Filed Under" text, verbatim, to
`BlogPost.original_category_label` regardless of which bucket the
category ends up being.
"""

from __future__ import annotations

#: (slug, display name) in the order the category filter bar should show
#: them. `transits` and `everyday-astrology` already exist (seeded to
#: match the locked design mockup) and are listed first/last respectively
#: to match that existing seed data; the six new buckets sit in roughly
#: descending order of how much of the archive they cover.
BUCKET_DEFINITIONS: list[tuple[str, str]] = [
    ("transits", "Transits"),
    ("yearly-forecasts", "Yearly & monthly forecasts"),
    ("eclipses", "Eclipses"),
    ("politics-elections", "Politics & elections"),
    ("public-figures", "Public figures & celebrities"),
    ("disasters-history", "Disasters & historic events"),
    ("relationships", "Relationships"),
    ("everyday-astrology", "Everyday astrology"),
]

#: Every one of the 66 distinct "Filed Under" labels found across all
#: 1460 archived posts, mapped to exactly one bucket slug above. Keys are
#: matched against label text *after* HTML-entity decoding (so
#: "Leslie's favorite blogs", not "Leslie&#x27;s favorite blogs") and
#: after only leading/trailing whitespace is stripped from each
#: comma-separated label — internal spacing quirks in the source (e.g.
#: the double space in "2014  monthly updates") and misspellings (e.g.
#: "Saturnn-Neptune square 2015-16") are preserved exactly as keys here,
#: matching what the parser actually extracts, rather than "corrected".
LABEL_TO_BUCKET: dict[str, str] = {
    # -- relationships --------------------------------------------------
    "Relationships and love": "relationships",
    # -- politics & elections --------------------------------------------
    "Political figures and politics": "politics-elections",
    "2024 Presidential election": "politics-elections",
    # -- public figures & celebrities ------------------------------------
    "Celebrities-Royalty": "public-figures",
    "Notorious and other public figures": "public-figures",
    # -- disasters & historic events --------------------------------------
    "Disasters": "disasters-history",
    "Historic figures/events": "disasters-history",
    # -- eclipses ----------------------------------------------------------
    "Eclipses": "eclipses",
    "The Great American eclipse of 2017": "eclipses",
    "Pre-natal charts/eclipses": "eclipses",
    # -- everyday astrology --------------------------------------------------
    "Basic astrology": "everyday-astrology",
    "Words of wisdom or advice": "everyday-astrology",
    "True stories": "everyday-astrology",
    "Miscellaneous": "everyday-astrology",
    "Leslie's favorite blogs": "everyday-astrology",
    "Holidays": "everyday-astrology",
    # -- transits & planets ------------------------------------------------
    "Jupiter": "transits",
    "Venus": "transits",
    "Uranus": "transits",
    "Saturn": "transits",
    "Pluto": "transits",
    "Mercury": "transits",
    "Neptune": "transits",
    "Mars": "transits",
    "Asteroids and fixed stars": "transits",
    "Uranus in Taurus": "transits",
    "Saturn in Aquarius 2020-23": "transits",
    "Saturn in Aquarius": "transits",
    "Saturn in Capricorn": "transits",
    "Saturn in Aries 2025-28": "transits",
    "Saturn in Pisces": "transits",
    "Pluto in Aquarius": "transits",
    "Saturn-Neptune square 2015-16": "transits",
    "Saturnn-Neptune square 2015-16": "transits",  # misspelling, present in source
    "Uranus-Pluto square of 2013/2014": "transits",
    "Uranus-Pluto square 2015-15": "transits",
    "Grand Cross of 2014": "transits",
    "Saturn-Pluto conjunction": "transits",
    "Saturn square Uranus 2021": "transits",
    "The Jupiter-Saturn conjunction of 2021": "transits",
    "Jupiter-Pluto-Uranus T-square 2013-14": "transits",
    "Jupiter-Uranus opposition 2017": "transits",
    "US Pluto return 2022-23": "transits",
    # -- yearly & monthly forecasts ------------------------------------------
    "Astrology of 2016": "yearly-forecasts",
    "Astrology of 2015": "yearly-forecasts",
    "Astrology of 2017": "yearly-forecasts",
    "2019 Astrology": "yearly-forecasts",
    "2010 astrology": "yearly-forecasts",
    "2020 Astrology": "yearly-forecasts",
    "2013 Astrology": "yearly-forecasts",
    "Astrology of 2014": "yearly-forecasts",
    "2012 astrology": "yearly-forecasts",
    "Astrology of 2022": "yearly-forecasts",
    "2011 astrology": "yearly-forecasts",
    "2021 Astrology": "yearly-forecasts",
    "2009 astrology": "yearly-forecasts",
    "2008 astrology": "yearly-forecasts",
    "Astrology of 2023": "yearly-forecasts",
    "Astrology of 2024": "yearly-forecasts",
    "Astrology of 2025": "yearly-forecasts",
    "Astrology of 2026": "yearly-forecasts",
    "2026": "yearly-forecasts",
    "2014  monthly updates": "yearly-forecasts",  # double space, present in source
    "2017 Monthly updates": "yearly-forecasts",
    "2015 monthly updates": "yearly-forecasts",
    "2007 Archive": "yearly-forecasts",
}

#: When a post carries several labels that map to different buckets, the
#: bucket highest in this list wins — most narratively-specific first,
#: most generic/near-universal last, so (for example) a post tagged both
#: "Relationships and love" and "Basic astrology" lands in Relationships,
#: and a year-round-up post that happens to also mention "Jupiter" lands
#: in Transits rather than the very generic Yearly bucket. This is a
#: deterministic, documented editorial call, not a guess: the post's full
#: original label set is never lost regardless (see
#: `BlogPost.original_category_label`), so a human can always
#: re-categorise a specific post later with the full picture.
BUCKET_PRIORITY: list[str] = [
    "relationships",
    "politics-elections",
    "public-figures",
    "disasters-history",
    "eclipses",
    "everyday-astrology",
    "transits",
    "yearly-forecasts",
]


def resolve_bucket_slug(labels: list[str]) -> tuple[str | None, list[str]]:
    """
    Given a post's original label list, return `(bucket_slug, unmapped)`:

    - `bucket_slug` is `None` if `labels` is empty (no "Filed Under" at
      all — imports uncategorised, per this task's brief) or if none of
      the labels are in `LABEL_TO_BUCKET`; otherwise it is the
      highest-priority bucket slug any label maps to.
    - `unmapped` lists any labels that are not in `LABEL_TO_BUCKET` — this
      should be empty for the real archive (every label found in it is
      mapped above) but is surfaced rather than silently dropped in case
      the archive this runs against ever has one this mapping doesn't
      know about.
    """
    if not labels:
        return None, []

    candidates: set[str] = set()
    unmapped: list[str] = []
    for label in labels:
        slug = LABEL_TO_BUCKET.get(label)
        if slug is None:
            unmapped.append(label)
        else:
            candidates.add(slug)

    if not candidates:
        return None, unmapped

    for slug in BUCKET_PRIORITY:
        if slug in candidates:
            return slug, unmapped

    # Unreachable while BUCKET_PRIORITY covers every bucket slug in
    # BUCKET_DEFINITIONS, kept only as a non-silent safety net.
    return sorted(candidates)[0], unmapped

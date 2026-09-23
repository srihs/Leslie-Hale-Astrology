"""
`apps.blog.keen_import.categories` — the label -> bucket mapping and the
priority rule used when a post carries labels from more than one bucket.
"""

from __future__ import annotations

from apps.blog.keen_import.categories import (
    BUCKET_DEFINITIONS,
    BUCKET_PRIORITY,
    LABEL_TO_BUCKET,
    resolve_bucket_slug,
)


def test_every_bucket_priority_slug_is_a_real_bucket():
    defined_slugs = {slug for slug, _ in BUCKET_DEFINITIONS}
    assert set(BUCKET_PRIORITY) == defined_slugs


def test_every_label_maps_to_a_real_bucket():
    defined_slugs = {slug for slug, _ in BUCKET_DEFINITIONS}
    assert set(LABEL_TO_BUCKET.values()) <= defined_slugs


def test_no_label_is_uncategorised_not_an_error():
    slug, unmapped = resolve_bucket_slug([])
    assert slug is None
    assert unmapped == []


def test_single_known_label_resolves_directly():
    slug, unmapped = resolve_bucket_slug(["Relationships and love"])
    assert slug == "relationships"
    assert unmapped == []


def test_unknown_label_is_reported_not_silently_dropped():
    slug, unmapped = resolve_bucket_slug(["Some Brand New Label Nobody Has Seen"])
    assert slug is None
    assert unmapped == ["Some Brand New Label Nobody Has Seen"]


def test_a_known_and_an_unknown_label_together_still_resolve_the_known_one():
    slug, unmapped = resolve_bucket_slug(["Saturn", "Some Brand New Label"])
    assert slug == "transits"
    assert unmapped == ["Some Brand New Label"]


def test_priority_order_picks_the_most_specific_bucket():
    """A post tagged both a near-universal label (a bare planet, in
    `transits`) and a narrow, specific one (`relationships`) should land
    in the specific bucket, per BUCKET_PRIORITY."""
    slug, _ = resolve_bucket_slug(["Jupiter", "Relationships and love"])
    assert slug == "relationships"


def test_priority_order_prefers_eclipses_over_generic_transits():
    slug, _ = resolve_bucket_slug(["Saturn", "Eclipses"])
    assert slug == "eclipses"


def test_priority_order_prefers_transits_over_yearly_forecasts():
    slug, _ = resolve_bucket_slug(["Jupiter", "Astrology of 2016"])
    assert slug == "transits"


def test_misspelled_label_present_in_the_real_archive_still_maps():
    """"Saturnn-Neptune square 2015-16" (the extra 'n') is a real,
    confirmed misspelling in the source archive, not a typo in this
    mapping — it must resolve exactly like its correctly-spelled twin."""
    assert LABEL_TO_BUCKET["Saturnn-Neptune square 2015-16"] == "transits"
    assert LABEL_TO_BUCKET["Saturn-Neptune square 2015-16"] == "transits"


def test_double_space_label_present_in_the_real_archive_still_maps():
    assert LABEL_TO_BUCKET["2014  monthly updates"] == "yearly-forecasts"

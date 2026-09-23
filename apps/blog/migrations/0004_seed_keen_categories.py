"""
Seed the 8 curated BlogCategory buckets the Keen archive's ~66 original
"Filed Under" labels are mapped onto (apps.blog.keen_import.categories —
see that module for the full mapping and the reasoning behind the
buckets).

Two of the eight ("Transits" / `transits`, "Everyday astrology" /
`everyday-astrology`) already exist, seeded earlier to match the locked
design's filter-bar mockup — `get_or_create` on slug leaves those two
exactly as they are rather than creating near-duplicates. The `order`
field only sets a value for a bucket this migration itself creates, so it
never reorders `transits`/`everyday-astrology` relative to whatever a
human editor has already set for them in Wagtail admin.

BlogCategory is small, editor-curated seed data (a fixed taxonomy the
site needs regardless of whether any import has run yet), not
irreplaceable per-post content — so, unlike a `BlogPost`, creating it via
a migration rather than only on an importer run is appropriate and
doesn't touch the "never delete existing content" rule that binds the
importer itself. This migration only ever creates; it never deletes or
renames an existing category, including on a fresh re-run of
`migrate` (idempotent via `get_or_create`).
"""

from django.db import migrations

# Mirrors apps.blog.keen_import.categories.BUCKET_DEFINITIONS — duplicated
# here (not imported) because migrations must not depend on application
# code that can change shape later; this is a snapshot of what this
# migration seeds, and is expected to stay in sync with that module by
# inspection, the same convention Django migrations always use for
# historical model state.
BUCKET_DEFINITIONS = [
    ("transits", "Transits"),
    ("yearly-forecasts", "Yearly & monthly forecasts"),
    ("eclipses", "Eclipses"),
    ("politics-elections", "Politics & elections"),
    ("public-figures", "Public figures & celebrities"),
    ("disasters-history", "Disasters & historic events"),
    ("relationships", "Relationships"),
    ("everyday-astrology", "Everyday astrology"),
]


def seed_categories(apps, schema_editor):
    BlogCategory = apps.get_model("blog", "BlogCategory")
    for position, (slug, name) in enumerate(BUCKET_DEFINITIONS):
        BlogCategory.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "order": position},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0003_blogpost_keen_content_hash_blogpost_keen_post_id_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]

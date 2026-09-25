"""
Build the site's initial Wagtail page tree (PROJECT-SCOPE.md §4).

The gap this closes: nothing in this project ever created HomePage, its
five §4 children, or pointed Wagtail's Site record at any of them. Every
page that exists on the development machine was clicked together by hand
in the admin. A fresh database — a new environment, a throwaway test
database, the real-domain cutover — runs migrations, has every table it
needs, and still serves Wagtail's own "Welcome to your new Wagtail site!"
page at "/", because that is genuinely all the data that exists. This
module is what `manage.py bootstrap_site` runs instead.

Mirrors `apps.blog.keen_import`'s shape (see that package's own
docstrings): a report dataclass, a class holding one run's configuration,
and a thin management command that only does argument parsing and
console output — see `apps/core/management/commands/bootstrap_site.py`.

Content rules (PROJECT-SCOPE.md §8 — binding):

- No price, reading name, testimonial, contact detail or years-of-
  experience figure is ever invented here. Every required text field a
  block schema demands (e.g. HeroBlock.headline) gets copy that visibly
  reads as a placeholder ("... coming soon"), matching the one placeholder
  string this codebase already ships (`ContactSettings.years_experience_label`
  default, "Experience details coming soon" — apps/core/models.py). Every
  field that is *optional* or *relational* (an image, a chosen Reading or
  Testimonial snippet, a linked page) is left blank/None rather than
  guessed, and every template that renders these sections already handles
  that gracefully (confirmed by reading templates/home/index.html and
  templates/core/about.html before writing this — neither errors on a
  blank image, an empty snippet list, or an unset page link).
- `ServicesTeaserBlock.featured_readings` (min_num=1) and
  `ThreePromisesBlock.promises` (min_num=3) are left empty. Wagtail only
  enforces `min_num`/`max_num` in the *editor form* (see HomePage.
  get_context's own comment in apps/home/models.py making the identical
  point) — a page built directly in Python, bypassing that form, can hold
  an empty list. That is used deliberately here: filling either with
  fabricated readings or promises would be exactly the invented content
  §8 forbids. Leslie will see Wagtail's own validation error asking her to
  add three promises / a featured reading the first time she tries to
  publish a change to these pages — which is the correct moment for that
  prompt, not now.

Idempotency and safety (binding, per CLAUDE.md's migration/import rules,
applied here to page creation instead):

- Every page type is matched on its own model class, never on title or
  slug (`AboutPage.objects.exists()`, not "a page titled 'About'"). All
  six models this command creates already declare `max_count = 1`
  (HomePage) or are children with `max_count = 1` of their own (About,
  Readings, Booking, Blog, Contact — see each model), so "does one exist
  anywhere" is the right existence check.
- A page type that already exists is never modified, re-parented,
  unpublished or deleted — reported as "existing" and left exactly as a
  human may have edited it.
- The two non-page-creation actions this module performs — pointing
  Wagtail's default Site at the real HomePage, and retiring Wagtail's own
  placeholder page — are each independently idempotent (see
  `_ensure_site_root` and `_retire_default_welcome_page` below) and each
  refuses to act if the state on disk doesn't match what it expects,
  rather than forcing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from wagtail.models import Page as WagtailPage
from wagtail.models import Site


@dataclass
class BootstrapReport:
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def write_summary(self, out) -> None:
        out(f"Created:  {len(self.created)}")
        out(f"Existing: {len(self.existing)}")
        out(f"Updated:  {len(self.updated)}")
        out(f"Skipped:  {len(self.skipped)}")

        if self.created:
            out("")
            out("Created:")
            for item in self.created:
                out(f"  - {item}")

        if self.existing:
            out("")
            out("Already existed (left untouched):")
            for item in self.existing:
                out(f"  - {item}")

        if self.updated:
            out("")
            out("Fixed (routing/cleanup, not page content):")
            for item in self.updated:
                out(f"  - {item}")

        if self.skipped:
            out("")
            out("Skipped, with reasons:")
            for item, reason in self.skipped:
                out(f"  - {item}: {reason}")

        if self.notes:
            out("")
            out("Notes:")
            for note in self.notes:
                out(f"  - {note}")


# The exact title Wagtail's own `wagtailcore.0002_initial_data` migration
# gives its default page — never guessed, this is the literal string that
# migration writes. Matched together with `content_type` (below) so this
# can only ever find that one stock fixture, never a real page Leslie
# happens to title similarly.
WAGTAIL_DEFAULT_PAGE_TITLE = "Welcome to your new Wagtail site!"


class SiteBootstrapper:
    """One instance per invocation of `manage.py bootstrap_site`. Holds
    the run's configuration; `run()` does the work (or, when `write` is
    False, only inspects and reports) and returns a `BootstrapReport`."""

    def __init__(self, *, write: bool):
        self.write = write

    def run(self) -> BootstrapReport:
        report = BootstrapReport()

        if self.write:
            with transaction.atomic():
                self._run(report)
        else:
            self._run(report)

        return report

    # -- top level ---------------------------------------------------

    def _run(self, report: BootstrapReport) -> None:
        from apps.blog.models import BlogIndexPage
        from apps.bookings.models import BookingPage
        from apps.contact.models import ContactPage
        from apps.core.models import AboutPage
        from apps.home.models import HomePage
        from apps.readings.models import ReadingsIndexPage

        # Retired *before* HomePage is created: Wagtail's own default page
        # (wagtailcore's 0002_initial_data migration) uses slug "home" —
        # the same human-friendly slug HomePage should get — so freeing it
        # first avoids a sibling-slug collision rather than working around
        # it with an uglier slug for the real homepage.
        self._retire_default_welcome_page(report)

        # Queried *after* the retirement above, deliberately: treebeard's
        # `add_child` below decides how to compute the new page's tree
        # path from `tree_root.numchild`/`is_leaf()` as held in memory on
        # this Python object, not from a fresh query — if this were
        # fetched first and the default page (the tree root's only child)
        # were then deleted, `tree_root` would still believe it had one
        # child, `add_child` would try to insert *after* that no-longer-
        # existing child via `get_last_child()`, and get `None` back.
        # Fetching it fresh here, once the tree's real shape is settled,
        # is what avoids that.
        tree_root = WagtailPage.objects.get(depth=1)

        home_page = self._ensure_page(
            HomePage,
            label="HomePage (site root)",
            parent=tree_root,
            build_kwargs=self._home_kwargs,
            report=report,
        )

        self._ensure_site_root(home_page, report)

        for model_cls, label, build_kwargs in (
            (AboutPage, "AboutPage (About)", self._about_kwargs),
            (ReadingsIndexPage, "ReadingsIndexPage (Readings)", self._readings_index_kwargs),
            (BookingPage, "BookingPage (Booking)", self._booking_kwargs),
            (BlogIndexPage, "BlogIndexPage (Blog)", self._blog_index_kwargs),
            (ContactPage, "ContactPage (Contact)", self._contact_kwargs),
        ):
            # `home_page` is only ever None when this is a dry run and no
            # HomePage exists yet (see `_ensure_page`'s write branch,
            # which is unreachable here in that case for the same reason
            # it's unreachable for HomePage itself) — each child's own
            # existence is still checked and reported regardless.
            self._ensure_page(
                model_cls,
                label=label,
                parent=home_page,
                build_kwargs=build_kwargs,
                report=report,
            )

    # -- generic page creation ----------------------------------------

    def _ensure_page(self, model_cls, *, label, parent, build_kwargs, report: BootstrapReport):
        """
        `model_cls.objects.exists()` is the whole idempotency check: every
        page type this command creates has `max_count = 1` (see the
        module docstring), so "one exists anywhere" is equivalent to
        "already bootstrapped" regardless of where it currently lives or
        whether a human has since edited, moved or unpublished it — none
        of which this command will ever touch.
        """
        if model_cls.objects.exists():
            report.existing.append(label)
            return model_cls.objects.first()

        if not self.write:
            report.created.append(f"{label} (dry run — would create)")
            return None

        kwargs = build_kwargs()
        kwargs["slug"] = self._unique_sibling_slug(parent, kwargs["slug"])
        page = model_cls(live=True, **kwargs)
        parent.add_child(instance=page)
        # A real initial revision, same as apps.blog.keen_import.importer
        # and apps.blog.blogger_import.importer do for imported posts —
        # keeps "latest revision" and "live" in sync from the moment this
        # page exists, rather than showing Leslie a false "unpublished
        # changes" state the first time she opens it.
        page.save_revision(log_action=False)
        report.created.append(label)
        return page

    @staticmethod
    def _unique_sibling_slug(parent, desired_slug: str) -> str:
        """
        `desired_slug` is normally free — a fresh database has no sibling
        to collide with. The one real exception this project has hit
        (retiring Wagtail's own default page is skipped when it
        unexpectedly has children — see `_retire_default_welcome_page`)
        would otherwise leave it sitting on slug "home" and make
        `parent.add_child()` raise a `ValidationError` on HomePage's own
        slug. Rather than let that abort the whole run, fall back to
        "<slug>-2", "<slug>-3", ... the same way Wagtail's own admin does
        when it auto-renames a slug clash.
        """
        existing = set(parent.get_children().values_list("slug", flat=True))
        if desired_slug not in existing:
            return desired_slug
        suffix = 2
        while f"{desired_slug}-{suffix}" in existing:
            suffix += 1
        return f"{desired_slug}-{suffix}"

    # -- Site record + Wagtail's own default page ----------------------

    def _ensure_site_root(self, home_page, report: BootstrapReport) -> None:
        """
        Wagtail's own initial migration always creates exactly one Site
        row (hostname="localhost", port=80, is_default_site=True) pointed
        at its default page — that row is what resolves "/" for any
        request whose Host header matches no other Site (see Wagtail's
        `Site.find_for_request`), which in practice means every request
        until a real hostname is configured. Nothing else in this project
        repoints it: `docker/entrypoint.sh`'s WAGTAIL_SITE_HOSTNAME step
        (added for the RSS-feed hostname fix — see OVERSIGHT_LOG.md,
        2026-09-24) only ever syncs this same row's hostname/port from the
        environment, and explicitly does nothing if the row doesn't exist.
        This method owns the other half: making sure that row's
        `root_page` is the real HomePage, without ever inventing a
        hostname (left at Wagtail's own "localhost" default for a
        genuinely new Site row — the entrypoint step corrects that
        separately, from configuration, not from a guess made here).
        """
        site = Site.objects.filter(is_default_site=True).first()

        if site is None:
            if not self.write:
                report.notes.append(
                    "No default Wagtail Site row exists — would create one "
                    "(hostname left at Wagtail's own 'localhost' default; "
                    "docker/entrypoint.sh syncs the real hostname separately) "
                    "pointed at the new HomePage."
                )
                return
            if home_page is None:
                report.skipped.append(
                    ("Default Wagtail Site", "no HomePage available yet to point it at")
                )
                return
            Site.objects.create(
                hostname="localhost", port=80, is_default_site=True, root_page=home_page
            )
            report.updated.append(
                "Created the default Wagtail Site record, pointed at the new HomePage "
                "(hostname left at Wagtail's own default — see docker/entrypoint.sh)"
            )
            return

        if home_page is not None and site.root_page_id == home_page.pk:
            report.existing.append(f"Default Site root page (already {home_page.title!r})")
            return

        if not self.write:
            current = site.root_page
            current_desc = f"{current.title!r} (id={current.pk})" if current else "no page"
            report.notes.append(
                f"Default Site's root page is currently {current_desc} — would repoint it "
                "at the new HomePage. Hostname/port are left untouched (docker/entrypoint.sh's "
                "concern, not this command's)."
            )
            return

        if home_page is None:
            report.skipped.append(
                ("Default Site root page", "no HomePage available yet to point it at")
            )
            return

        site.root_page = home_page
        site.save(update_fields=["root_page"])
        report.updated.append(
            f"Repointed the default Site's root page to the new HomePage (id={home_page.pk}) "
            "— hostname/port left untouched"
        )

    def _retire_default_welcome_page(self, report: BootstrapReport) -> None:
        """
        Wagtail's own default page has to go once HomePage is the site
        root, or it sits live and orphaned in the tree — reachable by its
        own URL, indexed, and confusing to find in the page explorer.
        Matched on BOTH its content type (a plain `wagtailcore.Page`, the
        type Wagtail's own migration used — never one of this project's
        own page types, which each have their own distinct content type)
        AND its exact stock title, so this can never match a real page a
        human created and happened to title similarly. If it has ever
        grown children (impossible via the admin, since every page type
        here restricts its own `parent_page_types` to `home.HomePage` —
        but this script does not trust the admin's own guardrails against
        itself), it is left alone rather than deleted out from under them.
        """
        default_page = WagtailPage.objects.filter(
            content_type=ContentType.objects.get_for_model(WagtailPage),
            title=WAGTAIL_DEFAULT_PAGE_TITLE,
        ).first()

        default_page_label = "Wagtail's default 'Welcome to your new Wagtail site!' page"

        if default_page is None:
            report.existing.append(f"{default_page_label} (already gone)")
            return

        if default_page.get_children().exists():
            report.skipped.append(
                (
                    default_page_label,
                    "it has child pages under it — left in place rather than guessing "
                    "what to do with them",
                )
            )
            return

        if not self.write:
            report.notes.append(f"Would delete {default_page_label} (id={default_page.pk}).")
            return

        page_id = default_page.pk
        default_page.delete()
        report.updated.append(f"Deleted {default_page_label} (id={page_id})")

    # -- placeholder content, one builder per page type ----------------
    #
    # Every builder below returns plain kwargs for its model's
    # constructor. Required StreamField text reads as an obvious
    # placeholder ("... coming soon", matching the wording style of
    # ContactSettings.years_experience_label's own default — apps/core/
    # models.py); every optional/relational field (image, snippet, linked
    # page) is left blank or None. See the module docstring for why.

    @staticmethod
    def _cta_kwargs(text: str = "") -> dict:
        return {"text": text, "page": None, "url": ""}

    def _home_kwargs(self) -> dict:
        return dict(
            title="Home",
            slug="home",
            hero=[
                (
                    "hero",
                    {
                        "eyebrow": "",
                        "headline": "Homepage headline coming soon",
                        "subheading": "",
                        "primary_button": self._cta_kwargs("Book a Reading"),
                        "secondary_button": self._cta_kwargs(),
                    },
                )
            ],
            services=[
                (
                    "services",
                    {
                        "heading": "Services",
                        "subline": "",
                        "featured_readings": [],
                        "image": None,
                        "image_caption": "",
                        "image_link": self._cta_kwargs(),
                    },
                )
            ],
            about=[
                (
                    "about",
                    {
                        "portrait": None,
                        "story": "<p>Full story coming soon.</p>",
                        "pull_quote": "",
                        "link_text": "Read my story",
                        "link_page": None,
                    },
                )
            ],
            testimonials=[("testimonials", {"heading": "What clients say", "testimonials": []})],
            latest_blog=[
                (
                    "latest_blog",
                    {
                        "heading": "From the Blog",
                        "subline": "",
                        "view_all_link_text": "View all posts",
                    },
                )
            ],
            final_cta=[
                (
                    "final_cta",
                    {
                        "headline": "Closing call-to-action heading coming soon",
                        "subline": "",
                        "button": self._cta_kwargs("Book a Reading"),
                    },
                )
            ],
        )

    def _about_kwargs(self) -> dict:
        return dict(
            title="About",
            slug="about",
            portrait=None,
            intro="",
            body=[],
            pull_quote="",
            three_promises=[
                (
                    "section",
                    {
                        "eyebrow": "What you can expect",
                        "heading": "Three promises",
                        "promises": [],
                    },
                )
            ],
            training_background=[
                (
                    "section",
                    {
                        "eyebrow": "Training & background",
                        "heading": "Where the knowledge comes from",
                        "body": "<p>Training and background details coming soon.</p>",
                        "link": self._cta_kwargs(),
                    },
                )
            ],
            cta=[],
        )

    def _readings_index_kwargs(self) -> dict:
        return dict(title="Readings", slug="readings", intro="", faq=[])

    def _booking_kwargs(self) -> dict:
        return dict(
            title="Book a Reading",
            slug="booking",
            intro="",
            cancellation_policy="",
            confirmation_message="",
        )

    def _blog_index_kwargs(self) -> dict:
        return dict(title="Blog", slug="blog", intro="")

    def _contact_kwargs(self) -> dict:
        # thank_you_message is deliberately not set here — ContactPage's
        # own field default ("Thank you — your message has been sent...")
        # is real, usable copy, not a §8-open item, so there is nothing
        # to place a placeholder in front of.
        return dict(title="Contact", slug="contact", intro="")

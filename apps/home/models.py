"""
The homepage (§7): hero, services, about, testimonials, latest blog posts,
final call-to-action, in that fixed order.

That order is locked by the design, not something Leslie should be able
to disturb. Rather than one reorderable StreamField holding all six
section types (which would let her drag "Final CTA" above the hero), each
section is its own StreamField field, restricted to exactly one block of
its own type. She still gets StreamField's rich editing UI (image
choosers, structured sub-fields, collapsible blocks) for each section —
she just can't reorder, remove, or duplicate sections into a layout the
design doesn't support.
"""

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from apps.home.blocks import (
    AboutTeaserBlock,
    FinalCTABlock,
    HeroBlock,
    LatestBlogTeaserBlock,
    ServicesTeaserBlock,
    TestimonialsTeaserBlock,
)


class HomePage(Page):
    # templates/home/index.html is the real file (see FINDING 3, review
    # 2026-09-22-project-structure-scaffold.md) — Wagtail's default lookup
    # would otherwise look for home/home_page.html and never find it.
    template = "home/index.html"

    hero = StreamField(
        [("hero", HeroBlock())],
        min_num=1,
        max_num=1,
        help_text="The top banner every visitor sees first.",
    )
    services = StreamField(
        [("services", ServicesTeaserBlock())],
        min_num=1,
        max_num=1,
        help_text="The services/readings section.",
    )
    about = StreamField(
        [("about", AboutTeaserBlock())],
        min_num=1,
        max_num=1,
        help_text="The short 'About' introduction.",
    )
    testimonials = StreamField(
        [("testimonials", TestimonialsTeaserBlock())],
        min_num=1,
        max_num=1,
        help_text="The testimonials section.",
    )
    latest_blog = StreamField(
        [("latest_blog", LatestBlogTeaserBlock())],
        min_num=1,
        max_num=1,
        help_text="The latest blog posts section. The posts themselves are "
        "chosen automatically — this is just its heading text.",
    )
    final_cta = StreamField(
        [("final_cta", FinalCTABlock())],
        min_num=1,
        max_num=1,
        help_text="The closing call-to-action band at the bottom of the page.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel([FieldPanel("hero")], heading="1. Hero"),
        MultiFieldPanel([FieldPanel("services")], heading="2. Services"),
        MultiFieldPanel([FieldPanel("about")], heading="3. About"),
        MultiFieldPanel([FieldPanel("testimonials")], heading="4. Testimonials"),
        MultiFieldPanel([FieldPanel("latest_blog")], heading="5. Latest Blog Posts"),
        MultiFieldPanel([FieldPanel("final_cta")], heading="6. Final Call to Action"),
    ]

    parent_page_types = ["wagtailcore.Page"]
    subpage_types = [
        "core.AboutPage",
        "readings.ReadingsIndexPage",
        "bookings.BookingPage",
        "blog.BlogIndexPage",
        "contact.ContactPage",
    ]
    max_count = 1

    class Meta:
        verbose_name = "Homepage"

    def get_context(self, request, *args, **kwargs):
        """
        FINDING 4 fix: the template's own section markup (hero/services/
        about/testimonials/latest_blog/final_cta) needs each section's
        *content*, not the raw StreamField wrapper. Each of those fields is
        restricted to exactly one block (min_num=1, max_num=1 — see the
        module docstring), so `self.<field>[0].value` is that section's
        StructValue: e.g. context["about"].portrait / .story / .pull_quote
        / .link_text / .link_page — there is no `.years` or
        `.practising_since` on it or anywhere else in this model; the
        years-of-experience figure is ContactSettings.years_experience_label
        (already available site-wide as settings.core.ContactSettings, see
        apps/core/models.py), not homepage content.

        The `[0]` is guarded rather than assumed, because min_num/max_num
        are editor-form validation, not a database constraint — a HomePage
        created outside the admin (a fixture, a script) could still have an
        empty StreamField.
        """
        context = super().get_context(request, *args, **kwargs)
        context["active_nav"] = "home"

        def section(stream_field):
            return stream_field[0].value if stream_field else None

        context["hero"] = section(self.hero)
        context["services"] = section(self.services)
        context["about"] = section(self.about)
        context["testimonials"] = section(self.testimonials)
        context["latest_blog"] = section(self.latest_blog)
        context["final_cta"] = section(self.final_cta)

        # Deferred import avoids a hard cross-app import at module load time.
        from apps.blog.models import BlogPost

        context["latest_posts"] = (
            BlogPost.objects.live()
            .public()
            .order_by("-published_date")
            .select_related("featured_image", "category")[:2]
        )
        return context

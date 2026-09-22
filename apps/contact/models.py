"""
Contact (§4/§5): a Contact page, and local storage for what it collects.

The email-marketing platform (Mailchimp, etc.) is unconfirmed (§8), so
`NewsletterSignup` deliberately just stores an email address locally
rather than calling out to a specific provider's API. Once a platform is
chosen, whoever wires it in can sync from this table (or replace it with
a direct API integration) — nothing here needs to guess that choice now.
"""

from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page


class ContactPage(Page):
    """The Contact page (§4): enquiry form, plus contact details and socials
    from ContactSettings (see apps.core) rendered around it."""

    intro = models.TextField(
        blank=True, help_text="Shown above the contact form."
    )
    thank_you_message = models.TextField(
        blank=True,
        default="Thank you — your message has been sent. I'll be in touch soon.",
        help_text="Shown after someone successfully submits the contact form.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("thank_you_message"),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1

    class Meta:
        verbose_name = "Contact page"


class ContactSubmission(models.Model):
    """
    A single contact form enquiry. Stored so nothing is lost if an email
    fails to send, and so Leslie has a record of enquiries even before an
    email-marketing/CRM platform is chosen.
    """

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField()
    newsletter_opt_in = models.BooleanField(
        default=False,
        help_text="Whether this person also asked to join the newsletter.",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contact submission"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.submitted_at:%Y-%m-%d}"


class NewsletterSignup(models.Model):
    """
    A newsletter signup captured on the site. This is local storage only
    — §8 leaves the email-marketing platform open, so no provider-specific
    sync happens here.
    """

    email = models.EmailField(unique=True)
    source = models.CharField(
        max_length=50,
        blank=True,
        help_text="Where this signup came from, e.g. 'homepage footer' or "
        "'contact page'. Helps Leslie see what's working.",
    )
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Newsletter signup"
        ordering = ["-subscribed_at"]

    def __str__(self):
        return self.email

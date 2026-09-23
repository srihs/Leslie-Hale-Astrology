"""
Plain Django forms for every /manage/ screen.

None of these are Wagtail's own `WagtailAdminModelForm` or StreamField
widgets — that machinery expects Wagtail admin's own JS/CSS bundle
(telepath), which this bespoke admin never loads (Leslie never sees
Wagtail's admin at all — see apps/backoffice/middleware.py). Every field
a model stores as a StreamField is represented here as a plain field
instead (a line-per-item textarea, a "one blank line between paragraphs"
textarea), converted at the view layer through apps/backoffice/content.py
— never rendered as Wagtail's block editor.

Labels are written for Leslie, not for a developer (interaction-design:
form-design — a label is the field's only documentation for someone who
will never read this file). Several fields' labels spell out exactly
which public page a value appears on, per the task brief's instruction
for the Readings screen ("make that relationship obvious in the form
labels") — applied here to every screen, not just that one, since the
same confusion (does editing this change one thing or three?) is
possible anywhere a snippet or setting feeds more than one page.
"""

from __future__ import annotations

from django import forms
from django.utils import timezone

from apps.backoffice.content import charlist_to_lines, create_image_from_upload, lines_to_charlist
from apps.bookings.models import AvailabilityException, AvailabilityRule, Booking
from apps.readings.models import Reading


class ReadingForm(forms.ModelForm):
    """
    A reading's name, description and price — the ONE place that
    controls what appears as a reading on the Services page (/readings/)
    AND as a choosable option on the booking page. Editing it here
    changes both at once (see apps/readings/models.py's own design).
    """

    image_upload = forms.ImageField(
        required=False,
        label="Photo or icon",
        help_text="Upload an image for this reading (JPG or PNG). Leave blank to keep the current one.",
    )
    remove_image = forms.BooleanField(
        required=False,
        label="Remove the current image",
        help_text="Tick to remove the image without replacing it.",
    )
    features_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="What's included",
        help_text="One item per line, e.g. '60 minutes, online or by phone'. Shown as a "
        "checklist on this reading's own page, if it has one.",
    )

    class Meta:
        model = Reading
        fields = [
            "name",
            "tag_label",
            "summary",
            "description",
            "duration_minutes",
            "price",
            "price_note",
            "order",
            "is_active",
            "is_most_booked",
        ]
        labels = {
            "name": "Name (shown on the Services page and in the booking form)",
            "tag_label": "Short tag, e.g. 'Natal chart' (shown next to this reading's number)",
            "summary": "Short description (Services page card and homepage)",
            "description": "Full description (this reading's own page, if it has one)",
            "duration_minutes": "Duration in minutes (used to build the booking calendar's time slots)",
            "price": "Price in NZD (shown on the Services page; charged when a client books)",
            "price_note": "Price note (shown instead of, or alongside, the price above — e.g. 'Price on enquiry')",
            "order": "Display order (lower numbers appear first, on the Services page and the booking form)",
            "is_active": "Show on the Services page and offer in the booking form",
            "is_most_booked": "Highlight as 'Most booked' on the Services page",
        }
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["features_text"].initial = charlist_to_lines(self.instance.features)

    def save(self, commit=True):
        reading = super().save(commit=False)
        reading.features = lines_to_charlist(self.cleaned_data.get("features_text", ""))

        upload = self.cleaned_data.get("image_upload")
        if upload:
            reading.image = create_image_from_upload(upload, title=reading.name)
        elif self.cleaned_data.get("remove_image"):
            reading.image = None

        if commit:
            reading.save()
        return reading


class AvailabilityRuleForm(forms.ModelForm):
    """A recurring weekly window when Leslie is available to take
    bookings, e.g. 'every Monday, 9am to 5pm'."""

    class Meta:
        model = AvailabilityRule
        fields = ["weekday", "start_time", "end_time", "is_active"]
        labels = {
            "weekday": "Day of the week",
            "start_time": "Available from",
            "end_time": "Available until",
            "is_active": "This weekly window is currently in use",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "Must be later than the start time.")
        return cleaned


class AvailabilityExceptionForm(forms.ModelForm):
    """A one-off change to a single date — a day off, a public holiday,
    or special hours that replace the usual weekly pattern just for that
    date."""

    class Meta:
        model = AvailabilityException
        fields = ["date", "is_closed", "start_time", "end_time", "note"]
        labels = {
            "date": "Date",
            "is_closed": "Closed all day (no bookings at all on this date)",
            "start_time": "Special hours from (only if not closed all day)",
            "end_time": "Special hours until (only if not closed all day)",
            "note": "Private note to yourself (not shown to clients)",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("is_closed"):
            start, end = cleaned.get("start_time"), cleaned.get("end_time")
            if not start or not end:
                raise forms.ValidationError(
                    "Set both a start and end time for the special hours, or tick "
                    "'Closed all day' instead."
                )
            if end <= start:
                self.add_error("end_time", "Must be later than the start time.")
        return cleaned


class BookingAnnotateForm(forms.ModelForm):
    """Leslie's own private note on a booking — never shown to the
    client (see apps/bookings/models.py:Booking.internal_notes)."""

    class Meta:
        model = Booking
        fields = ["internal_notes"]
        labels = {"internal_notes": "Private notes (only you see these)"}
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 4})}


class WebsiteTextForm(forms.Form):
    """
    Every piece of copy Leslie can change without a page tree or a
    StreamField editor: the homepage hero, her story, its pull quote and
    the three promises (About page), the Contact page's intro, and her
    contact details (ContactSettings). See
    apps/backoffice/views/website_text.py for exactly which model field
    each one reads from and writes back to, and for which fields this
    screen deliberately does NOT cover.
    """

    # --- Homepage hero ---------------------------------------------------
    hero_headline = forms.CharField(
        max_length=120,
        label="Homepage headline",
        help_text="The large heading on the homepage banner.",
    )
    hero_subheading = forms.CharField(
        max_length=200,
        required=False,
        label="Homepage intro line",
        help_text="The one line shown under the headline.",
    )

    # --- About page -------------------------------------------------------
    story_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10}),
        required=False,
        label="Your story",
        help_text="Shown on the About page. Leave a blank line between paragraphs.",
    )
    pull_quote = forms.CharField(
        max_length=300,
        required=False,
        label="Pull quote",
        help_text="A short line shown in large italic type on the About page.",
    )
    promises_eyebrow = forms.CharField(
        max_length=60, label="'Three promises' section label",
        help_text="Small label shown above the heading below.",
    )
    promises_heading = forms.CharField(max_length=100, label="'Three promises' heading")
    promise_1_title = forms.CharField(max_length=60, label="Promise 1 — title")
    promise_1_description = forms.CharField(
        max_length=250, widget=forms.Textarea(attrs={"rows": 2}), label="Promise 1 — description"
    )
    promise_2_title = forms.CharField(max_length=60, label="Promise 2 — title")
    promise_2_description = forms.CharField(
        max_length=250, widget=forms.Textarea(attrs={"rows": 2}), label="Promise 2 — description"
    )
    promise_3_title = forms.CharField(max_length=60, label="Promise 3 — title")
    promise_3_description = forms.CharField(
        max_length=250, widget=forms.Textarea(attrs={"rows": 2}), label="Promise 3 — description"
    )

    # --- Contact page -----------------------------------------------------
    contact_intro = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Contact page intro",
        help_text="Shown above the contact form.",
    )

    # --- Contact details (ContactSettings — shown across the whole site) --
    contact_email = forms.EmailField(
        required=False,
        label="Contact email",
        help_text="Used on the Contact page and for booking notifications. Nothing is "
        "shown on the site until this is filled in.",
    )
    contact_phone = forms.CharField(max_length=30, required=False, label="Contact phone (optional)")
    studio_address = forms.CharField(
        max_length=255,
        required=False,
        label="Studio address (optional)",
        help_text="Only fill this in if you see clients in person.",
    )
    instagram_url = forms.URLField(
        required=False, label="Instagram link (optional)", assume_scheme="https"
    )
    facebook_url = forms.URLField(
        required=False, label="Facebook link (optional)", assume_scheme="https"
    )
    years_experience_label = forms.CharField(
        max_length=60,
        label="Years of experience, as shown on the site",
        help_text="E.g. '12+ years'. Shown on the homepage and About page.",
    )


class BlogPostForm(forms.Form):
    """A single blog post. Categories are a short, curated list Leslie
    doesn't manage from here — ask your developer to add a new one."""

    title = forms.CharField(max_length=255, label="Title")
    excerpt = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Short summary",
        help_text="Shown on the blog index and homepage. Leave blank to use the start "
        "of the post instead.",
    )
    body_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12}),
        label="Post text",
        help_text="Leave a blank line between paragraphs.",
    )
    featured_image_upload = forms.ImageField(
        required=False,
        label="Featured image",
        help_text="Shown with this post on the blog index and homepage. Leave blank to "
        "keep the current one.",
    )
    remove_featured_image = forms.BooleanField(
        required=False, label="Remove the current featured image"
    )
    category = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Category",
        help_text="Which category this post appears under, and is filtered by, on the blog.",
    )
    published_date = forms.DateTimeField(
        label="Published date",
        help_text=f"When this should appear as published ({timezone.get_current_timezone_name()} time).",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    is_live = forms.BooleanField(
        required=False,
        label="Published (visible on the site)",
        help_text="Untick to save as a draft only you can see.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.blog.models import BlogCategory

        self.fields["category"].queryset = BlogCategory.objects.all().order_by("order", "name")

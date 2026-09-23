"""
Bookings screen (task item 3): a read list with a detail view.

Deliberate scope decision — cancellation vs. annotation, per the task
brief's instruction to "decide deliberately... and say what you chose":

Leslie CAN cancel a booking (sets `status=CANCELLED`, which frees the
slot — see apps/bookings/models.py's `ACTIVE_BOOKING_STATUSES` and the
`booking_no_overlapping_active_slots` exclusion constraint) and CAN add
a private note (`internal_notes`). She CANNOT touch `payment_status`,
issue a refund, or change `start_at`/`end_at` from here. Rescheduling
would mean re-running the same availability/concurrency logic
`apps/bookings/availability.py` and the exclusion constraint already
own, and refunds are a Stripe operation — both are booking-payments'
domain, and the task brief is explicit: "do not build payment
operations." Cancelling a booking here never touches `payment_status` —
`cancel_warns_about_payment` in the context contract below tells
htmx-frontend's template to say plainly that cancelling does not process
a refund, so Leslie isn't misled into thinking it does.

Birth data (birth_date, birth_time, birth_place) appears on the detail
view only, never the list — see the task brief and
apps/bookings/models.py's own module docstring on why it's sensitive.
Nothing here logs booking or client data.
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.backoffice.forms import BookingAnnotateForm
from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.bookings.availability import SITE_ZONE, tz_label
from apps.bookings.models import Booking, BookingStatus

PAGE_SIZE = 25
CANCELLABLE_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


def _localize(booking: Booking) -> Booking:
    """Attaches Leslie's-own-timezone display fields — view/model-method
    work, not template logic (CLAUDE.md: "No business logic in
    templates"). `SITE_ZONE` is the site's own operating timezone
    (settings.TIME_ZONE, Pacific/Auckland — apps/bookings/availability.py),
    not a per-visitor one: this screen is for Leslie, who only ever needs
    to see bookings in her own time."""
    booking.start_at_local = booking.start_at.astimezone(SITE_ZONE)
    booking.end_at_local = booking.end_at.astimezone(SITE_ZONE)
    booking.display_tz_label = tz_label(SITE_ZONE, at=booking.start_at)
    return booking


class BookingListView(BackofficeAccessRequiredMixin, ListView):
    template_name = "backoffice/booking_list.html"
    context_object_name = "bookings"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        qs = Booking.objects.select_related("reading").order_by("-start_at")
        status = self.request.GET.get("status", "").strip()
        if status in BookingStatus.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bookings"] = [_localize(b) for b in context["bookings"]]
        context["status_choices"] = BookingStatus.choices
        context["selected_status"] = self.request.GET.get("status", "")
        context["site_timezone_name"] = str(SITE_ZONE)
        return context


class BookingDetailView(BackofficeAccessRequiredMixin, DetailView):
    template_name = "backoffice/booking_detail.html"
    context_object_name = "booking"

    def get_queryset(self):
        return Booking.objects.select_related("reading")

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        return get_object_or_404(queryset, public_ref=self.kwargs["public_ref"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["booking"] = _localize(context["booking"])
        context["notes_form"] = BookingAnnotateForm(instance=self.object)
        context["can_cancel"] = self.object.status in CANCELLABLE_STATUSES
        context["cancel_warns_about_payment"] = self.object.payment_status == "paid"
        return context


class BookingAnnotateView(BackofficeAccessRequiredMixin, View):
    """POST-only: save `internal_notes`. See the module docstring for
    why this, and cancellation below, are the only two things Leslie can
    change about a booking from here."""

    def post(self, request, public_ref):
        booking = get_object_or_404(Booking, public_ref=public_ref)
        form = BookingAnnotateForm(request.POST, instance=booking)
        if form.is_valid():
            form.save()
            messages.success(request, "Note saved.")
        else:
            messages.error(request, "Could not save that note.")
        return redirect(reverse("backoffice:booking_detail", args=[public_ref]))


class BookingCancelView(BackofficeAccessRequiredMixin, View):
    """POST-only: cancel a booking (status -> CANCELLED). Never touches
    `payment_status` — see the module docstring."""

    def post(self, request, public_ref):
        booking = get_object_or_404(Booking, public_ref=public_ref)
        if booking.status in CANCELLABLE_STATUSES:
            booking.status = BookingStatus.CANCELLED
            booking.save(update_fields=["status", "updated_at"])
            messages.success(request, "Booking cancelled. This does not process a refund.")
        else:
            messages.error(request, "This booking can't be cancelled from here.")
        return redirect(reverse("backoffice:booking_detail", args=[public_ref]))

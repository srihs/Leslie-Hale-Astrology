"""
The /manage/ landing screen (task item 2): a quick at-a-glance summary
and, via the template's own navigation, links into every other screen.
No editing happens here — see this task's final report for the exact
context contract.
"""

from __future__ import annotations

from django.utils import timezone
from django.views.generic import TemplateView

from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.bookings.availability import SITE_ZONE, tz_label
from apps.bookings.models import ACTIVE_BOOKING_STATUSES, Booking
from apps.readings.models import Reading


class DashboardView(BackofficeAccessRequiredMixin, TemplateView):
    template_name = "backoffice/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()

        upcoming = (
            Booking.objects.filter(status__in=ACTIVE_BOOKING_STATUSES, start_at__gte=now)
            .select_related("reading")
            .order_by("start_at")
        )
        next_booking = upcoming.first()
        if next_booking is not None:
            next_booking.start_at_local = next_booking.start_at.astimezone(SITE_ZONE)
            next_booking.display_tz_label = tz_label(SITE_ZONE, at=next_booking.start_at)

        context["upcoming_booking_count"] = upcoming.count()
        context["next_booking"] = next_booking
        context["active_reading_count"] = Reading.objects.filter(is_active=True).count()
        return context

"""
Readings & prices screen (task item 4): full CRUD over the `Reading`
snippet — the one thing that drives both the Services page (/readings/)
and the booking page's list of choosable readings. See
apps/backoffice/forms.py:ReadingForm for why every label spells out
which of those two surfaces it affects.
"""

from __future__ import annotations

from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.backoffice.forms import ReadingForm
from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.readings.models import Reading


class ReadingListView(BackofficeAccessRequiredMixin, ListView):
    template_name = "backoffice/reading_list.html"
    context_object_name = "readings"
    queryset = Reading.objects.select_related("image", "detail_page").order_by("order", "name")


class ReadingCreateView(BackofficeAccessRequiredMixin, CreateView):
    model = Reading
    form_class = ReadingForm
    template_name = "backoffice/reading_form.html"
    success_url = reverse_lazy("backoffice:reading_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"'{self.object.name}' created.")
        return response


class ReadingUpdateView(BackofficeAccessRequiredMixin, UpdateView):
    model = Reading
    form_class = ReadingForm
    template_name = "backoffice/reading_form.html"
    success_url = reverse_lazy("backoffice:reading_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"'{self.object.name}' updated.")
        return response


class ReadingDeleteView(BackofficeAccessRequiredMixin, DeleteView):
    model = Reading
    template_name = "backoffice/reading_confirm_delete.html"
    success_url = reverse_lazy("backoffice:reading_list")

    def form_valid(self, form):
        """A Reading with existing bookings (or its own detail page) is
        protected from deletion at the database level (`on_delete=PROTECT`
        — see apps/bookings/models.py:Booking.reading and
        apps/readings/models.py:ReadingDetailPage.reading). Caught here so
        that hits a plain, friendly message instead of a 500."""
        name = self.object.name
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                f"'{name}' can't be deleted — it has existing bookings or its own "
                "page. Untick 'Show on the Services page' instead to hide it.",
            )
            return redirect(reverse("backoffice:reading_list"))
        messages.success(self.request, f"'{name}' deleted.")
        return redirect(self.success_url)

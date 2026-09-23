"""
Availability screen (task item 5): CRUD over `AvailabilityRule` (a
recurring weekly pattern) and `AvailabilityException` (a one-off date
override). Both together answer the same question in plain English —
"when am I free to take bookings" — see apps/bookings/availability.py,
which is what actually turns these into bookable slots on the public
site. This module never touches that file; it only edits the two models
it reads from.
"""

from __future__ import annotations

from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.backoffice.forms import AvailabilityExceptionForm, AvailabilityRuleForm
from apps.backoffice.permissions import BackofficeAccessRequiredMixin
from apps.bookings.models import AvailabilityException, AvailabilityRule

AVAILABILITY_URL = reverse_lazy("backoffice:availability")


class AvailabilityView(BackofficeAccessRequiredMixin, ListView):
    """One screen showing both the weekly pattern and any date-specific
    overrides — see the module docstring."""

    template_name = "backoffice/availability.html"
    context_object_name = "rules"
    queryset = AvailabilityRule.objects.order_by("weekday", "start_time")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["exceptions"] = AvailabilityException.objects.order_by("date")
        return context


class AvailabilityRuleCreateView(BackofficeAccessRequiredMixin, CreateView):
    model = AvailabilityRule
    form_class = AvailabilityRuleForm
    template_name = "backoffice/availability_rule_form.html"
    success_url = AVAILABILITY_URL


class AvailabilityRuleUpdateView(BackofficeAccessRequiredMixin, UpdateView):
    model = AvailabilityRule
    form_class = AvailabilityRuleForm
    template_name = "backoffice/availability_rule_form.html"
    success_url = AVAILABILITY_URL


class AvailabilityRuleDeleteView(BackofficeAccessRequiredMixin, DeleteView):
    model = AvailabilityRule
    template_name = "backoffice/availability_rule_confirm_delete.html"
    success_url = AVAILABILITY_URL


class AvailabilityExceptionCreateView(BackofficeAccessRequiredMixin, CreateView):
    model = AvailabilityException
    form_class = AvailabilityExceptionForm
    template_name = "backoffice/availability_exception_form.html"
    success_url = AVAILABILITY_URL


class AvailabilityExceptionUpdateView(BackofficeAccessRequiredMixin, UpdateView):
    model = AvailabilityException
    form_class = AvailabilityExceptionForm
    template_name = "backoffice/availability_exception_form.html"
    success_url = AVAILABILITY_URL


class AvailabilityExceptionDeleteView(BackofficeAccessRequiredMixin, DeleteView):
    model = AvailabilityException
    template_name = "backoffice/availability_exception_confirm_delete.html"
    success_url = AVAILABILITY_URL

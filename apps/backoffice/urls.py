"""
URL map for /manage/ — see this task's final report for the full table
alongside the context contract per screen (what each view puts in
context for htmx-frontend's templates to render).
"""

from __future__ import annotations

from django.urls import path

from apps.backoffice.views import auth, availability, blog, bookings, dashboard, readings, website_text

app_name = "backoffice"

urlpatterns = [
    path("login/", auth.BackofficeLoginView.as_view(), name="login"),
    path("logout/", auth.BackofficeLogoutView.as_view(), name="logout"),
    path("", dashboard.DashboardView.as_view(), name="dashboard"),
    # --- Bookings (screen 3) ---------------------------------------------
    path("bookings/", bookings.BookingListView.as_view(), name="booking_list"),
    path("bookings/<uuid:public_ref>/", bookings.BookingDetailView.as_view(), name="booking_detail"),
    path(
        "bookings/<uuid:public_ref>/notes/",
        bookings.BookingAnnotateView.as_view(),
        name="booking_annotate",
    ),
    path(
        "bookings/<uuid:public_ref>/cancel/",
        bookings.BookingCancelView.as_view(),
        name="booking_cancel",
    ),
    # --- Readings & prices (screen 4) -------------------------------------
    path("readings/", readings.ReadingListView.as_view(), name="reading_list"),
    path("readings/new/", readings.ReadingCreateView.as_view(), name="reading_create"),
    path("readings/<int:pk>/edit/", readings.ReadingUpdateView.as_view(), name="reading_update"),
    path("readings/<int:pk>/delete/", readings.ReadingDeleteView.as_view(), name="reading_delete"),
    # --- Availability (screen 5) ------------------------------------------
    path("availability/", availability.AvailabilityView.as_view(), name="availability"),
    path(
        "availability/rules/new/",
        availability.AvailabilityRuleCreateView.as_view(),
        name="availability_rule_create",
    ),
    path(
        "availability/rules/<int:pk>/edit/",
        availability.AvailabilityRuleUpdateView.as_view(),
        name="availability_rule_update",
    ),
    path(
        "availability/rules/<int:pk>/delete/",
        availability.AvailabilityRuleDeleteView.as_view(),
        name="availability_rule_delete",
    ),
    path(
        "availability/exceptions/new/",
        availability.AvailabilityExceptionCreateView.as_view(),
        name="availability_exception_create",
    ),
    path(
        "availability/exceptions/<int:pk>/edit/",
        availability.AvailabilityExceptionUpdateView.as_view(),
        name="availability_exception_update",
    ),
    path(
        "availability/exceptions/<int:pk>/delete/",
        availability.AvailabilityExceptionDeleteView.as_view(),
        name="availability_exception_delete",
    ),
    # --- Blog posts (screen 6) --------------------------------------------
    path("blog/", blog.BlogPostListView.as_view(), name="blog_list"),
    path("blog/new/", blog.BlogPostFormView.as_view(), name="blog_create"),
    path("blog/<int:pk>/edit/", blog.BlogPostFormView.as_view(), name="blog_update"),
    path("blog/<int:pk>/delete/", blog.BlogPostDeleteView.as_view(), name="blog_delete"),
    # --- Website text (screen 7) -------------------------------------------
    path("website-text/", website_text.WebsiteTextView.as_view(), name="website_text"),
]

"""
Login/logout for /manage/ — a small, separate auth flow from Wagtail's
own (/admin/login/) and Django's (/django-admin/login/), per the task
brief: Leslie never sees either of those. Both other admin logins keep
working unmodified; this is a third, independent one, reusing Django's
own `LoginView`/`LogoutView` rather than writing session handling by
hand.

django-axes coverage (task brief: "confirm it covers this view too") —
config/settings/base.py lists `axes.backends.AxesStandaloneBackend`
first in `AUTHENTICATION_BACKENDS` and `axes.middleware.AxesMiddleware`
last in `MIDDLEWARE`, both applied globally to every request and every
call to `django.contrib.auth.authenticate()`, not scoped to a particular
URL (that scoping exists — `AXES_ONLY_ADMIN_SITE` — and is deliberately
NOT set here, per that setting's own comment). `BackofficeLoginForm`
below subclasses Django's own `AuthenticationForm`, which calls
`authenticate()` the same way Django's and Wagtail's login views do, so
a brute-force attempt against THIS view is throttled by the same
AXES_FAILURE_LIMIT / cooloff as the other two. See
apps/backoffice/tests/test_login.py for a test that exercises the shared
`authenticate()` call directly.
"""

from __future__ import annotations

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy

from apps.backoffice.permissions import user_can_access_backoffice


class BackofficeLoginForm(AuthenticationForm):
    """Correct credentials for an account without /manage/ access are
    still refused — `confirm_login_allowed` runs after Django's own
    credential check, so this never reveals whether a username exists,
    only that "that account can't sign in here"."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "no_access": "That account can't sign in here.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user_can_access_backoffice(user):
            raise ValidationError(self.error_messages["no_access"], code="no_access")


class BackofficeLoginView(LoginView):
    """
    Context contract for htmx-frontend: just `form` (a `BackofficeLoginForm`,
    Django's own LoginView convention) — see this task's final report for
    the full per-screen contract table.
    """

    template_name = "backoffice/login.html"
    authentication_form = BackofficeLoginForm
    # An authenticated-but-unauthorised visitor must be told "no access"
    # via the form above, not silently bounced back to /manage/ (which
    # would 403) and then back here again.
    redirect_authenticated_user = False

    def get_success_url(self):
        return str(reverse_lazy("backoffice:dashboard"))


class BackofficeLogoutView(LogoutView):
    """POST-only (Django 5's own LogoutView default) — htmx-frontend's
    logout control must be a form, not a bare link. Intentionally NOT
    gated by BackofficeAccessRequiredMixin: logging out an
    already-anonymous or already-unauthorised session is a harmless
    no-op, and gating it would only risk a confusing 403 on the one
    action meant to always succeed."""

    next_page = reverse_lazy("backoffice:login")

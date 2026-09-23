"""
Access control for /manage/, the bespoke admin.

One gate, checked the same way by every view: the requesting user must be
authenticated, active, and hold the `backoffice.access_backoffice`
permission (see `apps/backoffice/models.py:BackofficeAccess`).
Deliberately not `is_staff` or `is_superuser` — Leslie's account holds
neither (see `apps/backoffice/management/commands/create_editor.py`), so
this is the one flag that actually distinguishes "can use /manage/" from
"can use Wagtail's /admin/ or Django's /django-admin/" (locked down
separately — see `apps/backoffice/middleware.py`).

A superuser passes this check too: Django's `ModelBackend.has_perm`
always returns True for `is_superuser`, regardless of what's actually
been granted. That's intentional here, not an oversight — SAS Creative's
own superuser accounts can QA /manage/ without a second, parallel
permission grant.
"""

from __future__ import annotations

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy

BACKOFFICE_PERMISSION = "backoffice.access_backoffice"


def user_can_access_backoffice(user) -> bool:
    """The one predicate every /manage/ view's access decision reduces
    to. Kept as a plain function (not just inlined in the mixin below) so
    it can be unit-tested directly, without a request/response cycle —
    see apps/backoffice/tests/test_access.py."""
    return bool(
        user.is_authenticated and user.is_active and user.has_perm(BACKOFFICE_PERMISSION)
    )


class BackofficeAccessRequiredMixin:
    """
    Mix into every class-based view under /manage/ except the login view
    itself (login must be reachable by definition). Checked in
    `dispatch()`, before any other view logic runs — including any
    `get_object()`/database lookup a subclass's GET or POST would
    otherwise do first — so a refused request never touches booking,
    reading or page data, and never reaches `render()` either.

    An anonymous request is sent to the bespoke login page (never
    Wagtail's or Django's — see apps/backoffice/views/auth.py). An
    authenticated request without the permission gets a plain 403, not a
    redirect loop back to a login screen it would never pass.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(), login_url=reverse_lazy("backoffice:login")
            )
        if not user_can_access_backoffice(request.user):
            raise PermissionDenied("This account cannot access the management area.")
        return super().dispatch(request, *args, **kwargs)

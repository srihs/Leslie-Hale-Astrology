"""
Explicit, defensive lock on Wagtail's and Django's own admin sites —
`/admin/` and `/django-admin/` (config/urls.py) — to superusers only.

Wagtail's own permission model would already block Leslie in practice:
`/admin/` requires the `wagtailadmin.access_admin` permission, which
nobody has unless granted directly or via the "Editors"/"Moderators"
groups Wagtail creates, and Leslie's account (see
apps/backoffice/management/commands/create_editor.py) is never added to
either. But "blocked provided nobody ever adds her to a group later" is
an emergent property, not a locked-down rule — the task brief is
explicit that Wagtail's admin "stays available to superusers only. Lock
it down." This middleware makes that a standing, explicit rule instead,
independent of group membership nobody has audited.

Only acts on authenticated requests: an anonymous visitor hitting
`/admin/login/` or `/django-admin/login/` must still see the real login
form so a superuser can actually sign in. Once authenticated, a
non-superuser hitting either prefix gets a plain 403.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied

LOCKED_PREFIXES = ("/admin/", "/django-admin/")


class WagtailAdminSuperuserOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.is_superuser
            and request.path.startswith(LOCKED_PREFIXES)
        ):
            raise PermissionDenied("This account cannot access the Wagtail or Django admin.")
        return self.get_response(request)

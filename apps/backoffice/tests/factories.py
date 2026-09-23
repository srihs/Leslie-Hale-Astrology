from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission


def make_backoffice_user(username="leslie", password="not-a-real-password", **extra):
    """A user who CAN reach /manage/ — non-staff, non-superuser, holding
    only the one custom permission that actually gates it. Mirrors what
    `python manage.py create_editor` sets up for real (see
    apps/backoffice/management/commands/create_editor.py)."""
    User = get_user_model()
    user = User.objects.create_user(username=username, password=password, is_staff=False, **extra)
    permission = Permission.objects.get(
        content_type__app_label="backoffice", codename="access_backoffice"
    )
    user.user_permissions.add(permission)
    return user


def make_plain_user(username="visitor", password="not-a-real-password", **extra):
    """An ordinary authenticated user with no /manage/ access at all —
    the 'non-staff user' the task brief asks every /manage/ view to
    refuse."""
    User = get_user_model()
    return User.objects.create_user(username=username, password=password, is_staff=False, **extra)

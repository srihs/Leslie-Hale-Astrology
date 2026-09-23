"""
Creates or updates Leslie's /manage/ account: a normal Django user with
`is_staff=False` and `is_superuser=False` (so /admin/ and /django-admin/
both stay closed to her — see apps/backoffice/middleware.py), granted the
one permission that actually opens /manage/
(`backoffice.access_backoffice` — see apps/backoffice/models.py).

Usage:
    python manage.py create_editor <username> <email> --password <password>

If the username already exists, its password/email/permission are
updated rather than a second account being created — safe to re-run,
e.g. to reset a forgotten password.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the non-superuser account used to sign in at /manage/."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("email")
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        username, email, password = options["username"], options["email"], options["password"]

        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.set_password(password)
        user.save()

        try:
            permission = Permission.objects.get(
                content_type__app_label="backoffice", codename="access_backoffice"
            )
        except Permission.DoesNotExist as exc:
            raise CommandError(
                "backoffice.access_backoffice permission not found — run "
                "`python manage.py migrate` first."
            ) from exc
        user.user_permissions.add(permission)

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} /manage/ account '{username}'."))

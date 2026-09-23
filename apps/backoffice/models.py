"""
apps.backoffice has no content models of its own. Every /manage/ screen
reads and writes models owned by other apps — apps.readings.Reading,
apps.bookings.{AvailabilityRule,AvailabilityException,Booking},
apps.core.{AboutPage,ContactSettings}, apps.contact.ContactPage,
apps.blog.BlogPost — never duplicating their data. See each view
module's own docstring (apps/backoffice/views/) for exactly which fields
of which app it touches.

The one thing defined here, `BackofficeAccess`, is not a real database
table (`managed = False` — Django still creates its Permission and
ContentType rows via the normal post-migrate signal, which is all this
exists for; no CREATE TABLE is ever issued). It exists purely so Django's
permission system has somewhere to attach a custom permission,
`backoffice.access_backoffice` — the single gate every /manage/ view
checks (see `apps/backoffice/permissions.py`).

Deliberately independent of `is_staff` and `is_superuser`: those are what
Django's own admin (/django-admin/) and Wagtail's admin (/admin/) key
off, and the access brief is explicit that Leslie's account must reach
neither. Granting this one permission — directly, or via a group — is
enough to reach /manage/ and nothing else. See
apps/backoffice/management/commands/create_editor.py for how her actual
account is provisioned with it.
"""

from django.db import models


class BackofficeAccess(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("access_backoffice", "Can access the management dashboard (/manage/)"),
        ]

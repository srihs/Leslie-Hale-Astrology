"""
Locks /admin/ (Wagtail) and /django-admin/ (Django) to superusers only —
see apps/backoffice/middleware.py's own docstring for why this is an
explicit, standing rule rather than an emergent property of nobody
having granted Leslie's account admin group membership.

Uses `client.force_login(user)` throughout, not `client.login(username=,
password=)`: the latter calls `django.contrib.auth.authenticate()`
without a real request object, which django-axes' backend rejects
outright (see test_login.py's `_request()` helper, where a real request
is deliberately constructed because THAT test is specifically about
axes). Irrelevant to what these tests check, so sidestepped here.
"""

from __future__ import annotations

import pytest

from apps.backoffice.tests.factories import make_backoffice_user, make_plain_user

pytestmark = pytest.mark.django_db


def test_wagtail_admin_blocks_a_manage_only_account(client):
    """Holding `backoffice.access_backoffice` (i.e. full /manage/ access)
    must not, by itself, open /admin/ too — the two are independent."""
    user = make_backoffice_user()
    client.force_login(user)
    response = client.get("/admin/")
    assert response.status_code == 403


def test_wagtail_admin_blocks_plain_non_superuser(client):
    user = make_plain_user()
    client.force_login(user)
    response = client.get("/admin/")
    assert response.status_code == 403


def test_django_admin_blocks_non_superuser(client):
    user = make_plain_user()
    client.force_login(user)
    response = client.get("/django-admin/")
    assert response.status_code == 403


def test_wagtail_admin_still_open_to_superusers(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="agency", email="agency@example.com", password="not-a-real-password"
    )
    client.force_login(user)
    response = client.get("/admin/")
    assert response.status_code != 403


def test_django_admin_still_open_to_superusers(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="agency2", email="agency2@example.com", password="not-a-real-password"
    )
    client.force_login(user)
    response = client.get("/django-admin/")
    assert response.status_code != 403


def test_anonymous_can_still_reach_wagtail_login(client):
    """The middleware must not block an anonymous request outright — a
    superuser still needs to be able to log in."""
    response = client.get("/admin/login/")
    assert response.status_code != 403


def test_anonymous_can_still_reach_django_admin_login(client):
    response = client.get("/django-admin/login/")
    assert response.status_code != 403

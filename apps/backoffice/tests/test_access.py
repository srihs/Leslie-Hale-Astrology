"""
Access control for every /manage/ view (task instruction: "add tests for
access control — that an anonymous request and a non-staff user are both
refused on every /manage/ view").

Deliberately does NOT assert what a *permitted* user sees — the
templates each view renders (backoffice/*.html) are htmx-frontend's
concurrent, not-yet-built work, and asserting a 200 here would just be
testing whether that other agent has finished, not whether this app's
own access control is correct. What every parametrised test below
asserts instead is that refusal happens in
`BackofficeAccessRequiredMixin.dispatch()` (apps/backoffice/permissions.py)
— before any template is ever touched, and before any booking/reading/
page object is even looked up — which is true regardless of what
htmx-frontend has built so far.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.backoffice.permissions import user_can_access_backoffice
from apps.backoffice.tests.factories import make_backoffice_user, make_plain_user

pytestmark = pytest.mark.django_db


def _protected_urls():
    """(name, kwargs, method) for every /manage/ view except login/
    logout. Logout is intentionally reachable regardless of auth state
    (see apps/backoffice/views/auth.py) and login is the one screen
    anonymous visitors must reach — neither belongs in a "must refuse"
    list. Object pks/refs below don't need to exist: the permission
    check runs before any lookup, so a refused request never reaches
    `get_object()`."""
    booking_ref = uuid.uuid4()
    return [
        ("backoffice:dashboard", {}, "get"),
        ("backoffice:booking_list", {}, "get"),
        ("backoffice:booking_detail", {"public_ref": booking_ref}, "get"),
        ("backoffice:booking_annotate", {"public_ref": booking_ref}, "post"),
        ("backoffice:booking_cancel", {"public_ref": booking_ref}, "post"),
        ("backoffice:reading_list", {}, "get"),
        ("backoffice:reading_create", {}, "get"),
        ("backoffice:reading_update", {"pk": 1}, "get"),
        ("backoffice:reading_delete", {"pk": 1}, "get"),
        ("backoffice:availability", {}, "get"),
        ("backoffice:availability_rule_create", {}, "get"),
        ("backoffice:availability_rule_update", {"pk": 1}, "get"),
        ("backoffice:availability_rule_delete", {"pk": 1}, "get"),
        ("backoffice:availability_exception_create", {}, "get"),
        ("backoffice:availability_exception_update", {"pk": 1}, "get"),
        ("backoffice:availability_exception_delete", {"pk": 1}, "get"),
        ("backoffice:blog_list", {}, "get"),
        ("backoffice:blog_create", {}, "get"),
        ("backoffice:blog_update", {"pk": 1}, "get"),
        ("backoffice:blog_delete", {"pk": 1}, "get"),
        ("backoffice:website_text", {}, "get"),
    ]


@pytest.mark.parametrize("name,kwargs,method", _protected_urls())
def test_anonymous_request_is_sent_to_login(client, name, kwargs, method):
    url = reverse(name, kwargs=kwargs)
    response = getattr(client, method)(url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("backoffice:login"))


@pytest.mark.parametrize("name,kwargs,method", _protected_urls())
def test_authenticated_non_staff_user_is_refused(client, name, kwargs, method):
    # `force_login` (sets the session directly), not `client.login`
    # (`login` calls `django.contrib.auth.authenticate()` without a real
    # request, which django-axes' backend rejects outright — see
    # test_login.py's own `_request()` helper for the same constraint
    # handled deliberately there; here it's simply irrelevant to what
    # this test is checking, so it's sidestepped instead).
    user = make_plain_user()
    client.force_login(user)
    url = reverse(name, kwargs=kwargs)
    response = getattr(client, method)(url)
    assert response.status_code == 403


def test_permitted_user_passes_the_access_check():
    """Unit-level, template-free proof that a correctly permissioned
    account is NOT refused by the mixin's own predicate — the one thing
    the two parametrised tests above don't cover on their own (they only
    prove refusal)."""
    user = make_backoffice_user()
    assert user_can_access_backoffice(user) is True


def test_plain_authenticated_user_fails_the_access_check():
    user = make_plain_user()
    assert user_can_access_backoffice(user) is False


def test_anonymous_fails_the_access_check():
    assert user_can_access_backoffice(AnonymousUser()) is False


def test_inactive_backoffice_user_is_refused(client):
    """A permission grant alone isn't enough — a deactivated account
    (e.g. offboarding) must lose access even if nobody remembers to
    revoke the permission too."""
    user = make_backoffice_user(username="leaving", is_active=False)
    assert user_can_access_backoffice(user) is False

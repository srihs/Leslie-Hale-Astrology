"""
Login behaviour for /manage/ (apps/backoffice/views/auth.py).

The lockout test below is deliberately template-free: it exercises
`django.contrib.auth.authenticate()` directly rather than posting to the
login view, because `BackofficeLoginView` renders `backoffice/login.html`
on every GET and every invalid POST (Django's own `LoginView.
form_invalid` behaviour), and that template is htmx-frontend's
concurrent, not-yet-built work — see test_access.py's module docstring
for the same constraint applied to every other /manage/ view.

What this proves instead, confirmed empirically against this project's
pinned django-axes (8.3.1) before being written this way:
`AxesStandaloneBackend.authenticate()` requires a real `request` and
raises if passed one; five failed calls through it lock the account out
such that even a SIXTH call with the CORRECT password still returns
`None` — proof the lockout, not just a wrong password, is what's
blocking. `BackofficeLoginForm` is a subclass of Django's own
`AuthenticationForm`, which calls exactly this `authenticate()` — the
same call Django's and Wagtail's own login views make (AUTHENTICATION_
BACKENDS is global, config/settings/base.py) — so locking out this call
locks out this view too.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.backoffice.tests.factories import make_backoffice_user, make_plain_user
from apps.backoffice.views.auth import BackofficeLoginForm

pytestmark = pytest.mark.django_db


def _request():
    """A real request with a real session — axes reads/writes session
    state as part of its own tracking, and `AxesStandaloneBackend.
    authenticate()` raises outright if `request` is None."""
    request = RequestFactory().post("/manage/login/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


def test_login_form_reuses_djangos_authentication_form():
    """The structural fact the module docstring's reasoning depends on:
    if this ever stopped being true, django-axes coverage would need
    re-confirming."""
    assert issubclass(BackofficeLoginForm, AuthenticationForm)


def test_repeated_failed_logins_are_locked_out_by_axes():
    make_backoffice_user(username="leslie", password="correct-horse-battery-staple")

    for _ in range(5):  # AXES_FAILURE_LIMIT, config/settings/base.py
        result = authenticate(request=_request(), username="leslie", password="wrong-password")
        assert result is None

    # A 6th attempt, even with the RIGHT password, must still fail.
    locked_out_result = authenticate(
        request=_request(), username="leslie", password="correct-horse-battery-staple"
    )
    assert locked_out_result is None


def test_user_without_backoffice_access_is_rejected_by_the_login_form():
    # `request=` is required here, not optional: AuthenticationForm.clean()
    # calls authenticate(self.request, ...), and AxesStandaloneBackend
    # raises if that request is None (see _request()'s own docstring).
    make_plain_user(username="visitor", password="pw-for-test-only")
    form = BackofficeLoginForm(
        _request(), data={"username": "visitor", "password": "pw-for-test-only"}
    )
    assert form.is_valid() is False


def test_user_with_backoffice_access_passes_the_login_form():
    make_backoffice_user(username="leslie", password="correct-horse-battery-staple")
    form = BackofficeLoginForm(
        _request(), data={"username": "leslie", "password": "correct-horse-battery-staple"}
    )
    assert form.is_valid() is True

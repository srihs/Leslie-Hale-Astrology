"""
f989c39 — the managed focus-to-confirmation handler in static/js/main.js
tested the OLD, pre-submission form node (`e.detail.target`, fixed at
request time) against `target.matches('form.sent')`. The old form is
never marked `.sent` — only the freshly swapped-in one is — so that
condition was always false. This handler had never fired, on any form,
since it was written: 82ce1d8's own commit message claimed it worked,
and the accessibility audit recorded it as satisfied. Both were wrong.

The server-rendered fragment was never the problem — `.form.sent .ok`
really is in the response, really has `display:block` (static/css/
_components.css). The only thing broken is whether a real browser
actually MOVES FOCUS there, which is exactly what this asserts and
exactly what no pytest-django response-content assertion can see.

Uses a fresh, disposable email address per run (uuid4) rather than a
fixed one: NewsletterSignup.email is unique, and this suite is run
against a real, persistent dev database — a fixed address would either
collide harmlessly (get_or_create) or, worse, make a rerun's pass
depend on state a previous run happened to leave behind.
"""

from __future__ import annotations

import uuid


def test_contact_form_focuses_confirmation_after_submit(page, base_url):
    page.goto(f"{base_url}/contact/")
    page.fill("#n", "Playwright Regression")
    page.fill("#e", f"pw-contact-{uuid.uuid4().hex}@example.invalid")
    page.fill("#m", "Automated browser regression test — safe to delete.")
    page.click("#contact-form-wrap button[type=submit]")
    page.wait_for_selector("#contact-form-wrap.sent")

    focus_is_confirmation = page.evaluate(
        "() => document.activeElement === document.querySelector('#contact-form-wrap .ok')"
    )
    assert focus_is_confirmation, (
        "focus did not move to the .ok confirmation after the contact form was "
        "marked .sent — the f989c39 focus handler is not firing"
    )


def test_newsletter_form_focuses_confirmation_after_submit(page, base_url):
    page.goto(f"{base_url}/contact/")
    page.fill("#em", f"pw-newsletter-{uuid.uuid4().hex}@example.invalid")
    page.click("#newsletter-form button[type=submit]")
    page.wait_for_selector("#newsletter-form.sent")

    focus_is_confirmation = page.evaluate(
        "() => document.activeElement === document.querySelector('#newsletter-form .ok')"
    )
    assert focus_is_confirmation, (
        "focus did not move to the .ok confirmation after the newsletter form was "
        "marked .sent — the f989c39 focus handler is not firing"
    )

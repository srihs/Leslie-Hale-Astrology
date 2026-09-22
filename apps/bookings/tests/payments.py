"""
A stub `PaymentProvider` (see apps/bookings/payments/base.py) for tests
that exercise `apps.bookings.views` without ever importing the real
`stripe` SDK or making a network call — the project rule ("No network
calls in tests. Mock Stripe and email at the boundary.") applied at
exactly the boundary `views.py` itself uses: `get_provider()`. Tests
monkeypatch `apps.bookings.views.get_provider` to return one of these,
scripted with whatever CheckoutSession/NormalizedWebhookEvent/error the
test is about — never a real Stripe call.
"""

from __future__ import annotations

from apps.bookings.payments.base import (
    CheckoutSession,
    NormalizedWebhookEvent,
    PaymentProvider,
    PaymentProviderError,
)


class StubPaymentProvider(PaymentProvider):
    name = "stub"

    def __init__(self, *, checkout_session=None, checkout_error=None, webhook_event=None, webhook_error=None):
        self._checkout_session = checkout_session
        self._checkout_error = checkout_error
        self._webhook_event = webhook_event
        self._webhook_error = webhook_error
        self.checkout_calls = []
        self.webhook_calls = []

    def create_checkout_session(self, booking, success_url, cancel_url):
        self.checkout_calls.append((booking, success_url, cancel_url))
        if self._checkout_error is not None:
            raise self._checkout_error
        return self._checkout_session or CheckoutSession(
            provider_reference=f"cs_test_{booking.public_ref}",
            redirect_url="https://checkout.stripe.test/pay/cs_test",
        )

    def verify_and_parse_webhook(self, payload, headers):
        self.webhook_calls.append((payload, headers))
        if self._webhook_error is not None:
            raise self._webhook_error
        if self._webhook_event is None:
            raise AssertionError("StubPaymentProvider.verify_and_parse_webhook called with no scripted event")
        return self._webhook_event


__all__ = [
    "StubPaymentProvider",
    "CheckoutSession",
    "NormalizedWebhookEvent",
    "PaymentProviderError",
]

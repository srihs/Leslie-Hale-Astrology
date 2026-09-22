"""
Stripe adapter — the one place in this codebase allowed to import the
`stripe` SDK, or to know about Stripe Checkout Sessions, webhook
signature verification, or Stripe's own event-type names. Everything
downstream (models.py, views.py, emails.py) works only with the
provider-agnostic types in payments/base.py.

Requires the `stripe` package. It is NOT yet in pyproject.toml — that
file belongs to docker-infra (see the final report's §8/dependency note)
— and the three env vars docker-infra already plumbed:
STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET.

Amounts: Stripe's Checkout API already takes `unit_amount` in integer
minor units (cents), which is exactly what `Booking.amount_minor` stores
— no conversion happens in this file, only in
apps.bookings.views.start_checkout where the snapshot is first taken from
the Reading's Decimal price.
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings

from apps.bookings.payments import register
from apps.bookings.payments.base import (
    CheckoutSession,
    NormalizedWebhookEvent,
    PaymentProvider,
    PaymentProviderError,
)

# Stripe's own event-type strings -> this app's provider-agnostic
# vocabulary (PaymentProvider.EVENT_*). Anything not listed here is a
# real Stripe event this app simply doesn't act on (EVENT_IGNORED), not
# an error.
_EVENT_MAP = {
    "checkout.session.completed": PaymentProvider.EVENT_PAYMENT_SUCCEEDED,
    "checkout.session.async_payment_succeeded": PaymentProvider.EVENT_PAYMENT_SUCCEEDED,
    "checkout.session.async_payment_failed": PaymentProvider.EVENT_PAYMENT_FAILED,
    "checkout.session.expired": PaymentProvider.EVENT_CHECKOUT_EXPIRED,
    "charge.refunded": PaymentProvider.EVENT_REFUNDED,
    "charge.dispute.created": PaymentProvider.EVENT_REFUNDED,
}


@register("stripe")
class StripeProvider(PaymentProvider):
    name = "stripe"

    def _client(self):
        # Imported lazily, and only here, so the `stripe` package is only
        # required at runtime when Stripe is actually the selected
        # provider — importing this module for its EVENT_* constants (as
        # payments/__init__.py does to register it) never requires the
        # package to be installed at all... except registration itself
        # only needs the class, not this method, so this stays lazy.
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    def create_checkout_session(self, booking, success_url: str, cancel_url: str) -> CheckoutSession:
        try:
            stripe = self._client()
            session = stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=booking.client_email,
                client_reference_id=str(booking.public_ref),
                line_items=[
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": booking.currency.lower(),
                            "unit_amount": booking.amount_minor,
                            "product_data": {
                                "name": f"{booking.reading.name} — Leslie Hale Astrology",
                            },
                        },
                    }
                ],
                metadata={"booking_ref": str(booking.public_ref)},
            )
        except Exception as exc:  # stripe.error.StripeError and any transport failure
            raise PaymentProviderError("Stripe checkout session creation failed") from exc

        return CheckoutSession(provider_reference=session.id, redirect_url=session.url)

    def verify_and_parse_webhook(self, payload: bytes, headers) -> NormalizedWebhookEvent:
        try:
            stripe = self._client()
        except ImportError as exc:  # the `stripe` package isn't installed
            raise PaymentProviderError("Stripe SDK is not available") from exc

        sig_header = headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except ValueError as exc:  # malformed payload
            raise PaymentProviderError("Stripe webhook payload could not be parsed") from exc
        except stripe.error.SignatureVerificationError as exc:  # untrusted sender
            raise PaymentProviderError("Stripe webhook signature did not verify") from exc

        data_object = event["data"]["object"]
        return NormalizedWebhookEvent(
            event_id=event["id"],
            event_type=_EVENT_MAP.get(event["type"], PaymentProvider.EVENT_IGNORED),
            provider_reference=data_object.get("id", ""),
            amount_minor=data_object.get("amount_total") or data_object.get("amount"),
            currency=(data_object.get("currency") or "").upper() or None,
            occurred_at=datetime.fromtimestamp(event["created"], tz=dt_timezone.utc),
        )

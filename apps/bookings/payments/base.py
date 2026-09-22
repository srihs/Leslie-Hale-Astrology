"""
The provider-agnostic shape every payment adapter implements.

§8 lists "booking/payment tools already in use" as unconfirmed with the
client. Stripe is wired in now (apps/bookings/payments/stripe_provider.py)
because the agent instruction directing this build named it as the
concrete choice — not because §8 is resolved. Everything in models.py and
views.py imports only from this module, never from a concrete adapter, so
a second provider is addable by writing one more file like
stripe_provider.py and changing `PAYMENT_PROVIDER` — nothing in booking
logic would need to change.

Nothing in this module, or in any code that imports only from this
module, may import a specific provider's SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class PaymentProviderError(Exception):
    """
    Raised by an adapter when it can't complete a request — a failed
    checkout-session creation, or a webhook that fails signature
    verification. The message is always safe to log: adapters must never
    put card data, tokens or provider secrets into it.
    """


@dataclass(frozen=True)
class CheckoutSession:
    """What booking logic needs back after starting a payment, and
    nothing provider-specific beyond it."""

    provider_reference: str  # the provider's own ID for this session/payment
    redirect_url: str  # where to send the browser to complete payment


@dataclass(frozen=True)
class NormalizedWebhookEvent:
    """
    A provider's webhook payload, reduced to only what booking logic acts
    on. `event_id` is the provider's own unique event identifier and is
    what makes webhook handling idempotent — see models.PaymentEvent and
    views.stripe_webhook.
    """

    event_id: str
    event_type: str  # one of PaymentProvider.EVENT_* below
    provider_reference: str
    amount_minor: Optional[int] = None
    currency: Optional[str] = None
    occurred_at: Optional[datetime] = None


class PaymentProvider(ABC):
    """
    Every concrete adapter (one per provider) implements this. The four
    event types below are the only vocabulary booking logic understands —
    an adapter translates whatever its own provider calls things into
    one of these, so provider-specific event names never leak past
    payments/<provider>_provider.py.
    """

    name: str = ""

    EVENT_PAYMENT_SUCCEEDED = "payment_succeeded"
    EVENT_PAYMENT_FAILED = "payment_failed"
    EVENT_CHECKOUT_EXPIRED = "checkout_expired"
    EVENT_REFUNDED = "refunded"
    # A real event the provider sent that booking logic doesn't act on
    # (e.g. Stripe sends many event types besides the ones above) — kept
    # distinct from an *invalid/unverifiable* event, which raises
    # PaymentProviderError instead.
    EVENT_IGNORED = "ignored"

    @abstractmethod
    def create_checkout_session(self, booking, success_url: str, cancel_url: str) -> CheckoutSession:
        """Start a payment for `booking` (a bookings.models.Booking, already
        holding its slot). `booking.amount_minor`/`booking.currency` are the
        integer-minor-units amount to charge — never re-derive money from a
        float here."""

    @abstractmethod
    def verify_and_parse_webhook(self, payload: bytes, headers) -> NormalizedWebhookEvent:
        """Verify the request actually came from this provider (signature
        check) before returning anything — webhooks are untrusted input.
        Raise PaymentProviderError for a payload that doesn't verify."""

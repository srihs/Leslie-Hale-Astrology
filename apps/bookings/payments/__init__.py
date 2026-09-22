"""
Payment provider factory. `get_provider()` is the only thing views.py
calls — it never imports a concrete adapter directly, which is what keeps
the provider swappable (SCOPE §8: the payment tool is unconfirmed with
the client). See base.py for the interface and stripe_provider.py for
the one adapter wired in so far.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.bookings.payments.base import PaymentProvider

_PROVIDERS: dict[str, type[PaymentProvider]] = {}


def register(name: str):
    """Decorator a concrete adapter uses to make itself selectable by name."""

    def _wrap(cls):
        _PROVIDERS[name] = cls
        return cls

    return _wrap


def get_provider() -> PaymentProvider:
    """
    Returns the configured provider. Reads `settings.PAYMENT_PROVIDER` if
    it's set (it isn't, yet — adding it to config/settings/base.py is a
    one-line, non-secret change left for whoever wires up a second
    provider); defaults to "stripe" to match the concrete choice this
    build was directed to implement.
    """
    from apps.bookings.payments import stripe_provider  # noqa: F401 — registers itself on import

    name = getattr(settings, "PAYMENT_PROVIDER", "stripe")
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError as exc:
        raise ImproperlyConfigured(
            f"PAYMENT_PROVIDER={name!r} has no registered adapter. "
            f"Registered: {sorted(_PROVIDERS)}"
        ) from exc
    return provider_cls()

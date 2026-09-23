"""
Non-page endpoints for the booking flow. BookingPage itself is a Wagtail
page (served by wagtail_urls; its step 1-2 GET flow lives in
BookingPage.get_context / apps/bookings/availability.py, not here) and has
no entry in apps/bookings/urls.py.

Three views live here:

- `save_details` — step 3's "your details" form. Unchanged in behaviour
  from the version this module already had: it validates and stages
  details in the session (`SESSION_KEY`), it does not create a `Booking`
  row. That was the right call when it was written (no availability/
  payment logic existed yet to attach a row to) and stays the right call
  now: the row is created at checkout time (`start_checkout`), in the
  same transaction as the slot reservation, once reading/day/slot are
  also known — creating it earlier would mean creating (and having to
  clean up) a booking row before a client has chosen a time at all.
- `start_checkout` (new) — turns steps 1-3 into one held `Booking` row
  plus a payment provider checkout session. This is where the database
  exclusion constraint in models.py actually gets exercised.
- `stripe_webhook` (new) — the untrusted, possibly-duplicated notification
  from the payment provider that money actually moved. Verifies the
  signature before trusting anything in the payload, and is idempotent
  via `PaymentEvent`'s unique constraint.
- `booking_status` (new) — a small polling fragment so the browser can
  find out once `stripe_webhook` has actually confirmed a booking, rather
  than trusting the payment provider's redirect alone (see the final
  report's note on why the redirect is UX only).

Sensitive data discipline: nothing in this file logs a card number,
token, email address, or birth detail — only `booking.public_ref` and,
for provider failures, an exception's type name.

Rate limiting (reviews/2026-09-22-final-security-review.md finding 1):
`save_details` and `start_checkout` are both public, unauthenticated POST
endpoints, and `start_checkout` is the one the finding names as serious —
a scripted attacker who never intends to pay can hold every visible slot
for HOLD_MINUTES at a time, indefinitely, by re-submitting before each
hold expires, which is a direct attack on the site's only revenue
mechanism. Both carry `@ratelimit` (key="ip", the cache configured in
config/settings/base.py CACHES/RATELIMIT_USE_CACHE). `start_checkout`
stacks two windows — a burst limit generous enough for a genuine retry
after a declined card or a "someone just took that slot" conflict, and an
hourly ceiling that caps how much of the calendar one IP can hold at all,
independent of how it paces its requests. `save_details` gets one
looser window: it only stages session data, so the blast radius of
flooding it is smaller, but it is the endpoint that must tolerate a
visitor genuinely re-typing/correcting their details several times.

Every limiter uses `block=False` and is checked explicitly
(`request.limited`) so a rate-limited visitor gets the same warm,
in-voice response the rest of this module already gives failures —
never django-ratelimit's bare default 403 — on both the htmx and the
no-JS path (see `_checkout_error`/`_render_booking_page`, reused as-is).

Proxy caveat: `key="ip"` resolves to `request.META['REMOTE_ADDR']` only
(django_ratelimit.core._get_ip) — it never reads X-Forwarded-For or any
other client-supplied header, so it cannot be spoofed by a header an
attacker sets themselves. That is also its limit: it is only *accurate*
— i.e. actually distinguishes one visitor's IP from another's, rather
than counting every request behind the same front door as one visitor —
if the process serving Django sees the real client socket. `prod.py`'s
own `SECURE_PROXY_SSL_HEADER` comment says a proxy sits in front of this
container, and Prohosting's actual proxy topology is unconfirmed
(PROJECT-SCOPE.md §1, same open item the CACHES backend comment already
flags). If that proxy forwards to gunicorn without preserving the real
client address, every visitor behind it collapses onto one REMOTE_ADDR
and shares one limit — worse for real visitors, not exploitable by an
attacker, but not the intended behaviour either. Deliberately not
"fixed" here by trusting X-Forwarded-For instead: that header is
attacker-writable unless the proxy is verified to strip any
client-supplied copy before appending its own, and that verification
depends on infrastructure this repo does not control and §1 does not yet
confirm. Whoever deploys this needs to confirm gunicorn actually sees
genuine per-visitor REMOTE_ADDR values (direct exposure, or a proxy that
preserves the real address) before trusting this limit's accuracy in
production; if that turns out not to hold, the fix is
`RATELIMIT_IP_META_KEY` pointed at whichever header the confirmed proxy
guarantees is clean, not a change to the key type here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal
import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.utils import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.bookings import availability
from apps.bookings.emails import send_booking_emails, send_payment_needs_attention_email
from apps.bookings.models import (
    Booking,
    BookingPage,
    BookingStatus,
    CURRENCY,
    HOLD_MINUTES,
    PaymentEvent,
    PaymentStatus,
)
from apps.bookings.payments import get_provider
from apps.bookings.payments.base import PaymentProviderError
from apps.readings.models import Reading

logger = logging.getLogger(__name__)

SESSION_KEY = "booking_details"
SESSION_KEY_HOLD = "booking_hold_ref"

# Rate-limited copy — Leslie's own voice (§2: warm, grounded, never
# "invalid"), not django-ratelimit's bare 403. Reassures nothing was lost
# or charged and says what to do next, per the same error-handling
# philosophy _checkout_error already documents.
DETAILS_RATE_LIMIT_MESSAGE = (
    "That's a few tries in a row — nothing you've typed has been lost. "
    "Please wait a minute and try again."
)
CHECKOUT_RATE_LIMIT_MESSAGE = (
    "That's a few attempts in quick succession — nothing has been charged, "
    "and your details are still here. Please wait a minute and try again."
)


def _render_booking_page(request, extra_context, *, status=200):
    """
    No-JS fallback for this module's booking-flow endpoints — BookingPage
    is these forms' one and only home (`save_details`'s form and the Pay
    form that leads to `start_checkout`/`_checkout_error` both only ever
    live on it), so we can render it directly rather than guessing from a
    referrer (contrast apps.contact.views._render_referring_page, needed
    there because the newsletter form is shared across several pages).

    FINDING 1, reviews/2026-09-22-final-build-review.md: `save_details`
    and `_checkout_error` used to `render()` their own bare partial for
    every request, htmx or not — a real no-JS POST (a full page
    navigation) got back a fragment with no `<!DOCTYPE>`, no nav, no
    stylesheet. Building the same context BookingPage's own GET would
    (`page.get_context`) and rendering the whole page means a no-JS
    visitor always lands back inside the site, styled, with a way back to
    every other page — not a dead end.
    """
    page = BookingPage.objects.live().first()
    if not page:
        # No BookingPage published yet — an unusual/edge state this fix
        # isn't responsible for.
        return None
    context = page.get_context(request)
    context.update(extra_context)
    return render(request, page.get_template(request), context, status=status)


@ratelimit(key="ip", rate="10/m", method="POST", block=False)
def save_details(request):
    """Validate the client's personal/birth details (POST only) and stage
    them in the session for `start_checkout` to read. htmx requests get
    the bare `_details_form.html` fragment back (correct — htmx swaps it
    into the form's own wrapper); a plain no-JS POST gets the whole
    booking page re-rendered with this same partial showing the saved
    state or field errors (see `_render_booking_page` above).

    Rate limit: 10/minute per IP (see module docstring). Generous enough
    for a visitor genuinely correcting a mistyped field several times in
    a row — this endpoint only stages session data, so the limit exists
    to stop cheap scripted flooding, not to police normal revision."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    values = {
        "first_name": request.POST.get("first_name", "").strip(),
        "last_name": request.POST.get("last_name", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "dob": request.POST.get("dob", "").strip(),
        "tob": request.POST.get("tob", "").strip(),
        "pob": request.POST.get("pob", "").strip(),
        "focus": request.POST.get("focus", "").strip(),
    }

    if getattr(request, "limited", False):
        context = {
            "details_values": values,
            "details_errors": {"rate_limited": [DETAILS_RATE_LIMIT_MESSAGE]},
            "details_submitted": False,
        }
        if getattr(request, "htmx", False):
            return render(request, "bookings/partials/_details_form.html", context, status=429)
        return _render_booking_page(request, context, status=429) or render(
            request, "bookings/partials/_details_form.html", context, status=429
        )

    errors = {}
    if not values["first_name"]:
        errors.setdefault("first_name", []).append("Please enter your first name.")
    if not values["last_name"]:
        errors.setdefault("last_name", []).append("Please enter your last name.")
    try:
        validate_email(values["email"])
    except ValidationError:
        errors.setdefault("email", []).append("Please enter a valid email.")
    if not values["dob"]:
        errors.setdefault("dob", []).append("Please enter your date of birth.")
    if not values["pob"]:
        errors.setdefault("pob", []).append("Please enter your place of birth.")

    submitted = False
    if not errors:
        request.session[SESSION_KEY] = values
        submitted = True

    context = {
        "details_values": values,
        "details_errors": errors,
        "details_submitted": submitted,
    }
    if getattr(request, "htmx", False):
        return render(request, "bookings/partials/_details_form.html", context)
    return _render_booking_page(request, context) or render(
        request, "bookings/partials/_details_form.html", context
    )


def _parse_date(value: str):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _parse_time(value: str):
    try:
        return datetime.strptime(value, "%H:%M").time() if value else None
    except ValueError:
        return None


def _checkout_error(request, message: str, *, status: int = 400):
    """
    A friendly, in-place error for the checkout step — per the
    error-handling-ux skill, this preserves everything the visitor has
    already entered (details stay staged in the session; reading/day/slot
    are re-posted, not lost) and explains what to do next rather than
    surfacing a stack trace. An htmx request gets the bare
    `_checkout_error.html` fragment back, swapped into `#checkout-error`
    in place; a plain no-JS POST gets the whole booking page re-rendered
    with the same message showing in that same region (see
    `_render_booking_page` above and partials/_booking_summary.html,
    which renders `checkout_error` inline) — FINDING 1, reviews/2026-09-22-
    final-build-review.md.
    """
    context = {"checkout_error": message}
    if getattr(request, "htmx", False):
        return render(request, "bookings/partials/_checkout_error.html", context, status=status)
    return _render_booking_page(request, context, status=status) or render(
        request, "bookings/partials/_checkout_error.html", context, status=status
    )


def _expire_stale_holds() -> None:
    """Lazily releases any PENDING booking whose hold has run out, so its
    slot becomes available again. Run inside the same transaction as a new
    hold attempt (see start_checkout) — there is no background task queue
    in this stack to do it on a timer instead; see the final report."""
    Booking.objects.filter(status=BookingStatus.PENDING, hold_expires_at__lt=dj_timezone.now()).update(
        status=BookingStatus.CANCELLED, updated_at=dj_timezone.now()
    )


def _redirect_or_htmx(request, url: str):
    if getattr(request, "htmx", False):
        response = HttpResponse(status=200)
        response["HX-Redirect"] = url
        return response
    return HttpResponseRedirect(url)


@require_POST
@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@ratelimit(key="ip", rate="20/h", method="POST", block=False)
def start_checkout(request):
    """
    Combines the reading/day/slot chosen in steps 1-2 (posted as hidden
    fields alongside the "Pay" control — see the context contract in the
    final report) with the details staged in the session by
    `save_details`, reserves the slot, and hands off to the payment
    provider.

    Double-submission safety: a second click (or a resubmitted form)
    while the first hold is still live reuses that same hold — see
    `SESSION_KEY_HOLD` below — rather than creating a second row, which
    would otherwise collide with the first under the same exclusion
    constraint that protects against two different people booking the
    same slot.

    Rate limit: 5/minute and 20/hour per IP (see module docstring) — the
    serious one. A genuine visitor retrying after a declined card or a
    slot taken out from under them stays well inside 5/minute; nobody
    legitimately needs 20 checkout attempts in an hour. This is what
    stops a script from holding every visible slot for HOLD_MINUTES at a
    time, indefinitely, without ever paying (reviews/2026-09-22-final-
    security-review.md finding 1) — from one IP. It does not, and cannot,
    stop the same abuse spread across many IPs; see that finding's
    adjudication and the final report for why that is a separate,
    unbuilt defence, not something rate limiting solves.
    """
    if getattr(request, "limited", False):
        return _checkout_error(request, CHECKOUT_RATE_LIMIT_MESSAGE, status=429)

    details = request.session.get(SESSION_KEY)
    if not details:
        return _checkout_error(
            request,
            "We don't have your details yet — please fill in your details below before continuing to payment.",
        )

    reading = Reading.objects.filter(pk=request.POST.get("reading", "").strip(), is_active=True).first()
    if not reading or not reading.duration_minutes:
        return _checkout_error(request, "Please choose a reading before continuing to payment.")
    if reading.price is None:
        return _checkout_error(
            request,
            "Pricing for this reading isn't set up yet, so we can't take payment online for it. "
            "Please get in touch directly and Leslie will help you book it.",
        )

    slot_value = request.POST.get("slot", "").strip()
    try:
        slot_start = datetime.fromisoformat(slot_value)
        if slot_start.tzinfo is None:
            raise ValueError("naive datetime")
        slot_start = slot_start.astimezone(dt_timezone.utc)
    except (ValueError, TypeError):
        return _checkout_error(request, "That time doesn't look right — please choose a time again.")

    tz = availability.resolve_timezone(request.POST.get("tz", "").strip())
    local_day = slot_start.astimezone(tz).date()

    # Defensive re-check against a stale page (the database constraint
    # below is the real guard; this just lets an honest, specific answer
    # be given instead of a generic constraint-violation error).
    if slot_start not in availability.get_slots_for_day(reading, local_day):
        return _checkout_error(
            request,
            "That time was just taken, or has passed. Please choose another time "
            "— we've kept your details.",
            status=409,
        )

    existing_ref = request.session.get(SESSION_KEY_HOLD)
    if existing_ref:
        existing = Booking.objects.filter(
            public_ref=existing_ref, status=BookingStatus.PENDING, reading=reading, start_at=slot_start
        ).first()
        if existing and existing.hold_expires_at and existing.hold_expires_at > dj_timezone.now() and existing.payment_reference:
            provider = get_provider()
            if provider.name == existing.payment_provider:
                # Re-use the hold already made by an earlier click rather
                # than creating a second, colliding one.
                try:
                    session = provider.create_checkout_session(
                        existing,
                        success_url=_return_url(request, existing, "success"),
                        cancel_url=_return_url(request, existing, "cancelled"),
                    )
                    return _redirect_or_htmx(request, session.redirect_url)
                except PaymentProviderError:
                    pass  # fall through and try a fresh hold below

    duration = timedelta(minutes=reading.duration_minutes)
    end_at = slot_start + duration
    amount_minor = int((Decimal(reading.price) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    try:
        with transaction.atomic():
            _expire_stale_holds()
            booking = Booking.objects.create(
                reading=reading,
                client_first_name=details["first_name"],
                client_last_name=details["last_name"],
                client_email=details["email"],
                birth_date=_parse_date(details.get("dob", "")),
                birth_time=_parse_time(details.get("tob", "")),
                birth_time_unknown=not bool(details.get("tob", "")),
                birth_place=details.get("pob", ""),
                client_notes=details.get("focus", ""),
                start_at=slot_start,
                end_at=end_at,
                duration_minutes=reading.duration_minutes,
                display_timezone=str(tz),
                status=BookingStatus.PENDING,
                hold_expires_at=dj_timezone.now() + timedelta(minutes=HOLD_MINUTES),
                payment_status=PaymentStatus.UNPAID,
                amount_minor=amount_minor,
                currency=CURRENCY,
            )
    except IntegrityError:
        logger.info("booking hold rejected by exclusion constraint slot_start=%s", slot_start.isoformat())
        return _checkout_error(
            request,
            "That time was just taken by someone else. Please choose another time "
            "— we've kept your details.",
            status=409,
        )

    provider = get_provider()
    try:
        session = provider.create_checkout_session(
            booking,
            success_url=_return_url(request, booking, "success"),
            cancel_url=_return_url(request, booking, "cancelled"),
        )
    except PaymentProviderError:
        logger.exception("payment provider failed to start checkout booking_ref=%s", booking.public_ref)
        # Cancel the hold immediately so the slot doesn't sit reserved for
        # nothing until it naturally expires, and so a retry by the same
        # visitor doesn't collide with this one.
        booking.status = BookingStatus.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        return _checkout_error(
            request,
            "We couldn't start payment just now — nothing has been charged. Please try again in a moment.",
        )

    booking.payment_provider = provider.name
    booking.payment_reference = session.provider_reference
    booking.save(update_fields=["payment_provider", "payment_reference", "updated_at"])

    request.session[SESSION_KEY_HOLD] = str(booking.public_ref)

    return _redirect_or_htmx(request, session.redirect_url)


def _return_url(request, booking: Booking, result: str) -> str:
    page = BookingPage.objects.live().first()
    base = page.get_full_url(request) if page else "/"
    return f"{base}?ref={booking.public_ref}&result={result}"


def booking_status(request, ref):
    """
    Small polling fragment (`GET forms/booking/status/<ref>/`) for the
    payment-return screen to re-check while a booking is still `pending`
    — the provider's success redirect happens in the browser and can
    arrive before `stripe_webhook` has actually processed the payment;
    this is how the UI finds out once it has, instead of trusting the
    redirect as the source of truth. Renders
    bookings/partials/_booking_status_inner.html — the poll's own swap
    unit, one level inside the persistent aria-live region in
    partials/_booking_status.html, which this view never re-renders (see
    that template's own comment — A11Y FINDING 4, reviews/2026-09-22-
    final-accessibility-audit.md — for why the two are now split).
    """
    booking = Booking.objects.filter(public_ref=ref).select_related("reading").first()
    return render(request, "bookings/partials/_booking_status_inner.html", {"booking": booking})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Untrusted, possibly-duplicated input (SCOPE correctness rule). Every
    event is signature-verified before anything in it is trusted
    (`provider.verify_and_parse_webhook`), and handling is idempotent:
    inserting the `PaymentEvent` row happens inside the same transaction
    as acting on the event, so a second delivery of the same
    (provider, event_id) hits the model's unique constraint and is a
    no-op rather than being reprocessed.
    """
    provider = get_provider()
    try:
        event = provider.verify_and_parse_webhook(request.body, request.headers)
    except PaymentProviderError:
        logger.warning("rejected webhook: signature verification failed")
        return HttpResponseBadRequest("invalid signature")

    try:
        with transaction.atomic():
            booking = (
                Booking.objects.select_for_update()
                .filter(payment_reference=event.provider_reference)
                .first()
            )
            PaymentEvent.objects.create(
                provider=provider.name,
                event_id=event.event_id,
                event_type=event.event_type,
                booking=booking,
            )
            if not booking:
                logger.info(
                    "webhook for unrecognised booking provider=%s type=%s", provider.name, event.event_type
                )
            else:
                _apply_webhook_event(provider, event, booking)
    except IntegrityError:
        # Same event delivered more than once — already processed.
        return HttpResponse(status=200)

    return HttpResponse(status=200)


def _apply_webhook_event(provider, event, booking) -> None:
    if event.event_type == provider.EVENT_PAYMENT_SUCCEEDED:
        booking.payment_status = PaymentStatus.PAID
        if booking.status == BookingStatus.PENDING:
            booking.status = BookingStatus.CONFIRMED
            booking.hold_expires_at = None
            booking.save(update_fields=["payment_status", "status", "hold_expires_at", "updated_at"])
            transaction.on_commit(lambda: send_booking_emails(booking.pk))
        else:
            # The hold had already expired/been cancelled by the time
            # payment landed — the slot may since have gone to someone
            # else. This is the "paid booking that was never confirmed"
            # case: represented honestly (payment_status=paid,
            # status unchanged) rather than forcing a confirmation the
            # calendar can no longer guarantee.
            note = "Payment received after this hold expired — needs manual follow-up."
            booking.internal_notes = f"{booking.internal_notes}\n{note}" if booking.internal_notes else note
            booking.save(update_fields=["payment_status", "internal_notes", "updated_at"])
            transaction.on_commit(lambda: send_payment_needs_attention_email(booking.pk))

    elif event.event_type == provider.EVENT_PAYMENT_FAILED:
        booking.payment_status = PaymentStatus.FAILED
        booking.save(update_fields=["payment_status", "updated_at"])

    elif event.event_type == provider.EVENT_CHECKOUT_EXPIRED:
        if booking.status == BookingStatus.PENDING:
            booking.status = BookingStatus.CANCELLED
            booking.save(update_fields=["status", "updated_at"])

    elif event.event_type == provider.EVENT_REFUNDED:
        # Deliberately does not touch booking.status — a confirmed
        # appointment whose payment was later refunded/disputed is a
        # separate fact from whether the appointment itself still goes
        # ahead; that's Leslie's call, made from the admin, not this
        # handler's.
        booking.payment_status = PaymentStatus.REFUNDED
        booking.save(update_fields=["payment_status", "updated_at"])

    # EVENT_IGNORED: a real event this app doesn't act on — no-op.

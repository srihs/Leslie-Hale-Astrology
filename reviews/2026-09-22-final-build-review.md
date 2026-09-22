# Review: final build (whole delivered site, pre-handover)

**Date:** 2026-09-22
**Reviewed:** whole working tree at commit `652e956` (all apps, templates, static,
config, migrations, tests); stack run live via `docker compose` on
`localhost:8005`; `pytest` run inside the `web` container
**Reviewer:** code-critic (agent)

## Findings

### 1. Every no-JS form submission renders a bare, unstyled fragment instead of a full page — contradicting the code's own no-JS claims

- **Severity:** major
- **Confidence:** verified
- **Where:** `apps/contact/views.py:submit_contact` and `newsletter_signup`;
  `apps/bookings/views.py:save_details` and `_checkout_error`; the four
  templates whose own comments assert otherwise —
  `templates/includes/_newsletter_form.html:6-11`,
  `templates/contact/partials/_contact_form.html:6-8`,
  `templates/bookings/partials/_details_form.html:6-7`.
- **What looks correct but is not:** every one of these views is written to
  handle both an htmx request and a plain-JS-off POST identically —
  `return render(request, "<partial>.html", {...})` with no branch on
  `request.htmx` (the `django_htmx` middleware is installed and sets that
  attribute, but nothing reads it in these four views). For an htmx request
  that's correct: htmx swaps the returned fragment into the DOM. But for a
  real no-JS browser, a plain `<form method="post">` submission is a full
  page navigation, and the browser renders whatever comes back as the
  entire document. I reproduced this live against the running container
  (`docker compose exec web python`, a cookie-jar `urllib` POST carrying a
  real CSRF token, no `HX-Request` header — i.e. exactly what a no-JS
  browser sends): `POST /forms/contact/newsletter/` returns a 200 whose
  entire body is the bare `<form id="newsletter-form">…</form>` fragment —
  no `<!DOCTYPE>`, no `<head>`, no stylesheet, no `<nav>`, nothing else on
  the page. `POST /forms/booking/details/` behaves identically. The
  templates' own comments claim the opposite:
  `_newsletter_form.html:6-7` says "a real `<form method=\"post\">`, full
  page reload on submit"; `_details_form.html:6-7` says "the server
  re-renders the full booking page with this partial showing the saved
  state" — neither is what the code does.
- **Why it matters:** this is exactly the property CLAUDE.md and every
  agent's own comments state as a requirement — "every htmx interaction is
  supposed to work without JavaScript" — and it is the specific thing this
  review was asked to verify rather than accept. It affects three of the
  five §5 functions (contact form, newsletter signup, the booking flow's
  details step, and the checkout failure path): the data is saved
  correctly (the defect is not data loss), but a visitor with JavaScript
  disabled who submits any of these forms lands on an orphaned, unstyled
  fragment with no way back into the site except the browser's back
  button — for a mainstream audience (§2: "women aged 27–70", not
  necessarily tech-savvy) on a site that advertises booking as its primary
  conversion path, that is a real dead end, not a degraded experience.
  It is also untested in a way that looks tested: `apps/contact/tests/
  test_views.py`'s own module docstring states "tested with and without
  the `HX-Request` header throughout: the same view/template must serve a
  working no-JS POST-and-reload flow" and the tests do parametrize on
  `HX-Request`, but every assertion only checks `status_code == 200` and
  that certain text appears in the body — none checks that the non-htmx
  response is a full document (e.g. contains `<!DOCTYPE html>` or `<nav>`)
  rather than a bare fragment, so the suite's own stated intent isn't
  actually enforced by its assertions, and 110/110 passing conceals this.
- **Suggested action:** branch each of these four views on `request.htmx`
  (already available via `django_htmx`): render the bare partial for an
  htmx request as now, but for a plain request render the owning page
  template (or redirect back to it with the result flashed) so a no-JS
  visitor always ends up back inside the site. Add an assertion to the
  existing parametrized tests that the non-htmx branch's response contains
  the site chrome.

**Adjudication:** _pending_

### 2. The booking page hardcodes two different, invented cancellation/refund policies directly in the template, bypassing the CMS field built for exactly this purpose

- **Severity:** major
- **Confidence:** verified
- **Where:** `templates/bookings/booking.html:76` (FAQ: *"Can I get a
  refund? Full refund if you cancel more than 24 hours before."*);
  `templates/bookings/partials/_booking_summary.html:65` (*"🔒 Secure
  payment · Free reschedule up to 24h before"*); contrast with
  `apps/bookings/models.py:469-473` (`BookingPage.cancellation_policy`, a
  CMS `TextField` with help text *"Your cancellation/rescheduling policy,
  shown near the booking form and included in confirmation emails"*) and
  `apps/bookings/emails.py:76-83`, which correctly reads that field live
  and — critically — omits the paragraph entirely if Leslie hasn't filled
  it in, rather than inventing one.
- **What looks correct but is not:** `BookingPage` has a real,
  Wagtail-editable `cancellation_policy` field, and the confirmation email
  it's actually wired to (`emails.py`) honours the discipline the rest of
  this codebase applies to every other §8-open fact: show nothing rather
  than a guess. But nowhere in `templates/bookings/booking.html` or its
  partials is `page.cancellation_policy` (or `page.intro`) ever rendered —
  confirmed with `grep -n "cancellation_policy\|intro\b" templates/
  bookings/*.html templates/bookings/partials/*.html`, no matches. Instead
  the on-page FAQ and the payment-summary microcopy each state a specific,
  invented policy — and the two disagree with each other: one promises a
  *refund* if cancelled >24h out, the other promises a *free reschedule*
  <24h out. Both are plausible-sounding, specific business rules nobody
  at Leslie's business confirmed, hardcoded into every render of the page
  every visitor sees before paying.
- **Why it matters:** this is the same category of defect PROJECT-SCOPE.md
  §8 and CLAUDE.md's own oversight log already caught and fixed once
  (`6947cc5`, "Remove invented values for unconfirmed client facts") — an
  agent inventing a specific, real-looking fact for an item the client
  never confirmed. It's worse here in one respect: a booking cancellation/
  refund policy is a commitment Leslie may be legally or contractually
  bound by once a client relies on it, not just cosmetic copy. It's also
  an editor-experience defect independent of the scope question: Leslie
  has a field literally labelled for this in Wagtail admin
  ("Policies & confirmation → Cancellation policy"), and filling it in
  would appear to do something (it does — in the confirmation email) while
  the two policy statements a client actually sees *before paying* stay
  fixed regardless of what she writes there, and won't even match it once
  she does.
- **Suggested action:** replace both hardcoded strings with
  `{{ page.cancellation_policy|default:"[cancellation policy TBC]" }}` (or
  omit the block when blank, matching `emails.py`'s own pattern), and
  render `page.intro` somewhere on the page — currently defined on the
  model, documented in the template's own header comment as a context
  value, and never output.

**Adjudication:** _pending_

### 3. Homepage hero hardcodes "60 min" as a blanket duration claim, contradicting the per-reading duration model

- **Severity:** minor
- **Confidence:** suspected
- **Where:** `templates/home/index.html:89` (`<strong>60 min</strong>
  Enough time to actually talk`); contrast with
  `apps/readings/models.py:66-71` (`Reading.duration_minutes` is
  `null=True, blank=True`, help text: *"Leave blank if it varies"*).
- **What looks correct but is not:** the model was deliberately built so
  each reading's duration is independent and optionally unset, because
  durations vary or may not be settled yet. The hero band asserts a single
  fixed "60 min" figure unconditionally, regardless of what any actual
  `Reading` says. It happens to match the 60-minute figure used in several
  test fixtures/factories, which may be why it reads as safe, but nothing
  ties it to real reading data.
- **Why it matters:** lower stakes than findings 1-2 (this is marketing
  copy, not a policy commitment, and §8 doesn't name reading duration as a
  confirmed/unconfirmed fact the way it does price), but it will silently
  go stale the moment Leslie sets any reading to a different duration or
  leaves it blank, and nothing in the codebase would catch that drift.
  Flagged as suspected rather than verified because I can't confirm
  whether this was a deliberate, accepted piece of hero copy (distinct
  from the per-reading duration shown lower on the same page) rather than
  an oversight.
- **Suggested action:** either confirm this is acceptable general copy
  (not a specific claim), or make it CMS-editable/derived from the
  featured readings' actual durations.

**Adjudication:** _pending_

### 4. The one pre-existing box-shadow focus ring is still unreconciled with §7 at final handover

- **Severity:** minor
- **Confidence:** verified
- **Where:** `static/css/_components.css:35-40`
  (`.field input:focus,...{...box-shadow:0 0 0 3px rgba(217,192,138,.18)}`)
- **What looks correct but is not:** this was already surfaced in the
  scaffold-stage review (`reviews/2026-09-22-project-structure-scaffold.md`,
  "Reviewed and found sound") as "flagged in-file as a known,
  not-yet-reconciled tension rather than an unflagged violation." The
  in-file comment (`_components.css:35-38`) still reads "FLAG (not
  fixed)" verbatim at final handover — the tension between §7's "no
  box-shadow" rule and a visible focus indicator was never actually
  resolved, only re-flagged, across the whole build that followed.
- **Why it matters:** low severity — it's a single, deliberate,
  self-documented exception for an accessibility-motivated affordance
  (focus visibility), not a drifting pattern, and box-shadow-as-focus-ring
  is a defensible trade-off against §7. Noted because it is the one
  documented §7 exception that shipped to handover still open rather than
  either fixed (e.g. an outline-based alternative) or formally accepted.
- **Suggested action:** either replace with a non-shadow focus treatment
  (e.g. `outline` with `outline-offset`, which doesn't read as a
  drop-shadow) or explicitly accept the exception and remove the "not
  fixed" language.

**Adjudication:** _pending_

## Reviewed and found sound

- **Double-booking prevention.** `Booking.Meta.constraints` carries a real
  Postgres `ExclusionConstraint` over `tstzrange(start_at, end_at)`, gated
  by `btree_gist` (`BtreeGistExtension()` in
  `apps/bookings/migrations/0001_initial.py`). Verified this is what
  actually stops a race, not just the Python pre-check, via
  `test_stale_availability_read_is_still_caught_by_the_database_constraint`
  (`apps/bookings/tests/test_checkout.py`), which stubs the availability
  pre-check to lie and confirms the database still rejects the second
  booking with a 409, not a 500.
- **Webhook idempotency.** `PaymentEvent`'s unique `(provider, event_id)`
  constraint, inserted inside the same transaction as acting on the event,
  is exercised end-to-end by
  `test_replayed_webhook_delivery_is_a_no_op` — same event delivered
  twice, confirms status/payment state and email send-count are unchanged
  on the second delivery.
- **Double-submission at checkout.** `test_double_submission_reuses_the_
  existing_hold_not_a_second_booking` and the provider-mismatch variant
  both pass and match `start_checkout`'s actual session-key-based reuse
  logic.
- **Payment/booking state independence.** `status` and `payment_status`
  really are decoupled fields with no CHECK constraint tying them, and
  `_apply_webhook_event` (`apps/bookings/views.py`) handles the
  paid-after-hold-expired and refunded-after-confirmed cases explicitly,
  each covered by its own test.
- **Blogger importer idempotency.** Matches on `blogger_post_id`
  (never title/slug), compares `blogger_content_hash` to skip unchanged
  posts, updates in place rather than duplicating on a second run —
  confirmed in `apps/blog/blogger_import/importer.py:190-306`.
- **XML hardening.** `apps/blog/blogger_import/feed.py` imports
  `defusedxml.ElementTree`, matching the `a162d59` fix; not re-verified
  against the billion-laughs/XXE fixtures beyond confirming the import is
  in place and the test files referencing them exist and pass.
- **Money handling.** `amount_minor` is computed once via `Decimal(...) *
  100` with explicit `ROUND_HALF_UP` quantization and stored as
  `PositiveIntegerField` — never a float — from `start_checkout` onward.
- **§8 discipline, everywhere else checked.** `Reading.price`/`price_note`,
  `ContactSettings.contact_email`/`years_experience_label`,
  `Testimonial` (empty-state, no invented quotes), blog empty states, and
  the Blogger URL (never hardcoded, `source` always supplied by the
  caller) all correctly render an honest placeholder or nothing rather
  than a guess — findings 2 and 3 above are the exceptions to an
  otherwise consistently-applied rule, not the norm.
- **Previously-flagged §8 items resolved.** The named "Birth Chart
  reading" and the invented contact email/years figure from the scaffold
  review are gone; `settings.core.ContactSettings` (not the old,
  non-resolving `SiteSettings` name) is used consistently.
- **FAQ is now a real CMS block** (`apps/core/blocks.py:FAQListBlock`) on
  `ReadingsIndexPage` and `ReadingDetailPage`, correctly rendered from
  `page.faq` — the earlier concern about a hardcoded FAQ applies only to
  the booking page (finding 2), not readings.
- **No-JS blog filtering/pagination.** Every filter and pager control in
  `templates/blog/partials/_post_list.html` is a real `<a href="…">` to
  the same page with query params, with `hx-get`/`hx-select` layered on
  top as enhancement only — confirmed this is genuinely different from
  findings 1's pattern (these are real links, not POST-and-fragment).
- **No-JS mobile nav.** The checkbox/label disclosure
  (`dc2c98c`) is present in the live-rendered homepage HTML
  (`#menu-toggle` checkbox + label, `.menu-toggle-btn`/`.menu-toggle-label`
  pair) — confirmed by curling the running container, not just reading
  the CSS.
- **Scope exclusions honoured.** No forum, client list, gallery, video,
  site search, or member-account code anywhere in `apps/` or `templates/`.
- **Design fidelity, palette/borders/corners.** No stray `box-shadow` or
  `border-radius` beyond the one documented pill exception (`.hero-tag`)
  and the focus ring in finding 4.
- **All six §4 pages exist with real templates and render.** Home, About,
  Services (Readings), Booking, Blog (index + post), Contact — curled
  `/` and `/book-a-reading/` live, both 200; the other four were
  confirmed by template/model inspection plus the passing test suite.
- **Stack and tests.** `docker compose` brings up `db` (healthy) and `web`
  (healthy) from the committed compose files with no manual patching;
  `pytest` inside the `web` container: **110 passed**, 0 failed.


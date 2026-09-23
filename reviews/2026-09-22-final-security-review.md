# Review: final security review before handover

**Date:** 2026-09-22
**Reviewed:** working tree at commit `652e956` plus full git history (`git log --all`,
28 commits back to `6b40a5f`) - settings (`config/settings/`), booking/payment flow
(`apps/bookings/`), Blogger importer (`apps/blog/blogger_import/`), contact/newsletter
(`apps/contact/`), core settings/views (`apps/core/`), templates (`templates/`), Docker/
compose (`docker/`, `docker-compose.yml`), dependency pins (`pyproject.toml`)
**Reviewer:** security-reviewer (agent)
**Tools used:** `manage.py check --deploy` (against `config.settings.prod`, dummy env
values), `pip-audit` (against the actual pinned dependency set, installed into a scratch
venv since none existed in the environment), `git log -p --all` grepped for secret
patterns, manual read of every file listed above.

---

## Re-assessed from the earlier scaffold review

### 1. No rate limiting on any public POST endpoint - now live and exploitable

- **Severity:** major (upgraded from the earlier scaffold-stage note, now that the
  endpoints exist and are reachable)
- **Confidence:** confirmed
- **Where:** `apps/contact/views.py` (`submit_contact`, `newsletter_signup`),
  `apps/bookings/views.py` (`save_details`, `start_checkout`) - none of these views, and
  nothing in `config/settings/base.py` or `MIDDLEWARE`, applies any request throttling.
  No rate-limiting package (`django-ratelimit`, `django-axes`, etc.) appears in
  `pyproject.toml`. No CAPTCHA or honeypot field on any form.
- **What is wrong:** every public POST endpoint accepts unlimited requests from a single
  client. Concretely:
  - `bookings:checkout` (`start_checkout`) creates a real `Booking` row with
    `status=PENDING` and a 15-minute exclusive hold (`HOLD_MINUTES`) on a calendar slot
    enforced by a Postgres exclusion constraint, for the cost of one scripted POST with a
    plausible email and a slot value read straight off the public availability page - no
    payment has to complete. A trivial script that walks every open slot for the next N
    days and POSTs to `checkout/` can hold the entire visible calendar indefinitely by
    re-submitting every 15 minutes, taking real bookings off the table with no payment
    ever made. For a solo practitioner whose primary conversion goal is bookings, this is
    a real, low-effort denial-of-service against the site's main purpose, not a
    theoretical one.
  - `contact:submit` and `contact:newsletter_signup` can be flooded to fill
    `ContactSubmission`/`NewsletterSignup` with junk rows, and `newsletter_signup`'s
    `get_or_create` can be used to subscribe arbitrary third-party email addresses to the
    newsletter without their consent (no confirmation step) at unlimited rate.
  - `bookings:save_details` writes into the session on every call; cheap per-request but
    still unthrottled.
- **Why it matters:** none of this requires authentication, a captcha bypass, or any
  cleverness - a single unauthenticated script exhausts the booking calendar or fills the
  enquiry/newsletter tables. This is exactly the "credential and secret exposure, payment
  tampering, injection, dependency" class of realistic threat the brief asks to calibrate
  against, and booking-slot exhaustion sits squarely in it now that the flow is live and
  unauthenticated holds are real database rows.
- **Suggested action:** add per-IP (and ideally per-session) rate limiting on all four
  endpoints - `django-ratelimit` is the lightest fit for this stack. For `start_checkout`
  specifically, also consider capping the number of concurrent `PENDING` holds per
  session/IP, independent of the general rate limit, since the exclusion constraint alone
  does not stop one actor from holding many different slots.

**Adjudication:** accepted — fix now. A scripted attacker holding every slot for 15 minutes at a time, indefinitely, without paying, takes out the site's only revenue mechanism. Owners: `docker-infra` for the dependency, then `booking-payments` and the contact endpoints.

### 2. No Subresource Integrity on third-party CDN scripts

- **Severity:** minor
- **Confidence:** confirmed
- **Where:** `templates/base.html:118-121` - `gsap.min.js` and `ScrollTrigger.min.js`
  from `cdnjs.cloudflare.com`, `lenis.min.js` from `cdn.jsdelivr.net`, `htmx.org@2.0.4`
  from `unpkg.com`. None carries `integrity=`/`crossorigin=`.
- **What is wrong:** unchanged from the scaffold review - still no SRI on any of the four
  CDN-hosted scripts.
- **Why it matters, re-assessed now payment is live:** Stripe itself is not fetched
  client-side - checkout is a server-created Checkout Session with a redirect
  (`stripe_provider.py`'s `create_checkout_session`), so a compromised CDN script cannot
  intercept card data directly, which meaningfully lowers the severity from what it would
  be with Stripe.js/Elements embedded. It still stays at "minor" rather than "clean"
  because a compromised `htmx.org` or `gsap` payload runs on every page including the
  booking details step, and could exfiltrate the birth-date/place/email fields the
  visitor types before they ever reach Stripe, or rewrite the "Pay" form's action/target.
  This is a supply-chain risk on three reputable, low-churn CDNs - realistically low
  likelihood - not a proximate payment-tampering vector.
- **Suggested action:** add `integrity`/`crossorigin` attributes (all four libraries
  publish stable hashes for pinned versions); low effort for the residual defence-in-depth
  it buys given the booking form now sits behind these scripts.

**Adjudication:** accepted — fix now. Four fixed-version URLs is the cheapest this will ever be. Owner: `htmx-frontend`.

### 3. Wagtail image/document upload limits still not configured

- **Severity:** minor
- **Confidence:** confirmed
- **Where:** `config/settings/base.py` - no `WAGTAILIMAGES_MAX_UPLOAD_SIZE`,
  `WAGTAILIMAGES_MAX_IMAGE_PIXELS`, or `WAGTAILDOCS_MAX_UPLOAD_SIZE` set anywhere;
  Wagtail ships permissive defaults (documents in particular accept almost any file type
  at any size within server limits).
- **What is wrong:** unchanged from the scaffold review.
- **Why it matters:** uploads are staff-only (Wagtail admin, not a public form), so this
  is not attacker-reachable without an admin account already - it bounds the blast radius
  to "a compromised or careless staff account can push an oversized or unexpected file
  type," not "a member of the public can." Still worth closing before go-live since it is
  a two-line settings change.
- **Suggested action:** set both size limits explicitly; the defaults are unbounded
  server-side, which is more a resource-exhaustion/storage-cost issue than a direct
  security hole given the admin-only reach.

**Adjudication:** accepted — fix now. Admin-only reach bounds the severity, but relying on an unreviewed framework default is not a decision. Owner: `docker-infra`.

### 4. No brute-force protection on the Wagtail/Django admin login

- **Severity:** minor
- **Confidence:** confirmed
- **Where:** `config/urls.py:25-26` (`django-admin/`, `admin/`); no `django-axes`,
  `django-defender`, or equivalent in `pyproject.toml`; `AUTH_PASSWORD_VALIDATORS` in
  `config/settings/base.py` is Django's stock four validators (no custom lockout).
- **What is wrong:** unchanged from the scaffold review - Django's default auth has no
  failed-attempt lockout or delay.
- **Why it matters:** admin paths are at their default, guessable locations (`/admin/`,
  `/django-admin/`), and there is likely exactly one or two real accounts (Leslie, SAS
  Creative). Realistic risk is a slow credential-stuffing/password-guessing attempt
  against a small number of accounts, not a targeted attack - genuinely minor for a site
  this size, but cheap to close.
- **Suggested action:** `django-axes` (or Wagtail's own rate-limited login if configured)
  with a sane lockout threshold; alternatively, restrict `/admin/` and `/django-admin/` at
  the edge/proxy to known IPs if Leslie and the agency work from stable locations.

**Adjudication:** accepted — fix now. Owner: `docker-infra`.

---

## New findings

### 5. Core dependencies are pinned well behind versions with known, already-patched CVEs

- **Severity:** moderate
- **Confidence:** confirmed (via `pip-audit` run against the actual pinned versions from
  `pyproject.toml`, installed into a clean venv - `Django==5.1.4`, `wagtail==6.3.1`,
  `Pillow==11.0.0`, plus `pillow-heif` pulled in transitively by Wagtail's Willow image
  backend)
- **Where:** `pyproject.toml:10-27`
- **What is wrong:** `pip-audit` reports 94 known advisories across `django` (31),
  `wagtail` (29), `pillow` (33) and `pillow-heif` (1) at the pinned versions, every one of
  them already fixed in a later point release on the same branch the project is already
  committed to (e.g. Django fixes land through `5.1.15`; the project pins `5.1.4`.
  Wagtail fixes land through `6.3.8`; the project pins `6.3.1`). This is not a request to
  jump major versions - it is a same-branch patch lag. `stripe`, `psycopg`, `gunicorn`,
  `whitenoise`, `defusedxml`, `django-htmx`, `django-taggit`, `django-modelcluster` and
  `dj-database-url` came back clean.
- **Why it matters:** a small marketing/booking site is not a high-value target for a
  novel 0-day, but "already-fixed, already-known" issues in the exact framework and CMS
  serving every public form and the Wagtail admin are the realistic, low-effort end of
  the dependency-CVE threat this brief asks to check for. I have not individually
  triaged all 94 advisories for exploitability against this specific configuration (that
  would need per-CVE reading beyond this pass), so I can't say how many are actually
  reachable here - flagging the patch gap itself as confirmed, and the practical impact
  as something that needs a version bump plus a targeted re-check, not a full CVE-by-CVE
  audit in this pass.
- **Suggested action:** bump `Django` to the latest `5.1.x`, `wagtail` to the latest
  `6.3.x`, and `Pillow` to latest `11.x` (or, if a Wagtail major-version bump is
  otherwise on the roadmap, do it as part of that) before go-live, then re-run
  `pip-audit`. This is routine maintenance, not a redesign.

**Adjudication:** accepted — fix now. 94 advisories, all fixed in later point releases on the branch already pinned, is not a defensible thing to hand over. I flagged the upgrade as carrying its own risk: that risk is managed by the 110-test suite, which must pass after the bump, not by leaving the CVEs in place. Owner: `docker-infra`.

### 6. No data-retention policy for collected personal data

- **Severity:** minor / informational
- **Confidence:** confirmed
- **Where:** `apps/contact/models.py` (`ContactSubmission`, `NewsletterSignup`),
  `apps/bookings/models.py` (`Booking`, including birth date/time/place and
  `client_notes`) - none of these models, and nothing in settings or a management
  command, ever expires or purges a row. Retention is indefinite by default.
- **Why it matters:** not a vulnerability by itself, but the brief specifically asks
  "how long it is kept," and there is currently no answer beyond "forever." Booking rows
  carry the most sensitive field in the system (`client_notes`, which the brief
  specifically flags as potentially containing sensitive personal circumstances) with no
  retention or deletion path once a booking is old and completed.
- **Suggested action:** not a code fix so much as a decision for Leslie/SAS Creative to
  make and record - e.g. "keep booking records for N years for tax/business purposes,
  purge contact submissions after N months." Worth deciding before go-live given NZ
  Privacy Act principles around keeping personal information no longer than necessary,
  but this is a policy gap, not a bug.

**Adjudication:** deferred — pending the client. A retention period for booking records, birth data and contact submissions is a business and legal decision Leslie has to make, not one I can pick for her. Added to the §8 open items rather than invented. The finding is right and stays open.

---

## Reviewed and found sound

- **Secrets, full git history.** No secret was ever committed at any point in the 28
  commits of history. `git log --all -p` for `.env` (never tracked, at any path, at any
  point in history, confirmed with `git rev-list --all` plus `git ls-tree`) and a grep
  across every commit full diff for Stripe live/test key patterns (`sk_live_`,
  `sk_test_`, `whsec_`), AWS key patterns and PEM private-key headers found no matches.
  `.env.example`'s only non-placeholder value in history is `POSTGRES_PASSWORD=changeme`,
  an explicit dev placeholder, unchanged since it was added. `config/settings/base.py`'s
  `env()` helper raises loudly rather than falling back to a plausible-looking default,
  and every secret (`SECRET_KEY`, `DATABASE_URL`, SMTP creds, all three `STRIPE_*` vars)
  is environment-only with no hardcoded fallback. The alleged .env.example-renamed-to-
  .env event does not appear anywhere in history.
- **Django deploy settings.** `manage.py check --deploy` against `config.settings.prod`
  (real required env vars supplied, a deliberately weak dummy `SECRET_KEY`) returns
  exactly one warning, about the dummy key supplied for the test, not a real gap.
  `prod.py` hard-codes `DEBUG = False`, sets `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` to
  the real domain with an env override, and sets `SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` (1 year,
  include-subdomains, preload), `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`
  and `X_FRAME_OPTIONS = DENY` all correctly. `dev.py` never leaks into what prod uses.
- **Payments.** Amounts are computed server-side end to end: `start_checkout`
  (`apps/bookings/views.py:245`) derives `amount_minor` from `Reading.price` (a CMS-owned
  Decimal), never from any request field; the request only ever supplies which
  reading/slot was chosen, both re-validated server-side (`Reading.objects.filter(...,
  is_active=True)`, slot re-checked against `availability.get_slots_for_day`).
  `stripe_provider.py` never re-derives money from anything client-supplied. Webhook
  signature verification is real (`stripe.Webhook.construct_event` with
  `STRIPE_WEBHOOK_SECRET`; a wrong or missing signature raises `PaymentProviderError` and
  returns HTTP 400, never trusted). Idempotency is enforced by a database
  `UniqueConstraint` on the pair `(provider, event_id)` in `PaymentEvent`, exercised
  inside the same transaction as acting on the event, and covered by
  `apps/bookings/tests/test_webhooks.py`'s replay and invalid-signature tests. No card
  data, token, or full payment payload is ever logged; `views.py` and `emails.py` log
  only `booking.public_ref` and, on failure, an exception's type name.
- **Booking authorisation.** `Booking.public_ref` is a `UUIDField(default=uuid.uuid4,
  unique=True, ...)` and is the only identifier ever exposed to the browser, the payment
  provider, or a confirmation email (`apps/bookings/models.py:233`); every lookup in
  `views.py` (`booking_status`, the webhook handler, checkout's hold-reuse path) filters
  on `public_ref`/`payment_reference`, never on the numeric primary key. No endpoint
  accepts a numeric booking ID from the client. Draft or unpublished Wagtail pages are
  not separately reachable: every content queryset that surfaces pages
  (`BookingPage.objects.live()`, `BlogPost.objects.live()`, the RSS feed, the homepage
  latest-posts query) explicitly filters on `.live()`, and page serving goes through
  Wagtail's own catch-all with no override of serve/route anywhere in `apps/`.
- **The booking status poll endpoint's disclosure.** Confirmed what it discloses: reading
  name, appointment time and timezone, and, on the confirmed branch, the client's own
  email address, gated only by knowledge of the UUID `public_ref`
  (`templates/bookings/partials/_booking_status.html`). It does not disclose
  `client_notes`, birth date, time or place, payment amount or reference, or
  `internal_notes` - those never appear in this template. Given a UUID4's practical
  unguessability, and that the ref is only ever handed to the browser that made the
  booking or the client's own confirmation email, this is a proportionate design for a
  payment-return status poll, not a data leak - the same pattern most hosted-checkout
  integrations use for their own return pages.
- **XML parsing (Blogger importer).** `apps/blog/blogger_import/feed.py` routes every
  parse, the Atom path (`_parse_atom`), the RSS path (`_parse_rss`), and the pagination
  next-link probe (`_find_next_link`), through
  `defusedxml.ElementTree.fromstring(..., forbid_dtd=True)`, not the stdlib parser
  (`xml.etree.ElementTree` is imported only for its `ParseError` type, never for
  parsing). Confirmed no other module in the codebase parses untrusted XML at all, a
  grep for ElementTree/lxml/feedparser/xmltodict across `apps/` turns up nothing outside
  this file and its own test suite (`apps/blog/tests/blogger_import/test_feed.py`, which
  specifically exercises a billion-laughs payload and an XXE-with-external-entity
  payload and asserts both are refused).
- **XSS and the Blogger HTML import.** `apps/blog/blogger_import/sanitize.py` uses an
  allowlist, not denylist, approach built directly on Wagtail's own `Whitelister`
  primitive, the same one Wagtail's own rich text editor uses, configured to the exact
  tag set `BodyTextBlock` enables. Dangerous elements (script, style, iframe, object,
  embed, forms, svg, and more) are decomposed with their content before anything else
  runs; every remaining attribute except the anchor href is stripped; href values go
  through Wagtail's own `check_url` (rejects javascript: and similar). No `|safe` filter
  and no `mark_safe`/`format_html` call exists anywhere in `templates/` or `apps/`
  (confirmed by grep across both) - the only way HTML reaches the page unescaped is
  through this sanitizer's output stored in a Wagtail rich text block, which Wagtail's
  own renderer already treats as pre-sanitised by convention.
- **SQL injection.** No raw() query, cursor.execute(), or extra() call anywhere in
  `apps/` (confirmed by grep); every query goes through the ORM.
- **CSRF.** `CsrfViewMiddleware` is active in `MIDDLEWARE`; every public form template
  that POSTs (the details form, the contact form, the newsletter form, the checkout
  form) includes a csrf token. The one csrf-exempt view, `stripe_webhook`, is exempt for
  the correct reason: it has no browser session or cookie to carry a CSRF token, and its
  signature check is the real authentication, and it is also POST-only.
- **File uploads and path handling.** No app defines a custom FileField, ImageField, or
  upload_to anywhere (confirmed by grep); all media goes through Wagtail's built-in
  Image/Document models, which manage their own storage paths, so nothing user-controlled
  ever becomes a filesystem path. The Blogger importer's own image downloader
  (`importer.py:_download_image`) is a stronger case still: a URL scheme allowlist, a
  byte-size cap, a Content-Type check, and a filename builder that uses
  `os.path.basename` plus unquote, stripping any directory component before the name is
  ever handed to Wagtail, and this whole path only runs from an operator-invoked
  management command against a Blogger export, never from a public endpoint.
- **GA4 and personal data to Google.** All three custom conversion events
  (booking_completed, contact_form_submitted, newsletter_signup) fire with zero
  parameters, confirmed by reading every gtag event call site; none passes a second
  argument. The real gtag.js script and its config call are gated behind an explicit
  localStorage consent flag that nothing in this codebase sets automatically
  (`templates/includes/_analytics.html`); analytics loads for no one until a
  not-yet-built consent banner grants it. The measurement ID itself comes from a CMS
  setting, never hardcoded. A cookie-consent banner not existing yet is a product or
  legal gap, not a security one, and is explicitly out of this app's scope per the same
  template's own comment, noted for completeness rather than raised as a finding.
- **robots.txt and the indexing default.** `apps/core/views.py:robots_txt` defaults to
  disallow-all unless `SEARCH_ENGINE_INDEXING_ALLOWED` is explicitly true; that setting
  defaults to false in `config/settings/base.py` with no override in `prod.py`, and
  `.env.example` ships it commented with an explicit warning not to flip it except on
  the real production host. Confirmed this is genuinely what ships in every environment
  unless someone deliberately sets the env var on the real production deploy.
- **Personal data in logs and error reports.** Birth data and client notes never appear
  in a logger call anywhere in `apps/bookings/` (confirmed by reading every log line in
  `views.py` and `emails.py`; each carries only the booking's public reference and, on
  failure, an exception's type name). There is no Sentry or error-tracking integration
  and no admin-email handler configured anywhere in `config/`, so there is no mechanism
  in this codebase that would capture a request body, and therefore birth data, into an
  error report in the first place.
- **Availability and double-booking correctness (adjacent to payment tampering).** The
  Booking model carries a Postgres exclusion constraint over the appointment time range
  for any active-status booking, enforced at the database level regardless of what the
  Python availability check said a moment earlier, the right layer for this guarantee,
  not a defense-in-depth nice-to-have.

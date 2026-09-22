# Review: final accessibility audit (WCAG 2.2 AA, PROJECT-SCOPE.md §2 audience)

**Date:** 2026-09-22
**Reviewed:** whole working tree at commit `652e956` (templates, static/css, static/js);
stack run live via `docker compose` on `localhost:8005`, htmx endpoints exercised with real
`curl` POSTs (cookies + CSRF token from live responses)
**Reviewer:** accessibility-auditor (agent) - read-only; no source changed
**Audience:** WCAG 2.2 AA, for women 27-70 (PROJECT-SCOPE.md §2) - presbyopia, reduced contrast
sensitivity and reduced fine-motor precision are common and unremarkable in this range

## What I could and could not test

Confirmed with a real browser DOM: nothing - I do not have one in this environment. "Confirmed"
below means one of: (a) a live HTTP response from the running container, read byte-for-byte, or
(b) source (template/CSS/JS) read directly, combined with standard, spec-defined browser/DOM
behaviour (e.g. focus moving to `<body>` when the currently-focused node is removed from the
document - this is not a guess, it is what every evergreen browser does). "Suspected" below
means the code supports the concern but the actual rendered/announced behaviour needs a real
browser and/or screen reader (NVDA/JAWS/VoiceOver) to settle. I did NOT test: actual screen
reader announcements, 200%-zoom or 320px-width visual reflow, real touch-device tap accuracy, or
colour-blindness simulation. Findings in those areas are marked suspected and say so explicitly.

The locked-palette contrast pairs (`--muted`/`--ink`/`--gold`/`--danger` on `--bg`/`--bg-2`/
`--bg-3`) were not re-measured, per instruction - accepted as correct from the 22 Sept 2026
measurement.

## Findings

### 1. Every step of the booking flow throws away keyboard focus on its own htmx swap

- **Severity:** critical
- **Confidence:** confirmed (code + standard DOM focus-removal behaviour, not yet observed in a
  live browser)
- **Where:** `templates/bookings/partials/_booking_panel_form.html` - every control (`reading`
  radio, month prev/next, calendar day, time slot) carries `hx-target="#booking-panel"
  hx-swap="outerHTML"`; `templates/blog/partials/_post_list.html` - every filter/pager `<a>`
  carries `hx-target="#post-list" hx-swap="outerHTML"`; `static/js/main.js:41-47`, the only
  `htmx:afterSwap` focus-management handler in the codebase, checks `target.matches('form.sent')`
  only.
- **What looks correct but is not:** every one of these controls lives inside the very element
  it targets (`#booking-panel` contains the radio/day/slot buttons that trigger its own
  replacement; `#post-list` contains the filter/pager links that trigger its own replacement).
  With `hx-swap="outerHTML"`, htmx removes that whole container - including the control the
  visitor just activated with the keyboard - and inserts a new one built from the server
  response. When a browser removes the currently-focused element from the document, focus reverts
  to `<body>` (standard, specified behaviour, not implementation-specific). `main.js`'s only
  `afterSwap` focus handler fires exclusively for a successfully-submitted `form.sent`; it never
  runs for `#booking-panel` or `#post-list`, so nothing moves focus back into the new content
  after any of these swaps.
- **Why it matters:** this is the primary conversion path (PROJECT-SCOPE.md §3 goal 1). A
  keyboard-only visitor choosing a reading, then a month, then a day, then a time performs up to
  four separate interactions in Steps 1-2 alone - after each one, their keyboard focus silently
  disappears to the top of the document. To continue, they must tab all the way back down through
  the nav, hero, and every preceding panel control every single time. This is not a rough edge, it
  is a per-step tax on the one flow the whole site exists to complete, and it repeats on the blog
  filter/pager the same way (lower stakes, non-conversion path). `aria-live="polite"` is present
  on both containers, which may soften the screen-reader experience somewhat (see caveat below,
  finding 4, on whether an outerHTML-replaced live region reliably announces at all) but does
  nothing for a sighted keyboard user's lost place, and does not restore focus either way.
- **Suggested action:** add an `htmx:afterSwap` handler (or `hx-on::after-swap` inline) for
  `#booking-panel` and `#post-list` that moves focus to a sensible landing point in the new
  content - e.g. the just-selected control's equivalent in the new DOM, or the panel's own heading
  with `tabindex="-1"` - mirroring the pattern `main.js` already uses for `.ok` on form success.

**Adjudication:** _pending_

### 2. Validation errors are shown for fields that are not in error - the fix in `3c76760` is incomplete

- **Severity:** critical
- **Confidence:** confirmed live (reproduced against the running container)
- **Where:** `static/css/_components.css:43-44` (`.err{display:none} .form.invalid .err
  {display:block}`); `templates/bookings/partials/_details_form.html`;
  `templates/contact/partials/_contact_form.html`
- **What looks correct but is not:** the CSS rule that reveals error text keys off `.invalid` on
  the whole `<form>`, not on the individual field. Every `<span class="err">` in a form gets
  `display:block` the moment any field in that form is invalid, regardless of that particular
  field's own `aria-invalid` value. I reproduced this against the live app: POSTing to
  `/forms/booking/details/` with a valid first name, last name, email and place of birth but a
  blank date of birth returns a response where `dob`'s error is correctly `aria-invalid="true"`,
  but `first_name`, `last_name`, `email` and `pob` - each `aria-invalid="false"` - all render their
  own visible error text too ("Please enter your first name.", "Please enter your last name.",
  "Please enter a valid email.", "Please enter your place of birth."), none of which is true. The
  same reproduction against `/forms/contact/submit/` with only the email field invalid shows the
  identical pattern: the Name and Message fields' error spans render "Please enter your name." and
  "Please write a short message." alongside the one genuine email error.
- **Why it matters:** this is the exact defect `3c76760` ("Make form validation errors visible,
  not just coloured") was meant to fix, and it is still present - the fix made the error text
  visible, but visible for the wrong fields. Every visitor who makes one mistake in the booking
  details form or the contact form is now told, in visible red text under every field, that they
  also got their name, email and (for booking) place of birth wrong, when they did not. For the
  target audience this is confusing and anxiety-inducing rather than reassuring, and it invites
  people to re-enter data that was already correct. It is a direct WCAG 3.3.1 Error Identification
  failure (the item identified as in error is not, in fact, in error) on two of the site's three
  forms; the third (newsletter signup) has only one field so the bug is present but not
  observable there. The underlying association architecture is otherwise sound - every field has
  a real `<label for>`, a correctly-scoped `aria-describedby`, and a correctly per-field
  `aria-invalid` - only the CSS display rule ignores that per-field state.
- **Suggested action:** scope the reveal rule to the field, not the form, e.g.
  `.field [aria-invalid="true"] ~ .err{display:block}` (the existing markup order - input, then
  `.err` - already supports a sibling selector), and remove `.form.invalid .err`.

**Adjudication:** _pending_

### 3. Text inputs lose the sitewide focus-visible contract; the substitute focus ring measures approx 1.46:1, far under the 3:1 minimum - escalates the open item in final-build-review finding 4

- **Severity:** major
- **Confidence:** confirmed (computed contrast, not yet observed live)
- **Where:** `static/css/_base.css:14` (`:focus-visible{outline:2px solid var(--gold);
  outline-offset:4px}`, stated in `static/css/main.css:20` as "never remove it"); `static/css/
  _components.css:35-40` (`.field input:focus,.field select:focus,.field textarea:focus{
  border-color:var(--gold);outline:none;box-shadow:0 0 0 3px rgba(217,192,138,.18)}`) - every text
  input, select and textarea in the contact, newsletter and booking-details forms.
- **What looks correct but is not:** the already-open item in
  `reviews/2026-09-22-final-build-review.md` finding 4 and `reviews/2026-09-22-project-structure-
  scaffold.md` treats this as an unreconciled style tension (box-shadow vs. §7's "no
  box-shadow" rule) - neither review measured what the substitute ring actually renders as.
  `rgba(217,192,138,.18)` composited over `--bg` (`#0B1526`) renders as approximately `rgb(48,52,
  56)` - a near-invisible shift from the background it sits on. Computed WCAG contrast of that
  composited colour against `--bg` is approximately **1.46:1**, far short of the 3:1 minimum WCAG 2.2
  expects for a focus indicator to be visually distinguishable (1.4.11 Non-text Contrast, applied
  to focus indicators). The rule also uses `:focus` rather than `:focus-visible`, and
  `outline:none` with no fallback - it doesn't degrade gracefully, it removes the sitewide
  indicator outright. The `border-color` does change to solid `--gold` on focus, which in
  isolation contrasts at 10.32:1 against the field's own `--bg` fill (comfortably over 3:1) - but
  that shift is a 1px border going from translucent gold (`--line-strong`, already present
  unfocused) to solid gold, not an added outline, and is a subtler visual event than the bold
  2px/4px-offset ring every other interactive element on the site gets.
- **Why it matters:** these are the exact fields a keyboard user tabs through on all three forms,
  including the booking flow's birth-detail fields. For an audience where reduced contrast
  sensitivity is unremarkable, "does my cursor's location on the page use the loud, wide, gold
  outline everyone else gets, or a barely-there haze plus a thin border colour change" is not a
  cosmetic inconsistency, it's the difference between confidently and uncertainly knowing which
  field is about to receive a keystroke.
- **Suggested action:** drop the box-shadow override and let `.field input:focus` etc. fall
  through to the sitewide `:focus-visible` rule (or explicitly re-apply it), consistent with
  `main.css`'s own "never remove or weaken" instruction. Flagging this as a WCAG-level escalation
  of the already-pending item in `reviews/2026-09-22-final-build-review.md` #4, not a duplicate -
  that review's adjudication should account for the measured ratio.

**Adjudication:** _pending_

### 4. The booking-status poller replaces its own aria-live region wholesale every 2 seconds

- **Severity:** major
- **Confidence:** mixed - the cadence/repetition problem is confirmed from the markup; whether it
  is announced at all, or announced repeatedly, is suspected pending a real screen reader
- **Where:** `templates/bookings/partials/_booking_status.html:28-31` - `<div id="booking-status"
  class="panel" aria-live="polite" hx-get="..." hx-trigger="every 2s" hx-target="this"
  hx-swap="outerHTML">` while `booking.status == "pending"`.
- **What looks correct but is not:** the element carrying `aria-live="polite"` is also the element
  `hx-swap="outerHTML"` replaces on every poll. Two distinct risks follow from that, and they cut
  in opposite directions: (a) some assistive technology only reliably announces mutations within
  a live region it has already registered - a wholesale node replacement every 2 seconds is a
  known weak spot for that, so the update may go unannounced; or (b) if it is picked up each
  time, a screen reader user hears "Confirming your payment... this usually takes a few seconds,
  please don't close this page" repeated in full every 2 seconds for as long as the payment takes
  to confirm - plausibly 10-60+ seconds, i.e. 5-30 repeats of an unchanged sentence, during the
  single moment (mid-payment) a visitor most needs calm, trustworthy feedback. Contrast this with
  `templates/bookings/partials/_checkout_error.html`'s `role="alert"` pattern (a one-shot,
  user-triggered swap carrying genuinely new content) - that is a safer, standard pattern; the
  2-second auto-poll on unchanged content is not.
- **Why it matters:** this is the moment right after a visitor has paid - the point in the
  booking flow with the highest anxiety and the highest cost of a bad experience if it goes
  wrong. Either failure mode (silence, or a stuck audio loop) undermines exactly the reassurance
  the copy is trying to give.
- **Suggested action:** keep the live-region container stable and swap only its text content
  (e.g. `hx-swap="innerHTML"` targeting a child, or `hx-swap-oob` on just the message), and only
  re-render when the status actually changes rather than on every tick; consider slowing the
  interval or backing off geometrically instead of a flat 2s while pending.

**Adjudication:** _pending_

### 5. Booking page skips from H1 straight to H3 throughout its main content

- **Severity:** moderate
- **Confidence:** confirmed
- **Where:** `templates/bookings/booking.html` (h1 at line 39, no h2 anywhere until the FAQ
  section at line 72); `templates/bookings/partials/_booking_status.html` (h3 "Checkout
  cancelled" / "Confirming your payment..." / etc.); `templates/bookings/partials/
  _booking_panel_form.html` (h3 "Choose your reading", h3 "Pick a date and time");
  `templates/bookings/partials/_details_form.html` (h3 "Your details").
- **What looks correct but is not:** every other audited page (home, about, readings index/detail,
  blog index/post, contact) goes h1 to h2 to h3 correctly. The booking page alone jumps from its
  h1 directly to a run of h3s - the payment-status panel and Steps 1-3 - with no h2 anywhere in
  between, only picking up an h2 again at the FAQ near the bottom.
- **Why it matters:** a screen reader user navigating by heading level (a standard, frequently
  used technique) finds nothing at h2 across the entire booking form on the site's primary
  conversion page, and the h3s they do land on misrepresent the document's real structure.
- **Suggested action:** give the booking-form section and/or the payment-status section a proper
  h2 (visually hideable if the current heading-less layout is wanted, e.g. "Your booking" /
  "Payment status"), and demote Steps 1-3 to genuine h3 children of it - which they already are
  visually, just not structurally.

**Adjudication:** _pending_

### 6. No-JS mobile-menu checkbox sits before the brand link in tab order - already-disclosed trade-off, narrower in practice than it first appears

- **Severity:** minor
- **Confidence:** confirmed
- **Where:** `templates/base.html:85-86` (`<input type="checkbox" id="menu-toggle" ...>` precedes
  `<a class="brand" ...>`); `static/css/_layout.css:40-43` (`.menu-toggle-input{position:absolute;
  width:1px;height:1px;...clip:rect(0,0,0,0);...}`, `.menu-toggle-input:focus-visible~.nav-right
  .menu-toggle-label{outline:2px solid var(--gold);outline-offset:4px}`,
  `body:not(.no-js) .menu-toggle-input,body:not(.no-js) .menu-toggle-label{display:none}`).
- **What looks correct but is not:** nothing beyond what `dc2c98c`/design-system already
  disclosed - confirmed present exactly as described. Assessing severity in practice: (a) with JS
  running (the overwhelming majority of real visits), `body:not(.no-js)` sets the checkbox and its
  label to `display:none`, which removes both from the tab sequence entirely - the ordering
  problem does not exist for JS-enabled visitors at all. (b) In the no-JS path, the checkbox is
  visually hidden but does have a real accessible name ("Menu", via the `for`/`id` association
  with the label elsewhere in `.nav-right` - label-for association works regardless of DOM
  distance) and a genuine, correctly-positioned visible focus indicator (the `:focus-visible ~
  .nav-right .menu-toggle-label{outline:...}` sibling-combinator rule paints the outline on the
  visible label in the top-right, not on the invisible checkbox itself). The net effect for a
  sighted no-JS keyboard user is: the very first Tab press highlights the "Menu" control in the
  header's top-right before the second Tab press reaches the wordmark in the top-left - a real,
  confirmed WCAG 2.4.3 Focus Order deviation from visual order, but not a lost or invisible focus
  indicator, and scoped to the no-JS + keyboard intersection only.
- **Why it matters:** low - narrow population (no-JS keyboard users), one element displaced by one
  position, indicator remains visible throughout.
- **Suggested action:** none required beyond what's already tracked as an accepted trade-off; if
  revisited, moving the checkbox to be a DOM sibling immediately after the brand link (rather than
  before it) while keeping it ahead of `<nav>` would fix the ordering without disturbing the CSS
  sibling-combinator mechanism.

**Adjudication:** _pending_

### 7. Decorative editorial images carry alt text that duplicates the adjacent heading instead of alt=""

- **Severity:** minor
- **Confidence:** confirmed
- **Where:** `templates/blog/partials/_post_list.html:56-57` (`<a class="post" href="{{ post.url
  }}"><figure>{% image post.featured_image ... alt=post.title %}</figure>...<h3>{{ post.title
  }}</h3></a>`); `templates/blog/post.html:100` (related posts, same pattern);
  `templates/readings/index.html:50/53` (`alt=reading.name` beside `<h2>{{ reading.name }}</h2>`);
  `templates/readings/detail.html:53` (`alt=page.reading.name`).
- **What looks correct but is not:** PROJECT-SCOPE.md §7 itself describes this imagery as
  "monochrome portrait, eclipse, astrolabe, navy still-life - cinematic" - atmospheric editorial
  photography, not diagrams unique to each post or reading. Using the post title / reading name as
  alt text doesn't describe what's actually in the photo (it can't - the same stock-style image
  language repeats across cards), and it duplicates text a screen reader user is about to hear
  again immediately: the blog card wraps the image and the `<h3>` in one `<a>`, so the announced
  content is the title, then the title again. The About-page portrait
  (`templates/core/about.html:59`, `alt="Portrait of Leslie Hale"`) is the correct pattern by
  contrast - informative, non-redundant, and about an image that actually is specific.
- **Why it matters:** minor, repeated friction rather than a blocker - every blog card and reading
  card announces its title twice to screen reader users.
- **Suggested action:** `alt=""` on the blog thumbnail and reading-card images, consistent with
  the scope's own framing of this imagery as decorative; keep real alt text only where the image
  is genuinely informative (the About portrait).

**Adjudication:** _pending_

### 8. Booking-calendar day buttons compute to roughly 30px wide at 320px viewport width

- **Severity:** minor / enhancement
- **Confidence:** suspected - arithmetic from committed CSS values, not a rendered screenshot
- **Where:** `static/css/_pages.css:160-162` (`.cal{grid-template-columns:repeat(7,1fr);
  gap:4px}`, `.cal button{...min-height:44px...}`); `static/css/_base.css:19` (`--pad:clamp(20px,
  5vw,64px)`); `static/css/_pages.css:149` (`.panel{padding:clamp(24px,3vw,36px)}`).
- **What looks correct but is not:** at a 320px CSS viewport, `--pad` clamps to its 20px floor
  (5vw = 16px, under 20px) on each side of `.wrap`, and `.panel`'s own padding clamps to its 24px
  floor on each side inside that - 88px of horizontal chrome removed from 320px leaves 232px for
  the 7-column calendar grid; six 4px gaps remove a further 24px, leaving approximately 208px
  divided by 7, or roughly **30px per day button**, against a 44px min-height. The buttons stay
  comfortably above WCAG 2.5.8's actual AA floor of 24x24px, so this is not a confirmed SC
  failure, but it is a narrow, non-square target for exactly the day-picker step of the core
  booking flow, at the exact width WCAG's reflow criterion (1.4.10) requires the layout to
  support without horizontal scrolling.
- **Why it matters:** narrow tap targets are a real friction point for the fine-motor-precision
  profile PROJECT-SCOPE.md §2 names, specifically on a phone at typical width or a desktop
  browser zoomed to 400%.
- **Suggested action:** verify visually at 320px; if confirmed, consider dropping the calendar to
  a scrollable/paginated day list or reducing the number of visible weeks rather than shrinking
  every cell.

**Adjudication:** _pending_

## Reviewed and found sound

- **Motion.** `static/js/main.js` checks `matchMedia('(prefers-reduced-motion: reduce)')` once at
  load and, if true, sets `.reduced` and returns before GSAP/ScrollTrigger/Lenis are ever
  registered or instantiated - motion is genuinely never created, not created-then-shortened.
  Independently, `static/css/_base.css:39` neutralises the two CSS transitions that exist outside
  JS's control (`.post img`, `.btn`) under the same media query. Split-heading spans
  (`[data-split]`) also never run when reduced, so headings stay as plain, intact text for screen
  readers regardless. Confirmed by reading the code; not observed live with the media query
  toggled in a real browser.
- **Skip link.** Present, genuinely first in the DOM (`templates/base.html:58`, before the menu
  checkbox), targets a real `id="main"` on `<main>`, and has a working `:focus` reveal rule.
- **Colour independence.** Every state found that's conveyed by colour is also conveyed by a
  second channel: calendar/slot selection (`aria-pressed` plus full fill inversion, not a hue
  tweak), disabled days (`disabled` attribute plus reduced-opacity/no border, not colour alone),
  reading-type selection (a real `checked` radio plus border/background change), nav
  `aria-current="page"` (colour plus underline), form validity (`aria-invalid` plus visible text,
  modulo finding 2's per-field scoping bug). No colour-only signal found.
- **Non-token colours that have crept in.** Grepped every CSS file for hex/rgba literals outside
  `_tokens.css`. Three exist, all pre-flagged in-file as deliberate, verbatim-from-source
  exceptions pending a design-system token decision - measured rather than assumed: `#E6D2A3`
  (`.btn-solid:hover`, text `--bg` on it) computes to approximately **12.27:1**; `#D6DBE4`
  (`.article p` body text, against `--bg`) computes to approximately **13.15:1**; `#fff`
  (`.hero-stars`) is non-text, decorative, `pointer-events:none` starfield dots, not a
  contrast-relevant use. All comfortably clear AA; no contrast failure from any non-token colour
  found. Also checked `--gold` text against `--bg-2` (approximately 9.69:1) and `--bg-3`
  (approximately 8.94:1) - the "gold on gold-tinted panels" case called out for attention - both
  pass comfortably; and `--danger` against `--bg-2` (approximately 6.68:1, the error-text/panel
  combination), also passes.
- **Viewport meta tag.** `width=device-width, initial-scale=1`, no `maximum-scale` or
  `user-scalable=no` anywhere - pinch/zoom is not blocked at the meta-tag level. Actual 200%/320px
  visual reflow not verified without a browser.
- **Form field/label/error association architecture.** Every input across all three forms
  (contact, newsletter, booking details) has a real `<label for>`, a correctly-scoped
  `aria-describedby` pointing at that field's own error span id, and a correctly per-field
  `aria-invalid` - the architecture is right; only the CSS reveal rule is wrong (finding 2).
  `required`/`type="email"`/`type="date"` are used appropriately, and no field relies on
  placeholder text as its only label.
- **Checkout-error region.** `templates/bookings/partials/_checkout_error.html` uses
  `role="alert"` on a freshly-inserted, one-shot, user-triggered swap carrying genuinely new
  content - the standard, reliable pattern for this, and a better design than the booking-status
  poller (finding 4).
- **Heading structure, all pages except booking.** Home, About, Readings index/detail, Blog
  index/post, Contact each carry exactly one h1 and no skipped levels.
- **Touch targets, generally.** `.pager a`/`.cal button`/`.cal-head button` (44x44),
  `.svc .price a` (44px min-height, already patched per its own comment referencing "REVIEW.md
  C10"), and the `.opt` reading-type row (the whole `<label>` is the target, far over 44px) all
  meet or exceed the 44px best-practice bar this audience warrants. `.filters a` and `.nav
  .btn-nav` at 40px sit under that bar but still clear WCAG 2.5.8's actual 24px AA minimum -
  enhancement-level only, not a confirmed SC failure.
- **Link text.** Generally descriptive ("Book this reading", "Continue to payment", "Subscribe").
  One recurring exception: "Learn more" (`templates/readings/index.html:65`) is ambiguous read in
  isolation, but sits inside the same reading card as that reading's own name, which satisfies
  WCAG 2.4.4 Link Purpose (In Context) at AA - it only fails the stricter, AAA-only 2.4.9
  (Link Purpose, Link Only). Noted, not treated as an AA failure.

## Cross-references to other pending reviews

- `reviews/2026-09-22-final-build-review.md` finding 1 (no-JS POST to any of the three htmx forms
  returns a bare, unstyled fragment with no nav/skip-link/site chrome at all, not just an
  unhandled scope claim) has a direct accessibility reading worth recording here even though it's
  not mine to re-litigate: a no-JS visitor - including a screen reader user running with
  JavaScript disabled, not just an incidental scripting failure - who submits any of these forms
  is dropped entirely outside any landmark structure, with no way back into the site except the
  back button. If that finding is adjudicated as accepted, it should be understood as an
  accessibility fix, not only a UX one.
- `reviews/2026-09-22-final-build-review.md` finding 4 and `reviews/2026-09-22-project-structure-
  scaffold.md`'s "reviewed and found sound" note both already flag the form-field box-shadow focus
  ring as an unreconciled §7 style tension. Finding 3 above supplies the measured contrast ratio
  (approximately 1.46:1) neither of those reviews computed - recommend reading them together
  rather than adjudicating separately.

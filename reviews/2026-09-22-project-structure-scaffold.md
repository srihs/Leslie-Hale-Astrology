# Review: project structure scaffold (config/docker/apps/templates/static)

**Date:** 2026-09-22
**Reviewed:** uncommitted working tree — `config/`, `docker/`, `pyproject.toml`, `.env.example`,
`docker-compose.yml`, `manage.py` (docker-infra); `static/css/` (design-system); `apps/`
(wagtail-backend); `templates/` and `static/js/` (htmx-frontend)
**Reviewer:** code-critic (agent)

## Self-reported findings, independently verified

### S1. `pyproject.toml` pins a nonexistent package name

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `pyproject.toml:14`
- **What looks correct but is not:** `modelcluster==6.3` is pinned. The real PyPI distribution is
  `django-modelcluster`; there is no package published as plain `modelcluster`. I confirmed
  `pip download django-modelcluster` resolves and that `6.3` is a real version *of that package*
  (`pip index versions django-modelcluster` lists 6.3 among others) — so the version number is
  right, only the package name is wrong.
- **Why it matters:** `docker/Dockerfile:37` runs `pip install --no-cache-dir .` in the builder
  stage against exactly this file. The build fails immediately; nothing downstream (migrations,
  runtime image, docker-compose) can be exercised until this is fixed.
- **Suggested action:** change the dependency line to `django-modelcluster==6.3`.

**Adjudication:** _pending_

### S2. No-JS mobile visitors cannot open the nav menu

- **Severity:** major
- **Confidence:** verified
- **Where:** `static/css/_layout.css:18-19` (`.nav ul{display:none;...}` / `.nav ul.open{display:flex}`
  inside the ≤900px media query); toggle logic in `static/js/main.js:26-31`
- **What looks correct but is not:** Below 900px the `<ul id="menu">` is `display:none` until JS
  adds `.open` via the `.menu-btn` click handler. A visitor without JS has no way to reveal the
  menu items (Home/About/Readings/Blog/Contact/Book) — only the always-visible wordmark and the
  "Book a Reading" button in `.nav-right` remain reachable.
- **Why it matters:** contradicts the project's own no-JS requirement for interactive UI, and
  narrows non-JS/mobile navigation to two links.
- **Provenance confirmed:** the identical rule (`.nav ul{display:none;...}` / `.nav ul.open`) is
  present verbatim in the locked `versions/v1-ephemeris/style.css:47-48`, so this is inherited
  from the locked design source, not introduced by design-system.
- **Additional detail beyond the self-report:** `templates/includes/_nav.html:9-10`'s own comment
  says "without JS the `<ul id="menu">` is always visible via CSS (see `_layout.css` `.nav ul`)" —
  that comment is incorrect; the CSS it cites does the opposite below 900px. Worth fixing the
  comment regardless of how the underlying defect is resolved, since it will mislead the next
  person who reads it.
- **Suggested action:** either accept as an inherited/locked-design limitation (§7 is locked, so
  this may be a legitimate case for a signed-off exception) or add a no-JS fallback (e.g. a
  `<details>`-based disclosure, or unhiding the list via a `@media (hover:none)`-independent
  progressive-enhancement class). Either way, correct the false comment in `_nav.html`.

**Adjudication:** _pending_

### S3. `--muted` on `--bg-2` is not actually a risky contrast pair

- **Severity:** minor
- **Confidence:** verified
- **Where:** `static/css/_tokens.css:10` (`--muted:#A9B3C4`, `--bg-2:#0E1B33`);
  `.claude/agents/design-system.md:54` ("`--muted` on `--bg-2` is the risky pair")
- **What looks correct but is not:** I computed the WCAG relative-luminance contrast ratio for
  `#A9B3C4` on `#0E1B33` and got **8.12:1** (recomputed independently via the standard formula,
  matching the self-reported figure exactly). That clears AA (4.5:1) and AAA (7:1) for normal
  text with margin to spare. The "risky pair" framing in the agent definition (and, per the task
  brief, in my own brief) is not supported by the actual token values — both `--muted` and
  `--bg-2` are copied verbatim from the locked `versions/v1-ephemeris/style.css`.
- **Why it matters:** low severity on its own (nothing is actually failing), but a standing
  "risky pair" assumption baked into an agent definition can cause future work to over-correct
  (e.g. darkening `--muted` unnecessarily, drifting off the locked palette) chasing a problem
  that doesn't exist at these two token values. It may be a legitimate concern for some *other*
  pairing (e.g. `--muted` on `--bg-3`, or `--muted` at small/thin type sizes) that got mislabelled.
- **Suggested action:** correct or narrow the claim in `design-system.md`, or replace it with
  whichever pairing was actually intended to be flagged.

**Adjudication:** _pending_

## Findings from my own pass

### 1. No URL routing exists anywhere — every template references named URLs that don't resolve

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `config/urls.py` (no `include()` for any of `apps.core`, `apps.home`,
  `apps.readings`, `apps.bookings`, `apps.blog`, `apps.contact`); no `urls.py` file exists
  anywhere under `apps/` (`find apps -name urls.py` returns nothing); every template uses
  `{% url 'home:index' %}`, `{% url 'bookings:booking' %}`, `{% url 'contact:contact' %}`,
  `{% url 'blog:index' %}` / `'blog:post'`, `{% url 'readings:index' %}` / `'readings:detail'`,
  `{% url 'core:about' %}` / `'core:privacy'` / `'core:terms'`, `{% url 'contact:newsletter_signup' %}`,
  `{% url 'bookings:checkout' %}`, `{% url 'bookings:save_details' %}` — none of these namespaces
  exist.
- **What looks correct but is not:** `templates/base.html:24,27` (included on literally every
  page) and `templates/includes/_nav.html` and `_footer.html` (also included on every page) all
  call `{% url %}` with these names. Django raises `NoReverseMatch` at template-render time for
  an unresolvable URL name — there is no fallback. Even `templates/404.html` uses `{% url 'home:index' %}`
  and `{% url 'bookings:booking' %}`, so the custom 404 handler would itself fail to render.
- **Why it matters:** in the current state, no page in the site can render — not the homepage,
  not the error pages. This is scaffold-stage work and the per-app `views.py` files explicitly
  note routing is deferred ("No views yet"), so this may be expected sequencing rather than an
  oversight — but nothing in the four agents' output currently fits together enough to serve a
  single page, which is squarely what this review was asked to check.
- **Suggested action:** confirm whether wiring `urls.py` + `include()` is simply the next step
  (in which case this finding is informational, not a defect) or whether it was supposed to be
  part of this scaffold handoff.

**Adjudication:** _pending_

### 2. Templates assume classic Django URL namespacing for what are modelled as Wagtail pages

- **Severity:** blocker
- **Confidence:** suspected
- **Where:** every `{% url 'home:index' %}`, `{% url 'core:about' %}`, `{% url 'readings:index' %}`,
  `{% url 'readings:detail' slug %}`, `{% url 'blog:index' %}`, `{% url 'blog:post' slug %}`,
  `{% url 'bookings:booking' %}` call across `templates/`; `config/urls.py:37-39`
  (`path("", include(wagtail_urls))` as the catch-all); every page model's own docstring/views.py
  comment ("served by Wagtail's normal page-serving mechanism").
- **What looks correct but is not:** `apps.home.HomePage`, `apps.core.AboutPage`,
  `apps.readings.ReadingsIndexPage`/`ReadingDetailPage`, `apps.blog.BlogIndexPage`/`BlogPost`,
  and `apps.bookings.BookingPage` are all Wagtail `Page` subclasses, explicitly documented as
  served by Wagtail's tree-based routing via `wagtail_urls`. Wagtail pages don't get named,
  reversible URLs the way ordinary Django views do — they're addressed by `page.url` /
  `{% pageurl page %}` or by request path, not by `{% url 'app:name' %}`. Building every internal
  link in every template around namespace:name reversal is inconsistent with how the backend
  says these pages are served.
- **Why it matters:** if this is the real architecture (rather than S1's "not wired up yet"),
  fixing it isn't a matter of adding `urls.py` files — it requires either rewriting every
  internal link in every template to use `{% pageurl %}`, or adding parallel explicit URL routes
  for pages that duplicate Wagtail's own routing (unusual, and a source of dead-end/duplicate
  URLs). I could not confirm which path was intended since no `urls.py` exists yet to check
  against; flagging as suspected rather than verified for that reason.
- **Suggested action:** wagtail-backend and htmx-frontend should agree explicitly on the URL
  strategy for page-backed templates before more template work is built on the current
  `{% url %}` assumption.

**Adjudication:** _pending_

### 3. No page model overrides Wagtail's default template path — none of the actual template files would be found

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `apps/home/models.py`, `apps/readings/models.py`, `apps/blog/models.py`,
  `apps/contact/models.py`, `apps/bookings/models.py`, `apps/core/models.py` — none defines a
  `template` attribute or overrides `get_template()` (`grep -rn "template" apps/*/models.py`
  turns up only an unrelated comment in `bookings/models.py`).
- **What looks correct but is not:** Wagtail's default `Page.get_template()` resolves to
  `"{app_label}/{model_name}.html"` (e.g. `HomePage` → `home/home_page.html`,
  `ReadingsIndexPage` → `readings/readings_index_page.html`, `AboutPage` → `core/about_page.html`,
  `BlogPost` → `blog/blog_post.html`). The template files that actually exist are named
  differently and to a different convention: `templates/home/index.html`,
  `templates/readings/index.html` / `detail.html`, `templates/blog/index.html` / `post.html`,
  `templates/contact/contact.html`, `templates/bookings/booking.html` — and there is no
  `core/about_page.html`, `core/privacy.html` or `core/terms.html` at all (confirmed with
  `find templates -iname "*about*" -o -iname "*privacy*" -o -iname "*terms*"`, no results).
- **Why it matters:** even once URL routing (finding 1) is resolved, Wagtail would raise
  `TemplateDoesNotExist` serving any page in the site, and the About/Privacy/Terms pages have no
  template at all yet, invented or otherwise.
- **Suggested action:** either add `template = "..."` on each page model pointing at the existing
  file names, or rename the templates to match Wagtail's convention — plus author the three
  missing templates.

**Adjudication:** _pending_

### 4. `get_context()` supplies raw model instances whose field names don't match what the templates expect

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `apps/readings/models.py:126-131` (`ReadingsIndexPage.get_context`) vs.
  `templates/readings/index.html:7-11` header comment and body; `apps/home/models.py:90-102`
  (`HomePage.get_context`) vs. `templates/home/index.html:6-16` header comment and body;
  `apps/blog/models.py:39-49` (`BlogIndexPage.get_context`) vs.
  `templates/blog/partials/_post_list.html:14-17` header comment and body.
- **What looks correct but is not:**
  - `ReadingsIndexPage.get_context` sets `context["readings"]` to the raw `Reading` queryset.
    The `Reading` model (`apps/readings/models.py:27-106`) has fields `name`, `summary`,
    `description`, `duration_minutes`, `price`, `price_note`, `image` (a Wagtail image FK),
    `is_active`, `order` — **no `slug`, `title`, `number_label`, `tag_label`, `bullets`,
    `image_url` or `image_alt`**. The template's own comment documents exactly that shape as the
    expected context (`slug, number_label, tag_label, title, description, bullets, price,
    duration_minutes, image_url, image_alt`). `{{ reading.title }}`, `{{ reading.slug }}`,
    `{{ reading.bullets }}` etc. will all render empty; every reading card and the
    `{% url 'readings:detail' other.slug %}` links (empty slug) would be broken even once
    URL routing exists.
  - `HomePage.get_context` only adds `context["latest_posts"]`. The template loops over
    top-level `services`, `about`, `testimonials` variables (`{% for service in services %}`,
    `about.portrait_image`, `about.years`, `{% for t in testimonials %}`) that are **never set
    anywhere** — the actual data for these sections lives in `HomePage`'s StreamFields
    (`page.services`, `page.about`, `page.testimonials`, accessed via `page.`, not bare names),
    and even then the block shapes differ: `ServicesTeaserBlock` holds one `featured_reading`
    snippet chooser plus one image (not a list of many services with `number_label`/`featured`),
    and `AboutTeaserBlock` has `portrait`/`story`/`pull_quote` (not `portrait_image`/`years`/`quote`).
  - `BlogIndexPage.get_context` sets `context["posts"]` to the raw `BlogPost` queryset. The
    `_post_list.html` template expects `{url, image_url, image_alt, date, category, title,
    excerpt}`, but `BlogPost` (`apps/blog/models.py:60-124`) has `published_date` (not `date`),
    `featured_image` (an FK, not `image_url`), and **no `category` field at all** (only a
    `tags` taggable manager) — the category filter/eyebrow/breadcrumb on the blog pages has
    nothing to bind to.
- **Why it matters:** these are not edge cases — they are the primary content of the homepage,
  Services page and Blog index, the three pages carrying the site's main conversion paths. As
  written, once the scaffold is wired up, these sections will render structurally (the HTML
  shell is fine) but empty of the data described in every one of htmx-frontend's own context
  comments.
- **Suggested action:** either adapt `get_context()` in each page model to shape the data as the
  templates already document (a view-model/serialization layer), or rewrite the templates
  against the StreamField/model shapes wagtail-backend actually built. This needs to be
  reconciled by whichever agent's contract is meant to be authoritative — right now neither
  side matches the other.

**Adjudication:** _pending_

### 5. Footer/contact templates hardcode a fully-formed contact email as the fallback for an explicitly unconfirmed §8 item — and the wrong settings model means the fallback always fires

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `templates/includes/_footer.html:37`,
  `templates/contact/partials/... ` — actually `templates/contact/contact.html:27-30`
- **What looks correct but is not:** `_footer.html:4-9`'s own comment states: *"Until that
  snippet has real values, the `default` filters below render a bracketed placeholder rather
  than inventing a real-looking email/phone."* The code directly below it does the opposite for
  email: `{{ settings.core.SiteSettings.contact_email|default:'hello@lesliehale-astrology.com' }}`
  — a complete, plausible, real-looking business email address, used both as the `mailto:` href
  and the visible link text. The phone field two lines below it, by contrast, correctly falls
  back to the honest placeholder `"[phone TBC]"` (`contact.html:28`), showing the intended
  pattern was applied inconsistently.
  Separately, and compounding it: the accessor is `settings.core.SiteSettings`, but the actual
  registered setting in `apps/core/models.py:36` is `ContactSettings`
  (`@register_setting(icon="mail") class ContactSettings(BaseGenericSetting)`), not
  `SiteSettings`. `settings.core.SiteSettings` will never resolve to anything (Django template
  variable lookup fails silently to empty string), so **the `default:` fallback fires
  unconditionally, even after Leslie fills in her real email in the Wagtail admin** — the
  invented address would show on the live site regardless of what she enters, until the
  accessor name is fixed.
- **Why it matters:** §8 lists "Contact email / phone" as `TBC — not supplied in questionnaire`.
  This renders an invented, specific, real-looking business email address on the Contact page
  and site-wide footer of a real client's site — exactly the kind of open-item invention the
  scope document warns against — and, independently, is a wiring bug that would silently
  ignore whatever Leslie actually enters.
  `apps/core/models.py:18-22`'s own module docstring states the intended discipline explicitly
  ("Nothing here guesses at real-looking values... never a specific invented number"); this
  template directly violates that stated design principle, and the AboutTeaserBlock/years-figure
  discipline (finding 6) versus this email default shows the two agents' outputs disagree with
  each other on whether invented-looking placeholders are acceptable.
- **Suggested action:** fix `settings.core.SiteSettings` → `settings.core.ContactSettings`
  throughout, and replace the email `default:` value with an honest bracketed placeholder
  consistent with the phone field and with the rest of the codebase's own convention
  (`"[price TBC]"`, `"[TBC]"`, `"[phone TBC]"`).

**Adjudication:** _pending_

### 6. Homepage hardcodes an invented "practising since 2004" / "20+ years" figure for the explicitly unconfirmed years-of-experience item

- **Severity:** blocker
- **Confidence:** verified
- **Where:** `templates/home/index.html:47` and `:84`
- **What looks correct but is not:** Line 47: `<span>Readings since
  {{ about.practising_since|default:"2004" }}</span>`. Line 84: `<b>{{ about.years|default:"20+" }}</b><span>Years
  reading charts</span>`. §8 lists "Testimonials (3+) and years of experience figure" as an
  explicitly unconfirmed open item. As established in finding 4, `about` is never supplied by
  `HomePage.get_context`, and neither `AboutTeaserBlock` (`apps/home/blocks.py:79-101`) nor any
  other model defines `practising_since` or `years` fields — the real source of truth for this
  figure, per `apps/core/models.py:71-77`, is `ContactSettings.years_experience_label`, which is
  a free-text field defaulting to the honest, obviously-placeholder string `"Experience details
  coming soon"`. Because `about.practising_since`/`about.years` can never be populated by
  anything in this codebase as it stands, **the `default:"2004"` / `default:"20+"` values are not
  fallbacks — they are the only values that will ever render** on the homepage hero and About
  teaser.
- **Why it matters:** this states, in the site's own hero caption and about-stat badge, a
  specific and plausible-sounding claim about how long Leslie has been practising (since 2004,
  i.e. ~20+ years) that nobody has confirmed. It directly contradicts both §8 and the
  discipline `apps/core/models.py`'s own docstring lays out for exactly this figure ("never a
  specific invented number").
- **Suggested action:** replace both defaults with an honest placeholder (e.g. `"[years TBC]"`),
  or wire the hero/about teaser to read `ContactSettings.years_experience_label` (which already
  exists for this purpose) instead of a nonexistent `about.years`/`about.practising_since`.

**Adjudication:** _pending_

## Reviewed and found sound

- `pyproject.toml` — dependency set is otherwise sensible and pinned; only the modelcluster name
  is wrong (S1).
- `config/settings/base.py` — secrets are correctly never hard-coded, `env()` fails loudly on
  missing required vars, `DEBUG` is deliberately not environment-controlled, `TIME_ZONE`
  defaults sensibly to `Pacific/Auckland`, `INSTALLED_APPS`'s `LOCAL_APPS` list matches the six
  `apps/*` directories that actually exist.
- `docker/Dockerfile` — correct multi-stage build, non-root user, trimmed runtime image,
  Python-only healthcheck (no extra `curl` dependency); the base-image digest-pin gap is
  self-documented as a known follow-up, not a silent omission.
- `apps/readings/models.py` `Reading.price` — correctly left `null=True, blank=True` rather than
  guessing a number, consistent with §8; `price_note` gives Leslie an honest interim label.
  Same discipline in `apps/bookings/models.py` (`payment_provider` left as free text rather than
  assuming Stripe/Calendly/PayPal) and `apps/contact/models.py` (`NewsletterSignup` stores
  locally rather than guessing an email-marketing platform).
- Empty-state handling for genuinely unconfirmed content — `{% empty %}` blocks for readings,
  testimonials, and blog posts render nothing (with an explanatory HTML comment citing §8)
  rather than inventing placeholder testimonials or fake blog posts. This is the correct pattern,
  and makes the isolated violations in findings 5 and 6 stand out as inconsistent with the
  project's own established convention rather than a systemic policy failure.
- `static/css/` — no stray `box-shadow` or `border-radius` outside the one explicitly
  documented, deliberate exception (`_pages.css:24-28`, the pill-shaped hero tag), consistent
  with §7's "square/near-square corners, no shadows" rule. The one pre-existing focus-ring
  `box-shadow` on form fields is flagged in-file as a known, not-yet-reconciled tension rather
  than an unflagged violation.
- `.env.example` — no real secrets committed; `changeme`/blank values are clearly-labelled dev
  placeholders, consistent with `docker-compose.yml`'s `env_file` convention.
- Booking data model (`apps/bookings/models.py`) — correctly scoped to "data shape only" per its
  own docstring; does not attempt to invent availability/calendar/payment logic that §8 leaves
  open.

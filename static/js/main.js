/* Leslie Hale Astrology — motion + interaction layer.
   Ported from versions/v1-ephemeris/main.js (GSAP 3 + ScrollTrigger, Lenis
   as the sole smooth-scroll engine) onto the Django/htmx templates.

   Everything in this file is enhancement. Every interaction it touches —
   the mobile menu, the booking/contact/newsletter forms, blog filtering —
   already works as a plain link/form/button without it; see each
   template's own comment for that interaction's no-JS contract. This file
   never blocks or replaces the server round trip, it only makes it feel
   nicer when JS, GSAP and Lenis are all available.

   Removed from the original demo (deliberate, not an oversight): the
   `.form` submit-intercept-and-fake-a-response block and the
   `[data-booking]` client-side price/summary calculator. Both were
   static-prototype stand-ins for a real backend. Submission, validation
   and the booking summary are now genuinely computed server-side
   (apps.contact / apps.bookings) and delivered via htmx swaps or full page
   reloads — duplicating that logic here would race the real response and
   could show a fake "sent" state the server didn't actually accept. */
(function () {
  document.body.classList.remove('no-js');
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* [data-reveal]{opacity:0} (static/css/_base.css) is only ever cleared by
     .no-js/.reduced (the CSS escape hatch, for the no-JS and reduced-motion
     cases) or by the GSAP timelines further down this file. .no-js is
     removed UNCONDITIONALLY, one line up, because the mobile-menu
     progressive enhancement right below doesn't need GSAP at all — so if
     the GSAP <script> tags in base.html fail to load (CDN down,
     ad-blocked, offline: a real, not hypothetical, failure mode for a
     third-party script tag), window.gsap is undefined, .no-js is already
     gone, .reduced never gets added (prefers-reduced-motion is false for
     most visitors), and everything from "hero intro" onward below exits
     at the `if (reduced || !window.gsap) return;` guard before touching a
     single [data-reveal] element — every one of them would stay at its
     CSS opacity:0 forever, sitewide, with nothing in the console to say
     why. Treating "GSAP didn't load" the same as "reduced motion" for
     this one CSS class closes that: it's the same class _base.css already
     uses to mean "skip the animation, just show it". */
  if (reduced || !window.gsap) document.body.classList.add('reduced');

  /* ---------- mobile menu ---------- */
  var mb = document.querySelector('.menu-btn'), menu = document.getElementById('menu');
  if (mb && menu) {
    mb.addEventListener('click', function () { var o = menu.classList.toggle('open'); mb.setAttribute('aria-expanded', o); });
    menu.addEventListener('click', function (e) { if (e.target.tagName === 'A') { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); } });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.classList.contains('open')) { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); mb.focus(); } });
  }

  /* ---------- htmx event-detail rule (read this before adding a handler below) ----------
     Every htmx:afterSwap handler in this file that needs the element
     htmx just swapped in MUST read it off `e.target` — the event's
     native, bubbled DOM target — never off `e.detail.target`.
     `e.detail.target` is set once, at request time, to the element that
     was ABOUT to be replaced, and htmx never updates it afterwards. For
     hx-swap="outerHTML" (every swap in this file: #post-list,
     #booking-panel, and the self-targeting contact/newsletter/booking-
     details forms) that old element is removed from the document as
     part of the swap, so anything read off `e.detail.target` after that
     point — a querySelector, a classList check, anything — runs against
     a detached node: present in memory, invisible on screen, unreachable
     by the CSS or the visitor. `e.detail.elt` is safe to use below, but
     only on events that fire before any swap is attempted
     (htmx:sendError / htmx:responseError / htmx:timeout, immediately
     below) — nothing has been replaced yet at that point, so it still
     points at a live, attached element.
     This exact mistake has now shipped twice from this file on
     `e.detail.target` in an afterSwap handler: the blog-filter reveal
     fix below, and the form.sent focus handler further down, caught in
     the same sweep. If you're adding a third afterSwap handler, check it
     against this comment before it ships a third instance of the same
     bug. */

  /* ---------- htmx class/attribute-settle rule (read this too, before adding a handler below) ----------
     A SEPARATE trap from the one above, and one `e.target` does not fix:
     `e.target` on `htmx:afterSwap` is the right, live, attached element —
     but its CLASS ATTRIBUTE is not yet the response's real one. htmx
     keeps the pre-swap class on the incoming element (plus its own
     transient `htmx-swapping` / `htmx-added` / `htmx-settling` classes)
     for the whole swap step, precisely so a CSS transition has an old
     class and a new class to animate between, and only writes the
     response's actual class list once settle runs. Confirmed live
     (instrumented both events on the same page): a swapped `#post-list`'s
     `className` at `afterSwap` reads `"htmx-swapping htmx-added
     htmx-settling"`; the same element's `className` at `afterSettle`
     reads whatever the response actually sent. Any other attribute the
     response set directly on the swapped element — `id` included — is
     already correct at `afterSwap`; children and their own attributes
     (`querySelector`, `[data-reveal]`, tag names, text content) are
     already correct too, since they arrived with the swap, not with the
     settle step. Only the swapped element's OWN class is deferred.

     So: read the swapped ELEMENT off `e.target` on `afterSwap` (rule
     above), but a check that depends on the response's CLASS on that
     element — `.matches('form.sent')`, `.classList.contains(...)`, any
     selector with a class in it applied to `e.target` itself — must wait
     for `htmx:afterSettle` instead, or it will silently and permanently
     read the pre-swap class. This has now shipped once from this file:
     the form.sent focus handler below tested `target.matches('form.sent')`
     on `afterSwap` and was therefore always false, even after that
     handler's own `e.target` fix (f989c39) — necessary, not sufficient.
     If you're adding a handler that branches on `e.target`'s own class,
     check it against this comment first. */

  /* ---------- htmx: fall back to a real navigation when a request fails ----------
     ROOT CAUSE of "the blog category filters don't work" (reproduced live
     with Playwright: aborting the XHR for one `?category=` click leaves
     the grid, the pager and aria-current completely unchanged, with no
     error shown anywhere — indistinguishable from a dead control):
     htmx calls preventDefault() on a hx-get anchor's click the moment it
     decides to handle it, *before* the request is even sent. A plain
     `<a href>` that failed to load would fall back to nothing special —
     the browser just shows its own network-error page — but an
     intercepted one has already had its default cancelled, so a failed
     request (a dropped mobile connection, a mid-deploy server restart —
     genuinely observed against the dev server while investigating this —
     an ad-blocked or offline CDN, anything covered by this scope's "some
     of them have flaky JS") leaves the visitor stuck exactly where they
     clicked, with the chip they pressed still looking unpressed. Every
     hx-get control in this site (blog category filters, blog pager,
     booking calendar) is a real link/button with a working href/no-JS
     path first, so recovering is just: do what the browser would have
     done without htmx at all. Scoped to elements with an `href` (the
     booking calendar's controls are plain submit buttons with none, so
     this never touches them) so it only ever fires for a genuine
     hx-get-anchor failure. */
  function navigateOnHtmxFailure(e) {
    var elt = e.detail && e.detail.elt;
    var href = elt && elt.getAttribute && elt.getAttribute('href');
    if (href) window.location.href = href;
  }
  document.body.addEventListener('htmx:sendError', navigateOnHtmxFailure);
  document.body.addEventListener('htmx:responseError', navigateOnHtmxFailure);
  document.body.addEventListener('htmx:timeout', navigateOnHtmxFailure);

  /* ---------- htmx: focus the result of a form swap ----------
     Every htmx-swapped form (newsletter, contact, booking details) is
     declared with aria-live="polite" in its template, so screen reader
     users hear the swapped result regardless of this. This adds a
     managed focus move on top of that: once the server marks a form
     "sent" (static/css/_components.css .form.sent reveals .ok), move
     focus to the confirmation so sighted keyboard users land there too,
     instead of staying on a button that just disappeared.

     Reads `e.target`, not `e.detail.target` — see the htmx event-detail
     rule above. Each of these forms self-targets with hx-swap="outerHTML"
     (_contact_form.html, _newsletter_form.html, _details_form.html all
     set hx-target to their own id), so `e.detail.target` was the old,
     pre-submission form: never `.sent`, so `target.matches('form.sent')`
     was always false and this handler never fired. Found in the same
     sweep as the blog-filter reveal bug below; same fix.

     LISTENS ON afterSettle, not afterSwap — see the htmx class/attribute
     rule above. `target.matches('form.sent')` needs the RESPONSE's own
     class attribute on the swapped-in form, and htmx does not apply that
     until settle: at afterSwap time the form still carries its
     pre-submission class (plus the transient htmx-swapping/htmx-settling
     classes htmx adds for the swap), so `.matches('form.sent')` was still
     always false even after the e.target fix above. Confirmed live by
     test-engineer instrumenting both events on the same page: switching
     this one handler to afterSettle is what makes
     tests/browser/test_form_focus.py pass. This was necessary but not
     sufficient the first time around — recorded as its own thing below
     because it is a different failure mode from the e.target one, not a
     restatement of it. */
  document.body.addEventListener('htmx:afterSettle', function (e) {
    var target = e.target;
    if (target && target.matches && target.matches('form.sent')) {
      var ok = target.querySelector('.ok');
      if (ok) ok.focus();
    }
  });

  /* ---------- htmx: keyboard focus survives #booking-panel / #post-list swaps ----------
     A11Y FINDING 1, reviews/2026-09-22-final-accessibility-audit.md: both
     regions carry hx-swap="outerHTML" on a container that includes the
     very control the visitor just activated (reading radio, month nav,
     day, slot in _booking_panel_form.html; category filter, pager in
     _post_list.html) — the browser moves focus to <body> when the
     currently-focused node is removed from the document, and the
     form.sent handler just above only ever runs for a submitted form.

     htmx's own swap() already restores focus by id: if the previously-
     focused element had one and an element with the same id exists in
     the freshly-swapped content, htmx focuses it, before this event even
     fires — which is why every control in _booking_panel_form.html and
     _post_list.html now carries a stable id keyed on what it represents
     (reading slug, day iso, slot value, category slug, page number), not
     on its position. That covers the common case: the same control (or
     its equivalent after a month/category change) still exists after the
     swap, so focus lands right back on it.

     This handler is only the fallback for when nothing matched (e.g. the
     day just chosen is now disabled in the freshly-rendered calendar) —
     detected by focus having fallen through to <body> — and lands on the
     swapped-in panel's own first heading instead, with a managed
     tabindex so it's a genuine, announced landing point rather than
     leaving the visitor's keyboard position undefined.

     CORRECT on afterSwap, checked against the class/attribute-settle rule
     above: this handler reads `target.id` (an attribute the response set
     directly, not `target`'s class) and `target.querySelector('h2, h3')`
     (child elements that arrive with the swap). Verified live on both
     `#post-list` and `#booking-panel`: `headingFound`/`headingText` from
     `target.querySelector('h2, h3')` were identical at `afterSwap` and at
     `afterSettle` in every trial, while `target.className` in the same
     trials was the transient `htmx-swapping htmx-added htmx-settling` at
     `afterSwap` and only the response's real value at `afterSettle`. This
     handler never reads that class, so it isn't exposed to the deferral
     and afterSwap is the right event for it. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    var target = e.target;
    if (!target || !target.id || (target.id !== 'booking-panel' && target.id !== 'post-list')) return;
    if (document.activeElement && document.activeElement !== document.body) return;
    var heading = target.querySelector('h2, h3');
    if (!heading) return;
    if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
    heading.focus();
  });

  /* ---------- htmx: re-run scroll reveals for swapped-in content ----------
     #post-list (blog filter/pagination) is the one htmx target that can
     introduce fresh [data-reveal] cards after the page's initial GSAP pass
     has already run (see "section reveals" below, which only scans once
     on load). Rather than re-triggering a scroll-in animation for content
     the visitor just explicitly asked for, just make it visible —
     consistent with how [data-reveal] already degrades for .no-js/.reduced.

     ROOT CAUSE of "selecting a category filter leaves the post tiles
     invisible" (reproduced live: pagination and aria-current update
     correctly, no tiles render): this used to read `e.detail.target`.
     #post-list swaps with hx-swap="outerHTML", so `e.detail.target` is
     the OLD #post-list — removed from the document by the time this
     handler runs (see the htmx event-detail rule above) — so
     `querySelectorAll('[data-reveal]')` found the detached old cards and
     `gsap.set(..., {opacity:1})` made THOSE visible while the new cards,
     still governed by `[data-reveal]{opacity:0}` in _base.css, stayed
     invisible on screen. Fixed to `e.target`, matching the working
     booking-panel/post-list focus handler above.

     CORRECT on afterSwap, checked against the class/attribute-settle rule
     above: this handler reads `[data-reveal]` — a data attribute on
     `e.target`'s CHILDREN, not a class on `e.target` itself — and sets
     `opacity`/`y` directly as inline style via `gsap.set`, never
     consulting `e.target`'s own class either to decide whether to run or
     to compute the value. Verified live on `#post-list`: the swapped
     tiles' `[data-reveal]` count was identical (9) at `afterSwap` and at
     `afterSettle` in the same trial where `e.target.className` differed
     between those two events exactly as the rule above describes. Nothing
     this handler reads is deferred, so afterSwap is the right event for
     it. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (!window.gsap || reduced) return;
    var items = e.target ? e.target.querySelectorAll('[data-reveal]') : [];
    if (items.length) gsap.set(items, { opacity: 1, y: 0 });
    if (window.ScrollTrigger) ScrollTrigger.refresh();
  });

  if (reduced || !window.gsap) return;
  gsap.registerPlugin(ScrollTrigger);

  /* ---------- smooth scroll (Lenis only) ---------- */
  var lenis = null;
  if (window.Lenis) {
    lenis = new Lenis({ lerp: 0.1 });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
    gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) { var id = a.getAttribute('href'); if (id.length > 1 && document.querySelector(id)) { e.preventDefault(); lenis.scrollTo(id, { offset: -80 }); } });
    });
  }

  /* ---------- split headings (accessible name preserved) ---------- */
  document.querySelectorAll('[data-split]').forEach(function (h) {
    h.setAttribute('aria-label', h.textContent.trim());
    var html = '';
    h.childNodes.forEach(function (n) {
      var em = n.nodeType === 1 && n.tagName === 'EM';
      n.textContent.split(/(\s+)/).forEach(function (w) {
        if (/^\s+$/.test(w)) { html += w; return; }
        if (!w) return;
        html += em ? '<em class="w" aria-hidden="true">' + w + '</em>' : '<span class="w" aria-hidden="true">' + w + '</span>';
      });
    });
    h.innerHTML = html;
  });

  /* claimed — every [data-reveal] element handed to a GSAP timeline by the
     hero-intro pass or the section-reveal pass immediately below. Read by
     the orphan safety net that follows both: see its own comment for why
     this tracking exists rather than the more obvious "read the element's
     current opacity back" — a scroll-triggered `.to()` tween doesn't
     apply its end state at creation time (it's waiting on the trigger),
     so an as-yet-untriggered section item and a genuinely-unclaimed
     orphan are indistinguishable by computed style alone at this point in
     the script; they are not indistinguishable by whether a timeline
     above already took them. */
  var claimed = new Set();

  /* ---------- hero intro ---------- */
  var hero = document.querySelector('.hero, .page-hero');
  if (hero) {
    var tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    var words = hero.querySelectorAll('h1 .w');
    if (words.length) tl.from(words, { yPercent: 60, opacity: 0, duration: 0.9, stagger: 0.05 }, 0);
    var heroReveals = hero.querySelectorAll('[data-reveal]');
    tl.to(heroReveals, { opacity: 1, y: 0, duration: 0.8, stagger: 0.08 }, 0.35);
    heroReveals.forEach(function (el) { claimed.add(el); });
  }

  /* ---------- section reveals ---------- */
  gsap.utils.toArray('section:not(.hero):not(.page-hero), .detail, footer').forEach(function (s) {
    var words = s.querySelectorAll('h2 .w'), items = s.querySelectorAll('[data-reveal]');
    if (!words.length && !items.length) return;
    var t = gsap.timeline({ scrollTrigger: { trigger: s, start: 'top 90%', once: true } });
    if (words.length) t.from(words, { yPercent: 50, opacity: 0, duration: 0.7, stagger: 0.04, ease: 'power3.out' }, 0);
    if (items.length) {
      t.to(items, { opacity: 1, y: 0, duration: 0.7, stagger: 0.1, ease: 'power3.out' }, 0.15);
      items.forEach(function (el) { claimed.add(el); });
    }
  });

  /* ---------- orphan safety net: reveal anything neither pass above claimed ----------
     ROOT CAUSE of "the blog post hero image and share links never appear"
     (confirmed live: `figure.article-hero` and `div.share` in
     templates/blog/post.html sit inside a `<div class="wrap article">`
     that is a SIBLING of `<section class="page-hero">`, not a descendant
     of it, and is itself neither a `section`, `.detail` nor `footer` — so
     neither pass above, each scoped to a fixed, named list of containers,
     ever selects it): [data-reveal]{opacity:0} (static/css/_base.css)
     leaves every element carrying the attribute invisible until SOME
     GSAP timeline tweens it to opacity:1, with no error and no console
     warning when nothing does — indistinguishable from a broken image or
     missing content. The fix in this one template is one line
     (`.wrap.article` added to the container list); the actual defect is
     that the list is exhaustive by construction and every miss looks
     identical and silent. This has now shipped twice (see the
     `htmx:afterSwap` reveal handler above for the first).
     Rather than extend the list again and wait for the next miss, this
     sweeps every [data-reveal] in the document once both passes above
     have finished BUILDING their timelines (not playing them — their
     ScrollTriggers still fire on their own scroll position, per element,
     exactly as before) and gives anything neither pass claimed its own
     scroll-triggered reveal. A future template can put a [data-reveal]
     element anywhere — inside a recognised container, outside all of
     them, doesn't matter — and it will still resolve to visible; nothing
     needs to be told about a new container shape again. */
  document.querySelectorAll('[data-reveal]').forEach(function (el) {
    if (claimed.has(el)) return;
    gsap.to(el, { opacity: 1, y: 0, duration: 0.7, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 95%', once: true } });
  });

  /* ---------- hero media parallax ---------- */
  var hm = document.querySelector('.hero-media img');
  if (hm) gsap.to(hm, { yPercent: 8, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } });

  window.addEventListener('load', function () { ScrollTrigger.refresh(); });
  if (document.fonts) document.fonts.ready.then(function () { ScrollTrigger.refresh(); });
  window.addEventListener('pagehide', function () { if (lenis) lenis.destroy(); ScrollTrigger.getAll().forEach(function (t) { t.kill(); }); });
})();

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
  if (reduced) document.body.classList.add('reduced');

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
     sweep as the blog-filter reveal bug below; same fix. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
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
     leaving the visitor's keyboard position undefined. */
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
     booking-panel/post-list focus handler above. */
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

  /* ---------- hero intro ---------- */
  var hero = document.querySelector('.hero, .page-hero');
  if (hero) {
    var tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    var words = hero.querySelectorAll('h1 .w');
    if (words.length) tl.from(words, { yPercent: 60, opacity: 0, duration: 0.9, stagger: 0.05 }, 0);
    tl.to(hero.querySelectorAll('[data-reveal]'), { opacity: 1, y: 0, duration: 0.8, stagger: 0.08 }, 0.35);
  }

  /* ---------- section reveals ---------- */
  gsap.utils.toArray('section:not(.hero):not(.page-hero), .detail, footer').forEach(function (s) {
    var words = s.querySelectorAll('h2 .w'), items = s.querySelectorAll('[data-reveal]');
    if (!words.length && !items.length) return;
    var t = gsap.timeline({ scrollTrigger: { trigger: s, start: 'top 90%', once: true } });
    if (words.length) t.from(words, { yPercent: 50, opacity: 0, duration: 0.7, stagger: 0.04, ease: 'power3.out' }, 0);
    if (items.length) t.to(items, { opacity: 1, y: 0, duration: 0.7, stagger: 0.1, ease: 'power3.out' }, 0.15);
  });

  /* ---------- hero media parallax ---------- */
  var hm = document.querySelector('.hero-media img');
  if (hm) gsap.to(hm, { yPercent: 8, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } });

  window.addEventListener('load', function () { ScrollTrigger.refresh(); });
  if (document.fonts) document.fonts.ready.then(function () { ScrollTrigger.refresh(); });
  window.addEventListener('pagehide', function () { if (lenis) lenis.destroy(); ScrollTrigger.getAll().forEach(function (t) { t.kill(); }); });
})();

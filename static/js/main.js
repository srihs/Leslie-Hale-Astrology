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

  /* ---------- htmx: focus the result of a form swap ----------
     Every htmx-swapped form (newsletter, contact, booking details) is
     declared with aria-live="polite" in its template, so screen reader
     users hear the swapped result regardless of this. This adds a
     managed focus move on top of that: once the server marks a form
     "sent" (static/css/_components.css .form.sent reveals .ok), move
     focus to the confirmation so sighted keyboard users land there too,
     instead of staying on a button that just disappeared. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    var target = e.detail.target;
    if (target && target.matches && target.matches('form.sent')) {
      var ok = target.querySelector('.ok');
      if (ok) ok.focus();
    }
  });

  /* ---------- htmx: re-run scroll reveals for swapped-in content ----------
     #post-list (blog filter/pagination) is the one htmx target that can
     introduce fresh [data-reveal] cards after the page's initial GSAP pass
     has already run (see "section reveals" below, which only scans once
     on load). Rather than re-triggering a scroll-in animation for content
     the visitor just explicitly asked for, just make it visible —
     consistent with how [data-reveal] already degrades for .no-js/.reduced. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (!window.gsap || reduced) return;
    var items = e.detail.target ? e.detail.target.querySelectorAll('[data-reveal]') : [];
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

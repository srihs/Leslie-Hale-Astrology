/* V1 Ephemeris — motion + interaction. GSAP 3 + ScrollTrigger, Lenis as the sole smooth-scroll engine. */
(function () {
  document.body.classList.remove('no-js');
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) document.body.classList.add('reduced');

  /* ---------- menu ---------- */
  var mb = document.querySelector('.menu-btn'), menu = document.getElementById('menu');
  if (mb && menu) {
    mb.addEventListener('click', function () { var o = menu.classList.toggle('open'); mb.setAttribute('aria-expanded', o); });
    menu.addEventListener('click', function (e) { if (e.target.tagName === 'A') { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); } });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.classList.contains('open')) { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); mb.focus(); } });
  }

  /* ---------- forms (demo validation only) ---------- */
  document.querySelectorAll('form.form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var bad = null;
      form.querySelectorAll('[required]').forEach(function (i) {
        var ok = i.type === 'email' ? /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(i.value) : !!i.value.trim();
        i.setAttribute('aria-invalid', !ok);
        if (!ok && !bad) bad = i;
      });
      form.classList.toggle('invalid', !!bad);
      if (bad) { bad.focus(); return; }
      var btn = form.querySelector('.btn'); if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      setTimeout(function () { form.classList.add('sent'); var ok = form.querySelector('.ok'); ok && ok.focus && ok.setAttribute('tabindex', '-1'); ok && ok.focus(); }, 600);
    });
  });

  /* ---------- booking demo ---------- */
  var book = document.querySelector('[data-booking]');
  if (book) {
    var state = { reading: null, price: 0, day: null, slot: null };
    var out = { r: book.querySelector('[data-sum-reading]'), d: book.querySelector('[data-sum-date]'), t: book.querySelector('[data-sum-time]'), p: book.querySelector('[data-sum-price]'), btn: book.querySelector('[data-sum-btn]') };
    function render() {
      out.r.textContent = state.reading || '—'; out.d.textContent = state.day ? state.day + ' September 2026' : '—'; out.t.textContent = state.slot || '—'; out.p.textContent = state.price ? '$' + state.price : '$0';
      var ready = state.reading && state.day && state.slot; out.btn.disabled = !ready; out.btn.textContent = ready ? 'Continue to payment' : 'Choose a reading, date and time';
    }
    book.querySelectorAll('input[name=reading]').forEach(function (i) { i.addEventListener('change', function () { state.reading = i.dataset.label; state.price = +i.dataset.price; render(); }); });
    book.querySelectorAll('.cal button:not([disabled])').forEach(function (b) { b.addEventListener('click', function () { book.querySelectorAll('.cal button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); }); b.setAttribute('aria-pressed', 'true'); state.day = b.textContent; render(); }); });
    book.querySelectorAll('.slots button').forEach(function (b) { b.addEventListener('click', function () { book.querySelectorAll('.slots button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); }); b.setAttribute('aria-pressed', 'true'); state.slot = b.textContent; render(); }); });
    var pre = book.querySelector('input[name=reading]:checked'); if (pre) { state.reading = pre.dataset.label; state.price = +pre.dataset.price; }
    render();
  }

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

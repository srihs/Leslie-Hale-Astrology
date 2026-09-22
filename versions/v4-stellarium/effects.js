/* V4 Stellarium-style effects: hero slider, parallax washes, circular image reveals. Runs after main.js (GSAP + ScrollTrigger present). */
(function () {
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- Hero slider (3 slides, fade + text) ---- */
  var slider = document.querySelector('[data-slider]');
  if (slider) {
    var slides = slider.querySelectorAll('.slide'), dots = slider.querySelectorAll('.dots button'), i = 0, timer = null;
    function go(n) {
      i = (n + slides.length) % slides.length;
      slides.forEach(function (s, k) { s.classList.toggle('on', k === i); s.setAttribute('aria-hidden', k !== i); });
      dots.forEach(function (d, k) { d.setAttribute('aria-current', k === i ? 'true' : 'false'); });
      if (window.gsap && !reduced) {
        var el = slides[i];
        gsap.fromTo(el.querySelectorAll('.copy > *'), { y: 24, opacity: 0 }, { y: 0, opacity: 1, duration: .8, stagger: .1, ease: 'power3.out', overwrite: true });
        var art = el.querySelector('.art'); if (art) gsap.fromTo(art, { scale: .92, opacity: 0 }, { scale: 1, opacity: 1, duration: 1.2, ease: 'power2.out', overwrite: true });
      }
    }
    function play() { if (reduced) return; stop(); timer = setInterval(function () { go(i + 1); }, 6500); }
    function stop() { if (timer) clearInterval(timer); timer = null; }
    dots.forEach(function (d, k) { d.addEventListener('click', function () { go(k); play(); }); });
    slider.querySelector('[data-prev]').addEventListener('click', function () { go(i - 1); play(); });
    slider.querySelector('[data-next]').addEventListener('click', function () { go(i + 1); play(); });
    slider.addEventListener('mouseenter', stop); slider.addEventListener('mouseleave', play);
    slider.addEventListener('focusin', stop); slider.addEventListener('focusout', play);
    document.addEventListener('visibilitychange', function () { document.hidden ? stop() : play(); });
    go(0); play();
  }

  if (reduced || !window.gsap || !window.ScrollTrigger) return;

  /* ---- Parallax washes ---- */
  document.querySelectorAll('.wash, .paint').forEach(function (w, k) {
    gsap.to(w, { yPercent: (k % 2 ? -18 : 14), xPercent: (k % 2 ? 6 : -6), ease: 'none', scrollTrigger: { trigger: w.parentElement, start: 'top bottom', end: 'bottom top', scrub: true } });
  });

  /* ---- Circular image reveals ---- */
  gsap.utils.toArray('.circles a, .detail-media').forEach(function (f) {
    gsap.fromTo(f, { clipPath: 'circle(0% at 50% 50%)' }, { clipPath: 'circle(75% at 50% 50%)', duration: 1.1, ease: 'power2.out', scrollTrigger: { trigger: f, start: 'top 88%', once: true } });
  });

  /* ---- Zodiac blobs drift in ---- */
  var z = document.querySelectorAll('.z');
  if (z.length) gsap.from(z, { y: 30, opacity: 0, duration: .8, stagger: { each: .05, from: 'random' }, ease: 'power2.out', scrollTrigger: { trigger: '.zodiac', start: 'top 85%', once: true } });

  /* ---- Planet row float ---- */
  document.querySelectorAll('.planets i').forEach(function (p, k) { gsap.to(p, { y: (k % 2 ? -8 : 8), duration: 3 + k * .4, yoyo: true, repeat: -1, ease: 'sine.inOut' }); });
})();

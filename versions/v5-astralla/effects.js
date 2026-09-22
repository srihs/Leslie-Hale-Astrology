/* V5 Astralla-style effects: live starfield with pointer drift, constellation slider, banner carousel, testimonial slider. */
(function () {
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- Starfield (2D canvas, fixed, cheap) ---- */
  var sky = document.querySelector('.starfield');
  if (sky && !reduced) {
    var ctx = sky.getContext('2d'), stars = [], W, H, tx = 0, ty = 0, cx = 0, cy = 0, raf, last = 0;
    var DPR = Math.min(devicePixelRatio || 1, 1.5);
    function size() { W = innerWidth; H = innerHeight; sky.width = W * DPR; sky.height = H * DPR; sky.style.width = W + 'px'; sky.style.height = H + 'px'; ctx.setTransform(DPR, 0, 0, DPR, 0, 0); seed(); }
    function seed() { stars = []; var n = Math.round((W * H) / 6000); for (var i = 0; i < n; i++) stars.push({ x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.2 + .3, p: Math.random() * 6.28, s: .4 + Math.random() * .6, d: Math.random() }); }
    function draw(t) {
      raf = requestAnimationFrame(draw); if (document.hidden) return;
      cx += (tx - cx) * .03; cy += (ty - cy) * .03;
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < stars.length; i++) { var s = stars[i]; var a = .35 + .65 * (0.5 + 0.5 * Math.sin(t / 1000 * s.s + s.p)); var x = s.x + cx * 18 * s.d, y = s.y + cy * 12 * s.d + ((t / 1000) * 2 * s.d) % H; if (y > H) y -= H; ctx.globalAlpha = a; ctx.fillStyle = s.d > .8 ? '#CDBBFF' : '#ffffff'; ctx.beginPath(); ctx.arc(x, y, s.r, 0, 6.28); ctx.fill(); }
      ctx.globalAlpha = 1;
    }
    window.addEventListener('resize', size); size(); raf = requestAnimationFrame(draw);
    window.addEventListener('pointermove', function (e) { var now = performance.now(); if (now - last < 32) return; last = now; tx = e.clientX / W - .5; ty = e.clientY / H - .5; }, { passive: true });
    window.addEventListener('blur', function () { tx = 0; ty = 0; });
    window.addEventListener('pagehide', function () { cancelAnimationFrame(raf); });
  }

  /* ---- Generic slider helper ---- */
  function slider(root, opts) {
    if (!root) return;
    var track = root.querySelector('[data-track]'), items = track.children, per = opts.per(), i = 0, timer = null, n = items.length;
    function step() { return items[0].getBoundingClientRect().width + parseFloat(getComputedStyle(track).gap || 0); }
    function go(k) { per = opts.per(); var max = Math.max(0, n - per); i = ((k % (max + 1)) + (max + 1)) % (max + 1); track.style.transform = 'translateX(' + (-i * step()) + 'px)'; }
    function play() { if (reduced || !opts.auto) return; stop(); timer = setInterval(function () { go(i + 1); }, opts.auto); }
    function stop() { if (timer) clearInterval(timer); timer = null; }
    root.querySelector('[data-prev]').addEventListener('click', function () { go(i - 1); play(); });
    root.querySelector('[data-next]').addEventListener('click', function () { go(i + 1); play(); });
    root.addEventListener('mouseenter', stop); root.addEventListener('mouseleave', play); root.addEventListener('focusin', stop); root.addEventListener('focusout', play);
    window.addEventListener('resize', function () { go(i); });
    document.addEventListener('visibilitychange', function () { document.hidden ? stop() : play(); });
    go(0); play();
  }
  slider(document.querySelector('[data-constellations]'), { per: function () { return innerWidth < 760 ? 2 : 4; }, auto: 5000 });
  slider(document.querySelector('[data-testimonials]'), { per: function () { return innerWidth < 900 ? 1 : 3; }, auto: 7000 });

  /* ---- Banner carousel (fade) ---- */
  var ban = document.querySelector('[data-banners]');
  if (ban) {
    var bs = ban.querySelectorAll('.banner-slide'), bi = 0, bt = null;
    function bgo(k) { bi = (k + bs.length) % bs.length; bs.forEach(function (b, j) { b.classList.toggle('on', j === bi); b.setAttribute('aria-hidden', j !== bi); }); if (window.gsap && !reduced) gsap.fromTo(bs[bi].querySelectorAll('.wrap > *'), { x: -24, opacity: 0 }, { x: 0, opacity: 1, duration: .8, stagger: .08, ease: 'power3.out', overwrite: true }); }
    function bplay() { if (reduced) return; if (bt) clearInterval(bt); bt = setInterval(function () { bgo(bi + 1); }, 6000); }
    ban.querySelector('[data-prev]').addEventListener('click', function () { bgo(bi - 1); bplay(); });
    ban.querySelector('[data-next]').addEventListener('click', function () { bgo(bi + 1); bplay(); });
    document.addEventListener('visibilitychange', function () { if (document.hidden && bt) { clearInterval(bt); bt = null; } else bplay(); });
    bgo(0); bplay();
  }

  if (reduced || !window.gsap || !window.ScrollTrigger) return;
  /* ---- Ring pulse on constellation hover / zodiac grid stagger ---- */
  var zc = document.querySelectorAll('.zc');
  if (zc.length) gsap.from(zc, { opacity: 0, y: 16, duration: .6, stagger: .05, ease: 'power2.out', scrollTrigger: { trigger: '.zgrid', start: 'top 85%', once: true } });
  var sc = document.querySelectorAll('.sc');
  if (sc.length) gsap.from(sc, { opacity: 0, y: 24, duration: .7, stagger: .1, ease: 'power2.out', scrollTrigger: { trigger: '.sgrid', start: 'top 85%', once: true } });
})();

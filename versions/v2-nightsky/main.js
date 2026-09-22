/* V2 Night Sky — shared interactions + GSAP/Lenis + a single-purpose Three.js star-field in the hero.
   Star-field responsibility: depth + pointer parallax behind the headline. Poster fallback stays for no-WebGL / reduced motion. */
(function () {
  document.body.classList.remove('no-js');
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) document.body.classList.add('reduced');

  /* menu */
  var mb = document.querySelector('.menu-btn'), menu = document.getElementById('menu');
  if (mb && menu) {
    mb.addEventListener('click', function () { var o = menu.classList.toggle('open'); mb.setAttribute('aria-expanded', o); });
    menu.addEventListener('click', function (e) { if (e.target.tagName === 'A') { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); } });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.classList.contains('open')) { menu.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); mb.focus(); } });
  }
  var nav = document.querySelector('.nav');
  window.addEventListener('scroll', function () { nav && nav.classList.toggle('scrolled', scrollY > 40); }, { passive: true });

  /* forms (demo validation) */
  document.querySelectorAll('form.form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault(); var bad = null;
      form.querySelectorAll('[required]').forEach(function (i) { var ok = i.type === 'email' ? /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(i.value) : !!i.value.trim(); i.setAttribute('aria-invalid', !ok); if (!ok && !bad) bad = i; });
      form.classList.toggle('invalid', !!bad); if (bad) { bad.focus(); return; }
      var btn = form.querySelector('.btn'); if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      setTimeout(function () { form.classList.add('sent'); var ok = form.querySelector('.ok'); if (ok) { ok.setAttribute('tabindex', '-1'); ok.focus(); } }, 600);
    });
  });

  /* booking demo */
  var book = document.querySelector('[data-booking]');
  if (book) {
    var state = { reading: null, price: 0, day: null, slot: null };
    var out = { r: book.querySelector('[data-sum-reading]'), d: book.querySelector('[data-sum-date]'), t: book.querySelector('[data-sum-time]'), p: book.querySelector('[data-sum-price]'), btn: book.querySelector('[data-sum-btn]') };
    function render() { out.r.textContent = state.reading || '—'; out.d.textContent = state.day ? state.day + ' September 2026' : '—'; out.t.textContent = state.slot || '—'; out.p.textContent = state.price ? '$' + state.price : '$0'; var ready = state.reading && state.day && state.slot; out.btn.disabled = !ready; out.btn.textContent = ready ? 'Continue to payment' : 'Choose a reading, date and time'; }
    book.querySelectorAll('input[name=reading]').forEach(function (i) { i.addEventListener('change', function () { state.reading = i.dataset.label; state.price = +i.dataset.price; render(); }); });
    book.querySelectorAll('.cal button:not([disabled])').forEach(function (b) { b.addEventListener('click', function () { book.querySelectorAll('.cal button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); }); b.setAttribute('aria-pressed', 'true'); state.day = b.textContent; render(); }); });
    book.querySelectorAll('.slots button').forEach(function (b) { b.addEventListener('click', function () { book.querySelectorAll('.slots button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); }); b.setAttribute('aria-pressed', 'true'); state.slot = b.textContent; render(); }); });
    var pre = book.querySelector('input[name=reading]:checked'); if (pre) { state.reading = pre.dataset.label; state.price = +pre.dataset.price; }
    render();
  }

  /* ---------- Three.js star-field (hero only) ---------- */
  var sky = document.querySelector('.sky');
  var cleanupStars = null;
  if (sky && !reduced && window.THREE) {
    try {
      var canvas = document.createElement('canvas'); canvas.setAttribute('aria-hidden', 'true');
      var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: false, powerPreference: 'low-power' });
      renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
      var scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100); camera.position.z = 6;
      var N = innerWidth < 700 ? 500 : 1100, pos = new Float32Array(N * 3), sz = new Float32Array(N);
      for (var i = 0; i < N; i++) { pos[i * 3] = (Math.random() - .5) * 24; pos[i * 3 + 1] = (Math.random() - .5) * 14; pos[i * 3 + 2] = (Math.random() - .5) * 10; sz[i] = Math.random(); }
      var geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
      var mat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, uniforms: { uTime: { value: 0 }, uPR: { value: renderer.getPixelRatio() } },
        vertexShader: 'attribute float aSize;uniform float uTime;uniform float uPR;varying float vA;void main(){vec4 mv=modelViewMatrix*vec4(position,1.);float tw=.6+.4*sin(uTime*(.6+aSize*1.2)+aSize*40.);vA=tw*(.35+.65*aSize);gl_PointSize=(1.2+aSize*2.2)*uPR*(6./-mv.z);gl_Position=projectionMatrix*mv;}',
        fragmentShader: 'varying float vA;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float a=smoothstep(.5,.1,d)*vA;gl_FragColor=vec4(vec3(.95,.92,.85),a);}' });
      var pts = new THREE.Points(geo, mat); scene.add(pts);
      sky.insertBefore(canvas, sky.firstChild);
      var poster = sky.querySelector('.poster'); poster && poster.classList.add('off');
      var tx = 0, ty = 0, cx = 0, cy = 0, raf = null, visible = true, last = 0;
      function size() { var w = sky.clientWidth, h = sky.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
      size();
      function onMove(e) { var now = performance.now(); if (now - last < 32) return; last = now; var r = sky.getBoundingClientRect(); tx = ((e.clientX - r.left) / r.width - .5); ty = ((e.clientY - r.top) / r.height - .5); }
      function reset() { tx = 0; ty = 0; }
      var t0 = performance.now();
      function loop(now) { raf = requestAnimationFrame(loop); if (!visible || document.hidden) return; cx += (tx - cx) * .04; cy += (ty - cy) * .04; pts.rotation.y = cx * .25; pts.rotation.x = cy * .15; pts.position.x = -cx * .6; pts.position.y = cy * .4; mat.uniforms.uTime.value = (now - t0) / 1000; renderer.render(scene, camera); }
      raf = requestAnimationFrame(loop);
      var io = new IntersectionObserver(function (en) { visible = en[0].isIntersecting; }); io.observe(sky);
      sky.addEventListener('pointermove', onMove); sky.addEventListener('pointerleave', reset); window.addEventListener('blur', reset); window.addEventListener('resize', size);
      canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); cleanupStars && cleanupStars(); poster && poster.classList.remove('off'); });
      cleanupStars = function () { cancelAnimationFrame(raf); io.disconnect(); sky.removeEventListener('pointermove', onMove); sky.removeEventListener('pointerleave', reset); window.removeEventListener('blur', reset); window.removeEventListener('resize', size); geo.dispose(); mat.dispose(); renderer.dispose(); canvas.remove(); cleanupStars = null; };
    } catch (err) { /* poster fallback remains visible */ }
  }

  if (reduced || !window.gsap) return;
  gsap.registerPlugin(ScrollTrigger);

  /* Lenis — sole smooth-scroll engine */
  var lenis = null;
  if (window.Lenis) {
    lenis = new Lenis({ lerp: 0.09 }); lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add(function (t) { lenis.raf(t * 1000); }); gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach(function (a) { a.addEventListener('click', function (e) { var id = a.getAttribute('href'); if (id.length > 1 && document.querySelector(id)) { e.preventDefault(); lenis.scrollTo(id, { offset: -80 }); } }); });
  }

  /* split headings */
  document.querySelectorAll('[data-split]').forEach(function (h) {
    h.setAttribute('aria-label', h.textContent.trim()); var html = '';
    h.childNodes.forEach(function (n) { var em = n.nodeType === 1 && n.tagName === 'EM'; n.textContent.split(/(\s+)/).forEach(function (w) { if (/^\s+$/.test(w)) { html += w; return; } if (!w) return; html += em ? '<em class="w" aria-hidden="true">' + w + '</em>' : '<span class="w" aria-hidden="true">' + w + '</span>'; }); });
    h.innerHTML = html;
  });

  /* hero intro: moon rises, words lift, then supporting content */
  var hero = document.querySelector('.sky, .page-hero');
  if (hero) {
    var tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    var moon = hero.querySelector('.moon'); if (moon) tl.from(moon, { yPercent: 18, opacity: 0, duration: 1.6, ease: 'power2.out' }, 0);
    var words = hero.querySelectorAll('h1 .w'); if (words.length) tl.from(words, { yPercent: 70, opacity: 0, duration: 1, stagger: 0.06 }, 0.2);
    tl.to(hero.querySelectorAll('[data-reveal]'), { opacity: 1, y: 0, duration: 0.8, stagger: 0.1 }, 0.6);
    if (moon) gsap.to(moon, { yPercent: -25, ease: 'none', scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom top', scrub: true } });
  }

  gsap.utils.toArray('section:not(.sky):not(.page-hero), .detail, footer').forEach(function (s) {
    var words = s.querySelectorAll('h2 .w'), items = s.querySelectorAll('[data-reveal]'); if (!words.length && !items.length) return;
    var t = gsap.timeline({ scrollTrigger: { trigger: s, start: 'top 90%', once: true } });
    if (words.length) t.from(words, { yPercent: 50, opacity: 0, duration: 0.7, stagger: 0.04, ease: 'power3.out' }, 0);
    if (items.length) t.to(items, { opacity: 1, y: 0, duration: 0.7, stagger: 0.1, ease: 'power3.out' }, 0.15);
  });

  window.addEventListener('load', function () { ScrollTrigger.refresh(); });
  if (document.fonts) document.fonts.ready.then(function () { ScrollTrigger.refresh(); });
  window.addEventListener('pagehide', function () { if (lenis) lenis.destroy(); ScrollTrigger.getAll().forEach(function (t) { t.kill(); }); cleanupStars && cleanupStars(); });
})();

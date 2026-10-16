/* Terralyt · bg.js — living "mitti & darakht" background
   Drop-in replacement for assets/bg.js (self-starting, no setup needed).
   Layers: sky glow + sun rays, 3 parallax hills (far/mid/soil), swaying trees,
   drifting mist, fireflies, falling leaves, moving grass. */
(function () {
  'use strict';

  /* ---- easy knobs ---- */
  var CFG = {
    wind: 1,        // 0 = calm, 1 = natural, 2 = stormy
    leaves: 26,     // falling leaves
    fireflies: 36,  // warm glowing pollen / fireflies (whole screen)
    birds: 7,       // birds crossing the sky
    respectReducedMotion: false, // true = static if the OS has animations turned off
    rays: true,     // sunlight shafts from top-right
    grass: true     // swaying grass on the front soil
  };

  var reduce = CFG.respectReducedMotion && window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MAXD = 6;

  function rng(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  var LDEF = [
    { base: .74, amp: .030, f: [1.3, 3.1], par: .020, fill: ['#15341f', '#0f2417'], trees: .9, scale: .55, alpha: .55, trunk: '#1a2c1c', leaf: ['#1f4a2c', '#2a6038'] },
    { base: .82, amp: .035, f: [1.0, 2.6], par: .035, fill: ['#12281a', '#0c1a11'], trees: .7, scale: .85, alpha: .82, trunk: '#2a2216', leaf: ['#245432', '#2f6b3d', '#4a7a3a'] },
    { base: .915, amp: .025, f: [.8, 2.2], par: .050, fill: ['#3a2716', '#170f08'], trees: .35, scale: 1.25, alpha: 1, trunk: '#24180e', leaf: ['#1d4a2a', '#28603a'], soil: true }
  ];

  var LEAF_COL = ['#c8a13a', '#8cbf5a', '#d9b44a', '#6fae5e', '#b5651d'];

  function init() {
    var cv = document.createElement('canvas');
    cv.id = 'terra-bg';
    cv.setAttribute('aria-hidden', 'true');
    cv.style.cssText = 'position:fixed;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block';
    document.body.insertBefore(cv, document.body.firstChild);
    var ctx = cv.getContext('2d');

    var W = 0, H = 0, dpr = 1, prog = 0, progT = 0;
    var baseGrad, sunGlow, leaves = [], flies = [], birds = [], specks = [], blades = [];

    function sprite(w, h, stops) {
      var c = document.createElement('canvas'); c.width = w; c.height = h;
      var g = c.getContext('2d'), gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) / 2);
      stops.forEach(function (s) { gr.addColorStop(s[0], s[1]); });
      g.save(); g.translate(w / 2, h / 2); g.scale(1, h / w); g.translate(-w / 2, -w / 2);
      g.fillStyle = gr; g.fillRect(0, 0, w, w); g.restore();
      return c;
    }
    var glow = sprite(64, 64, [[0, 'rgba(255,224,140,1)'], [.25, 'rgba(255,200,100,.45)'], [1, 'rgba(255,190,80,0)']]);
    var mist = sprite(256, 128, [[0, 'rgba(190,225,190,.55)'], [1, 'rgba(190,225,190,0)']]);

    function hy(L, x) {
      return H * L.base + L.off +
        Math.sin(x / W * Math.PI * L.f[0] * 2 + L.ph) * H * L.amp +
        Math.sin(x / W * Math.PI * L.f[1] * 2 + L.ph * 1.7) * H * L.amp * .5;
    }

    function build() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = window.innerWidth; H = window.innerHeight;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      baseGrad = ctx.createLinearGradient(0, 0, 0, H);
      baseGrad.addColorStop(0, '#08150c');
      baseGrad.addColorStop(.55, '#0e2316');
      baseGrad.addColorStop(1, '#1a2a16');
      sunGlow = ctx.createRadialGradient(W * .85, H * .05, 0, W * .85, H * .05, Math.max(W, H) * .7);
      sunGlow.addColorStop(0, 'rgba(255,220,140,.10)');
      sunGlow.addColorStop(1, 'rgba(255,220,140,0)');

      LDEF.forEach(function (L, i) {
        var r = rng(100 + i * 31);
        L.ph = i * 2.1 + .7; L.off = 0; L.list = [];
        var n = Math.max(1, Math.round(W / 1000 * L.trees * 5));
        for (var k = 0; k < n; k++) {
          L.list.push({ x: (k + .3 + r() * .4) / n * W, seed: r() * 10, s: L.scale * (.8 + r() * .5) });
        }
      });

      var r2 = rng(7);
      specks = []; var ns = Math.min(170, Math.round(W / 8));
      for (var i = 0; i < ns; i++) specks.push({ x: r2() * W, dy: 10 + r2() * H * .1, s: .8 + r2() * 1.8, c: r2() < .5 ? 'rgba(150,105,60,.35)' : 'rgba(90,60,35,.5)' });

      blades = []; var step = 13;
      for (var x = 0; x < W + step; x += step) blades.push({ x: x + Math.sin(x * 12.9) * 4, h: 6 + 10 * Math.abs(Math.sin(x * 4.37)), p: x * .03 });

      if (!leaves.length) {
        var r3 = rng(21);
        for (var j = 0; j < CFG.leaves; j++) leaves.push({
          x: r3() * W, y: r3() * H, s: 5 + r3() * 6, vy: 24 + r3() * 26,
          ph: r3() * 6.28, rot: r3() * 6.28, vr: (.4 + r3() * .9) * (r3() < .5 ? -1 : 1),
          c: LEAF_COL[Math.floor(r3() * LEAF_COL.length)], a: .5 + r3() * .3
        });
        var r4 = rng(55);
        for (var q = 0; q < CFG.fireflies; q++) flies.push({
          x: r4(), y: .12 + r4() * .8, ax: 30 + r4() * 70, ay: 20 + r4() * 50,
          fx: .2 + r4() * .35, fy: .2 + r4() * .35, ph: r4() * 6.28, s: 6 + r4() * 8
        });
      }
    }

    function branch(x, y, len, a, d, seed, t, L, idx, w) {
      var sway = Math.sin(t * .9 * CFG.wind + seed + d * .55) * .024 * (d + 1) * CFG.wind +
                 Math.sin(t * .37 + seed * 2) * .007 * (d + 1) * CFG.wind;
      a += sway;
      var x2 = x + Math.cos(a) * len, y2 = y + Math.sin(a) * len;
      ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
      if (d >= MAXD) {
        ctx.fillStyle = L.leaf[idx % L.leaf.length];
        ctx.beginPath(); ctx.arc(x2, y2, len * 1.3, 0, 6.283); ctx.fill();
        return;
      }
      var sp = .38 + .14 * Math.sin(seed + d * 1.7 + idx * 2.3);
      var nl = len * (.72 + .05 * Math.sin(seed * 3 + idx));
      branch(x2, y2, nl, a - sp, d + 1, seed, t, L, idx * 2, w * .68);
      branch(x2, y2, nl, a + sp * (.8 + .3 * Math.sin(seed + idx)), d + 1, seed, t, L, idx * 2 + 1, w * .68);
    }

    function drawRays(t) {
      ctx.globalCompositeOperation = 'lighter';
      var ox = W * .85, oy = -H * .1, len = H * 1.5;
      for (var i = 0; i < 5; i++) {
        var th = Math.PI / 2 + .3 + i * .12 + Math.sin(t * .15 + i) * .035;
        var w = .028 + .012 * Math.sin(t * .2 + i * 2);
        var ex = Math.cos(th) * len, ey = Math.sin(th) * len;
        var g = ctx.createLinearGradient(ox, oy, ox + ex, oy + ey);
        g.addColorStop(0, 'rgba(255,235,170,.9)'); g.addColorStop(1, 'rgba(255,235,170,0)');
        ctx.globalAlpha = .075 * (.6 + .4 * Math.sin(t * .3 + i * 1.7));
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.moveTo(ox, oy);
        ctx.lineTo(ox + Math.cos(th - w) * len, oy + Math.sin(th - w) * len);
        ctx.lineTo(ox + Math.cos(th + w) * len, oy + Math.sin(th + w) * len);
        ctx.closePath(); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }

    function drawMist(t, k) {
      ctx.globalAlpha = .24;
      for (var i = 0; i < 2; i++) {
        var span = W * 1.6, x = ((t * (18 + k * 8 + i * 6) + i * span * .5 + k * 300) % span) - W * .3;
        ctx.drawImage(mist, x, H * (.68 + k * .07 + i * .04), W * .7, H * .2);
      }
      ctx.globalAlpha = 1;
    }

    function drawLayer(L, t) {
      var g = ctx.createLinearGradient(0, H * (L.base - .05), 0, H);
      g.addColorStop(0, L.fill[0]); g.addColorStop(1, L.fill[1]);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.moveTo(0, H + 140);
      for (var x = 0; x <= W + 24; x += 24) ctx.lineTo(x, hy(L, x));
      ctx.lineTo(W + 24, H + 140); ctx.closePath(); ctx.fill();

      // soft grass-green rim light on the hill edge
      ctx.strokeStyle = L.soil ? 'rgba(110,170,80,.35)' : 'rgba(110,170,80,.14)';
      ctx.lineWidth = 1.5; ctx.beginPath();
      for (var x2 = 0; x2 <= W + 24; x2 += 24) { var yy = hy(L, x2); x2 ? ctx.lineTo(x2, yy) : ctx.moveTo(x2, yy); }
      ctx.stroke();

      // trees
      ctx.lineCap = 'round'; ctx.strokeStyle = L.trunk; ctx.globalAlpha = L.alpha;
      L.list.forEach(function (tr) {
        var len = H * .085 * tr.s;
        branch(tr.x, hy(L, tr.x) + 4, len, -Math.PI / 2, 0, tr.seed, t, L, 0, Math.max(1.4, len * .14));
      });
      ctx.globalAlpha = 1;

      if (L.soil) {
        // soil strata lines
        ctx.lineWidth = 1.3;
        for (var s = 1; s <= 3; s++) {
          ctx.strokeStyle = 'rgba(170,120,65,' + (.16 - s * .03) + ')';
          ctx.beginPath();
          for (var x3 = 0; x3 <= W + 24; x3 += 24) {
            var y3 = hy(L, x3) + s * H * .03 + Math.sin(x3 * .012 + s * 2) * 4;
            x3 ? ctx.lineTo(x3, y3) : ctx.moveTo(x3, y3);
          }
          ctx.stroke();
        }
        // soil specks
        specks.forEach(function (p) { ctx.fillStyle = p.c; ctx.fillRect(p.x, hy(L, p.x) + p.dy, p.s, p.s); });
        // swaying grass
        if (CFG.grass) {
          ctx.strokeStyle = 'rgba(80,150,80,.7)'; ctx.lineWidth = 1.4; ctx.beginPath();
          blades.forEach(function (b) {
            var y = hy(L, b.x) + 2, sw = Math.sin(t * 1.3 * CFG.wind + b.p) * 4 * CFG.wind;
            ctx.moveTo(b.x, y); ctx.quadraticCurveTo(b.x + sw * .5, y - b.h * .6, b.x + sw, y - b.h);
          });
          ctx.stroke();
        }
      }
    }

    function drawBirds(t, dt) {
      if (!birds.length) {
        for (var i = 0; i < CFG.birds; i++) birds.push({
          x: -Math.random() * W * 1.6, y: H * (.08 + Math.random() * .28),
          v: 50 + Math.random() * 35, s: 6 + Math.random() * 4, ph: Math.random() * 6.28
        });
      }
      ctx.strokeStyle = 'rgba(227,207,165,.55)'; ctx.lineWidth = 1.6; ctx.lineCap = 'round';
      birds.forEach(function (b) {
        b.x += b.v * dt;
        if (b.x > W + 40) { b.x = -60 - Math.random() * W * .8; b.y = H * (.08 + Math.random() * .28); }
        var y = b.y + Math.sin(t * .7 + b.ph) * 10, fl = Math.sin(t * 6 + b.ph) * b.s * .8, s = b.s;
        ctx.beginPath();
        ctx.moveTo(b.x - s * 1.5, y - fl);
        ctx.quadraticCurveTo(b.x - s * .6, y - s * .5, b.x, y);
        ctx.quadraticCurveTo(b.x + s * .6, y - s * .5, b.x + s * 1.5, y - fl);
        ctx.stroke();
      });
    }

    function drawFlies(t) {
      ctx.globalCompositeOperation = 'lighter';
      flies.forEach(function (f) {
        var x = f.x * W + Math.sin(t * f.fx + f.ph) * f.ax;
        var y = f.y * H + Math.cos(t * f.fy + f.ph * 1.3) * f.ay;
        var p = .5 + .5 * Math.sin(t * 1.6 + f.ph * 3);
        ctx.globalAlpha = .12 + .7 * p * p;
        var sz = f.s * 2.4;
        ctx.drawImage(glow, x - sz / 2, y - sz / 2, sz, sz);
      });
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }

    function drawLeaves(t, dt) {
      leaves.forEach(function (l) {
        l.y += l.vy * dt;
        l.x += (Math.sin(t * 1.0 + l.ph) * 34 + 16 * CFG.wind) * dt;
        l.rot += l.vr * dt;
        if (l.y > H + 20) { l.y = -20; l.x = Math.random() * W; }
        if (l.x > W + 30) l.x = -30;
        var edge = Math.min(1, l.y / 80, (H - l.y) / 80 + .3);
        ctx.save();
        ctx.translate(l.x, l.y); ctx.rotate(l.rot);
        ctx.scale(.35 + .65 * Math.abs(Math.cos(t * 1.2 + l.ph)), 1);
        ctx.globalAlpha = l.a * Math.max(0, edge);
        ctx.fillStyle = l.c;
        var s = l.s;
        ctx.beginPath(); ctx.moveTo(0, -s); ctx.quadraticCurveTo(s * .8, 0, 0, s); ctx.quadraticCurveTo(-s * .8, 0, 0, -s); ctx.fill();
        ctx.strokeStyle = 'rgba(40,25,10,.35)'; ctx.lineWidth = .8;
        ctx.beginPath(); ctx.moveTo(0, -s); ctx.lineTo(0, s); ctx.stroke();
        ctx.restore();
      });
      ctx.globalAlpha = 1;
    }

    function frame(t, dt) {
      prog += (progT - prog) * .06;
      LDEF.forEach(function (L) { L.off = (prog - .5) * L.par * H * 3; });

      ctx.fillStyle = baseGrad; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = sunGlow; ctx.fillRect(0, 0, W, H);
      if (CFG.rays) drawRays(t);
      drawBirds(t, dt);
      drawLayer(LDEF[0], t); drawMist(t, 0);
      drawLayer(LDEF[1], t); drawMist(t, 1);
      drawFlies(t);
      drawLayer(LDEF[2], t);
      drawLeaves(t, dt);
    }

    function onScroll() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      progT = Math.min(1, Math.max(0, window.scrollY / max));
    }

    build(); onScroll();
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { build(); if (reduce) frame(0, 0); }, 120);
    });
    window.addEventListener('scroll', onScroll, { passive: true });

    if (reduce) { frame(0, 0); return; }

    var last = performance.now(), T = 0;
    (function loop(now) {
      var dt = Math.min(.05, (now - last) / 1000);
      if (W < 700 && dt < 1 / 40) { requestAnimationFrame(loop); return; }
      last = now; T += dt;
      frame(T, dt);
      requestAnimationFrame(loop);
    })(last);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
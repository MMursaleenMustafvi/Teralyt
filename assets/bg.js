/* Terralyt · bg.js — "mitti & darakht" living background (lightweight)
   Everything heavy is pre-rendered once; each frame only moves sprites.
   Drop-in replacement for assets/bg.js — self-starting.                  */
(function () {
  'use strict';

  var CFG = {
    wind: 1,        // 0 calm · 1 natural · 2 stormy
    leaves: 14,     // falling leaves
    fireflies: 24,  // glowing motes / fireflies
    birds: 5,       // birds crossing the sky
    rays: true,     // sunlight shafts
    grass: true,    // swaying grass
    respectReducedMotion: false
  };

  var reduce = CFG.respectReducedMotion && window.matchMedia &&
    matchMedia('(prefers-reduced-motion: reduce)').matches;

  function rng(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function mk(w, h) { var c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; }
  function gust(t) { return .75 + .25 * Math.sin(t * .31) + .15 * Math.sin(t * .83 + 1.3); }

  var LDEF = [
    { base: .74, amp: .030, f: [1.3, 3.1], par: .020, fill: ['#17382a', '#10261c'], trees: .9, scale: .55, alpha: .6,
      trunk: '#16281d', kinds: [1, 1, 0], leafD: ['#173b27', '#1b4430'], leafL: ['#2a5c3c', '#2f6644'], sway: .05 },
    { base: .82, amp: .035, f: [1.0, 2.6], par: .035, fill: ['#14301f', '#0c1c13'], trees: .7, scale: .85, alpha: .85,
      trunk: '#241d13', kinds: [0, 1, 0], leafD: ['#1a4a2b', '#215733', '#2a5a2a'], leafL: ['#2c6038', '#35704a', '#55782f'], sway: .05 },
    { base: .915, amp: .025, f: [.8, 2.2], par: .050, fill: ['#3d2917', '#160e07'], trees: .3, scale: 1.0, alpha: .95,
      trunk: '#22170d', kinds: [0, 0, 0], leafD: ['#143a22', '#1a4529', '#27481f'], leafL: ['#2f6a3a', '#387444', '#587a2e'], sway: .05, soil: true }
  ];
  var LEAF_COL = ['#c8a13a', '#8cbf5a', '#d9b44a', '#6fae5e', '#b5651d'];
  var FLOWER_COL = ['#f2d479', '#f4b6c2', '#c9b3e6', '#e0a93a'];

  function init() {
    var cv = document.createElement('canvas');
    cv.id = 'terra-bg';
    cv.setAttribute('aria-hidden', 'true');
    cv.style.cssText = 'position:fixed;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block';
    document.body.insertBefore(cv, document.body.firstChild);
    var ctx = cv.getContext('2d', { alpha: false });

    var W = 0, H = 0, dpr = 1, dprMax = 1.25, prog = 0, progT = 0;
    var bg, beam, glow, mist, leafSpr = [];
    var leaves = [], flies = [], birds = [], blades = [];

    /* ---------- sprites ---------- */
    function radial(w, h, stops) {
      var c = mk(w, h), g = c.getContext('2d'), gr = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
      stops.forEach(function (s) { gr.addColorStop(s[0], s[1]); });
      g.save(); g.scale(1, h / w); g.fillStyle = gr; g.fillRect(0, 0, w, w); g.restore();
      return c;
    }
    function makeStatic() {
      glow = radial(64, 64, [[0, 'rgba(255,226,150,1)'], [.3, 'rgba(255,200,100,.4)'], [1, 'rgba(255,190,80,0)']]);
      mist = radial(256, 96, [[0, 'rgba(185,220,185,.5)'], [.6, 'rgba(185,220,185,.18)'], [1, 'rgba(185,220,185,0)']]);
      beam = mk(128, 512);
      var g = beam.getContext('2d');
      if ('filter' in g) g.filter = 'blur(7px)';
      var gr = g.createLinearGradient(0, 0, 0, 512);
      gr.addColorStop(0, 'rgba(255,236,170,.95)'); gr.addColorStop(.55, 'rgba(255,236,170,.28)'); gr.addColorStop(1, 'rgba(255,236,170,0)');
      g.fillStyle = gr; g.beginPath(); g.moveTo(58, 8); g.lineTo(70, 8); g.lineTo(108, 500); g.lineTo(20, 500); g.closePath(); g.fill();
      LEAF_COL.forEach(function (col) {
        var c = mk(32, 32), q = c.getContext('2d');
        q.translate(16, 16);
        q.fillStyle = col; q.beginPath(); q.moveTo(0, -14); q.quadraticCurveTo(11, 0, 0, 14); q.quadraticCurveTo(-11, 0, 0, -14); q.fill();
        q.fillStyle = 'rgba(255,255,255,.14)'; q.beginPath(); q.moveTo(0, -14); q.quadraticCurveTo(11, 0, 0, 14); q.closePath(); q.fill();
        q.strokeStyle = 'rgba(40,25,10,.4)'; q.lineWidth = 1; q.beginPath(); q.moveTo(0, -14); q.lineTo(0, 14); q.stroke();
        leafSpr.push(c);
      });
    }

    function bakeBG() {
      var c = mk(W * dpr, H * dpr), g = c.getContext('2d');
      g.scale(dpr, dpr);
      var gr = g.createLinearGradient(0, 0, 0, H);
      gr.addColorStop(0, '#06120a'); gr.addColorStop(.45, '#0d2417'); gr.addColorStop(.78, '#17321b'); gr.addColorStop(1, '#202f17');
      g.fillStyle = gr; g.fillRect(0, 0, W, H);
      var R = Math.max(W, H);
      var s = g.createRadialGradient(W * .85, H * .04, 0, W * .85, H * .04, R * .75);
      s.addColorStop(0, 'rgba(255,222,150,.14)'); s.addColorStop(1, 'rgba(255,222,150,0)');
      g.fillStyle = s; g.fillRect(0, 0, W, H);
      var h = g.createRadialGradient(W * .5, H * .8, 0, W * .5, H * .8, W * .7);
      h.addColorStop(0, 'rgba(215,170,90,.11)'); h.addColorStop(1, 'rgba(215,170,90,0)');
      g.fillStyle = h; g.fillRect(0, 0, W, H);
      var v = g.createRadialGradient(W / 2, H / 2, R * .3, W / 2, H / 2, R * .85);
      v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.38)');
      g.fillStyle = v; g.fillRect(0, 0, W, H);
      return c;
    }

    function baseY(L, x) {
      return H * L.base +
        Math.sin(x / W * Math.PI * L.f[0] * 2 + L.ph) * H * L.amp +
        Math.sin(x / W * Math.PI * L.f[1] * 2 + L.ph * 1.7) * H * L.amp * .5;
    }
    function hy(L, x) { return baseY(L, x) + L.off; }

    function bakeHill(L, r) {
      var top = Math.floor(H * (L.base - L.amp * 1.7) - 30), hh = Math.ceil(H - top + 170);
      var c = mk(W * dpr, hh * dpr), g = c.getContext('2d'), x;
      g.scale(dpr, dpr);
      var e = function (x) { return baseY(L, x) - top; };
      var gr = g.createLinearGradient(0, e(W / 2) - H * .05, 0, hh);
      gr.addColorStop(0, L.fill[0]); gr.addColorStop(1, L.fill[1]);
      g.fillStyle = gr; g.beginPath(); g.moveTo(0, hh);
      for (x = 0; x <= W + 16; x += 16) g.lineTo(x, e(x));
      g.lineTo(W + 16, hh); g.closePath(); g.fill();
      g.strokeStyle = L.soil ? 'rgba(125,180,90,.4)' : 'rgba(125,180,90,.15)'; g.lineWidth = L.soil ? 2 : 1.4;
      g.beginPath(); for (x = 0; x <= W + 16; x += 16) { x ? g.lineTo(x, e(x)) : g.moveTo(x, e(x)); } g.stroke();

      if (L.soil) {
        var i, n, y;
        g.lineWidth = 1.3;
        for (i = 1; i <= 3; i++) {
          g.strokeStyle = 'rgba(175,125,70,' + (.17 - i * .03) + ')'; g.beginPath();
          for (x = 0; x <= W + 16; x += 16) { y = e(x) + i * H * .03 + Math.sin(x * .012 + i * 2) * 4; x ? g.lineTo(x, y) : g.moveTo(x, y); }
          g.stroke();
        }
        n = Math.min(220, Math.round(W / 6));
        for (i = 0; i < n; i++) {
          x = r() * W; y = e(x) + 10 + r() * H * .1;
          g.fillStyle = r() < .5 ? 'rgba(155,110,62,.35)' : 'rgba(80,52,30,.5)';
          g.fillRect(x, y, .8 + r() * 1.8, .8 + r() * 1.8);
        }
        n = Math.round(W / 110);
        for (i = 0; i < n; i++) {
          x = r() * W; y = e(x) + 14 + r() * 50;
          g.fillStyle = 'rgba(120,98,76,.45)'; g.beginPath(); g.ellipse(x, y, 3 + r() * 4, 2 + r() * 2.5, 0, 0, 6.283); g.fill();
        }
        var cols = ['rgba(38,92,48,.95)', 'rgba(60,128,66,.9)'];
        for (var k = 0; k < 2; k++) {
          g.strokeStyle = cols[k]; g.lineWidth = 1.3; g.beginPath();
          for (x = k * 2.5; x < W + 6; x += 5) {
            var hgt = 4 + r() * 10, yy = e(x) + 2;
            g.moveTo(x, yy); g.quadraticCurveTo(x + (r() - .5) * 4, yy - hgt * .6, x + (r() - .5) * 6, yy - hgt);
          }
          g.stroke();
        }
        n = Math.round(W / 48);
        for (i = 0; i < n; i++) {
          x = r() * W; y = e(x); var sh = 8 + r() * 10;
          g.strokeStyle = '#3a7a44'; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y + 1); g.lineTo(x + 1, y - sh); g.stroke();
          g.fillStyle = FLOWER_COL[Math.floor(r() * FLOWER_COL.length)]; g.globalAlpha = .9;
          g.beginPath(); g.arc(x + 1, y - sh, 2.2, 0, 6.283); g.fill(); g.globalAlpha = 1;
        }
      }
      L.hs = c; L.top = top; L.hh = hh;
    }

    /* ---------- trees (baked) ---------- */
    function treeSprite(L, len, seed, kind) {
      var w = Math.ceil(len * 5.2), h = Math.ceil(len * 4.6);
      var c = mk(w * dpr, h * dpr), g = c.getContext('2d');
      g.scale(dpr, dpr);
      var ox = w / 2, oy = h - 3;
      g.lineCap = 'round'; g.strokeStyle = L.trunk; g.fillStyle = L.trunk;
      if (kind === 1) conifer(g, ox, oy, len, L);
      else {
        var blobs = [];
        branch(g, ox, oy, len, -Math.PI / 2, 0, seed, 0, Math.max(1.8, len * .16), blobs);
        blobs.forEach(function (b) {
          var i = b[3] % L.leafD.length;
          g.fillStyle = L.leafD[i]; g.beginPath(); g.arc(b[0], b[1], b[2], 0, 6.283); g.fill();
        });
        blobs.forEach(function (b) {
          var i = b[3] % L.leafL.length;
          g.globalAlpha = .6; g.fillStyle = L.leafL[i];
          g.beginPath(); g.arc(b[0] + b[2] * .25, b[1] - b[2] * .3, b[2] * .6, 0, 6.283); g.fill();
        });
        g.globalAlpha = 1;
      }
      return { c: c, w: w, h: h, ox: ox, oy: oy };
    }
    function branch(g, x, y, len, a, d, seed, idx, w, blobs) {
      var x2 = x + Math.cos(a) * len, y2 = y + Math.sin(a) * len;
      g.lineWidth = w; g.beginPath(); g.moveTo(x, y); g.lineTo(x2, y2); g.stroke();
      if (d >= 5) blobs.push([x2, y2, len * 1.7, idx]);
      if (d >= 7) return;
      var sp = .30 + .12 * Math.sin(seed + d * 1.7 + idx * 2.3);
      var nl = len * (.72 + .05 * Math.sin(seed * 3 + idx));
      branch(g, x2, y2, nl, a - sp, d + 1, seed, idx * 2, w * .68, blobs);
      branch(g, x2, y2, nl, a + sp * (.8 + .3 * Math.sin(seed + idx)), d + 1, seed, idx * 2 + 1, w * .68, blobs);
    }
    function conifer(g, ox, oy, len, L) {
      var trunkH = len * .5;
      g.fillRect(ox - len * .05, oy - trunkH, len * .1, trunkH);
      for (var k = 0; k < 6; k++) {
        var by = oy - trunkH * .6 - k * len * .5, half = len * (1.05 - k * .15);
        g.fillStyle = L.leafD[0]; g.beginPath(); g.moveTo(ox - half, by);
        g.quadraticCurveTo(ox - half * .25, by - len * .35, ox, by - len * .85);
        g.quadraticCurveTo(ox + half * .25, by - len * .35, ox + half, by);
        g.quadraticCurveTo(ox, by + len * .08, ox - half, by); g.fill();
        g.globalAlpha = .4; g.fillStyle = L.leafL[0]; g.beginPath(); g.moveTo(ox, by - len * .85);
        g.quadraticCurveTo(ox + half * .25, by - len * .35, ox + half, by); g.lineTo(ox, by); g.closePath(); g.fill();
        g.globalAlpha = 1;
      }
    }

    /* ---------- build (on load / resize) ---------- */
    function build() {
      dpr = Math.min(window.devicePixelRatio || 1, W0() < 700 ? 1 : dprMax);
      W = window.innerWidth; H = window.innerHeight;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bg = bakeBG();

      var sizes = [.85, 1, 1.15];
      LDEF.forEach(function (L, i) {
        var r = rng(100 + i * 31);
        L.ph = i * 2.1 + .7; L.off = 0; L.list = []; L.vars = [];
        bakeHill(L, rng(9 + i));
        for (var v = 0; v < 3; v++) {
          var kind = L.kinds[v], len = H * .085 * L.scale * sizes[v] * (kind ? .85 : 1);
          L.vars.push(treeSprite(L, len, r() * 10, kind));
        }
        var n = Math.max(1, Math.round(W / 1000 * L.trees * 5));
        for (var k = 0; k < n; k++)
          L.list.push({ x: (k + .3 + r() * .4) / n * W, seed: r() * 10, v: L.vars[Math.floor(r() * 3)] });
      });

      blades = []; var x;
      for (x = 0; x < W + 18; x += 18) blades.push({ x: x + Math.sin(x * 12.9) * 5, h: 10 + 12 * Math.abs(Math.sin(x * 4.37)), p: x * .03 });

      if (!leaves.length) {
        var r3 = rng(21), nl = W < 700 ? Math.ceil(CFG.leaves / 2) : CFG.leaves;
        for (var j = 0; j < nl; j++) leaves.push({
          x: r3() * W, y: r3() * H, s: 6 + r3() * 6, vy: 22 + r3() * 24, ph: r3() * 6.28, rot: r3() * 6.28,
          vr: (.4 + r3() * .9) * (r3() < .5 ? -1 : 1), spr: leafSpr[Math.floor(r3() * leafSpr.length)], a: .55 + r3() * .3
        });
        var r4 = rng(55), nf = W < 700 ? Math.ceil(CFG.fireflies / 2) : CFG.fireflies;
        for (var q = 0; q < nf; q++) flies.push({
          x: r4(), y: .15 + r4() * .78, ax: 30 + r4() * 70, ay: 20 + r4() * 50,
          fx: .15 + r4() * .3, fy: .15 + r4() * .3, ph: r4() * 6.28, s: 8 + r4() * 12
        });
        for (var b = 0; b < CFG.birds; b++) birds.push({
          x: -Math.random() * W * 1.6, y: H * (.08 + Math.random() * .28),
          v: 50 + Math.random() * 35, s: 6 + Math.random() * 4, ph: Math.random() * 6.28
        });
      }
    }
    function W0() { return window.innerWidth; }

    /* ---------- per-frame drawing ---------- */
    function base() { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }

    function drawRays(t) {
      var ox = W * .85, oy = -H * .08, len = H * 1.45;
      for (var i = 0; i < 4; i++) {
        var phi = .28 + i * .16 + Math.sin(t * .15 + i) * .035, w = len * (.2 + .04 * Math.sin(t * .2 + i * 2));
        var cs = Math.cos(phi), sn = Math.sin(phi);
        ctx.setTransform(dpr * cs, dpr * sn, -dpr * sn, dpr * cs, ox * dpr, oy * dpr);
        ctx.globalAlpha = .1 * (.6 + .4 * Math.sin(t * .3 + i * 1.7));
        ctx.drawImage(beam, -w / 2, 0, w, len);
      }
      ctx.globalAlpha = 1; base();
    }

    function drawBirds(t, dt) {
      ctx.strokeStyle = 'rgba(227,207,165,.55)'; ctx.lineWidth = 1.6; ctx.lineCap = 'round';
      ctx.beginPath();
      birds.forEach(function (b) {
        b.x += b.v * dt;
        if (b.x > W + 40) { b.x = -60 - Math.random() * W * .8; b.y = H * (.08 + Math.random() * .28); }
        var y = b.y + Math.sin(t * .7 + b.ph) * 10, fl = Math.sin(t * 6 + b.ph) * b.s * .8, s = b.s;
        ctx.moveTo(b.x - s * 1.5, y - fl);
        ctx.quadraticCurveTo(b.x - s * .6, y - s * .5, b.x, y);
        ctx.quadraticCurveTo(b.x + s * .6, y - s * .5, b.x + s * 1.5, y - fl);
      });
      ctx.stroke();
    }

    function drawLayer(L, t, g) {
      ctx.drawImage(L.hs, 0, L.top + L.off, W, L.hh);
      var amp = L.sway * CFG.wind * g;
      ctx.globalAlpha = L.alpha;
      for (var i = 0; i < L.list.length; i++) {
        var tr = L.list[i], v = tr.v;
        var sw = (Math.sin(t * .8 + tr.seed) * .6 + Math.sin(t * 1.9 + tr.seed * 2.3) * .25) * amp;
        ctx.setTransform(dpr, 0, -sw * dpr, dpr, tr.x * dpr, (hy(L, tr.x) + 3) * dpr);
        ctx.drawImage(v.c, -v.ox, -v.oy, v.w, v.h);
      }
      ctx.globalAlpha = 1; base();
    }

    function drawMist(t, k) {
      var span = W * 1.7, sp = 14 + k * 7;
      ctx.globalAlpha = .26;
      var x = ((t * sp + k * span * .45) % span) - W * .5;
      ctx.drawImage(mist, x, H * (.66 + k * .07), W * .8, H * .2);
      ctx.globalAlpha = 1;
    }

    function drawFlies(t) {
      ctx.globalCompositeOperation = 'lighter';
      for (var i = 0; i < flies.length; i++) {
        var f = flies[i];
        var x = f.x * W + Math.sin(t * f.fx + f.ph) * f.ax, y = f.y * H + Math.cos(t * f.fy + f.ph * 1.3) * f.ay;
        var p = .5 + .5 * Math.sin(t * 1.5 + f.ph * 3);
        ctx.globalAlpha = .1 + .6 * p * p;
        ctx.drawImage(glow, x - f.s / 2, y - f.s / 2, f.s, f.s);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }

    function drawGrass(L, t, g) {
      ctx.strokeStyle = 'rgba(120,185,95,.75)'; ctx.lineWidth = 1.5; ctx.lineCap = 'round'; ctx.beginPath();
      for (var i = 0; i < blades.length; i++) {
        var b = blades[i], y = hy(L, b.x) + 2, sw = Math.sin(t * 1.4 * CFG.wind + b.p) * 4 * CFG.wind * g;
        ctx.moveTo(b.x, y); ctx.quadraticCurveTo(b.x + sw * .5, y - b.h * .6, b.x + sw, y - b.h);
      }
      ctx.stroke();
    }

    function drawLeaves(t, dt, g) {
      for (var i = 0; i < leaves.length; i++) {
        var l = leaves[i];
        l.y += l.vy * dt;
        l.x += (Math.sin(t + l.ph) * 34 + 16 * CFG.wind * g) * dt;
        l.rot += l.vr * dt;
        if (l.y > H + 20) { l.y = -20; l.x = Math.random() * W; }
        if (l.x > W + 30) l.x = -30;
        var fade = Math.max(0, Math.min(1, (l.y + 20) / 80, (H + 20 - l.y) / 80));
        var cs = Math.cos(l.rot), sn = Math.sin(l.rot), sx = .35 + .65 * Math.abs(Math.cos(t * 1.2 + l.ph));
        ctx.setTransform(dpr * cs * sx, dpr * sn * sx, -dpr * sn, dpr * cs, l.x * dpr, l.y * dpr);
        ctx.globalAlpha = l.a * fade;
        ctx.drawImage(l.spr, -l.s, -l.s, l.s * 2, l.s * 2);
      }
      ctx.globalAlpha = 1; base();
    }

    function frame(t, dt) {
      var g = gust(t);
      LDEF.forEach(function (L) { L.off = (prog - .5) * L.par * H * 3; });
      ctx.drawImage(bg, 0, 0, W, H);
      if (CFG.rays) drawRays(t);
      drawBirds(t, dt);
      drawLayer(LDEF[0], t, g);
      drawMist(t, 0);
      drawLayer(LDEF[1], t, g);
      drawMist(t, 1);
      drawFlies(t);
      drawLayer(LDEF[2], t, g);
      if (CFG.grass) drawGrass(LDEF[2], t, g);
      drawLeaves(t, dt, g);
    }

    /* ---------- run ---------- */
    function onScroll() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      progT = Math.min(1, Math.max(0, window.scrollY / max));
    }

    makeStatic(); build(); onScroll();
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (window.innerWidth === W && Math.abs(window.innerHeight - H) < 150) return; // mobile URL-bar jitter
        build(); if (reduce) frame(0, 0);
      }, 150);
    });
    window.addEventListener('scroll', onScroll, { passive: true });

    if (reduce) { frame(0, 0); return; }

    var lastDraw = performance.now(), lastTick = lastDraw, T = 0;
    var acc = 0, nF = 0, warm = 0, stage = 0, cap30 = false;

    function degrade() {
      stage++;
      if (stage === 1) {            // lighter: lower resolution, no rays, fewer particles
        dprMax = 1; CFG.rays = false;
        leaves.length = Math.ceil(leaves.length / 2);
        flies.length = Math.ceil(flies.length / 2);
        build();
      } else cap30 = true;          // still slow: 30 fps
    }

    function loop(now) {
      requestAnimationFrame(loop);
      var raw = (now - lastTick) / 1000; lastTick = now;
      if (cap30 && now - lastDraw < 30) return;
      var dt = Math.min(.05, (now - lastDraw) / 1000); lastDraw = now; T += dt;
      frame(T, dt);
      if (raw < .2) {
        if (++warm > 40) {
          acc += raw; nF++;
          if (nF === 60) { if (acc / 60 > .027 && stage < 2 && !cap30) degrade(); acc = 0; nF = 0; }
        }
      }
    }
    requestAnimationFrame(loop);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
/* Terralyt · bg.js — "mitti & darakht" PRO  (v3 · photoreal living background)
   · fBm-lit volumetric clouds + cirrus, sun bloom, lens ghosts, film grain
   · ridge-noise mountains with atmospheric perspective, baked forests
   · real branching trees: tapered bark trunks, limbs, thousands of lit leaf
     dots (broadleaf / conifer / poplar), sun rim-light, ground shadows,
     canopy sway + leaf shimmer
   · bump-mapped soil (clods, pebbles, roots-green edge), tapered grass,
     wild flowers, wind-wave grass
   · anatomical bird silhouettes (flap / glide cycles, flocks), butterflies,
     pollen motes, tumbling leaves, cloud shadows, valley mist
   Everything heavy is pre-rendered once; each frame only moves sprites.
   Drop-in replacement for assets/bg.js — self-starting.                  */
(function () {
  'use strict';

  var CFG = {
    wind: 1,          // 0 calm · 1 natural · 2 stormy
    leaves: 12,       // falling leaves
    motes: 34,        // pollen / dust in the sunlight
    birds: 7,         // birds (flocks of 3)
    butterflies: 3,
    clouds: 8,
    rays: true,       // sunlight shafts
    grass: true,      // swaying grass
    shadows: true,    // cloud shadows on the land
    grain: true,      // subtle film grain (kills gradient banding)
    respectReducedMotion: false
  };

  var reduce = CFG.respectReducedMotion && window.matchMedia &&
    matchMedia('(prefers-reduced-motion: reduce)').matches;

  var TAU = 6.283185307179586;

  /* ================= helpers ================= */
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
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function sm(a, b, x) { var t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); }
  function hex(h) { h = h.replace('#', ''); return [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)]; }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function rgb(c, a) { return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + (a == null ? 1 : a) + ')'; }
  function hexA(h, a) { return rgb(hex(h), a); }
  function ramp(stops, n) {
    var cs = stops.map(hex), out = [], i, t, k;
    for (i = 0; i < n; i++) {
      t = i / (n - 1) * (cs.length - 1); k = Math.min(cs.length - 2, Math.floor(t));
      out.push(rgb(mix(cs[k], cs[k + 1], t - k)));
    }
    return out;
  }
  function makeNoise(seed) {
    var r = rng(seed), P = new Uint8Array(512), V = new Float32Array(256), i, j, t;
    for (i = 0; i < 256; i++) { P[i] = i; V[i] = r(); }
    for (i = 255; i > 0; i--) { j = (r() * (i + 1)) | 0; t = P[i]; P[i] = P[j]; P[j] = t; }
    for (i = 0; i < 256; i++) P[i + 256] = P[i];
    function n2(x, y) {
      var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
      xi &= 255; yi &= 255;
      var u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
      var a = V[P[P[xi] + yi]], b = V[P[P[xi + 1] + yi]], c = V[P[P[xi] + yi + 1]], d = V[P[P[xi + 1] + yi + 1]];
      return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
    }
    function f(x, y, o) { var s = 0, a = .5, q = 1; for (var k = 0; k < o; k++) { s += a * n2(x * q, y * q); q *= 2; a *= .5; } return s; }
    return { n: n2, f: f };
  }

  /* ================= palettes ================= */
  var PR = {
    broad: [
      ramp(['#0b2013', '#163820', '#245a2f', '#3b7b38', '#628f40', '#94ac55'], 12),
      ramp(['#142414', '#25401b', '#385c25', '#567c2e', '#80983f', '#aeb25c'], 12),
      ramp(['#0d2a19', '#1a4529', '#2d6a38', '#478a43', '#6fa24e', '#a2bd6c'], 12)
    ],
    conif: [ramp(['#08190f', '#11301f', '#1b4a2f', '#2d6642', '#4c875a', '#7aa774'], 12)],
    pop:   [ramp(['#11291a', '#214228', '#356336', '#518543', '#7ba052', '#aac26e'], 12)]
  };
  function palFor(kind, k) { return kind === 1 ? PR.conif[0] : kind === 2 ? PR.pop[0] : PR.broad[k % 3]; }
  var BARK = ['#251a11', '#4b3a28', '#8c7352'];
  var LEAF_COL = [['#a87a22', '#dcb64c'], ['#6f9b3f', '#a9cd6c'], ['#b8651f', '#e49b48'], ['#4f8e3f', '#88c06a'], ['#9a4a17', '#d2812f'], ['#7e9a2c', '#c7d352']];
  var FLOWER_COL = ['#f2d479', '#fbfaf0', '#f4b6c2', '#c9b3e6', '#f0a43a'];
  var GRASS_COL = ['#1b4120', '#2b6329', '#3d8333', '#5fa238', '#93bd48', '#b9c767'];

  /* ================= layer definitions ================= */
  var LDEF = [
    { base: .645, amp: .13, freq: 2.9, ridge: true, par: .010, c0: '#5d84a6', c1: '#8aaec8', haze: ['#bcd6e6', .2], rim: 1, blotch: .5, snow: true, rock: true },
    { base: .76, amp: .050, freq: 2.8, par: .022, c0: '#3d7659', c1: '#2a5842', haze: ['#a9cfdc', .22], rim: .6, blotch: .6,
      tree: { h: [.05, .08], kinds: [0, 0, 1, 2, 0], rows: 5, step: 12, bake: true, shrub: .028 } },
    { base: .835, amp: .040, freq: 2.2, par: .036, c0: '#4f8c3b', c1: '#2e5f2c', haze: ['#d9ecd9', .05], rim: .8, blotch: 1,
      tree: { h: [.03, .045], kinds: [3, 3, 0, 2, 3], rows: 1, step: 30, bake: true, shrub: .02 },
      anim: { h: [.15, .22], kinds: [0, 0, 2, 1, 0, 0], sway: .035, alpha: 1 } },
    { base: .945, amp: .03, freq: 1.9, par: .05, soil: true }
  ];

  /* ================= init ================= */
  function init() {
    var cv = document.createElement('canvas');
    cv.id = 'terra-bg';
    cv.setAttribute('aria-hidden', 'true');
    cv.style.cssText = 'position:fixed;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block';
    document.body.insertBefore(cv, document.body.firstChild);

    /* light sky -> keep cream text readable (shadow only; layout & colours untouched) */
    var st = document.createElement('style'); st.id = 'terra-sky-style';
    st.textContent = 'html{background:#9fd0f1}' +
      '.sc h1,.sc h2,.hg p,.sc .lead,.sc .tag,.pg>h1,.pg>p,.pg>.mut,.kp b,.kp span{text-shadow:0 1px 2px rgba(6,30,56,.6),0 3px 18px rgba(6,30,56,.45)}' +
      '.hg p,.sc .lead{color:#f6efe0}' +
      '.pg>p,.pg>.mut{color:#f6efe0}' +
      '.hg>div:first-child,.two>div:first-child,.two3>div:first-child,.fgrid>div:first-child,.sc.last .mid{position:relative;z-index:2;isolation:isolate}' +
      '.hg>div:first-child::before,.two>div:first-child::before,.two3>div:first-child::before,.fgrid>div:first-child::before,.sc.last .mid::before{content:"";position:absolute;z-index:-1;inset:-16px -22px;border-radius:28px;background:linear-gradient(135deg,rgba(7,30,54,.5),rgba(7,30,54,.34));-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.14);pointer-events:none}' +
      '.sc.last .mid::before{inset:auto;left:50%;top:50%;width:min(700px,92%);height:calc(100% - 30px);transform:translate(-50%,-50%)}' +
      '@media(max-width:900px){.hg>div:first-child::before,.two>div:first-child::before,.two3>div:first-child::before,.fgrid>div:first-child::before{inset:-12px -12px}}' +
      '.btn.gh{background:rgba(7,30,54,.5)}' +
      '.dots a{background:rgba(255,255,255,.6);box-shadow:0 0 0 1px rgba(6,30,56,.25)}.dots a.on{background:#7bd08b}';
    document.head.appendChild(st);
    var tc = document.querySelector('meta[name="theme-color"]'); if (tc) tc.setAttribute('content', '#74b9ee');
    var ctx = cv.getContext('2d', { alpha: false });

    var W = 0, H = 0, dpr = 1, dprMax = 1.25, prog = 0, progT = 0;
    var bg, beam, glow, mist, shadowSpr, cloudSpr = [], leafSpr = [], birdSpr = [], NF = 10;
    var clouds = [], leaves = [], motes = [], birds = [], flocks = [], bflies = [], blades = [];
    var skyN = makeNoise(5);

    /* ================= static sprites ================= */
    function radial(w, h, stops) {
      var c = mk(w, h), g = c.getContext('2d'), gr = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
      stops.forEach(function (s) { gr.addColorStop(s[0], s[1]); });
      g.save(); g.scale(1, h / w); g.fillStyle = gr; g.fillRect(0, 0, w, w); g.restore();
      return c;
    }

    /* volumetric cumulus: fBm density, sun-side lighting, flat base */
    function cloudSprite(seed) {
      var w = 480, h = 210, c = mk(w, h), g = c.getContext('2d'), im = g.createImageData(w, h), d = im.data,
        N = makeNoise(seed * 13 + 1), dn = new Float32Array(w * h), x, y, i, o;
      for (y = 0; y < h; y++) {
        var ny = (y / h - .6) * 2;
        for (x = 0; x < w; x++) {
          var nx = (x / w - .5) * 2;
          var e = 1 - Math.sqrt(nx * nx * .9 + (ny < 0 ? ny * ny * 1.15 : ny * ny * 7));
          dn[y * w + x] = N.f(x * .0105 + seed, y * .0165, 6) * 1.25 + e * 1.05 - .78;
        }
      }
      for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
        i = y * w + x; var den = dn[i], a = sm(0, .22, den);
        if (a <= 0) continue;
        var lit = den - dn[Math.max(0, y - 5) * w + Math.min(w - 1, x + 5)];
        var t = clamp(.6 + lit * 3.4 + (.6 - y / h) * .55 + den * .25, 0, 1);
        var rim = clamp(lit * 6, 0, 1) * (1 - sm(0, .3, den));
        a *= 1 - sm(.7, .93, y / h);
        o = i * 4;
        d[o] = 146 + 109 * t + rim * 6; d[o + 1] = 168 + 86 * t + rim * 4; d[o + 2] = 200 + 54 * t - rim * 10;
        d[o + 3] = a * 238;
      }
      g.putImageData(im, 0, 0);
      return c;
    }

    function birdFrames() {
      function wings(g, f) {
        g.fillStyle = 'rgba(24,32,44,.97)';
        for (var sd = -1; sd <= 1; sd += 2) {
          var wy = -1.6 - f * 6.5, tx = sd * 16.5, ty = -.5 - f * 13;
          g.beginPath(); g.moveTo(0, -1.5);
          g.quadraticCurveTo(sd * 3.5, -2.8 - f * 3.2, sd * 7, wy - .6);
          g.quadraticCurveTo(sd * 11.5, wy + (ty - wy) * .35 - 1.3, tx, ty);
          g.quadraticCurveTo(sd * 12.5, wy + (ty - wy) * .5 + 2.2, sd * 8.5, wy + 3.2);
          g.quadraticCurveTo(sd * 4, 2 - f * 1.4, 0, 1.4);
          g.closePath(); g.fill();
          g.strokeStyle = 'rgba(24,32,44,.9)'; g.lineWidth = .7;       // primary feather tips
          for (var q = 0; q < 3; q++) {
            g.beginPath(); g.moveTo(sd * (13 + q * 1.1), ty + (wy - ty) * (.12 + q * .05) + 1);
            g.lineTo(sd * (17.2 - q * .7), ty + q * .9 - f * 1.2 + .3); g.stroke();
          }
        }
      }
      for (var f = 0; f <= NF; f++) {
        var c = mk(144, 88), g = c.getContext('2d');
        g.scale(2, 2); g.translate(36, 24);
        var e = f < NF ? Math.sin(f / NF * TAU) : .3;
        wings(g, e);
        g.fillStyle = 'rgba(24,32,44,.97)';
        g.beginPath(); g.ellipse(.6, .6, 3.6, 2.1, 0, 0, TAU); g.fill();                       // body
        g.beginPath(); g.arc(4.1, -.2, 1.5, 0, TAU); g.fill();                                  // head
        g.beginPath(); g.moveTo(5.2, -.6); g.lineTo(7.6, .1); g.lineTo(5.2, .5); g.fill();      // beak
        g.beginPath(); g.moveTo(-2.6, .3); g.lineTo(-8, -.9); g.lineTo(-8.6, 1.1); g.lineTo(-7.6, 2.6); g.lineTo(-2.6, 1.7); g.closePath(); g.fill(); // tail
        birdSpr.push(c);
      }
    }

    function makeStatic() {
      [11, 23, 37, 51].forEach(function (sd) { cloudSpr.push(cloudSprite(sd)); });
      glow = radial(64, 64, [[0, 'rgba(255,250,225,1)'], [.3, 'rgba(255,236,170,.4)'], [1, 'rgba(255,226,150,0)']]);
      mist = radial(256, 96, [[0, 'rgba(232,244,238,.55)'], [.6, 'rgba(232,244,238,.2)'], [1, 'rgba(232,244,238,0)']]);
      shadowSpr = radial(128, 40, [[0, 'rgba(8,28,36,.55)'], [.6, 'rgba(8,28,36,.25)'], [1, 'rgba(8,28,36,0)']]);
      beam = mk(128, 512);
      var g = beam.getContext('2d');
      if ('filter' in g) g.filter = 'blur(7px)';
      var gr = g.createLinearGradient(0, 0, 0, 512);
      gr.addColorStop(0, 'rgba(255,238,176,.95)'); gr.addColorStop(.55, 'rgba(255,238,176,.28)'); gr.addColorStop(1, 'rgba(255,238,176,0)');
      g.fillStyle = gr; g.beginPath(); g.moveTo(58, 8); g.lineTo(70, 8); g.lineTo(108, 500); g.lineTo(20, 500); g.closePath(); g.fill();
      LEAF_COL.forEach(function (col, n) {
        var c = mk(40, 40), q = c.getContext('2d'), long = n % 3 === 2, wd = long ? 7 : 11;
        q.translate(20, 20);
        var lg = q.createLinearGradient(-wd, 0, wd, 0); lg.addColorStop(0, col[0]); lg.addColorStop(1, col[1]);
        q.fillStyle = lg; q.beginPath(); q.moveTo(0, -16); q.quadraticCurveTo(wd, -4, 0, 15); q.quadraticCurveTo(-wd, -4, 0, -16); q.fill();
        q.strokeStyle = 'rgba(40,25,10,.45)'; q.lineWidth = .9;
        q.beginPath(); q.moveTo(0, -15); q.lineTo(0, 17); q.stroke();
        q.lineWidth = .6; q.beginPath();
        for (var k = -8; k <= 6; k += 5) { q.moveTo(0, k); q.lineTo(wd * .6, k - 4); q.moveTo(0, k); q.lineTo(-wd * .6, k - 4); }
        q.stroke();
        leafSpr.push(c);
      });
      birdFrames();
    }

    /* ================= sky ================= */
    function bakeBG() {
      var c = mk(W * dpr, H * dpr), g = c.getContext('2d');
      g.scale(dpr, dpr);
      var R = Math.max(W, H), gr, i, x, y, o;
      gr = g.createLinearGradient(0, 0, 0, H);
      gr.addColorStop(0, '#4a9be0'); gr.addColorStop(.32, '#74b9ee'); gr.addColorStop(.6, '#a8d9f5');
      gr.addColorStop(.8, '#d5eefa'); gr.addColorStop(1, '#d3e7d6');
      g.fillStyle = gr; g.fillRect(0, 0, W, H);

      /* high cirrus streaks (half-res fBm, stretched) */
      var cw = Math.ceil(W / 4), ch = Math.ceil(H * .5 / 4), cc = mk(cw, ch), cg = cc.getContext('2d'),
        ci = cg.createImageData(cw, ch), cd = ci.data;
      for (y = 0; y < ch; y++) for (x = 0; x < cw; x++) {
        var f = skyN.f(x * .016 + 9, y * .07 + x * .004, 5), a = sm(.5, .8, f) * (1 - y / ch) * .4;
        o = (y * cw + x) * 4; cd[o] = 255; cd[o + 1] = 255; cd[o + 2] = 255; cd[o + 3] = a * 255;
      }
      cg.putImageData(ci, 0, 0); g.imageSmoothingEnabled = true; g.drawImage(cc, 0, 0, cw * 4, ch * 4);

      /* sun bloom + disc */
      var sx = W * .84, sy = H * .1;
      gr = g.createRadialGradient(sx, sy, 0, sx, sy, R * .62);
      gr.addColorStop(0, 'rgba(255,252,232,.95)'); gr.addColorStop(.08, 'rgba(255,246,214,.75)');
      gr.addColorStop(.3, 'rgba(255,240,200,.26)'); gr.addColorStop(1, 'rgba(255,240,200,0)');
      g.fillStyle = gr; g.fillRect(0, 0, W, H);
      gr = g.createRadialGradient(sx, sy, 0, sx, sy, Math.max(16, H * .035));
      gr.addColorStop(0, 'rgba(255,255,250,1)'); gr.addColorStop(.7, 'rgba(255,253,238,.96)'); gr.addColorStop(1, 'rgba(255,250,225,0)');
      g.fillStyle = gr; g.fillRect(sx - 90, sy - 90, 180, 180);
      /* faint lens ghosts along the sun -> centre axis */
      [[.38, .035, .05], [.62, .06, .035], [1.05, .025, .05], [1.45, .08, .03]].forEach(function (G) {
        var gx = sx + (W / 2 - sx) * G[0], gy = sy + (H / 2 - sy) * G[0], rr = H * G[1];
        var lg = g.createRadialGradient(gx, gy, 0, gx, gy, rr);
        lg.addColorStop(0, 'rgba(255,250,225,' + G[2] + ')'); lg.addColorStop(.7, 'rgba(255,240,200,' + G[2] * .6 + ')'); lg.addColorStop(1, 'rgba(255,240,200,0)');
        g.fillStyle = lg; g.fillRect(gx - rr, gy - rr, rr * 2, rr * 2);
      });
      /* horizon haze */
      gr = g.createLinearGradient(0, H * .5, 0, H * .8);
      gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.7, 'rgba(255,255,255,.34)'); gr.addColorStop(1, 'rgba(255,255,255,.12)');
      g.fillStyle = gr; g.fillRect(0, H * .5, W, H * .3);
      /* vignette */
      var v = g.createRadialGradient(W / 2, H / 2, R * .35, W / 2, H / 2, R * .9);
      v.addColorStop(0, 'rgba(8,40,80,0)'); v.addColorStop(1, 'rgba(8,40,80,.22)');
      g.fillStyle = v; g.fillRect(0, 0, W, H);
      /* film grain */
      if (CFG.grain) {
        var gt = mk(128, 128), gg = gt.getContext('2d'), gi = gg.createImageData(128, 128), gd = gi.data, rr2 = rng(3);
        for (i = 0; i < 128 * 128; i++) { var q = rr2() * 255; gd[i * 4] = gd[i * 4 + 1] = gd[i * 4 + 2] = q; gd[i * 4 + 3] = 255; }
        gg.putImageData(gi, 0, 0);
        g.globalCompositeOperation = 'soft-light'; g.globalAlpha = .08;
        g.fillStyle = g.createPattern(gt, 'repeat'); g.fillRect(0, 0, W, H);
        g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
      }
      return c;
    }

    /* ================= terrain ================= */
    function baseY(L, x) {
      var u = x / W * L.freq + L.ph;
      if (L.ridge) { var m = 1 - Math.abs(2 * L.nz.f(u, 3.7, 6) - 1); return H * L.base + (.5 - m) * H * L.amp * 2.4; }
      return H * L.base + (L.nz.f(u, L.ph * 2.1, 4) - .5) * H * L.amp * 2.2;
    }
    function hy(L, x) { return baseY(L, x) + L.off; }

    /* ================= trees ================= */
    function limb(g, x0, y0, cx, cy, x1, y1, w0, w1) {
      var n = 9, px = x0, py = y0, i, t, u, x, y;
      g.lineCap = 'round';
      for (i = 1; i <= n; i++) {
        t = i / n; u = 1 - t;
        x = u * u * x0 + 2 * u * t * cx + t * t * x1; y = u * u * y0 + 2 * u * t * cy + t * t * y1;
        g.lineWidth = Math.max(.6, w0 + (w1 - w0) * t);
        g.beginPath(); g.moveTo(px, py); g.lineTo(x, y); g.stroke();
        px = x; py = y;
      }
    }

    /* kind 0 broadleaf · 1 conifer · 2 poplar.  opt: shadow, canopyOnly, dseed */
    function mkTree(Ht, kind, seed, pal, opt) {
      opt = opt || {};
      var r = rng(seed), rd = rng(opt.dseed || (seed * 7 + 3));
      var w = Math.ceil(Ht * 1.55) + 6, h = Math.ceil(Ht * 1.08) + 8, ox = w / 2, oy = h - 4;
      var c = mk(w * dpr, h * dpr), g = c.getContext('2d');
      g.scale(dpr, dpr); g.translate(ox, oy);
      var th, rx, ry, cy, i, k, cl = [];
      if (kind === 1) { th = Ht * .12; rx = Ht * .27 * (.9 + r() * .2); ry = Ht * .47; }
      else if (kind === 2) { th = Ht * .2; rx = Ht * .13 * (.9 + r() * .25); ry = Ht * .42; }
      else if (kind === 3) { th = Ht * .05; rx = Ht * (.5 + r() * .1); ry = Ht * .46; }
      else { th = Ht * .27; rx = Ht * (.38 + r() * .1); ry = Ht * .36; }
      cy = -Ht + ry;

      /* --- foliage clumps (geometry first so variants stay identical) --- */
      var n = Math.round(clamp(9 + Ht / 9, 10, 34));
      if (kind === 1) {
        var T = Math.min(9, Math.max(4, Math.round(Ht / 16)));
        for (i = 0; i < T; i++) {
          var f = (i + .5) / T, yy = -Ht + f * 2 * ry * .98, hw = rx * (.22 + .78 * f) * 1.05,
            m = Math.max(2, Math.round(hw / (Ht * .07)));
          for (k = 0; k < m; k++) {
            var u = m > 1 ? k / (m - 1) * 2 - 1 : 0;
            cl.push({ x: u * hw * .82 + (r() - .5) * hw * .2, y: yy + Math.abs(u) * hw * .12 + (r() - .5) * ry * .05,
              rx: Ht * .085 * (.8 + f * .5), ry: Ht * .05 * (.9 + f * .4), z: r() * .6 + (1 - Math.abs(u)) * .4 });
          }
        }
      } else {
        var p1 = r() * TAU, p2 = r() * TAU, skew = (r() - .5) * .3;
        for (i = 0; i < n; i++) {
          var a = r() * TAU, lobe = 1 + .2 * Math.sin(a * 3 + p1) + .12 * Math.sin(a * 5 + p2), dd = Math.min(1.05, Math.pow(r(), .65) * lobe),
            px = Math.cos(a) * dd * rx * (kind === 2 ? .7 : .78) + skew * rx * Math.sin(a) ,
            py = Math.sin(a) * dd * ry * .8 - (kind === 0 ? ry * .05 : 0),
            cr = Ht * (kind === 2 ? .075 : .115) * (.6 + r() * .8);
          cl.push({ x: px, y: cy + py, rx: cr * (kind === 2 ? 1 : 1.15), ry: cr * (kind === 2 ? 1.25 : .9), z: r() });
        }
      }
      cl.sort(function (A, B) { return A.z - B.z; });

      /* --- ground shadow, trunk, limbs --- */
      if (!opt.canopyOnly) {
        if (opt.shadow !== false) {
          g.save(); g.translate(-Ht * .14, 0); g.scale(1, .16);
          var sg = g.createRadialGradient(0, 0, 0, 0, 0, rx * 1.2);
          sg.addColorStop(0, 'rgba(10,20,10,.5)'); sg.addColorStop(1, 'rgba(10,20,10,0)');
          g.fillStyle = sg; g.beginPath(); g.arc(0, 0, rx * 1.2, 0, TAU); g.fill(); g.restore();
        }
        var bw = Math.max(1.1, Ht * (kind === 0 ? .034 : .022)), wob = (r() - .5) * Ht * .05;
        var tg = g.createLinearGradient(-bw, 0, bw, 0);
        tg.addColorStop(0, BARK[0]); tg.addColorStop(.55, BARK[1]); tg.addColorStop(1, BARK[2]);
        g.fillStyle = tg; g.beginPath(); g.moveTo(-bw * 1.55, 0);
        g.bezierCurveTo(-bw * 1.05, -th * .15, -bw * .75 + wob * .2, -th * .5, -bw * .55 + wob, -th);
        g.lineTo(bw * .55 + wob, -th);
        g.bezierCurveTo(bw * .75 + wob * .2, -th * .5, bw * 1.05, -th * .15, bw * 1.55, 0);
        g.closePath(); g.fill();
        if (Ht > 60) {                                    // bark furrows
          g.strokeStyle = 'rgba(10,6,3,.4)'; g.lineWidth = .8;
          for (i = 0; i < 4; i++) {
            var bx = (r() - .5) * bw * 1.2; g.beginPath(); g.moveTo(bx, -r() * th * .1);
            g.quadraticCurveTo(bx + (r() - .5) * 3, -th * .5, bx * .6 + wob * .8, -th * (.6 + r() * .4)); g.stroke();
          }
        }
        if (kind === 0) {
          g.strokeStyle = BARK[1];
          var nl = 3 + Math.floor(r() * 3);
          for (i = 0; i < nl; i++) {
            var ex = (i / (nl - 1) - .5) * rx * 1.15 + (r() - .5) * rx * .2, ey = cy - ry * .15 + r() * ry * .5;
            limb(g, wob, -th * .92, wob + ex * .15, -th - (th * .5), ex, ey, bw * .75, bw * .18);
            for (k = 0; k < 2; k++) limb(g, ex * .8, ey + ry * .2, ex + (k ? 1 : -1) * rx * .15, ey - ry * .1, ex + (k ? 1 : -1) * rx * .3, ey - ry * .28, bw * .22, .6);
          }
        } else {
          g.strokeStyle = BARK[1]; limb(g, wob, -th, wob, -th - (Ht - th) * .45, wob * .5, -Ht + Ht * .06, bw * .5, .6);
        }
      }

      /* --- canopy: dark mass + thousands of lit leaf dots --- */
      var dr = Math.max(.6, Ht * .0125), PL = pal.length - 1;
      cl.forEach(function (q) {
        g.fillStyle = pal[Math.round(2 + q.z * 2)];
        g.beginPath(); g.ellipse(q.x, q.y, q.rx * .78, q.ry * .78, 0, 0, TAU); g.fill();
        var m = clamp(Math.round(2.2 * q.rx * q.ry / (dr * dr)), 16, 170), j;
        for (j = 0; j < m; j++) {
          var aa = rd() * TAU, de = Math.sqrt(rd()), dx = Math.cos(aa) * de, dy = Math.sin(aa) * de;
          if (de > .82 && rd() < .28) continue;                            // ragged edge, sky shows through
          var px2 = q.x + dx * q.rx, py2 = q.y + dy * q.ry;
          var t = .4 + dx * .2 - dy * .3 + (q.z - .5) * .3 + (rd() - .5) * .34 + (px2 / rx) * .1 - ((py2 - cy) / ry) * .12;
          g.fillStyle = pal[Math.round(clamp(t, 0, 1) * PL)];
          var s = dr * (.7 + rd() * .8);
          g.beginPath(); g.ellipse(px2, py2, s * 1.2, s * .75, rd() * 3.14, 0, TAU); g.fill();
        }
      });
      /* sun rim-light / bottom-left shade over the whole tree */
      g.globalCompositeOperation = 'source-atop';
      var lg = g.createLinearGradient(rx, cy - ry, -rx, cy + ry);
      lg.addColorStop(0, 'rgba(255,238,180,.22)'); lg.addColorStop(.5, 'rgba(255,238,180,0)'); lg.addColorStop(1, 'rgba(6,22,14,.32)');
      g.fillStyle = lg; g.fillRect(-ox, -oy, w, h);
      if (opt.haze) { g.fillStyle = hexA(opt.haze[0], opt.haze[1]); g.fillRect(-ox, -oy, w, h); }
      g.globalCompositeOperation = 'source-over';
      return { c: c, w: w, h: h, ox: ox, oy: oy };
    }

    function bakeHill(L, i) {
      var T = L.tree || {}, Hmax = T.h ? T.h[1] * H * 1.3 : 0, x, miny = 1e9;
      for (x = 0; x <= W; x += 12) miny = Math.min(miny, baseY(L, x));
      var top = Math.floor(miny - Hmax - 8), hh = Math.ceil(H * 1.12 - top);
      var c = mk(W * dpr, hh * dpr), g = c.getContext('2d'), r = rng(70 + i);
      var e = function (xx) { return baseY(L, xx) - top; };
      g.scale(dpr, dpr);
      var gr = g.createLinearGradient(0, e(W / 2) - H * .06, 0, hh);
      gr.addColorStop(0, L.c0); gr.addColorStop(1, L.c1);
      g.fillStyle = gr; g.beginPath(); g.moveTo(-8, hh);
      for (x = -8; x <= W + 16; x += 8) g.lineTo(x, e(x));
      g.lineTo(W + 16, hh); g.closePath(); g.fill();

      g.globalCompositeOperation = 'source-atop';
      /* field / meadow mottling */
      var nb = Math.round(W / 5 * (L.blotch || 0)), k;
      for (k = 0; k < nb; k++) {
        var bx = r() * W, by = e(bx) + 4 + r() * H * .28, bs = 30 + r() * 110, lite = r() < .5;
        var bg2 = g.createRadialGradient(bx, by, 0, bx, by, bs);
        bg2.addColorStop(0, lite ? 'rgba(190,210,110,.11)' : 'rgba(10,40,24,.13)');
        bg2.addColorStop(1, lite ? 'rgba(190,210,110,0)' : 'rgba(10,40,24,0)');
        g.fillStyle = bg2; g.fillRect(bx - bs, by - bs, bs * 2, bs * 2);
      }
      /* fine surface texture: tufts / rock grain */
      var nt = Math.round(W * (L.rock ? 1.6 : L.base > .8 ? 3.2 : 1.1));
      g.lineWidth = 1; g.lineCap = 'round';
      for (k = 0; k < nt; k++) {
        var tx = r() * W, ty = e(tx) + 2 + Math.pow(r(), 1.6) * H * (L.rock ? .3 : .2), dark = r() < .5, tl = 2 + r() * (L.base > .8 ? 8 : 5);
        g.strokeStyle = L.rock ? (dark ? 'rgba(40,60,86,.16)' : 'rgba(225,235,245,.14)') : (dark ? 'rgba(8,36,20,.3)' : 'rgba(205,230,125,.26)');
        g.beginPath(); g.moveTo(tx, ty); g.lineTo(tx + (L.rock ? tl : (r() - .5) * 3), ty + (L.rock ? tl * .6 : -tl)); g.stroke();
      }
      if (L.base > .8 && L.base < .9) {                   /* meadow flower specks */
        for (k = 0; k < W / 2.5; k++) {
          var fx = r() * W, fyy = e(fx) + 6 + Math.pow(r(), 1.3) * H * .16;
          g.fillStyle = FLOWER_COL[(r() * FLOWER_COL.length) | 0]; g.globalAlpha = .55 + r() * .4;
          g.fillRect(fx, fyy, .9 + r() * 1.3, .9 + r() * 1.1);
        }
        g.globalAlpha = 1;
      }
      if (L.rock) {                                       /* ravines & ridge folds that follow the slope */
        for (k = 0; k < W * 1.4; k++) {
          var rx0 = r() * W, sl0 = e(rx0 + 10) - e(rx0 - 10), aa0 = clamp(sl0 / 16, -1, 1);
          if (Math.abs(aa0) < .12) continue;
          var ry0 = e(rx0) + 1 + r() * 8, rl = 10 + r() * 48, lit0 = aa0 > 0;
          g.strokeStyle = lit0 ? 'rgba(238,244,250,' + (.03 + .05 * aa0) + ')' : 'rgba(26,48,78,' + (.03 - .05 * aa0) + ')';
          g.lineWidth = .7 + r() * 1.5;
          g.beginPath(); g.moveTo(rx0, ry0);
          g.quadraticCurveTo(rx0 + (lit0 ? 1 : -1) * rl * .12, ry0 + rl * .5, rx0 + (lit0 ? 1 : -1) * rl * .3, ry0 + rl); g.stroke();
        }
      }
      /* slope lighting: sun from the right */
      var sl = H * .07;
      for (x = 0; x < W && !L.rock; x += 1) {
        var s = e(x + 8) - e(x - 8), a = clamp(s / 14, -1, 1), y0 = e(x), cs = a > 0 ? '255,244,196' : '6,22,30',
          sg = g.createLinearGradient(0, y0, 0, y0 + sl);
        sg.addColorStop(0, 'rgba(' + cs + ',' + (Math.abs(a) * .15 * (a > 0 ? L.rim : 1)) + ')');
        sg.addColorStop(1, 'rgba(' + cs + ',0)');
        g.fillStyle = sg; g.fillRect(x, y0 - 2, 2, sl + 2);
      }
      if (L.snow) {                                       /* snow caps on the highest peaks */
        var snowY = miny - top + (H * L.amp) * .42, sN = makeNoise(17);
        for (x = 0; x < W; x += 2) {
          var yy = e(x);
          if (yy < snowY) {
            var th2 = (snowY - yy) * (.3 + sN.f(x * .08, 1.7, 3) * 1.1) * .75;
            var sg2 = g.createLinearGradient(0, yy, 0, yy + th2);
            sg2.addColorStop(0, 'rgba(250,252,255,.95)'); sg2.addColorStop(.5, 'rgba(238,244,252,.6)'); sg2.addColorStop(1, 'rgba(240,246,252,0)');
            g.fillStyle = sg2; g.fillRect(x, yy, 2.2, th2);
          }
        }
      }
      g.strokeStyle = 'rgba(255,248,214,' + (.3 * L.rim) + ')'; g.lineWidth = 1.2; g.beginPath();
      for (x = 0; x <= W + 8; x += 8) { x ? g.lineTo(x, e(x)) : g.moveTo(x, e(x)); } g.stroke();
      g.globalCompositeOperation = 'source-over';

      /* baked forest / tree-line, back row first */
      if (T.bake && T.kinds) {
        var vs = [], v, ht, kind, row, step;
        for (k = 0; k < 4; k++) {
          kind = T.kinds[k % T.kinds.length]; ht = H * (T.h[0] + r() * (T.h[1] - T.h[0]));
          vs.push(mkTree(ht, kind, (r() * 1000) | 0, palFor(kind, k), { shadow: false }));
        }
        for (row = 0; row < T.rows; row++) {
          for (x = -10; x < W + 20; x += T.step * (.6 + r() * .8)) {
            v = vs[(r() * vs.length) | 0];
            var sc = (.8 + r() * .4) * (1 + row * .1), fy = e(x) + row * H * (T.h[1] > .03 ? .011 : .006) + r() * H * .005 + 3;
            g.drawImage(v.c, x - v.ox * sc, fy - v.oy * sc, v.w * sc, v.h * sc);
          }
        }
      }
      if (T.shrub) {                                       /* undergrowth hides trunk bases */
        var sv = [];
        for (k = 0; k < 3; k++) sv.push(mkTree(H * T.shrub * (.9 + r() * .4), 3, (r() * 1000) | 0, palFor(0, k + 1), { shadow: false }));
        var offs = T.rows > 1 ? [.05, .066] : [.012];
        offs.forEach(function (of) {
          for (x = -10; x < W + 20; x += 9 + r() * 8) {
            v = sv[(r() * sv.length) | 0];
            var fy2 = e(x) + H * of + r() * H * .006;
            g.drawImage(v.c, x - v.ox, fy2 - v.oy, v.w, v.h);
          }
        });
      }
      /* atmospheric perspective */
      if (L.haze) {
        g.globalCompositeOperation = 'source-atop';
        var hg = g.createLinearGradient(0, 0, 0, hh);
        hg.addColorStop(0, hexA(L.haze[0], L.haze[1] * .7)); hg.addColorStop(1, hexA(L.haze[0], L.haze[1] * 1.3));
        g.fillStyle = hg; g.fillRect(0, 0, W, hh); g.globalCompositeOperation = 'source-over';
      }
      L.hs = c; L.top = top; L.hh = hh;

      /* animated near trees (with leaf shimmer) */
      L.list = [];
      if (L.anim) {
        var A = L.anim, vv = [];
        for (k = 0; k < 4; k++) {
          kind = A.kinds[k % A.kinds.length]; ht = H * (A.h[0] + r() * (A.h[1] - A.h[0]));
          var sd = (r() * 1000) | 0, pal = palFor(kind, k), tv = mkTree(ht, kind, sd, pal, { shadow: true });
          tv.c2 = kind !== 1 ? mkTree(ht, kind, sd, pal, { canopyOnly: true, dseed: sd + 99 }) : null;
          vv.push(tv);
        }
        var nT = Math.max(3, Math.round(W / 270));
        for (k = 0; k < nT; k++) L.list.push({ x: (k + .25 + r() * .5) / nT * W, seed: r() * 10, v: vv[(r() * vv.length) | 0], s: .85 + r() * .3 });
      }
    }

    /* ================= soil, pebbles, grass, flowers ================= */
    function blade(g, x, y, h, lean, w, col) {
      g.fillStyle = col; g.beginPath(); g.moveTo(x - w, y);
      g.quadraticCurveTo(x - w * .4 + lean * .3, y - h * .55, x + lean, y - h);
      g.quadraticCurveTo(x + w * .4 + lean * .35, y - h * .5, x + w, y);
      g.closePath(); g.fill();
    }

    function bakeSoil(L, i) {
      var x, y, miny = 1e9;
      for (x = 0; x <= W; x += 12) miny = Math.min(miny, baseY(L, x));
      var top = Math.floor(miny - H * .05), hh = Math.ceil(H * 1.12 - top);
      var sw = Math.ceil(W), sh = hh, r = rng(200), nz = L.nz, nz2 = makeNoise(91);
      var ey = new Float32Array(sw + 2); for (x = 0; x < sw + 2; x++) ey[x] = baseY(L, x) - top;
      var hm = new Float32Array(sw * sh);
      for (y = 0; y < sh; y++) for (x = 0; x < sw; x++) hm[y * sw + x] = nz2.f(x * .04, y * .05, 4) * .65 + nz2.f(x * .16 + 40, y * .18, 3) * .35;

      var sc = mk(sw, sh), sg = sc.getContext('2d'), im = sg.createImageData(sw, sh), d = im.data;
      var CD = hex('#3a2a1d'), CM = hex('#7a5636'), CL = hex('#b48d5e'), CG = hex('#2c4a22'), CG2 = hex('#4b7a30');
      for (y = 0; y < sh; y++) for (x = 0; x < sw; x++) {
        var dd = y - ey[x]; if (dd < -3) continue;
        var i2 = y * sw + x,
          hx = (x > 0 && x < sw - 1) ? hm[i2 + 1] - hm[i2 - 1] : 0,
          hy2 = (y > 0 && y < sh - 1) ? hm[i2 + sw] - hm[i2 - sw] : 0,
          lt = clamp(.7 - hx * 5.2 + hy2 * 6.2, .3, 1.3),
          v = nz.f(x * .006 + 3, y * .01, 3), patch = sm(.5, .72, nz2.f(x * .012 + 9, y * .02, 3));
        var col = mix(mix(CD, CM, sm(.25, .75, v)), CL, patch * .7);
        col = mix(col, CD, .45 * (1 - sm(0, 70, dd)));
        var gf = 1 - sm(1, 10 + nz2.f(x * .09, 3.3, 2) * 14, dd);
        var creep = sm(.52, .74, nz2.f(x * .022 + 5, y * .07, 3)) * (1 - sm(6, 80, dd));
        col = mix(col, mix(CG, CG2, hm[i2]), Math.max(gf * .9, creep * .7));
        var shade = lt * (.92 + (r() - .5) * .16) * (1 - .3 * sm(.35, 1, y / sh)), o = i2 * 4;
        d[o] = clamp(col[0] * shade, 0, 255); d[o + 1] = clamp(col[1] * shade, 0, 255); d[o + 2] = clamp(col[2] * shade, 0, 255);
        d[o + 3] = 255 * sm(-3, 1, dd);
      }
      sg.putImageData(im, 0, 0);

      var c = mk(W * dpr, hh * dpr), g = c.getContext('2d');
      g.scale(dpr, dpr); g.imageSmoothingEnabled = true; g.drawImage(sc, 0, 0, sw, sh);

      /* pebbles with contact shadow + stone shading */
      var np = Math.round(W / 36), k;
      for (k = 0; k < np; k++) {
        x = r() * W; var ye = ey[x | 0], py = ye + 10 + r() * Math.min(130, sh - ye - 14), s = 2 + r() * r() * 10;
        g.fillStyle = 'rgba(20,12,6,.45)'; g.beginPath(); g.ellipse(x - s * .25, py + s * .5, s * 1.2, s * .45, 0, 0, TAU); g.fill();
        var pg = g.createRadialGradient(x + s * .3, py - s * .3, 0, x, py, s * 1.15);
        pg.addColorStop(0, '#d2c7b2'); pg.addColorStop(.55, '#85796a'); pg.addColorStop(1, '#4a4038');
        g.fillStyle = pg; g.beginPath(); g.ellipse(x, py, s, s * .76, r() * .6 - .3, 0, TAU); g.fill();
      }
      /* wild flowers */
      var nf = Math.round(W / 55);
      for (k = 0; k < nf; k++) {
        x = r() * W; var fy = ey[x | 0] + 2, fh = 10 + r() * 18, fc = FLOWER_COL[(r() * FLOWER_COL.length) | 0], lean = (r() - .5) * 6;
        g.strokeStyle = '#3f7a3a'; g.lineWidth = 1; g.beginPath(); g.moveTo(x, fy); g.quadraticCurveTo(x + lean * .2, fy - fh * .5, x + lean, fy - fh); g.stroke();
        var fr = 1.5 + r() * 1.1; g.fillStyle = fc;
        for (var p = 0; p < 5; p++) { g.beginPath(); g.arc(x + lean + Math.cos(p * 1.2566) * fr, fy - fh + Math.sin(p * 1.2566) * fr, fr * .8, 0, TAU); g.fill(); }
        g.fillStyle = '#e3a52a'; g.beginPath(); g.arc(x + lean, fy - fh, fr * .55, 0, TAU); g.fill();
      }
      /* three rows of tapered grass blades */
      [{ st: 1.8, h: [5, 13], c: [0, 1] }, { st: 2.2, h: [8, 20], c: [1, 2, 3] }, { st: 2.8, h: [10, 26], c: [2, 3, 4] }, { st: 4.6, h: [14, 34], c: [3, 4, 5] }].forEach(function (row) {
        for (x = 0; x < W + 4; x += row.st) {
          var xx = x + (r() - .5) * row.st, bh = row.h[0] + r() * (row.h[1] - row.h[0]);
          blade(g, xx, ey[clamp(xx | 0, 0, sw)] + 3, bh, (r() - .5) * bh * .7, .8 + r() * .9, GRASS_COL[row.c[(r() * row.c.length) | 0]]);
        }
      });
      L.hs = c; L.top = top; L.hh = hh;
    }

    /* ================= build (on load / resize) ================= */
    function build() {
      W = window.innerWidth; H = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, W < 700 ? 1 : dprMax);
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bg = bakeBG();

      LDEF.forEach(function (L, i) {
        L.ph = i * 2.7 + .4; L.nz = makeNoise(40 + i * 11); L.off = 0; L.list = [];
        if (L.soil) bakeSoil(L, i); else bakeHill(L, i);
      });

      blades = []; var rb = rng(5), x;
      for (x = 0; x < W + 18; x += 9) blades.push({ x: x + (rb() - .5) * 6, h: 12 + rb() * 22, p: rb() * 6.28, w: 1.2 + rb() * .8 });

      if (!leaves.length) {
        var r3 = rng(21), nl = W < 700 ? Math.ceil(CFG.leaves / 2) : CFG.leaves, j;
        for (j = 0; j < nl; j++) leaves.push({
          x: r3() * W, y: r3() * H, s: 5 + r3() * 6, vy: 20 + r3() * 24, ph: r3() * 6.28, rot: r3() * 6.28,
          vr: (.4 + r3() * .9) * (r3() < .5 ? -1 : 1), spr: leafSpr[Math.floor(r3() * leafSpr.length)], a: .6 + r3() * .3
        });
        var r4 = rng(55), nf = W < 700 ? Math.ceil(CFG.motes / 2) : CFG.motes;
        for (j = 0; j < nf; j++) motes.push({
          x: r4(), y: .1 + r4() * .85, ax: 30 + r4() * 70, ay: 20 + r4() * 50,
          fx: .15 + r4() * .3, fy: .15 + r4() * .3, ph: r4() * 6.28, s: 4 + r4() * 8
        });
        var r5 = rng(77), ncl = W < 700 ? Math.ceil(CFG.clouds / 2) : CFG.clouds;
        for (j = 0; j < ncl; j++) {
          var z = r5(), scl = 1.35 - z * .8;
          clouds.push({ spr: cloudSpr[j % cloudSpr.length], s: scl, z: z, x: r5() * (W + 600) - 480, y: H * (.025 + z * .36),
            v: 2.2 + scl * 5, a: .5 + (1 - z) * .4 });
        }
        clouds.sort(function (a, b) { return b.z - a.z; });
        for (var gI = 0; gI * 3 < CFG.birds; gI++) flocks.push({ y: H * (.07 + Math.random() * .26), v: 30 + Math.random() * 30, k: (.5 + Math.random() * .55) * 1.1,
          d: Math.random() < .78 ? 1 : -1, x: Math.random() * W * 1.4 - W * .2 });
        for (var bI = 0; bI < CFG.birds; bI++) {
          var G = flocks[(bI / 3) | 0];
          birds.push({ G: G, ox: -((bI % 3) * (22 + Math.random() * 10)) * G.d + (Math.random() - .5) * 8,
            oy: (bI % 3) * (7 + Math.random() * 5) * (Math.random() < .5 ? -1 : 1), ph: Math.random() * 6.28,
            flap: Math.random() < .6, ft: Math.random() * 2, k: G.k * (.85 + Math.random() * .3) });
        }
        var bcol = ['#f0a43a', '#f6e27a', '#fbfbf0', '#8fb8e8'];
        for (j = 0; j < CFG.butterflies; j++) bflies.push({ cx: Math.random() * W, cy: H * (.84 + Math.random() * .08), ph: Math.random() * 6.28,
          sp: .6 + Math.random() * .6, col: bcol[j % 4] });
      }
    }

    /* ================= per-frame drawing ================= */
    function base() { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }

    function drawRays(t) {
      var ox = W * .85, oy = -H * .08, len = H * 1.45;
      ctx.globalCompositeOperation = 'lighter';
      for (var i = 0; i < 4; i++) {
        var phi = .28 + i * .16 + Math.sin(t * .15 + i) * .035, w = len * (.2 + .04 * Math.sin(t * .2 + i * 2));
        var cs = Math.cos(phi), sn = Math.sin(phi);
        ctx.setTransform(dpr * cs, dpr * sn, -dpr * sn, dpr * cs, ox * dpr, oy * dpr);
        ctx.globalAlpha = .085 * (.6 + .4 * Math.sin(t * .3 + i * 1.7));
        ctx.drawImage(beam, -w / 2, 0, w, len);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; base();
    }

    function drawClouds(dt) {
      var mob = W < 700 ? .7 : 1;
      for (var i = 0; i < clouds.length; i++) {
        var c = clouds[i], w = 480 * c.s * mob, h = 210 * c.s * mob;
        c.x += c.v * dt;
        if (c.x > W + 20) c.x = -w - 20;
        ctx.globalAlpha = Math.min(1, c.a);
        ctx.drawImage(c.spr, c.x, c.y - (prog - .5) * H * .03 * (1 - c.z), w, h);
      }
      ctx.globalAlpha = 1;
    }

    function drawCloudShadows() {
      var mob = W < 700 ? .7 : 1;
      for (var i = 0; i < Math.min(3, clouds.length); i++) {
        var c = clouds[clouds.length - 1 - i], w = 480 * c.s * mob;
        ctx.globalAlpha = .13 * c.a;
        ctx.drawImage(shadowSpr, c.x - w * .25, H * (.78 + i * .03), w * 1.3, H * .08);
      }
      ctx.globalAlpha = 1;
    }

    function drawBirds(t, dt) {
      var i, G;
      for (i = 0; i < flocks.length; i++) {
        G = flocks[i]; G.x += G.v * G.d * dt;
        if (G.d > 0 && G.x > W + 220) { G.x = -220 - Math.random() * 300; G.y = H * (.07 + Math.random() * .26); }
        if (G.d < 0 && G.x < -220) { G.x = W + 220 + Math.random() * 300; G.y = H * (.07 + Math.random() * .26); }
      }
      for (i = 0; i < birds.length; i++) {
        var b = birds[i]; G = b.G;
        b.ft -= dt;
        if (b.ft <= 0) { b.flap = !b.flap; b.ft = b.flap ? 1.2 + Math.random() * 1.8 : 1.6 + Math.random() * 3; }
        if (b.flap) b.ph += dt * (9 + b.k * 2);
        var fr = b.flap ? Math.floor(((b.ph % TAU) / TAU) * NF) % NF : NF;
        var x = G.x + b.ox, y = G.y + b.oy + Math.sin(t * .5 + b.k * 7) * 8;
        ctx.setTransform(dpr * G.d * b.k, 0, 0, dpr * b.k, x * dpr, y * dpr);
        ctx.globalAlpha = .55 + .4 * clamp(b.k / 1.4, 0, 1);
        ctx.drawImage(birdSpr[fr], -36, -24, 72, 44);
      }
      ctx.globalAlpha = 1; base();
    }

    function drawHill(L) { ctx.drawImage(L.hs, 0, L.top + L.off, W, L.hh); }

    function drawTrees(L, t, g) {
      var amp = L.anim.sway * CFG.wind * g;
      for (var i = 0; i < L.list.length; i++) {
        var tr = L.list[i], v = tr.v, sc = tr.s;
        var sw = (Math.sin(t * .8 + tr.seed) * .6 + Math.sin(t * 1.9 + tr.seed * 2.3) * .25) * amp + .02 * CFG.wind * g;
        ctx.setTransform(dpr * sc, 0, -sw * dpr * sc, dpr * sc, tr.x * dpr, (hy(L, tr.x) + 3) * dpr);
        ctx.drawImage(v.c, -v.ox, -v.oy, v.w, v.h);
        if (v.c2) {                                          // leaf shimmer: second dot-jitter fades in/out
          ctx.globalAlpha = .22 + .22 * Math.sin(t * 1.7 + tr.seed * 3);
          ctx.drawImage(v.c2.c, -v.ox, -v.oy, v.w, v.h); ctx.globalAlpha = 1;
        }
      }
      base();
    }

    function drawMist(t, k) {
      var span = W * 1.7, sp = 14 + k * 7;
      ctx.globalAlpha = .24;
      var x = ((t * sp + k * span * .45) % span) - W * .5;
      ctx.drawImage(mist, x, H * (.66 + k * .07), W * .8, H * .2);
      ctx.globalAlpha = 1;
    }

    function drawMotes(t) {
      ctx.globalCompositeOperation = 'lighter';
      for (var i = 0; i < motes.length; i++) {
        var f = motes[i];
        var x = f.x * W + Math.sin(t * f.fx + f.ph) * f.ax, y = f.y * H + Math.cos(t * f.fy + f.ph * 1.3) * f.ay;
        var p = .5 + .5 * Math.sin(t * 1.1 + f.ph * 3);
        ctx.globalAlpha = .05 + .32 * p * p;
        ctx.drawImage(glow, x - f.s / 2, y - f.s / 2, f.s, f.s);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }

    function drawGrass(L, t, gs) {
      var cols = ['#2a6328', '#4a9034', '#86b843'];
      for (var k = 0; k < 3; k++) {
        ctx.fillStyle = cols[k]; ctx.beginPath();
        for (var i = k; i < blades.length; i += 3) {
          var b = blades[i], y = hy(L, b.x) + 3;
          var wave = Math.sin(t * 1.7 * CFG.wind - b.x * .011 + b.p * .25) * .55 + Math.sin(t * 3.1 - b.x * .03 + b.p) * .2;
          var sw = (wave * 5 + gs * 3 * CFG.wind) * (b.h / 22);
          ctx.moveTo(b.x - b.w, y);
          ctx.quadraticCurveTo(b.x - b.w * .3 + sw * .35, y - b.h * .55, b.x + sw, y - b.h);
          ctx.quadraticCurveTo(b.x + b.w * .3 + sw * .4, y - b.h * .5, b.x + b.w, y);
        }
        ctx.fill();
      }
    }

    function drawButterflies(t, dt) {
      for (var i = 0; i < bflies.length; i++) {
        var b = bflies[i];
        b.cx += (7 + 5 * Math.sin(t * .2 + b.ph)) * dt * b.sp; if (b.cx > W + 40) b.cx = -40;
        var x = b.cx + Math.sin(t * .7 * b.sp + b.ph) * 50, y = b.cy + Math.sin(t * 1.3 + b.ph) * 20 + Math.sin(t * 3.1 + b.ph) * 4;
        var f = .2 + .8 * Math.abs(Math.sin(t * 13 + b.ph));
        ctx.setTransform(dpr, 0, 0, dpr, x * dpr, y * dpr);
        ctx.fillStyle = b.col; ctx.globalAlpha = .95;
        ctx.beginPath(); ctx.ellipse(-3.4 * f, -2.4, 4.2 * f, 3.2, -.5, 0, TAU); ctx.fill();
        ctx.beginPath(); ctx.ellipse(3.4 * f, -2.4, 4.2 * f, 3.2, .5, 0, TAU); ctx.fill();
        ctx.fillStyle = 'rgba(40,30,20,.55)';
        ctx.beginPath(); ctx.ellipse(-2.6 * f, 1.8, 2.6 * f, 2, .4, 0, TAU); ctx.fill();
        ctx.beginPath(); ctx.ellipse(2.6 * f, 1.8, 2.6 * f, 2, -.4, 0, TAU); ctx.fill();
        ctx.fillStyle = '#2a2018'; ctx.fillRect(-.5, -3.5, 1, 7);
      }
      ctx.globalAlpha = 1; base();
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
      prog += (progT - prog) * Math.min(1, dt * 3.5);
      LDEF.forEach(function (L) { L.off = (prog - .5) * L.par * H * 3; });
      ctx.drawImage(bg, 0, 0, W, H);
      drawClouds(dt);
      if (CFG.rays) drawRays(t);
      drawBirds(t, dt);
      drawHill(LDEF[0]);
      drawMist(t, 0);
      drawHill(LDEF[1]);
      drawMist(t, 1);
      drawHill(LDEF[2]);
      drawTrees(LDEF[2], t, g);
      if (CFG.shadows) drawCloudShadows();
      drawMotes(t);
      drawHill(LDEF[3]);
      if (CFG.grass) drawGrass(LDEF[3], t, g);
      drawButterflies(t, dt);
      drawLeaves(t, dt, g);
    }

    /* ================= run ================= */
    function onScroll() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      progT = Math.min(1, Math.max(0, window.scrollY / max));
    }

    makeStatic(); build(); onScroll(); prog = progT;
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
        dprMax = 1; CFG.rays = false; CFG.shadows = false;
        leaves.length = Math.ceil(leaves.length / 2);
        motes.length = Math.ceil(motes.length / 2);
        build();
        frame(T, 0);                // redraw at once so the sky never flashes black
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
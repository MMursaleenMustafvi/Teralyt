// Terralyt procedural 3D models for the FDA City society scene (three.js).
// Every landmark on the official FDA City block maps has a builder here:
// mosque, school, playground, commercial centre (with dispensary and water tank),
// park, hospital, sports complex, public building, university, cricket stadium,
// IMAX theatre, multi-purpose zone, grid station, graveyard, CNG station, shrine,
// main gate and roundabout monuments (Clock Tower replica, fountain).
//
// Builders work in a local frame: X along the footprint's long axis (length L),
// Z across it (width W), Y up, origin at the footprint centre, ground at y = 0.
// They add meshes through a "kit" (see makeKit) so society3d.js can merge
// everything by material into a few draw calls.
import * as THREE from 'three';

export const FLOOR = 3.4;
const PI = Math.PI;

export function rng(seed) {
  let a = (seed >>> 0) || 1;
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}

// ---------------------------------------------------------------------------
// textures
// ---------------------------------------------------------------------------
function cv(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); return c; }
function tex(c, { repeat = true, srgb = true } = {}) {
  const t = new THREE.CanvasTexture(c);
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
function speckle(g, w, h, cols, n, seed, smin = 1, smax = 3, amin = .2, amax = .5) {
  const r = rng(seed);
  for (let i = 0; i < n; i++) { g.globalAlpha = amin + r() * (amax - amin); g.fillStyle = cols[(r() * cols.length) | 0]; const s = smin + r() * (smax - smin); g.fillRect(r() * w, r() * h, s, s); }
  g.globalAlpha = 1;
}
const groundTex = (base, cols, n, seed, extra) => tex(cv(256, 256, (g, w, h) => { g.fillStyle = base; g.fillRect(0, 0, w, h); speckle(g, w, h, cols, n, seed); if (extra) extra(g, w, h); }));

function facadeTex(o) {
  // 4 bays x 4 floors on a 512 px tile; returns colour map + night (emissive) map
  const r = rng(o.seed || 7);
  const lit = [];
  for (let i = 0; i < 16; i++) lit.push(r() < (o.lit == null ? .45 : o.lit));
  const draw = (night) => (g, w, h) => {
    g.fillStyle = night ? '#000' : o.wall; g.fillRect(0, 0, w, h);
    if (!night && o.wallNoise) speckle(g, w, h, o.wallNoise, 3000, 3, 1, 2, .15, .3);
    for (let fy = 0; fy < 4; fy++) for (let bx = 0; bx < 4; bx++) {
      const x0 = bx * 128, y0 = fy * 128;
      if (!night && o.band) { g.fillStyle = o.band; g.fillRect(x0, y0 + 118, 128, 10); }
      const wx = x0 + (o.wide ? 10 : 30), ww = o.wide ? 108 : 68, wy = y0 + 26, wh = o.tall ? 88 : 64;
      const on = lit[fy * 4 + bx];
      if (night) { if (on) { g.fillStyle = r() < .8 ? '#ffd28a' : '#cfe4ff'; g.fillRect(wx + 3, wy + 3, ww - 6, wh - 6); } continue; }
      g.fillStyle = o.frame || '#f4f1ea';
      if (o.arch) { g.beginPath(); g.moveTo(wx - 4, wy + wh + 4); g.lineTo(wx - 4, wy + 26); g.arc(wx + ww / 2, wy + 26, ww / 2 + 4, PI, 0); g.lineTo(wx + ww + 4, wy + wh + 4); g.fill(); }
      else g.fillRect(wx - 4, wy - 4, ww + 8, wh + 8);
      const grd = g.createLinearGradient(wx, wy, wx + ww, wy + wh); grd.addColorStop(0, o.glass || '#3d5566'); grd.addColorStop(1, o.glass2 || '#6f8ea3');
      g.fillStyle = grd;
      if (o.arch) { g.beginPath(); g.moveTo(wx, wy + wh); g.lineTo(wx, wy + 26); g.arc(wx + ww / 2, wy + 26, ww / 2, PI, 0); g.lineTo(wx + ww, wy + wh); g.fill(); }
      else g.fillRect(wx, wy, ww, wh);
      g.fillStyle = o.frame || '#f4f1ea'; g.fillRect(wx + ww / 2 - 2, wy, 4, wh); if (!o.arch) g.fillRect(wx, wy + wh * .45, ww, 3);
      if (o.sill) { g.fillStyle = o.sill; g.fillRect(wx - 8, wy + wh + 4, ww + 16, 6); }
    }
  };
  return { map: tex(cv(512, 512, draw(false))), emi: tex(cv(512, 512, draw(true))) };
}

function footballTex() {
  return tex(cv(1024, 640, (g, w, h) => {
    for (let i = 0; i < 14; i++) { g.fillStyle = i % 2 ? '#4f9a3f' : '#5aa647'; g.fillRect(i * w / 14, 0, w / 14 + 1, h); }
    speckle(g, w, h, ['#3f7f32', '#6dbb57'], 5000, 11);
    g.strokeStyle = '#f4f4f0'; g.lineWidth = 5;
    const m = 30; g.strokeRect(m, m, w - 2 * m, h - 2 * m);
    g.beginPath(); g.moveTo(w / 2, m); g.lineTo(w / 2, h - m); g.stroke();
    g.beginPath(); g.arc(w / 2, h / 2, 70, 0, 2 * PI); g.stroke();
    for (const s of [0, 1]) {
      const x = s ? w - m : m, d = s ? -1 : 1;
      g.strokeRect(Math.min(x, x + d * 150), h / 2 - 160, 150, 320);
      g.strokeRect(Math.min(x, x + d * 55), h / 2 - 75, 55, 150);
      g.beginPath(); g.arc(x + d * 105, h / 2, 4, 0, 2 * PI); g.fillStyle = '#fff'; g.fill();
    }
    g.fillStyle = '#c9a874'; g.fillRect(w / 2 - 14, h / 2 - 90, 28, 180); // cricket pitch strip
  }), { repeat: false });
}
function courtTex(base, inner, line, kind) {
  return tex(cv(256, 512, (g, w, h) => {
    g.fillStyle = base; g.fillRect(0, 0, w, h); g.fillStyle = inner; g.fillRect(20, 30, w - 40, h - 60);
    g.strokeStyle = line; g.lineWidth = 4; g.strokeRect(20, 30, w - 40, h - 60);
    if (kind === 'tennis') { g.beginPath(); g.moveTo(20, h / 2); g.lineTo(w - 20, h / 2); g.moveTo(w / 2, 30 + 80); g.lineTo(w / 2, h - 110); g.moveTo(20, 110); g.lineTo(w - 20, 110); g.moveTo(20, h - 110); g.lineTo(w - 20, h - 110); g.stroke(); }
    else { g.beginPath(); g.moveTo(20, h / 2); g.lineTo(w - 20, h / 2); g.stroke(); g.beginPath(); g.arc(w / 2, h / 2, 34, 0, 2 * PI); g.stroke(); g.beginPath(); g.arc(w / 2, 30, 90, 0, PI); g.stroke(); g.beginPath(); g.arc(w / 2, h - 30, 90, PI, 2 * PI); g.stroke(); }
  }), { repeat: false });
}
function textTex(text, o = {}) {
  const w = o.w || 1024, h = o.h || 256;
  return tex(cv(w, h, (g) => {
    g.fillStyle = o.bg || '#1f5a38'; g.fillRect(0, 0, w, h);
    g.strokeStyle = o.border || '#d4a640'; g.lineWidth = 14; g.strokeRect(7, 7, w - 14, h - 14);
    g.fillStyle = o.fg || '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
    let size = o.size || h * .5;
    g.font = `800 ${size}px "Segoe UI", Arial, sans-serif`;
    while (g.measureText(text).width > w * .88 && size > 10) { size -= 4; g.font = `800 ${size}px "Segoe UI", Arial, sans-serif`; }
    g.fillText(text, w / 2, h / 2 + 4);
  }), { repeat: false });
}
function clockTex() {
  return tex(cv(256, 256, (g, w) => {
    g.fillStyle = '#f7f1e1'; g.beginPath(); g.arc(128, 128, 122, 0, 2 * PI); g.fill();
    g.lineWidth = 8; g.strokeStyle = '#2b2118'; g.stroke();
    for (let i = 0; i < 12; i++) { const a = i / 12 * 2 * PI; g.lineWidth = i % 3 ? 4 : 8; g.beginPath(); g.moveTo(128 + Math.sin(a) * 92, 128 - Math.cos(a) * 92); g.lineTo(128 + Math.sin(a) * 110, 128 - Math.cos(a) * 110); g.stroke(); }
    g.lineWidth = 8; g.beginPath(); g.moveTo(128, 128); g.lineTo(128 + 50, 128 - 30); g.stroke();
    g.lineWidth = 5; g.beginPath(); g.moveTo(128, 128); g.lineTo(128 - 10, 128 - 85); g.stroke();
  }), { repeat: false });
}
function flagTex() {
  return tex(cv(300, 200, (g, w, h) => {
    g.fillStyle = '#fff'; g.fillRect(0, 0, w * .25, h); g.fillStyle = '#01411c'; g.fillRect(w * .25, 0, w * .75, h);
    g.fillStyle = '#fff'; g.beginPath(); g.arc(w * .62, h * .5, h * .3, 0, 2 * PI); g.fill();
    g.fillStyle = '#01411c'; g.beginPath(); g.arc(w * .67, h * .44, h * .27, 0, 2 * PI); g.fill();
    g.fillStyle = '#fff'; g.beginPath();
    const cx = w * .72, cy = h * .36, R = h * .09;
    for (let i = 0; i < 10; i++) { const a = -PI / 2 + i * PI / 5 + .5, rr = i % 2 ? R * .45 : R; g.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); }
    g.fill();
  }), { repeat: false });
}
function helipadTex() {
  return tex(cv(256, 256, (g) => {
    g.fillStyle = '#3a3d40'; g.fillRect(0, 0, 256, 256);
    g.strokeStyle = '#f2c230'; g.lineWidth = 10; g.beginPath(); g.arc(128, 128, 110, 0, 2 * PI); g.stroke();
    g.fillStyle = '#fff'; g.fillRect(78, 66, 26, 124); g.fillRect(152, 66, 26, 124); g.fillRect(100, 116, 56, 24);
  }), { repeat: false });
}
function parkingTex() {
  return tex(cv(256, 256, (g, w, h) => {
    g.fillStyle = '#45474b'; g.fillRect(0, 0, w, h); speckle(g, w, h, ['#2f3033', '#5a5c60'], 1500, 5);
    g.fillStyle = '#e9e9e2'; for (let x = 0; x < w; x += 64) g.fillRect(x, 0, 5, h * .62); g.fillRect(0, h * .62, w, 4);
  }));
}
function seatsTex() {
  return tex(cv(64, 256, (g, w, h) => { for (let y = 0; y < h; y += 16) { g.fillStyle = (y / 16) % 4 === 0 ? '#e8e2d2' : '#2f7d4f'; g.fillRect(0, y, w, 12); g.fillStyle = '#7d7a74'; g.fillRect(0, y + 12, w, 4); } }));
}

function waterNormals() {
  // tileable ripple normal map from summed sine waves
  const S = 256, c = cv(S, S, (g) => {
    const im = g.createImageData(S, S), r = rng(77), waves = [];
    for (let i = 0; i < 9; i++) waves.push([Math.round((r() - .5) * 8) || 1, Math.round((r() - .5) * 8) || 2, r() * 6.28, .4 + r() * .6]);
    for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
      let dx = 0, dy = 0;
      for (const [kx, ky, ph, a] of waves) { const t = 2 * PI * (kx * x + ky * y) / S + ph, c_ = Math.cos(t) * a; dx += c_ * kx; dy += c_ * ky; }
      const nx = -dx * .05, ny = -dy * .05, l = Math.hypot(nx, ny, 1), i = (y * S + x) * 4;
      im.data[i] = (nx / l * .5 + .5) * 255; im.data[i + 1] = (ny / l * .5 + .5) * 255; im.data[i + 2] = (1 / l * .5 + .5) * 255; im.data[i + 3] = 255;
    }
    g.putImageData(im, 0, 0);
  });
  return tex(c, { srgb: false });
}

// ---------------------------------------------------------------------------
// materials
// ---------------------------------------------------------------------------
export function createMaterials() {
  const S = (color, o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color, roughness: .85, metalness: 0 }, o));
  const T = (map, o = {}) => new THREE.MeshStandardMaterial(Object.assign({ map, roughness: .9, metalness: 0 }, o));
  const night = [];
  const facade = (o, extra = {}) => { const t = facadeTex(o); const m = new THREE.MeshStandardMaterial(Object.assign({ map: t.map, roughness: .8, emissive: new THREE.Color('#ffffff'), emissiveMap: t.emi, emissiveIntensity: 0 }, extra)); night.push(m); return m; };
  const metres = (t, size) => { t.repeat.set(1 / size, 1 / size); return t; }; // for meshes whose uv is in metres
  const M = {
    // ground (uv in metres)
    grass: T(metres(groundTex('#5d8c42', ['#4a7a35', '#6f9f4f', '#7aa652', '#3f6b2d'], 2600, 1), 9)),
    lawn: T(metres(groundTex('#68a04b', ['#579040', '#79b158', '#86bb60', '#4c8139'], 2600, 2), 7)),
    paving: T(metres(groundTex('#c7bfb0', ['#b3ab9c', '#d6cfc1'], 900, 3, (g, w, h) => { g.strokeStyle = 'rgba(90,80,65,.35)'; g.lineWidth = 2; for (let i = 0; i <= w; i += 64) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, h); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(w, i); g.stroke(); } }), 4)),
    sidewalk: T(metres(groundTex('#b8b0a2', ['#a49c8e', '#cbc4b7'], 900, 4, (g, w, h) => { g.strokeStyle = 'rgba(70,62,52,.3)'; g.lineWidth = 2; for (let i = 0; i <= w; i += 32) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, h); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(w, i); g.stroke(); } }), 4)),
    asphalt: T(metres(groundTex('#3a3b3e', ['#2c2d30', '#4a4b4f', '#55565a'], 4000, 5, null), 6), { roughness: .95 }),
    dirt: T(metres(groundTex('#a08865', ['#8f7655', '#b39a74', '#7d6747'], 3000, 6), 6)),
    gravel: T(metres(groundTex('#a29d95', ['#8a857d', '#bdb8ae', '#6f6b65'], 6000, 7, null), 3)),
    marble: T(metres(groundTex('#ecebe6', ['#dcdad3', '#f7f6f2'], 600, 8, (g, w, h) => { g.strokeStyle = 'rgba(150,145,135,.35)'; g.lineWidth = 2; for (let i = 0; i <= w; i += 128) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, h); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(w, i); g.stroke(); } }), 2), { roughness: .35 }),
    track: T(metres(groundTex('#b05038', ['#9c4430', '#c25e45'], 2000, 9), 3)),
    flowers: T(metres(groundTex('#3f7a33', ['#e84a5f', '#ffd23f', '#f78c2b', '#c86dd7', '#ffffff', '#ff6fa5'], 4000, 10, null), 2)),
    hedge: S('#3d6e31', { roughness: 1 }),
    // vacant land as on the site today: sandy soil with dry scrub; dusty road verges
    scrub: T(metres(groundTex('#ae9c79', ['#9c8a68', '#8f8a62', '#7f8456', '#c3b18d', '#a89470', '#6f7a4c'], 7000, 12, (g, w, h) => {
      const r = rng(31); for (let i = 0; i < 140; i++) { g.globalAlpha = .35; g.fillStyle = r() < .5 ? '#6f7a4c' : '#86825a'; g.beginPath(); g.arc(r() * w, r() * h, 2 + r() * 5, 0, 2 * PI); g.fill(); } g.globalAlpha = 1; }), 9)),
    verge: T(metres(groundTex('#a8997e', ['#998a70', '#b6a88d', '#8d846a'], 3500, 13, null), 5)),
    // plain colours
    white: S('#f2efe8'), cream: S('#e8dcc4'), sand: S('#d6b88a'), brick: S('#a5533a'), concrete: S('#b8b3aa'), darkConcrete: S('#7b7770'),
    roofGray: S('#8f8b84'), roofDark: S('#55524d'), terracotta: S('#a14b30'), wood: S('#7a5232'), red: S('#c3392b'), blue: S('#2e6fb6'),
    yellow: S('#e9b738'), orange: S('#e07b2c'), black: S('#232323'), green: S('#2f7d4f'), purple: S('#6d4fa0'),
    steel: S('#9aa1a8', { metalness: .6, roughness: .35 }), darkSteel: S('#4b5056', { metalness: .5, roughness: .45 }),
    lattice: S('#9aa1a8', { metalness: .6, roughness: .4, wireframe: true }),
    gold: S('#d6a840', { metalness: .85, roughness: .28 }), domeGreen: S('#2e8a57', { metalness: .25, roughness: .35 }), domeWhite: S('#f5f3ee', { roughness: .35 }),
    glass: S('#6b93ab', { metalness: .55, roughness: .08 }), darkGlass: S('#2a3640', { metalness: .4, roughness: .15 }),
    water: S('#3c8fba', { metalness: .2, roughness: .05, emissive: new THREE.Color('#0b3550'), emissiveIntensity: .35 }),
    grave: S('#d9d4c6'), tank: S('#202020', { roughness: .6 }), rubber: S('#2b2b2b'),
    lampOn: new THREE.MeshStandardMaterial({ color: '#fff4d6', emissive: new THREE.Color('#ffd27a'), emissiveIntensity: 0 }),
    // textured fields
    football: T(footballTex()), tennis: T(courtTex('#3f7a62', '#3b6fa8', '#ffffff', 'tennis')), basket: T(courtTex('#9b5a3a', '#c9773f', '#ffffff', 'basket')),
    parking: T(parkingTex()), helipad: T(helipadTex()), seats: T(seatsTex(), { side: THREE.DoubleSide }),
    clock: new THREE.MeshStandardMaterial({ map: clockTex(), emissive: new THREE.Color('#fff2cc'), emissiveIntensity: 0 }),
    flag: new THREE.MeshStandardMaterial({ map: flagTex(), side: THREE.DoubleSide, roughness: .9 }),
    // facades (uv in units of 4 bays x 4 floors)
    facCream: facade({ wall: '#e6d8bd', wallNoise: ['#d8c9ad', '#efe3cb'], sill: '#cdbb98', seed: 1 }),
    facBrick: facade({ wall: '#a8553b', wallNoise: ['#93472f', '#b8634a', '#7f3d29'], frame: '#efe9dc', band: '#e8dfcc', seed: 2 }),
    facWhite: facade({ wall: '#f1efe9', wallNoise: ['#e2dfd7'], frame: '#dfe6ea', glass: '#2d6aa0', glass2: '#6aa8d6', band: '#d2d8dc', seed: 3, lit: .6 }),
    facGlass: facade({ wall: '#46677a', frame: '#9fb4c0', glass: '#2b4d63', glass2: '#7fb0cc', wide: true, tall: true, seed: 4, lit: .55 }, { metalness: .35, roughness: .2 }),
    facSand: facade({ wall: '#d9bd8f', wallNoise: ['#c8aa7b', '#e6cc9f'], frame: '#efe2c4', arch: true, sill: '#bfa274', seed: 5 }),
    facMosque: facade({ wall: '#f4f2ec', wallNoise: ['#e7e4dc'], frame: '#d9c48a', glass: '#2a5d4a', glass2: '#4f8f74', arch: true, tall: true, seed: 6, lit: .7 }),
    facShop: facade({ wall: '#ece6da', frame: '#c8c2b6', glass: '#2d4250', glass2: '#7fa0b4', wide: true, tall: true, seed: 8, lit: .85 }),
    facPink: facade({ wall: '#e6c3b4', wallNoise: ['#d8b2a2'], frame: '#f7efe8', seed: 9 }),
  };
  M.night = night.concat([M.lampOn, M.clock]);
  M.water.normalMap = waterNormals(); M.water.normalMap.repeat.set(.08, .08); M.water.normalScale = new THREE.Vector2(.6, .6);
  return M;
}

// ---------------------------------------------------------------------------
// geometry helpers
// ---------------------------------------------------------------------------
export function facadeBox(w, h, d) {
  // box whose uvs are scaled so a 4-bay x 4-floor facade texture repeats at real size
  const g = new THREE.BoxGeometry(w, h, d);
  const uv = g.attributes.uv, spans = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  const bay = 3.2;
  for (let f = 0; f < 6; f++) for (let i = 0; i < 4; i++) { const k = f * 4 + i; uv.setXY(k, uv.getX(k) * spans[f][0] / (bay * 4), uv.getY(k) * spans[f][1] / (FLOOR * 4)); }
  return g;
}
function onion(r, h) {
  const p = [[0, 0], [1, 0], [1.06, .18], [1.07, .38], [.98, .6], [.8, .8], [.55, .98], [.3, 1.12], [.12, 1.22], [0, 1.3]];
  return new THREE.LatheGeometry(p.map(([x, y]) => new THREE.Vector2(x * r, y * h / 1.3)), 28);
}
function dome(r, h) {
  const p = []; for (let i = 0; i <= 10; i++) { const a = i / 10 * PI / 2; p.push(new THREE.Vector2(Math.cos(a) * r, Math.sin(a) * h)); }
  return new THREE.LatheGeometry(p, 28);
}

// kit: thin wrapper so builders stay readable. Positions are local; y is the base.
export function makeKit(group, M, poly, hooks) {
  const k = { M, poly, top: 0, signs: 0 };
  const add = (geom, mat, x, y, z, ry = 0, opt = {}) => {
    const m = new THREE.Mesh(geom, mat); m.position.set(x, y, z); m.rotation.y = ry;
    if (opt.rx) m.rotation.x = opt.rx; if (opt.rz) m.rotation.z = opt.rz;
    m.castShadow = opt.shadow !== false; m.receiveShadow = true;
    if (opt.keep) m.userData.keep = true;
    if (opt.anim) m.userData.anim = opt.anim;
    group.add(m);
    k.top = Math.max(k.top, y + (geom.boundingBox ? 0 : 0));
    return m;
  };
  const up = (geom, h) => { geom.translate(0, h / 2, 0); return geom; };
  k.raw = add;
  k.box = (w, h, d, mat, x = 0, y = 0, z = 0, ry = 0, opt) => { k.top = Math.max(k.top, y + h); return add(up(new THREE.BoxGeometry(w, h, d), h), mat, x, y, z, ry, opt); };
  k.fbox = (w, h, d, mat, x = 0, y = 0, z = 0, ry = 0) => { k.top = Math.max(k.top, y + h); return add(up(facadeBox(w, h, d), h), mat, x, y, z, ry); };
  k.cyl = (rt, rb, h, seg, mat, x = 0, y = 0, z = 0, opt = {}) => { k.top = Math.max(k.top, y + h); return add(up(new THREE.CylinderGeometry(rt, rb, h, seg, 1, !!opt.open, opt.t0 || 0, opt.tl || 2 * PI), h), mat, x, y, z, opt.ry || 0, opt); };
  k.geo = (geom, mat, x = 0, y = 0, z = 0, ry = 0, opt) => { geom.computeBoundingBox(); k.top = Math.max(k.top, y + geom.boundingBox.max.y); return add(geom, mat, x, y, z, ry, opt); };
  k.plane = (w, d, mat, x = 0, y = 0, z = 0, ry = 0, opt = {}) => { const g = new THREE.PlaneGeometry(w, d); g.rotateX(-PI / 2); if (opt.metres) { const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * w, uv.getY(i) * d); } return add(g, mat, x, y, z, ry, { shadow: false }); };
  k.disc = (r, mat, x = 0, y = 0, z = 0, seg = 32) => { const g = new THREE.CircleGeometry(r, seg); g.rotateX(-PI / 2); const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, (uv.getX(i) - .5) * 2 * r, (uv.getY(i) - .5) * 2 * r); return add(g, mat, x, y, z, 0, { shadow: false }); };
  k.ring = (r0, r1, mat, x = 0, y = 0, z = 0, seg = 48) => { const g = new THREE.RingGeometry(r0, r1, seg); g.rotateX(-PI / 2); const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, p.getX(i), p.getZ(i)); return add(g, mat, x, y, z, 0, { shadow: false }); };
  k.shape = (pts, holes, mat, y = .02, extrude = 0) => {
    const s = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z)));
    for (const h of holes || []) s.holes.push(new THREE.Path(h.map(([x, z]) => new THREE.Vector2(x, -z))));
    const g = extrude ? new THREE.ExtrudeGeometry(s, { depth: extrude, bevelEnabled: false }) : new THREE.ShapeGeometry(s);
    g.rotateX(-PI / 2);
    return add(g, mat, 0, y, 0, 0, { shadow: !!extrude });
  };
  k.ground = (mat, y = .02, inset = 0) => {
    let pts = poly;
    if (inset) { const c = centroid(poly); pts = poly.map(([x, z]) => { const dx = x - c[0], dz = z - c[1], d = Math.hypot(dx, dz) || 1; return [x - dx / d * inset, z - dz / d * inset]; }); }
    return k.shape(pts, null, mat, y);
  };
  k.wall = (h, t, mat, gate = 6, posts = null) => {
    // boundary wall along the footprint, gate gap in the middle of the longest edge
    let longest = 0, li = 0;
    for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length], l = Math.hypot(b[0] - a[0], b[1] - a[1]); if (l > longest) { longest = l; li = i; } }
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length], dx = b[0] - a[0], dz = b[1] - a[1], l = Math.hypot(dx, dz);
      if (l < .5) continue;
      const ry = Math.atan2(-dz, dx);
      const seg = (s0, s1) => { const len = (s1 - s0) * l; if (len < .3) return; const m = (s0 + s1) / 2; k.box(len, h, t, mat, a[0] + dx * m, 0, a[1] + dz * m, ry); };
      if (i === li && gate > 0 && l > gate + 4) {
        const g0 = .5 - gate / 2 / l, g1 = .5 + gate / 2 / l;
        seg(0, g0); seg(g1, 1);
        for (const s of [g0, g1]) k.box(t * 2.2, h * 1.6, t * 2.2, posts || mat, a[0] + dx * s, 0, a[1] + dz * s, ry);
        k.gate = { x: a[0] + dx * .5, z: a[1] + dz * .5, ry, nx: dz / l, nz: -dx / l };
      } else seg(0, 1);
      if (posts) for (let s = 0; s <= l; s += 3) k.box(t * 1.6, h + .3, t * 1.6, posts, a[0] + dx * s / l, 0, a[1] + dz * s / l, ry);
    }
  };
  k.inside = (x, z, margin = 0) => pip(x, z, poly) && edgeDist(x, z, poly) >= margin;
  k.fillTrees = (busy, step = 9, seed = 1, types = ['round', 'round', 'cone']) => {
    const r = rng(seed); let minx = Infinity, maxx = -Infinity, minz = Infinity, maxz = -Infinity;
    for (const [x, z] of poly) { minx = Math.min(minx, x); maxx = Math.max(maxx, x); minz = Math.min(minz, z); maxz = Math.max(maxz, z); }
    for (let x = minx + step / 2; x < maxx; x += step) for (let z = minz + step / 2; z < maxz; z += step) {
      const px = x + (r() - .5) * step * .6, pz = z + (r() - .5) * step * .6;
      if (!k.inside(px, pz, 2.5) || busy.some(([x0, z0, x1, z1]) => px > x0 - 2 && px < x1 + 2 && pz > z0 - 2 && pz < z1 + 2)) continue;
      k.tree(px, pz, types[(r() * types.length) | 0], .8 + r() * .45);
    }
  };
  k.tree = (x, z, type = 'round', s = 1) => hooks.tree(group, x, z, type, s);
  k.lamp = (x, z, ry = 0, type = 'park') => hooks.lamp(group, x, z, ry, type);
  k.car = (x, z, ry = 0, color) => hooks.car(group, x, z, ry, color);
  k.sign = (text, w, h, x, y, z, ry = 0, o = {}) => {
    const t = textTex(text, o);
    const face = new THREE.MeshStandardMaterial({ map: t, emissive: new THREE.Color('#ffffff'), emissiveMap: t, emissiveIntensity: 0, roughness: .6 });
    hooks.nightMat(face);
    const edge = M.darkSteel;
    k.top = Math.max(k.top, y + h);
    return add(new THREE.BoxGeometry(w, h, .18), [edge, edge, edge, edge, face, face], x, y + h / 2, z, ry, { keep: true });
  };
  k.flag = (x, z, h = 10) => {
    k.cyl(.07, .09, h, 8, M.steel, x, 0, z);
    const g = new THREE.PlaneGeometry(2.4, 1.6, 8, 1); g.translate(1.2, 0, 0);
    add(g, M.flag, x, h - 1, z, 0, { keep: true, anim: 'flag' });
  };
  k.bench = (x, z, ry = 0) => { k.box(1.8, .1, .5, M.wood, x, .45, z, ry); k.box(1.8, .45, .1, M.wood, x + Math.sin(ry) * .25, .5, z + Math.cos(ry) * .25, ry); k.box(.1, .45, .45, M.darkSteel, x + Math.cos(ry) * .8, 0, z - Math.sin(ry) * .8, ry); k.box(.1, .45, .45, M.darkSteel, x - Math.cos(ry) * .8, 0, z + Math.sin(ry) * .8, ry); };
  k.building = (w, d, floors, fac, x, z, ry = 0, o = {}) => {
    const h = floors * FLOOR, y0 = o.y || 0;
    k.fbox(w, h, d, fac, x, y0, z, ry);
    k.box(w + .5, .45, d + .5, o.roof || M.roofGray, x, y0 + h, z, ry);
    if (o.parapet !== false) {
      const c = Math.cos(ry), s = Math.sin(ry), P = (lx, lz) => [x + lx * c + lz * s, z - lx * s + lz * c];
      for (const [lx, lz, ww, dd] of [[0, d / 2, w + .5, .25], [0, -d / 2, w + .5, .25], [w / 2, 0, .25, d + .5], [-w / 2, 0, .25, d + .5]]) { const [px, pz] = P(lx, lz); k.box(ww, .9, dd, o.parapetMat || M.cream, px, y0 + h + .45, pz, ry); }
      if (o.tanks !== false && w > 6 && d > 5) { const n = Math.min(3, Math.floor(w / 7)); for (let i = 0; i < n; i++) { const [px, pz] = P(-w / 2 + 2.5 + i * 2.6, -d / 2 + 2); k.cyl(.9, .9, 1.6, 14, i % 2 ? M.tank : M.white, px, y0 + h + .45, pz); } }
    }
    return y0 + h + .45;
  };
  return k;
}

export function centroid(p) { let x = 0, z = 0; for (const q of p) { x += q[0]; z += q[1]; } return [x / p.length, z / p.length]; }
export function pip(x, z, poly) {
  let ins = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i], [xj, zj] = poly[j];
    if (((zi > z) !== (zj > z)) && (x < (xj - xi) * (z - zi) / (zj - zi) + xi)) ins = !ins;
  }
  return ins;
}
function edgeDist(x, z, poly) {
  let d = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const [ax, az] = poly[i], [bx, bz] = poly[(i + 1) % poly.length], dx = bx - ax, dz = bz - az, l2 = dx * dx + dz * dz || 1;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / l2));
    d = Math.min(d, Math.hypot(x - ax - t * dx, z - az - t * dz));
  }
  return d;
}

// ---------------------------------------------------------------------------
// builders
// ---------------------------------------------------------------------------
function minaret(k, x, z, h, M, capMat) {
  k.cyl(.95, 1.2, h * .55, 8, M.white, x, 0, z);
  k.cyl(1.7, 1.25, .5, 8, M.cream, x, h * .55, z);
  k.cyl(.8, .95, h * .3, 8, M.white, x, h * .55 + .5, z);
  k.cyl(1.4, 1.0, .45, 8, M.cream, x, h * .85 + .5, z);
  k.cyl(.75, .75, 1.8, 8, M.white, x, h * .85 + .95, z);
  k.geo(onion(.85, 2.2), capMat, x, h * .85 + 2.75, z);
  k.cyl(.07, .07, 1.4, 6, M.gold, x, h * .85 + 4.9, z);
}

const B = {};

B.mosque = (k, L, W, lm) => {
  const M = k.M, s = Math.min(L, W), green = lm.id % 2 === 0;
  k.ground(M.marble, .03);
  k.wall(1.8, .4, M.cream, 7, M.white);
  const hallW = Math.max(12, W * .62), hallD = Math.max(10, Math.min(L * .42, hallW * .72));
  const x0 = -L / 2 + 4 + hallD / 2, hh = 8;
  k.fbox(hallD, hh, hallW, M.facMosque, x0, .05, 0);
  k.box(hallD + .6, .5, hallW + .6, M.white, x0, hh + .05, 0);
  for (let z = -hallW / 2; z <= hallW / 2 + .01; z += 2) for (const xx of [x0 - hallD / 2, x0 + hallD / 2]) k.box(.5, .8, .5, M.white, xx, hh + .55, z);
  const r = Math.min(hallW, hallD) * .3;
  k.cyl(r * .98, r, 2.2, 28, M.white, x0, hh + .55, 0);
  k.geo(onion(r * 1.02, r * 1.45), green ? M.domeGreen : M.domeWhite, x0, hh + 2.75, 0);
  const fin = hh + 2.75 + r * 1.45;
  k.cyl(.12, .12, 2.2, 8, M.gold, x0, fin, 0); k.geo(new THREE.SphereGeometry(.38, 14, 10), M.gold, x0, fin + 1.2, 0);
  k.geo(new THREE.TorusGeometry(.55, .09, 6, 18, PI * 1.35), M.gold, x0, fin + 2.6, 0, 0, { rz: PI * .3 });
  for (const z of [-hallW * .3, hallW * .3]) { k.cyl(r * .38, r * .38, 1.2, 20, M.white, x0 + hallD * .3, hh + .55, z); k.geo(onion(r * .4, r * .55), green ? M.domeGreen : M.domeWhite, x0 + hallD * .3, hh + 1.75, z); }
  const mh = Math.max(20, s * .45);
  for (const [dx, dz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) minaret(k, x0 + dx * (hallD / 2 + .6), dz * (hallW / 2 + .6), mh, M, green ? M.domeGreen : M.gold);
  // portico with arches and the main iwan
  const xa = x0 + hallD / 2 + 2.2;
  for (let z = -hallW / 2 + 1; z <= hallW / 2 - 1 + .01; z += 3) k.box(.8, 5, .8, M.white, xa, .05, z);
  k.box(1.6, 1.2, hallW, M.white, xa, 5.05, 0);
  k.box(1.8, 11, 7.5, M.white, xa + .2, .05, 0);
  k.box(.4, 8.5, 4.6, M.darkGlass, xa + 1.0, .05, 0);
  k.box(1.9, .5, 8, M.gold, xa + .2, 11.05, 0);
  // ablution pool in the courtyard
  const xc = (xa + L / 2) / 2;
  if (L / 2 - xa > 9) { k.box(4, .45, Math.min(12, W * .4), M.marble, xc, .03, 0); k.box(3.4, .05, Math.min(11.4, W * .4 - .6), M.water, xc, .46, 0); }
  for (const z of [-W / 2 + 3, W / 2 - 3]) k.tree(L / 2 - 4, z, 'cone', .9);
  if (k.gate) k.sign('JAMIA MASJID', 7, 1.4, k.gate.x + k.gate.nx * .4, 2.2, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#1d5e3f', border: '#d6a840' });
};

B.school = (k, L, W, lm) => {
  const M = k.M;
  k.ground(M.paving, .03);
  k.wall(2.0, .3, M.cream, 6, M.brick);
  const floors = L * W > 2600 ? 3 : 2, bd = Math.min(10, W * .3);
  const backX = -L / 2 + 3 + bd / 2, span = W - 6;
  k.building(bd, span, floors, M.facBrick, backX, 0, 0, { parapetMat: M.cream });
  const wingL = Math.min(L * .55, L - 10);
  for (const s of [-1, 1]) {
    const z = s * (W / 2 - 3 - bd / 2);
    k.building(wingL - bd, bd, floors, M.facBrick, backX + bd / 2 + (wingL - bd) / 2, z, 0, { parapetMat: M.cream });
    k.box(3.2, floors * FLOOR + 1.6, 3.2, M.cream, backX + bd / 2 + .8, 0, z - s * (bd / 2 - 1.6));
  }
  // assembly ground, flag, court and play area
  const cx = backX + bd / 2 + 6;
  k.flag(cx, 0, 11);
  k.box(4, .4, 6, M.concrete, cx - 1.5, .03, 0);
  const free = L / 2 - (backX + wingL) - 2;
  if (free > 14 && W > 18) k.plane(Math.min(14, free - 2), Math.min(26, W - 10), M.basket, L / 2 - 2 - Math.min(14, free - 2) / 2, .06, 0);
  for (const [x, z] of [[L / 2 - 5, W / 2 - 5], [L / 2 - 5, -W / 2 + 5]]) k.tree(x, z, 'round', .9);
  for (let x = -L / 2 + 6; x < L / 2 - 4; x += 9) { k.tree(x, -W / 2 + 1.8, 'cone', .7); k.tree(x, W / 2 - 1.8, 'cone', .7); }
  if (k.gate) k.sign('GOVT. PRIMARY SCHOOL', 9, 1.5, k.gate.x + k.gate.nx * .4, 2.4, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#7a2e1d', border: '#f1e6cf' });
};

B.playground = (k, L, W) => {
  const M = k.M;
  k.ground(M.lawn, .03);
  const tw = 3.2, rx = L / 2 - 2.5, rz = W / 2 - 2.5, rr = Math.min(rx, rz) * .45;
  const rrect = (hx, hz, r) => { const p = []; for (const [cx, cz, a0] of [[hx - r, hz - r, 0], [-hx + r, hz - r, PI / 2], [-hx + r, -hz + r, PI], [hx - r, -hz + r, 1.5 * PI]]) for (let i = 0; i <= 6; i++) { const a = a0 + i / 6 * PI / 2; p.push([cx + Math.cos(a) * r, cz + Math.sin(a) * r]); } return p; };
  if (rx > 12 && rz > 10) k.shape(rrect(rx, rz, rr), [rrect(rx - tw, rz - tw, Math.max(1, rr - tw)).reverse()], M.track, .05);
  const fl = Math.min(L - 14, 100), fw = Math.min(W - 14, 64);
  if (fl > 20 && fw > 14) {
    k.plane(fl, fw, M.football, 0, .06, 0);
    for (const s of [-1, 1]) { const x = s * (fl / 2 - .5); k.box(.15, 2.44, .15, M.white, x, 0, -3.66); k.box(.15, 2.44, .15, M.white, x, 0, 3.66); k.box(.15, .15, 7.5, M.white, x, 2.4, 0); }
  }
  if (W > 40) {
    const z = -W / 2 + 4.5;
    for (let t = 0; t < 4; t++) k.box(Math.min(40, L * .4), .5, 1.2, M.concrete, 0, t * .5, z - t * 1.0);
    k.box(Math.min(42, L * .42), .3, 6, M.blue, 0, 6.2, z - 1.5);
    for (const x of [-Math.min(20, L * .2), 0, Math.min(20, L * .2)]) k.cyl(.15, .15, 6.2, 8, M.steel, x, 0, z + 1.2);
  }
  for (const [sx, sz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) {
    const x = sx * (L / 2 - 1.5), z = sz * (W / 2 - 1.5);
    k.cyl(.22, .32, 22, 10, M.steel, x, 0, z);
    k.box(3, 1.6, .5, M.darkSteel, x, 21, z, Math.atan2(-z, -x) + PI / 2);
    k.box(2.6, 1.2, .2, M.lampOn, x - Math.sign(x) * .2, 21.2, z - Math.sign(z) * .2, Math.atan2(-z, -x) + PI / 2, { keep: false });
  }
  for (let x = -L / 2 + 4; x <= L / 2 - 4; x += 11) { k.tree(x, W / 2 - 1, 'round', .95); if (W <= 40) k.tree(x, -W / 2 + 1, 'round', .95); }
};

B.commercial = (k, L, W, lm) => {
  const M = k.M, r = rng(lm.id * 31);
  k.ground(M.paving, .03);
  const bd = Math.min(18, W * .5), zb = -W / 2 + 1.5 + bd / 2, usable = L - 8;
  const n = Math.max(2, Math.min(7, Math.floor(usable / 12))), uw = usable / n;
  const SHOPS = ['AL-MADINA STORE', 'BANK', 'PHARMACY', 'BAKERY', 'MOBILE ZONE', 'CAFE', 'SUPER MART', 'TAILORS', 'OPTICS', 'JEWELLERS', 'BOOK DEPOT', 'SHOES'];
  const BG = ['#1f5a8a', '#8a1f2d', '#1d6b3c', '#b5651d', '#4a2e7a', '#0e6e6e'];
  const facs = [M.facCream, M.facWhite, M.facGlass, M.facPink, M.facCream];
  for (let i = 0; i < n; i++) {
    const x = -L / 2 + 4 + uw * (i + .5), fl = 2 + ((r() * 3) | 0);
    k.fbox(uw - .4, 4.2, bd, M.facShop, x, 0, zb);
    k.building(uw - .4, bd, fl, facs[(i + lm.id) % facs.length], x, zb, 0, { y: 4.2, tanks: r() < .6 });
    k.box(uw - .2, .25, 2.2, M.darkSteel, x, 4.2, zb + bd / 2 + 1.1);
    k.sign(SHOPS[(i * 5 + lm.id * 3) % SHOPS.length], Math.min(uw - 1.4, 9), 1.1, x, 4.55, zb + bd / 2 + .15, 0, { bg: BG[(i + lm.id) % BG.length], border: '#f2e6c8' });
  }
  const pz = zb + bd / 2 + 2.4, pw = W / 2 - pz - 1;
  if (pw > 5) {
    k.plane(usable, Math.min(pw, 12), M.parking, 0, .05, pz + Math.min(pw, 12) / 2);
    for (let x = -usable / 2 + 2; x < usable / 2 - 2; x += 2.5) if (r() < .55) k.car(x, pz + 2.6, PI / 2 + (r() < .5 ? 0 : PI));
    for (let x = -usable / 2 + 5; x < usable / 2; x += 14) k.lamp(x, W / 2 - .8, PI, 'street');
  }
  // dispensary and overhead water tank at the ends
  const ex = L / 2 - 3.5;
  if (W > 16) {
    k.building(6, 6, 1, M.facWhite, ex, zb, 0, { tanks: false });
    k.sign('DISPENSARY', 5.6, .9, ex, 3.6, zb + 3.15, 0, { bg: '#ffffff', fg: '#1d6b3c', border: '#1d6b3c' });
  }
  const tx = -L / 2 + 3, tz = W / 2 - 3.5;
  for (const [a, b] of [[-1.4, -1.4], [-1.4, 1.4], [1.4, -1.4], [1.4, 1.4]]) k.cyl(.25, .3, 16, 8, M.concrete, tx + a, 0, tz + b);
  k.cyl(3, 2.6, 3.5, 20, M.cream, tx, 16, tz);
  k.geo(dome(3, 1.2), M.cream, tx, 19.5, tz);
};

B.park = (k, L, W, lm) => {
  const M = k.M, r = rng(lm.id * 17 + 3);
  k.ground(M.lawn, .03);
  k.wall(.9, .6, M.hedge, 4);
  const ins = 4.5, hx = L / 2 - ins, hz = W / 2 - ins, pw = 2.4;
  const big = L > 30 && W > 26;
  if (big) {
    const rr = Math.min(hx, hz) * .5;
    const rrect = (ax, az, rad) => { const p = []; for (const [cx, cz, a0] of [[ax - rad, az - rad, 0], [-ax + rad, az - rad, PI / 2], [-ax + rad, -az + rad, PI], [ax - rad, -az + rad, 1.5 * PI]]) for (let i = 0; i <= 6; i++) { const a = a0 + i / 6 * PI / 2; p.push([cx + Math.cos(a) * rad, cz + Math.sin(a) * rad]); } return p; };
    k.shape(rrect(hx, hz, rr), [rrect(hx - pw, hz - pw, Math.max(.5, rr - pw)).reverse()], M.paving, .05);
    k.plane(L - 2 * ins, pw, M.paving, 0, .051, 0, 0, { metres: true });
    k.plane(pw, W - 2 * ins, M.paving, 0, .052, 0, 0, { metres: true });
    // central fountain with flower beds
    k.cyl(3.4, 3.6, .6, 32, M.marble, 0, .03, 0);
    k.cyl(3.1, 3.1, .05, 32, M.water, 0, .58, 0);
    k.cyl(.45, .6, 1.6, 12, M.marble, 0, .6, 0); k.cyl(1.5, .7, .35, 20, M.marble, 0, 2.1, 0); k.cyl(.12, .12, 1.2, 8, M.water, 0, 2.4, 0);
    for (const [a, b] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) k.cyl(1.7, 1.8, .35, 20, M.flowers, a * 7.5, .03, b * 6.5);
    for (let x = -hx + 6; x < hx - 4; x += 9) { k.bench(x, hz - pw - .8, 0); k.bench(x, -hz + pw + .8, PI); }
    for (let x = -hx + 3; x <= hx - 3; x += 12) { k.lamp(x, hz - pw - 2, 0, 'park'); k.lamp(x, -hz + pw + 2, 0, 'park'); }
    // kids play area and gazebo
    if (L > 40) {
      const px = -hx / 2 - 2, pz = -hz / 2 - 1;
      k.plane(9, 7, M.dirt, px, .06, pz, 0, { metres: true });
      for (const z of [pz - 1.8, pz + 1.8]) { k.cyl(.08, .08, 2.6, 6, M.red, px - 2.5, 0, z, { rz: .2 }); k.cyl(.08, .08, 2.6, 6, M.red, px - 1.0, 0, z, { rz: -.2 }); }
      k.box(.15, .15, 4.2, M.red, px - 1.75, 2.5, pz);
      for (const z of [pz - .8, pz + .8]) k.box(.5, .08, .4, M.yellow, px - 1.75, .55, z);
      k.box(1, 2.2, 1, M.blue, px + 2, 0, pz + 1); k.box(.8, .1, 3.4, M.yellow, px + 2, 1.1, pz - .9, 0, { rx: .55 });
      k.box(3.2, .12, .3, M.orange, px + 1, .5, pz - 2.4);
    }
    if (L > 50 && W > 34) {
      const gx = hx / 2 + 2, gz = hz / 2;
      k.cyl(3.4, 3.4, .35, 8, M.paving, gx, .03, gz);
      for (let i = 0; i < 8; i++) { const a = i / 8 * 2 * PI; k.cyl(.15, .15, 3, 6, M.white, gx + Math.cos(a) * 2.9, .35, gz + Math.sin(a) * 2.9); }
      k.cyl(0, 3.9, 2.2, 8, M.terracotta, gx, 3.35, gz);
    }
  } else {
    k.plane(L - 6, pw, M.paving, 0, .05, 0, 0, { metres: true });
    for (let x = -L / 2 + 6; x < L / 2 - 4; x += 8) k.bench(x, pw / 2 + .6, PI);
  }
  // trees: perimeter row then scattered inside, avoiding paths and the centre
  for (let x = -L / 2 + 2.5; x <= L / 2 - 2.5; x += 7) for (const z of [-W / 2 + 2.3, W / 2 - 2.3]) if (k.inside(x, z, 1.5)) k.tree(x + (r() - .5), z, r() < .3 ? 'cone' : 'round', .8 + r() * .5);
  for (let z = -W / 2 + 9; z <= W / 2 - 9; z += 7) for (const x of [-L / 2 + 2.3, L / 2 - 2.3]) if (k.inside(x, z, 1.5)) k.tree(x, z + (r() - .5), 'round', .8 + r() * .5);
  const n = Math.min(70, Math.floor(L * W / 140));
  for (let i = 0, tries = 0; i < n && tries < n * 8; tries++) {
    const x = (r() - .5) * (L - 8), z = (r() - .5) * (W - 8);
    if (!k.inside(x, z, 3)) continue;
    if (Math.hypot(x, z) < 11 || Math.abs(z) < 2.5 || Math.abs(x) < 2.5) continue;
    if (big && (Math.abs(Math.abs(x) - (hx - pw / 2)) < 2.5 || Math.abs(Math.abs(z) - (hz - pw / 2)) < 2.5)) continue;
    k.tree(x, z, r() < .15 ? 'palm' : r() < .35 ? 'cone' : 'round', .75 + r() * .6); i++;
  }
};

B.hospital = (k, L, W) => {
  const M = k.M;
  k.ground(M.lawn, .03);
  k.wall(1.6, .3, M.white, 12, M.white);
  const cw = Math.min(L * .62, 110), cd = Math.min(W * .26, 24), zc = -W / 2 + 6 + cd / 2, wd = Math.min(W * .5, 52), ww = Math.min(18, cw * .22);
  const fl = L * W > 12000 ? 7 : 6;
  const top = k.building(cw, cd, fl, M.facWhite, 0, zc, 0, { parapetMat: M.white, tanks: false });
  for (const s of [-1, 1]) k.building(ww, wd, fl - 2, M.facWhite, s * (cw / 2 - ww / 2), zc + wd / 2 - cd / 2, 0, { parapetMat: M.white });
  k.building(cw * .3, 14, 3, M.facGlass, 0, zc + cd / 2 + 7, 0, { tanks: false });
  k.cyl(6, 6, .3, 32, M.darkConcrete, cw / 4, top, zc); k.plane(10, 10, M.helipad, cw / 4, top + .32, zc);
  k.box(1.2, 5, 5, M.red, -cw / 4, top, zc); k.box(1.25, 1.7, 5.02, M.white, -cw / 4, top + 1.65, zc); k.box(1.3, 5.02, 1.7, M.white, -cw / 4, top, zc);
  k.sign('HOSPITAL', 16, 2.6, 0, top - 4.5, zc - cd / 2 - .3, PI, { bg: '#ffffff', fg: '#c3392b', border: '#c3392b' });
  const fz = zc + cd / 2 + 14 + 6;
  k.plane(cw * .6, 12, M.paving, 0, .05, fz, 0, { metres: true });
  k.box(18, .4, 8, M.white, 0, 4.2, fz - 2); for (const x of [-8, 8]) for (const z of [fz + 1.5, fz - 5.5]) k.cyl(.25, .25, 4.2, 10, M.white, x, 0, z);
  const pz = Math.min(W / 2 - 10, fz + 18), pl = Math.min(L - 16, cw);
  if (pz > fz + 8) { k.plane(pl, 14, M.parking, 0, .05, pz); for (let x = -pl / 2 + 2; x < pl / 2 - 2; x += 2.5) if ((x * 13 | 0) % 3) k.car(x, pz - 2.2, PI / 2, x < -pl / 2 + 10 ? '#ffffff' : null); }
  k.fillTrees([[-cw / 2, zc - cd / 2, cw / 2, zc + wd], [-cw * .3, fz - 8, cw * .3, fz + 8], [-pl / 2, pz - 8, pl / 2, pz + 8]], 10, 3);
};

B.sports = (k, L, W) => {
  const M = k.M;
  k.ground(M.lawn, .03);
  k.wall(2.2, .2, M.darkSteel, 8, M.darkSteel);
  const aw = Math.min(L * .45, 50), ad = Math.min(W * .55, 34), ax = -L / 2 + 3 + aw / 2;
  k.fbox(aw, 9, ad, M.facGlass, ax, 0, 0);
  const roof = new THREE.CylinderGeometry(ad / 2, ad / 2, aw, 32, 1, false, 0, PI); roof.rotateZ(PI / 2); roof.rotateX(PI / 2); roof.scale(1, .35, 1);
  k.geo(roof, M.steel, ax, 9, 0);
  k.sign('SPORTS COMPLEX', 14, 2, ax, 6.5, ad / 2 + .3, 0, { bg: '#0e4f7a' });
  const cx0 = ax + aw / 2 + 4;
  let x = cx0;
  while (x + 12 < L / 2 - 1) { k.plane(11, Math.min(24, W - 6), M.tennis, x + 5.5, .06, -W / 4 + 2, 0); x += 12.5; if (x > cx0 + 26) break; }
  if (L / 2 - cx0 > 14 && W > 30) { k.box(14, .5, 26 > W / 2 ? W / 2 - 3 : 10, M.marble, cx0 + 7, .03, W / 4); k.box(12.6, .05, (26 > W / 2 ? W / 2 - 3 : 10) - 1.4, M.water, cx0 + 7, .53, W / 4); }
  for (let xx = -L / 2 + 3; xx < L / 2; xx += 9) k.tree(xx, -W / 2 + 1.4, 'cone', .8);
  if (L * W > 6000) k.fillTrees([[-L / 2, -ad / 2, x, ad / 2], [cx0, -W / 2, L / 2, W / 2]], 10, 6);
};

B.civic = (k, L, W) => {
  const M = k.M;
  k.ground(M.paving, .03);
  const bw = Math.min(L * .6, 46), bd = Math.min(W * .45, 24);
  k.box(bw + 6, 1.5, bd + 6, M.sand, 0, 0, 0);
  for (let i = 0; i < 4; i++) k.box(bw * .5, .375 * (i + 1), 1.2, M.sand, 0, 0, bd / 2 + 3 + 4.2 - i * 1.2);
  k.building(bw, bd, 3, M.facSand, 0, 0, 0, { y: 1.5, parapetMat: M.sand, tanks: false });
  const cz = bd / 2 + 2.2;
  for (let i = 0; i < 8; i++) k.cyl(.55, .6, 9, 16, M.white, -bw * .3 + i * bw * .6 / 7, 1.5, cz);
  k.box(bw * .66, 1.2, 3.4, M.white, 0, 10.5, cz - .6);
  const tri = new THREE.Shape([new THREE.Vector2(-bw * .34, 0), new THREE.Vector2(bw * .34, 0), new THREE.Vector2(0, 3.2)]);
  const ped = new THREE.ExtrudeGeometry(tri, { depth: 3.4, bevelEnabled: false }); ped.translate(0, 0, -1.7);
  k.geo(ped, M.white, 0, 11.7, cz - .6);
  k.cyl(5, 5, 2, 24, M.white, 0, 1.5 + 3 * FLOOR + .45, -bd * .1); k.geo(dome(5, 4.2), M.domeWhite, 0, 3.5 + 3 * FLOOR + .45, -bd * .1);
  k.flag(0, W / 2 - 4, 12);
  k.sign('PUBLIC BUILDING', 10, 1.4, 0, 9.3, cz + .8, 0, { bg: '#5b4a2a', border: '#e8d7a8' });
  for (let x = -L / 2 + 4; x < L / 2; x += 9) { k.tree(x, -W / 2 + 2, 'cone', .9); }
  if (L * W > 6000) k.fillTrees([[-bw / 2 - 3, -bd / 2 - 3, bw / 2 + 3, bd / 2 + 9]], 11, 5);
};

B.university = (k, L, W) => {
  const M = k.M;
  k.ground(M.lawn, .03);
  k.wall(1.8, .35, M.brick, 10, M.cream);
  const bd = 12;
  k.building(L - 12, bd, 4, M.facBrick, 0, -W / 2 + 4 + bd / 2, 0);
  for (const s of [-1, 1]) k.building(bd, W * .55, 4, M.facBrick, s * (L / 2 - 4 - bd / 2), -W / 2 + 4 + bd + W * .275, 0);
  k.plane(4, W - 8, M.paving, 0, .05, 0, 0, { metres: true });
  const tx = 0, tz = -W / 2 + 4 + bd + 6;
  k.box(6, 30, 6, M.brick, tx, 0, tz); k.box(6.8, 1, 6.8, M.cream, tx, 22, tz);
  for (const [dx, dz, ry] of [[0, 3.42, 0], [0, -3.42, PI], [3.42, 0, PI / 2], [-3.42, 0, -PI / 2]]) k.geo(new THREE.CircleGeometry(2.2, 32), M.clock, tx + dx, 26, tz + dz, ry, { keep: true });
  k.cyl(0, 4.8, 6, 4, M.terracotta, tx, 30, tz, { ry: PI / 4 });
  for (let i = 0; i < 18; i++) { const x = (i % 6 - 2.5) * L / 7, z = W / 2 - 6 - Math.floor(i / 6) * 7; if (k.inside(x, z, 3)) k.tree(x, z, i % 3 ? 'round' : 'cone', 1); }
  if (k.gate) k.sign('UNIVERSITY (PROPOSED)', 11, 1.4, k.gate.x + k.gate.nx * .4, 2.4, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#5a1f1f' });
};

B.stadium = (k, L, W) => {
  const M = k.M;
  k.ground(M.paving, .03);
  const a = L / 2 - 3, b = W / 2 - 3;
  const bowl = new THREE.CylinderGeometry(1, .74, 1, 64, 1, true); bowl.translate(0, .5, 0); bowl.scale(a, 15, b);
  k.geo(bowl, M.seats, 0, 0, 0);
  const outer = new THREE.CylinderGeometry(1, 1, 1, 64, 1, true); outer.translate(0, .5, 0); outer.scale(a, 16.5, b);
  k.geo(outer, M.concrete, 0, 0, 0);
  const field = new THREE.CircleGeometry(1, 64); field.rotateX(-PI / 2); field.scale(a * .74, 1, b * .74);
  const fuv = field.attributes.uv; for (let i = 0; i < fuv.count; i++) fuv.setXY(i, (fuv.getX(i) - .5) * a * 1.5, (fuv.getY(i) - .5) * b * 1.5);
  k.geo(field, M.lawn, 0, .08, 0, 0, { shadow: false });
  k.plane(3.2, 20, M.dirt, 0, .1, 0, PI / 2, { metres: true });
  const canopy = new THREE.CylinderGeometry(1.03, .82, 1, 48, 1, true, -PI * .35, PI * .7); canopy.translate(0, .5, 0); canopy.scale(a, 2, b);
  k.geo(canopy, M.white, 0, 15.5, 0);
  for (const [sx, sz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) { const x = sx * a * .8, z = sz * b * .8; k.cyl(.4, .6, 38, 10, M.steel, x, 0, z); k.box(6, 3, .6, M.darkSteel, x, 36, z, Math.atan2(-z, -x) + PI / 2); k.box(5.4, 2.4, .2, M.lampOn, x - Math.sign(x) * .3, 36.3, z - Math.sign(z) * .3, Math.atan2(-z, -x) + PI / 2); }
  k.sign('CRICKET STADIUM (PROPOSED)', 16, 2, 0, 12, b + .4, 0, { bg: '#1d5e3f' });
};

B.cinema = (k, L, W) => {
  const M = k.M;
  k.ground(M.parking, .03);
  const bw = Math.min(L * .6, 60), bd = Math.min(W * .62, 40), bz = -W / 2 + 3 + bd / 2;
  k.box(bw, 20, bd, M.darkConcrete, 0, 0, bz);
  k.box(bw + .6, .6, bd + .6, M.purple, 0, 20, bz);
  const front = new THREE.CylinderGeometry(bw * .3, bw * .3, 17, 32, 1, false, -PI / 2, PI); front.translate(0, 8.5, 0); front.scale(1, 1, .45);
  k.geo(front, M.glass, 0, 0, bz + bd / 2);
  k.sign('IMAX', 14, 4, 0, 13, bz + bd / 2 + bw * .3 * .45 + .2, 0, { bg: '#101820', fg: '#5ec8ff', border: '#5ec8ff' });
  for (let x = -L / 2 + 5; x < L / 2 - 5; x += 2.6) if ((x * 7) % 3 > 1) k.car(x, W / 2 - 5, PI / 2);
  for (let x = -L / 2 + 4; x < L / 2; x += 12) k.lamp(x, W / 2 - 1.2, PI, 'street');
};

B.multipurpose = (k, L, W, lm) => {
  const M = k.M, r = rng(lm.id);
  k.ground(M.paving, .03);
  k.box(L * .7, 8, W * .4, M.facShop ? M.cream : M.cream, -L * .1, 0, -W * .2);
  k.fbox(L * .7, 8, W * .4, M.facShop, -L * .1, 0, -W * .2);
  for (let i = 0; i < 3; i++) { const fl = 8 + ((r() * 6) | 0); k.building(14, 14, fl, i % 2 ? M.facGlass : M.facWhite, -L * .35 + i * L * .3, -W * .2, 0, { y: 8, tanks: false }); }
  for (let x = -L / 2 + 4; x < L / 2; x += 8) k.tree(x, W / 2 - 3, 'palm', 1);
  k.sign('MULTI-PURPOSE ZONE', 12, 1.6, -L * .1, 5.5, W * 0 + .1, 0, { bg: '#2d3b6b' });
};

B.grid = (k, L, W) => {
  const M = k.M;
  k.ground(M.gravel, .03);
  k.wall(.6, .25, M.concrete, 6, M.darkSteel);
  for (let i = 0; i < Math.min(4, Math.floor(L / 14)); i++) {
    const x = -L / 2 + 8 + i * 12;
    k.box(4, 3.4, 3, M.darkSteel, x, .3, -W * .15);
    for (let f = -1.5; f <= 1.5; f += .5) k.box(.12, 2.6, 3.6, M.darkSteel, x + f, .5, -W * .15);
    for (const dz of [-.8, 0, .8]) k.cyl(.12, .2, 1.6, 8, M.terracotta, x, 3.7, -W * .15 + dz);
    k.box(.6, 9, .6, M.lattice, x - 3, 0, W * .15); k.box(.6, 9, .6, M.lattice, x + 3, 0, W * .15); k.box(6.6, .6, .6, M.darkSteel, x, 9, W * .15);
  }
  k.building(8, 6, 1, M.facCream, L / 2 - 6, -W / 2 + 5, 0, { tanks: false });
  k.cyl(.8, 3.2, 32, 4, M.lattice, L / 2 - 6, 0, W / 2 - 6, { ry: PI / 4 });
  for (const y of [22, 28]) k.box(10, .5, .5, M.darkSteel, L / 2 - 6, y, W / 2 - 6);
  if (k.gate) k.sign('GRID STATION 132 kV', 8, 1.2, k.gate.x + k.gate.nx * .4, 1.2, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#e9b738', fg: '#222', border: '#222' });
};

B.graveyard = (k, L, W, lm) => {
  const M = k.M, r = rng(lm.id * 7);
  k.ground(M.dirt, .03);
  k.wall(1.4, .35, M.cream, 4, M.white);
  for (let x = -L / 2 + 4; x < L / 2 - 3; x += 2.2) for (let z = -W / 2 + 4; z < W / 2 - 3; z += 3.4) {
    if (r() < .35 || !k.inside(x, z, 2)) continue;
    k.box(.95, .35, 2.1, M.grave, x, 0, z); k.box(.9, .7, .12, M.grave, x, .35, z - .95);
  }
  for (let i = 0; i < 14; i++) { const x = (r() - .5) * (L - 6), z = (r() - .5) * (W - 6); if (k.inside(x, z, 2)) k.tree(x, z, 'round', .9 + r() * .4); }
  if (k.gate) k.sign('QABRISTAN', 5, 1, k.gate.x + k.gate.nx * .4, 2, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#1d3b2a' });
};

B.cng = (k, L, W) => {
  const M = k.M;
  k.ground(M.asphalt, .03);
  const cw = Math.min(L * .55, 20), cd = Math.min(W * .5, 13);
  for (const [a, b] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) k.cyl(.3, .3, 5.4, 10, M.white, a * cw * .35, 0, b * cd * .3);
  k.box(cw, .5, cd, M.white, 0, 5.4, 0); k.box(cw + .3, 1, cd + .3, M.green, 0, 5.9, 0);
  for (const x of [-cw * .2, cw * .2]) for (const z of [-cd * .15, cd * .15]) { k.box(.9, 1.8, .6, M.green, x, 0, z); k.box(.6, .5, .62, M.lampOn, x, 1.1, z); }
  k.building(8, 6, 1, M.facCream, -L / 2 + 5, -W / 2 + 4, 0, { tanks: false });
  k.cyl(.2, .2, 8, 8, M.steel, L / 2 - 2, 0, W / 2 - 2); k.sign('CNG', 3, 2, L / 2 - 2, 8, W / 2 - 2, 0, { bg: '#1d6b3c', size: 140 });
  for (const x of [-cw * .2, cw * .2]) k.car(x, cd * .42, 0);
};

B.shrine = (k, L, W) => {
  const M = k.M;
  k.ground(M.marble, .03);
  k.wall(1.5, .35, M.white, 4, M.domeGreen);
  const s = Math.min(9, Math.min(L, W) * .35);
  k.fbox(s, 5.5, s, M.facMosque, 0, 0, 0);
  k.box(s + .6, .4, s + .6, M.white, 0, 5.5, 0);
  k.cyl(s * .32, s * .32, 1.4, 24, M.white, 0, 5.9, 0); k.geo(onion(s * .34, s * .5), M.domeGreen, 0, 7.3, 0);
  k.cyl(.08, .08, 1.6, 6, M.gold, 0, 7.3 + s * .5, 0);
  for (const [a, b] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) { k.cyl(.35, .45, 8, 8, M.white, a * s / 2, 0, b * s / 2); k.geo(onion(.45, .9), M.domeGreen, a * s / 2, 8, b * s / 2); }
  for (const [x, z] of [[-L / 2 + 3, -W / 2 + 3], [L / 2 - 3, W / 2 - 3]]) { k.cyl(.05, .05, 9, 6, M.steel, x, 0, z); k.box(.05, 1.2, 1.8, M.domeGreen, x, 7.6, z + .9); }
  for (const [x, z] of [[-L / 2 + 3, W / 2 - 3], [L / 2 - 3, -W / 2 + 3]]) k.tree(x, z, 'round', 1.1);
};

B.roundabout = (k, L, W, lm) => {
  const M = k.M, R = Math.max(4, (lm.radius || Math.min(L, W) / 2) - .3);
  k.cyl(R, R, .35, 48, M.concrete, 0, 0, 0);
  k.disc(R - .5, M.lawn, 0, .36, 0, 48);
  k.ring(R * .45, R * .8, M.flowers, 0, .37, 0, 48);
  if (lm.monument === 'rings') {
    // concentric planted rings, as seen on the satellite image, with an FDA City obelisk
    for (const f of [.86, .66, .46]) k.ring(R * f - .7, R * f, M.hedge, 0, .38, 0, 56);
    for (const f of [.76, .56]) k.ring(R * f - 1.2, R * f, M.flowers, 0, .385, 0, 56);
    k.cyl(R * .3, R * .32, .5, 32, M.marble, 0, .36, 0);
    k.box(2.2, 1.2, 2.2, M.marble, 0, .86, 0);
    const ob = new THREE.CylinderGeometry(.35, 1.0, 12, 4, 1).translate(0, 6, 0); ob.rotateY(PI / 4);
    k.geo(ob, M.white, 0, 2.06, 0);
    k.geo(new THREE.ConeGeometry(.5, 1.4, 4).rotateY(PI / 4).translate(0, .7, 0), M.gold, 0, 14.06, 0);
    for (const s of [0, PI]) k.sign('FDA CITY', 4.2, 1.1, Math.sin(s) * 1.25, 1.5, Math.cos(s) * 1.25, s, { bg: '#1f5a38', border: '#d6a840' });
  } else if (lm.monument === 'tree') {
    k.cyl(R * .2, R * .22, .45, 24, M.paving, 0, .36, 0);
    k.tree(0, 0, 'round', 2.4);
    for (let i = 0; i < 14; i++) { const a = i / 14 * 2 * PI; k.tree(Math.cos(a) * R * .55, Math.sin(a) * R * .55, 'cone', .7); }
  } else if (lm.monument === 'clocktower') {
    // replica of Faisalabad's Ghanta Ghar (Clock Tower)
    k.box(8, 1.6, 8, M.sand, 0, .36, 0);
    k.fbox(5.2, 17, 5.2, M.facSand, 0, 1.96, 0);
    k.box(6.2, .8, 6.2, M.sand, 0, 18.96, 0);
    for (const [dx, dz, ry] of [[0, 2.62, 0], [0, -2.62, PI], [2.62, 0, PI / 2], [-2.62, 0, -PI / 2]]) k.geo(new THREE.CircleGeometry(1.8, 32), M.clock, dx, 16.4, dz, ry, { keep: true });
    k.cyl(2.3, 2.6, 3.2, 8, M.sand, 0, 19.76, 0);
    for (let i = 0; i < 8; i++) { const a = i / 8 * 2 * PI; k.cyl(.18, .18, 2.4, 6, M.cream, Math.cos(a) * 2.5, 22.96, Math.sin(a) * 2.5); }
    k.cyl(2.8, 2.8, .4, 8, M.sand, 0, 25.36, 0);
    k.geo(dome(2.4, 2.6), M.domeWhite, 0, 25.76, 0);
    k.cyl(.1, .1, 1.6, 6, M.gold, 0, 28.3, 0);
  } else {
    k.cyl(R * .42, R * .45, .7, 40, M.marble, 0, .36, 0);
    k.cyl(R * .39, R * .39, .05, 40, M.water, 0, 1.0, 0);
    k.cyl(.7, 1, 2.2, 16, M.marble, 0, 1.0, 0); k.cyl(2.4, .9, .4, 24, M.marble, 0, 3.2, 0); k.cyl(2.2, 2.2, .05, 24, M.water, 0, 3.55, 0);
    k.cyl(.4, .5, 1.6, 12, M.marble, 0, 3.6, 0); k.cyl(1.1, .5, .3, 16, M.marble, 0, 5.2, 0);
    for (let i = 0; i < 10; i++) { const a = i / 10 * 2 * PI; k.raw(new THREE.CylinderGeometry(.06, .12, 2.6, 6).translate(0, 1.3, 0), M.water, Math.cos(a) * R * .32, 1.0, Math.sin(a) * R * .32, 0, { rz: Math.cos(a) * .35, rx: -Math.sin(a) * .35, shadow: false }); }
    k.cyl(.12, .2, 4, 8, M.water, 0, 5.4, 0, { shadow: false });
  }
  for (let i = 0; i < 10; i++) { const a = i / 10 * 2 * PI; k.tree(Math.cos(a) * R * .88, Math.sin(a) * R * .88, 'palm', .85); }
};

B.dispensary = (k, L, W) => {
  const M = k.M;
  k.ground(M.paving, .03);
  const bw = Math.min(L - 3, 16), bd = Math.min(W - 3, 12);
  const top = k.building(bw, bd, 2, M.facWhite, 0, 0, 0, { parapetMat: M.white, tanks: false });
  k.box(1, 3.4, 3.4, M.red, bw / 2 + .55, top - 4, 0); k.box(1.05, 1.1, 3.42, M.white, bw / 2 + .57, top - 2.85, 0); k.box(1.08, 3.42, 1.1, M.white, bw / 2 + .58, top - 4, 0);
  k.sign('DISPENSARY', Math.min(bw - 1, 9), 1.1, 0, 3.8, bd / 2 + .15, 0, { bg: '#ffffff', fg: '#1d6b3c', border: '#1d6b3c' });
};

B.homes = (k, L, W, lm) => {
  // FDA City Homes: a gated scheme of identical double-storey houses on a street grid
  const M = k.M, r = rng(lm.id * 13);
  k.ground(M.lawn, .03);
  k.wall(2.2, .35, M.cream, 14, M.sand);
  const hw = 9.5, hd = 17, street = 9, rowD = hd * 2 + street;
  const facs = [M.facCream, M.facPink, M.facSand, M.facCream];
  const roofs = [M.terracotta, M.roofGray, M.roofDark];
  let n = 0;
  for (let z = -W / 2 + 8; z + hd * 2 < W / 2 - 6; z += rowD) {
    k.plane(L - 10, street, M.asphalt, 0, .05, z + hd * 2 + street / 2, 0, { metres: true });
    for (let x = -L / 2 + 7; x + hw < L / 2 - 6; x += hw + .6) {
      for (const [zz, ry] of [[z + hd / 2, PI], [z + hd * 1.5, 0]]) {
        if (!k.inside(x + hw / 2, zz, 3)) continue;
        if (n++ > 1500) break;
        const f = facs[(r() * facs.length) | 0];
        k.fbox(hw - .8, 6.8, 11, f, x + hw / 2, 0, zz + (ry ? -2.5 : 2.5));
        const roof = new THREE.ConeGeometry(Math.hypot(hw - .8, 11) / 2 * 1.05, 2.4, 4, 1).rotateY(PI / 4).scale((hw - .8) / 11, 1, 1);
        k.geo(roof, roofs[(r() * roofs.length) | 0], x + hw / 2, 6.8, zz + (ry ? -2.5 : 2.5));
        k.box(hw - .8, 1.2, .2, M.cream, x + hw / 2, 0, zz + (ry ? 5.6 : -5.6));
        if (r() < .5) k.tree(x + hw / 2 + 2.5, zz + (ry ? 4 : -4), 'round', .55);
      }
    }
  }
  if (k.gate) k.sign('FDA CITY HOMES', 10, 1.6, k.gate.x + k.gate.nx * .4, 2.6, k.gate.z + k.gate.nz * .4, k.gate.ry, { bg: '#1f5a38', border: '#d6a840' });
};

B.metro = (k, L, W) => {
  const M = k.M;
  k.ground(M.parking, .03);
  const bw = Math.min(L * .55, 160), bd = Math.min(W * .45, 110), bz = -W * .18;
  k.box(bw, 11, bd, M.concrete, 0, 0, bz);
  k.box(bw + .6, .8, bd + .6, M.blue, 0, 11, bz);
  for (let x = -bw / 2 + 8; x < bw / 2 - 6; x += 12) k.box(6, .5, bd * .8, M.steel, x, 11.8, bz);
  k.box(bw * .5, 5, 1.2, M.glass, 0, 0, bz + bd / 2 + .4);
  k.sign('METRO', 22, 5, 0, 5.4, bz + bd / 2 + .7, 0, { bg: '#0b3a7a', fg: '#ffd400', border: '#ffd400', size: 170 });
  for (let x = -bw / 2; x < bw / 2; x += 2.6) for (const z of [bz + bd / 2 + 14, bz + bd / 2 + 26]) if (((x * 7) | 0) % 3) k.car(x, z, PI / 2);
  for (let x = -L / 2 + 6; x < L / 2; x += 14) k.lamp(x, W / 2 - 3, PI, 'street');
};

B.sewerage = (k, L, W) => {
  const M = k.M;
  k.ground(M.gravel, .03);
  k.wall(1.8, .3, M.concrete, 6, M.darkSteel);
  const R = Math.min(L, W) * .2;
  for (const s of [-1, 1]) {
    k.cyl(R, R, 2.4, 40, M.concrete, s * L * .22, 0, -W * .1, { open: true });
    k.cyl(R - .3, R - .3, .05, 40, M.water, s * L * .22, 2.0, -W * .1);
    k.box(R * 2, .25, 1, M.darkSteel, s * L * .22, 2.6, -W * .1);
  }
  k.box(L * .7, .6, W * .25, M.concrete, 0, 0, W * .28);
  k.box(L * .7 - 1, .05, W * .25 - 1, M.water, 0, .5, W * .28);
  k.building(8, 6, 1, M.facCream, L / 2 - 6, -W / 2 + 5, 0, { tanks: false });
};

export function buildLandmark(kind, k, L, W, lm) {
  const f = B[kind];
  if (!f) { k.ground(k.M.paving, .03); return false; }
  f(k, L, W, lm);
  return true;
}

// main gate across the boulevard (local X along the road, Z across it)
export function buildGate(k, span) {
  const M = k.M, half = span / 2;
  for (const s of [-1, 1]) {
    const z = s * (half + 3);
    k.fbox(6, 15, 6, M.facSand, 0, 0, z);
    k.box(7, .8, 7, M.sand, 0, 15, z);
    k.cyl(2.4, 2.4, 1.6, 8, M.sand, 0, 15.8, z);
    k.geo(dome(2.4, 2.8), M.domeGreen, 0, 17.4, z);
    k.cyl(.08, .08, 1.6, 6, M.gold, 0, 20.2, z);
    k.box(3, 3.5, 14, M.sand, 0, 0, z + s * 10);
    k.box(3.4, .4, 14.4, M.cream, 0, 3.5, z + s * 10);
  }
  k.box(4, 3.2, span + 6, M.sand, 0, 11, 0);
  k.box(4.4, .6, span + 7, M.cream, 0, 14.2, 0);
  for (const s of [-1, 1]) k.sign('FDA CITY  FAISALABAD', Math.min(span * .8, 28), 2.2, s * 2.12, 11.5, 0, s * PI / 2, { bg: '#1f5a38', border: '#d6a840' });
}

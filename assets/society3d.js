// Terralyt detailed 3D society model (three.js r169, ES module, no build step).
//
//   import { Society3D } from './assets/society3d.js';
//   const s = Society3D(element, { onPick, onHover, onStatus, layer: 'cls' });
//   await s.ready;  s.setLayer('stat');  s.select(120);  s.setTime('night');
//
// Reads the same data/*.geojson files as the CesiumJS view (assets/map3d.js):
// boundary, roads, road_surface, outer_roads, blocks (land parcels + lawns),
// landmarks and plots. Coordinates are projected to local metres around the
// society centre (x = east, z = -north, y = up).
import * as THREE from 'three';
import { MapControls } from 'three/addons/controls/MapControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { createMaterials, makeKit, buildLandmark, buildGate, rng } from './models3d.js';

const PI = Math.PI;
const LAT_REF = 31.525, KX = 111320 * Math.cos(LAT_REF * PI / 180), KY = 111320;
const Y = { road: .04, mark: .075, curb: .18, lawn: .185, land: .19, plotBase: .19, plotTop: .55, median: .32 };
const COLORS = {
  cls: { High: '#3fae5f', Medium: '#e0a93a', Low: '#c9573f' },
  stat: { Available: '#34c38f', Reserved: '#e0a93a', Sold: '#c9573f', Unknown: '#9aa5a0' },
  sat: { built: '#9c8a72', vacant: '#ddd2b2' }
};
const KIND_LABEL = { nala: 'Storm drain (nalla)', mosque: 'Mosque', school: 'School', playground: 'Playground', commercial: 'Commercial', park: 'Park', hospital: 'Hospital', sports: 'Sports', civic: 'Public building', university: 'University', stadium: 'Stadium', cinema: 'Cinema', multipurpose: 'Multi-purpose', grid: 'Grid station', graveyard: 'Graveyard', cng: 'CNG', shrine: 'Shrine', gate: 'Main gate', roundabout: 'Roundabout' };
const KIND_COLOR = { nala: '#2b7fc4', mosque: '#2e8a57', school: '#a5533a', playground: '#5aa647', commercial: '#2e6fb6', park: '#3f8f3f', hospital: '#c3392b', sports: '#0e6e8a', civic: '#8a6d3b', university: '#7a2e1d', stadium: '#1d6b3c', cinema: '#6d4fa0', multipurpose: '#2d3b6b', grid: '#b08a1a', graveyard: '#55624a', cng: '#1d6b3c', shrine: '#2e8a57', gate: '#8a6d3b', roundabout: '#3f8f3f' };

export function Society3D(el, opts = {}) {
  opts = Object.assign({ dataUrl: 'data/', layer: 'cls', onPick: null, onHover: null, onStatus: null }, opts);
  const api = { plots: [], landmarks: [], layer: opts.layer, time: 'day', ground: 'plan', labels: true, selected: null };
  const status = (s, m) => { if (opts.onStatus) opts.onStatus(s, m); };
  const tick = () => new Promise(r => requestAnimationFrame(() => r()));

  // ---- renderer, scene, camera ------------------------------------------------
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true, powerPreference: 'high-performance' });
    if (!renderer.getContext()) throw new Error('no WebGL context');
  } catch (e) {
    status('error', 'This browser could not start WebGL, which the 3D model needs. ' + (e && e.message ? e.message : ''));
    api.ready = Promise.reject(e); return api;
  }
  const lowEnd = /Mobi|Android/i.test(navigator.userAgent) || (navigator.hardwareConcurrency || 8) <= 4;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, lowEnd ? 1.25 : 1.75));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.domElement.className = 's3d-canvas';
  el.classList.add('s3d');
  el.appendChild(renderer.domElement);
  injectCss();
  const labelR = new CSS2DRenderer();
  labelR.domElement.className = 's3d-labels';
  el.appendChild(labelR.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 1, 40000);
  const controls = new MapControls(camera, renderer.domElement);
  Object.assign(controls, { enableDamping: true, dampingFactor: .085, screenSpacePanning: false, maxPolarAngle: 1.43, minDistance: 18, maxDistance: 9000, zoomToCursor: true, zoomSpeed: 1.2 });
  api.viewer = { renderer, scene, camera, controls };

  const M = createMaterials();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), .04).texture;
  scene.environmentIntensity = .45;

  // lights
  const hemi = new THREE.HemisphereLight('#d6e9ff', '#6b5b3b', 1.05);
  const sun = new THREE.DirectionalLight('#fff0d4', 2.7);
  sun.castShadow = true;
  sun.shadow.mapSize.set(lowEnd ? 2048 : 4096, lowEnd ? 2048 : 4096);
  sun.shadow.bias = -.0004; sun.shadow.normalBias = .5;
  const SUN_DIR = new THREE.Vector3(-.5, .74, .45).normalize();
  scene.add(hemi, sun, sun.target);

  // sky dome + stars
  const skyU = { top: { value: new THREE.Color('#5d93d6') }, hor: { value: new THREE.Color('#dbe8f2') }, bot: { value: new THREE.Color('#c9c3b1') } };
  const sky = new THREE.Mesh(new THREE.SphereGeometry(18000, 32, 16), new THREE.ShaderMaterial({
    uniforms: skyU, side: THREE.BackSide, depthWrite: false, depthTest: false, fog: false,
    vertexShader: 'varying vec3 vD; void main(){ vec4 w = modelMatrix * vec4(position,1.); vD = w.xyz - cameraPosition; gl_Position = projectionMatrix * viewMatrix * w; }',
    fragmentShader: 'uniform vec3 top; uniform vec3 hor; uniform vec3 bot; varying vec3 vD; void main(){ float h = normalize(vD).y; vec3 c = h > 0. ? mix(hor, top, pow(clamp(h,0.,1.), .5)) : mix(hor, bot, pow(clamp(-h,0.,1.), .35)); gl_FragColor = vec4(c, 1.); }'
  }));
  sky.renderOrder = -1000; sky.frustumCulled = false;
  scene.add(sky);
  const stars = (() => {
    const r = rng(99), n = 1600, p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { const u = r() * 2 * PI, v = Math.acos(1 - r() * .95); p.set([Math.sin(v) * Math.cos(u) * 17000, Math.cos(v) * 17000, Math.sin(v) * Math.sin(u) * 17000], i * 3); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    const s = new THREE.Points(g, new THREE.PointsMaterial({ color: '#ffffff', size: 1.6, sizeAttenuation: false, depthTest: false, depthWrite: false, fog: false, transparent: true, opacity: .9 }));
    s.renderOrder = -999; s.frustumCulled = false; s.visible = false; return s;
  })();
  scene.add(stars);
  scene.fog = new THREE.Fog('#dbe8f2', 2600, 12500);

  // post-processing (used at night for glowing lights)
  let composer = null, bloom = null;
  function ensureComposer() {
    if (composer) return;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(size.x, size.y, { samples: 4, type: THREE.HalfFloatType }));
    composer.addPass(new RenderPass(scene, camera));
    bloom = new UnrealBloomPass(new THREE.Vector2(size.x, size.y), .9, .5, .82);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    resize();
  }

  // ---- projection ---------------------------------------------------------------
  let LON0 = 73.0875, LAT0 = 31.5255;
  const P = (lon, lat) => [(lon - LON0) * KX, (lat - LAT0) * KY];   // plan metres: east, north
  const W3 = (e, n, y = 0) => new THREE.Vector3(e, y, -n);
  const ringPlan = r => { const out = r.map(c => P(c[0], c[1])); const a = out[0], b = out[out.length - 1]; if (a[0] === b[0] && a[1] === b[1]) out.pop(); return out; };
  const area2 = r => { let s = 0; for (let i = 0; i < r.length; i++) { const a = r[i], b = r[(i + 1) % r.length]; s += a[0] * b[1] - b[0] * a[1]; } return s / 2; };
  const cen2 = r => { let x = 0, y = 0; for (const p of r) { x += p[0]; y += p[1]; } return [x / r.length, y / r.length]; };

  function shapeFrom(rings) {
    const s = new THREE.Shape(ringPlan(rings[0]).map(p => new THREE.Vector2(p[0], p[1])));
    for (const h of rings.slice(1)) s.holes.push(new THREE.Path(ringPlan(h).map(p => new THREE.Vector2(p[0], p[1]))));
    return s;
  }
  const polysOf = g => g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
  function flatGeom(features, y, filter) {
    const gs = [];
    for (const f of features) { if (filter && !filter(f)) continue; for (const rings of polysOf(f.geometry)) { const g = new THREE.ShapeGeometry(shapeFrom(rings)); g.rotateX(-PI / 2); g.translate(0, y, 0); gs.push(g.toNonIndexed()); } }
    return gs.length ? mergeGeometries(gs) : null;
  }
  function extrudeGeom(features, y, depth, filter) {
    const gs = [];
    for (const f of features) { if (filter && !filter(f)) continue; for (const rings of polysOf(f.geometry)) { const g = new THREE.ExtrudeGeometry(shapeFrom(rings), { depth, bevelEnabled: false, curveSegments: 1 }); g.rotateX(-PI / 2); g.translate(0, y, 0); gs.push(g); } }
    return gs.length ? mergeGeometries(gs) : null;
  }
  function addMesh(geom, mat, { cast = false, receive = true, name } = {}) {
    if (!geom) return null;
    const m = new THREE.Mesh(geom, mat); m.castShadow = cast; m.receiveShadow = receive; if (name) m.name = name; scene.add(m); return m;
  }

  // ---- state -------------------------------------------------------------------
  const layers = { stylised: [], markings: null, satellite: null };
  const byId = new Map(), byNo = new Map(), lmById = new Map();
  const pickables = [];
  const trees = { round: [], cone: [], palm: [] }, lamps = { street: [], park: [] }, staticCars = [];
  const flags = [], nightSigns = [];
  let plotMesh = null, plotGeom = null, plotLines = null, carSystem = null, frames = 0, built = false;
  let homeTarget = new THREE.Vector3(), homeDist = 2600, axisRad = 0, boundaryPlan = null;

  const hooks = {
    tree(group, x, z, type, s) { const v = group.localToWorld(new THREE.Vector3(x, 0, z)); trees[type in trees ? type : 'round'].push([v.x, v.y, v.z, s]); },
    lamp(group, x, z, ry, type) { const v = group.localToWorld(new THREE.Vector3(x, 0, z)); lamps[type in lamps ? type : 'park'].push([v.x, v.y, v.z, ry + group.rotation.y]); },
    car(group, x, z, ry, color) { const v = group.localToWorld(new THREE.Vector3(x, 0, z)); staticCars.push([v.x, v.y, v.z, ry + group.rotation.y, color]); },
    nightMat(m) { nightSigns.push(m); }
  };

  // ---- build ---------------------------------------------------------------------
  async function build() {
    status('loading', 'Loading map data…');
    const get = n => fetch(opts.dataUrl + n + '.geojson', { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error(n + '.geojson: HTTP ' + r.status); return r.json(); });
    const [boundary, roads, surface, outer, land, landmarks, plots, water] = await Promise.all(['boundary', 'roads', 'road_surface', 'outer_roads', 'blocks', 'landmarks', 'plots', 'water'].map(n => get(n).catch(e => { if (n === 'water') return { features: [] }; throw e; })));
    const bp = boundary.features[0].properties;
    LON0 = bp.centre_lon; LAT0 = bp.centre_lat;
    axisRad = (bp.axis_deg || 0) * PI / 180;
    api.society = { name: bp.name, area_km2: bp.area_km2, source: bp.source };
    boundaryPlan = ringPlan(boundary.features[0].geometry.coordinates[0]);

    status('loading', 'Building ground, roads and parcels…'); await tick();
    // countryside
    const farm = new THREE.Mesh(new THREE.PlaneGeometry(24000, 24000), new THREE.MeshStandardMaterial({ map: farmTexture(axisRad), roughness: 1 }));
    farm.rotation.x = -PI / 2; farm.position.y = -.25; farm.receiveShadow = true; scene.add(farm); layers.stylised.push(farm);
    // society ground, road surfaces and parcels
    layers.stylised.push(addMesh(flatGeom(boundary.features, .0), M.grass));
    layers.stylised.push(addMesh(flatGeom(outer.features, Y.road - .01), M.asphalt));
    layers.stylised.push(addMesh(flatGeom(surface.features, Y.road), M.asphalt));
    const isLand = f => f.properties.layer === 'land', isInner = f => f.properties.layer === 'inner';
    const parcelLike = f => f.properties.kind === 'parcel' || f.properties.kind === 'greenbelt';
    layers.stylised.push(addMesh(extrudeGeom(land.features, Y.road, Y.curb - Y.road, f => isLand(f) && parcelLike(f)), M.sidewalk));
    layers.stylised.push(addMesh(flatGeom(land.features, Y.lawn, f => isInner(f) && f.properties.kind === 'parcel'), M.grass));
    layers.stylised.push(addMesh(flatGeom(land.features, Y.lawn + .004, f => isInner(f) && f.properties.kind === 'greenbelt'), M.lawn));
    for (const f of land.features) if (isInner(f) && f.properties.kind === 'greenbelt') for (const rings of polysOf(f.geometry)) {
      const r = ringPlan(rings[0]); let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
      for (const [x, y] of r) { minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y); }
      for (let x = minx + 4; x < maxx; x += 9) for (let y = miny + 4; y < maxy; y += 9) if (pipPlan(x, y, r)) trees[(Math.round(x + y) % 3) ? 'round' : 'cone'].push([x, Y.lawn, -y, .9]);
    }
    buildNala(water.features);
    layers.stylised.push(addMesh(extrudeGeom(land.features, Y.road, Y.median - Y.road, f => isLand(f) && f.properties.kind === 'median'), M.concrete, { cast: true }));
    layers.stylised.push(addMesh(flatGeom(land.features, Y.median + .005, f => isLand(f) && f.properties.kind === 'median'), M.lawn));
    layers.stylised.push(addMesh(flatGeom(boundary.features, -.12), M.dirt));
    // lane markings, street lights, street trees
    buildStreetscape(roads.features);

    status('loading', 'Building landmarks…'); await tick();
    for (const f of landmarks.features) buildOne(f);
    bakeLandmarks();

    status('loading', 'Placing ' + plots.features.length.toLocaleString() + ' plots…'); await tick();
    buildPlots(plots.features);
    buildInstances();
    buildCars(roads.features);
    buildLabels();
    buildMinimap();

    // home view
    homeTarget.set(0, 0, 0);
    homeDist = Math.max(1500, Math.sqrt(Math.abs(area2(boundaryPlan))) * 1.3);
    reset(0);
    built = true;
    status('ready', api.plots.length + ' plots');
    if (opts.selectId != null) select(opts.selectId);
    return api;
  }

  // ---- nalla (storm drain) ---------------------------------------------------------------
  function buildNala(features) {
    if (!features.length) return;
    const of = k => features.filter(f => f.properties.kind === k);
    const bank = addMesh(flatGeom(of('nala_bank'), Y.lawn - .02), M.lawn);
    const wall = addMesh(extrudeGeom(of('nala_wall'), 0, .95), M.concrete, { cast: true });
    const bed = addMesh(flatGeom(of('nala_water'), .05), M.dirt);
    const wat = addMesh(flatGeom(of('nala_water'), .38), M.water);
    for (const f of of('nala_tree')) { const [e, n] = P(...f.geometry.coordinates); trees[(Math.round(e * 3 + n) % 4) ? 'round' : 'palm'].push([e, Y.lawn, -n, .95]); }
    // bridge railings where roads cross the channel
    const parts = [];
    for (const f of of('bridge')) {
      const [e, n] = P(...f.geometry.coordinates), h = f.properties.heading * PI / 180, off = f.properties.road_width / 2 + .35, span = f.properties.span + 3;
      for (const s of [-1, 1]) {
        const g = new THREE.BoxGeometry(span, 1.0, .35).translate(0, Y.road + .5, 0); g.rotateY(h);
        g.translate(e - Math.sin(h) * off * s, 0, -(n + Math.cos(h) * off * s)); parts.push(g.toNonIndexed());
        for (const t of [-span / 2, span / 2]) { const pgeo = new THREE.BoxGeometry(.6, 1.3, .6).translate(0, Y.road + .65, 0); pgeo.translate(e + Math.cos(h) * t - Math.sin(h) * off * s, 0, -(n + Math.sin(h) * t + Math.cos(h) * off * s)); parts.push(pgeo.toNonIndexed()); }
      }
    }
    const rails = parts.length ? addMesh(mergeGeometries(parts), M.cream, { cast: true }) : null;
    const line = of('nala_line')[0];
    const id = 9001, mid = line ? line.geometry.coordinates[Math.floor(line.geometry.coordinates.length * .45)] : null;
    const info = { id, kind: 'nala', name: 'Barani Nala (storm drain)', block: null, area_kanal: null, proposed: false, accuracy: 'approximate',
      source: 'Traced from Esri World Imagery', length_m: line ? line.properties.length_m : null,
      _group: { rotation: { y: 0 } }, _top: 2, _L: 160, _W: 30, _center: mid ? W3(...P(...mid), 0) : new THREE.Vector3() };
    lmById.set(id, info); api.landmarks.push(info);
    for (const m of [wall, wat, bed, rails]) if (m) { m.userData.lm = id; pickables.push(m); }
    layers.stylised.push(bank, wall, bed, wat, rails);
    api.nala = line ? line.geometry.coordinates.map(c => P(c[0], c[1])) : null;
  }

  // ---- streetscape -----------------------------------------------------------------
  function buildStreetscape(features) {
    const quads = [];
    const lines = [];
    for (const f of features) {
      const p = f.properties, pts = f.geometry.coordinates.map(c => P(c[0], c[1]));
      lines.push({ p, pts });
    }
    const mains = lines.filter(l => l.p.class === 'main');
    const stripe = (pts, off, dash, gap, w) => {
      let carry = 0, on = true;
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy); if (L < .01) continue;
        const ux = dx / L, uy = dy / L, nx = -uy, ny = ux;
        let s = 0;
        while (s < L) {
          const left = (on ? dash : gap) - carry, e = Math.min(L, s + left);
          if (on && e - s > .05) { const o = [a[0] + nx * off, a[1] + ny * off]; quads.push([o[0] + ux * s, o[1] + uy * s, o[0] + ux * e, o[1] + uy * e, nx * w / 2, ny * w / 2]); }
          carry += e - s; s = e; if (carry >= (on ? dash : gap) - 1e-6) { carry = 0; on = gap === 0 ? true : !on; }
        }
      }
    };
    const inB = (x, y) => pipPlan(x, y, boundaryPlan);
    const along = (pts, step, start, fn) => {
      let acc = -start;
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy); if (L < .01) continue;
        const ux = dx / L, uy = dy / L;
        let s = (step - acc) % step; if (s < 0) s += step;
        for (; s <= L; s += step) {
          const total = acc + s; const nearEnd = i === 0 && s < 14 || i === pts.length - 2 && L - s < 14;
          if (!nearEnd) fn(a[0] + ux * s, a[1] + uy * s, ux, uy, total);
        }
        acc = (acc + L) % step;
      }
    };
    const otherMainDist = (l, x, y) => { let d = Infinity; for (const m of mains) if (m !== l) for (let i = 0; i < m.pts.length - 1; i++) d = Math.min(d, segDist(x, y, m.pts[i], m.pts[i + 1])); return d; };
    for (const l of lines) {
      const w = l.p.width_m || 12, cls = l.p.class;
      if (cls === 'main') {
        stripe(l.pts, w / 6, 3, 6, .15); stripe(l.pts, -w / 6, 3, 6, .15);
        stripe(l.pts, w / 2 - .45, 1, 0, .2); stripe(l.pts, -(w / 2 - .45), 1, 0, .2);
        along(l.pts, 34, 6, (x, y, ux, uy) => {
          for (const s of [1, -1]) {
            const off = s * (w / 2 + 1.3), px = x - uy * off, py = y + ux * off;
            if (!inB(px, py)) continue;
            const median = otherMainDist(l, px, py) < w / 2 + 2.2;
            lamps.street.push([px, Y.curb, -py, Math.atan2(-(s * ux), s * uy) + PI]);
            if (median) { const tx = x - uy * off + ux * 17, ty = y + ux * off + uy * 17; trees.palm.push([tx, Y.median, -ty, 1.05]); }
          }
        });
      } else if (cls === 'collector' || cls === 'arterial') {
        stripe(l.pts, 0, 3, 5, .15); stripe(l.pts, w / 2 - .4, 1, 0, .18); stripe(l.pts, -(w / 2 - .4), 1, 0, .18);
        along(l.pts, 40, 10, (x, y, ux, uy, t) => { const s = Math.round(t / 40) % 2 ? 1 : -1, off = s * (w / 2 + 1.1), px = x - uy * off, py = y + ux * off; if (inB(px, py)) lamps.street.push([px, Y.curb, -py, Math.atan2(-(s * ux), s * uy) + PI]); });
        along(l.pts, 22, 0, (x, y, ux, uy, t) => { for (const s of [1, -1]) { const off = s * (w / 2 + 1.8), px = x - uy * off, py = y + ux * off; if (inB(px, py) && (Math.round(t / 22) % 2)) trees.round.push([px, Y.curb, -py, .8 + ((t * 7) % 10) / 25]); } });
      } else if (cls === 'residential') {
        stripe(l.pts, 0, 2.5, 6, .12);
        along(l.pts, 46, 12, (x, y, ux, uy, t) => { const s = Math.round(t / 46) % 2 ? 1 : -1, off = s * (w / 2 + .9), px = x - uy * off, py = y + ux * off; if (inB(px, py)) lamps.street.push([px, Y.curb, -py, Math.atan2(-(s * ux), s * uy) + PI]); });
      }
    }
    // stripes -> one mesh
    const pos = new Float32Array(quads.length * 18), nor = new Float32Array(quads.length * 18), uv = new Float32Array(quads.length * 12);
    quads.forEach((q, i) => {
      const [x0, y0, x1, y1, ox, oy] = q, y = Y.mark;
      const A = [x0 + ox, y, -(y0 + oy)], B = [x1 + ox, y, -(y1 + oy)], C = [x1 - ox, y, -(y1 - oy)], D = [x0 - ox, y, -(y0 - oy)];
      const tri = (a, b, c, k) => { const ux = b[0] - a[0], uz = b[2] - a[2], vx = c[0] - a[0], vz = c[2] - a[2]; if (uz * vx - ux * vz < 0) { const t = b; b = c; c = t; } pos.set([...a, ...b, ...c], k); };
      tri(A, B, C, i * 18); tri(A, C, D, i * 18 + 9);
      for (let j = 0; j < 6; j++) nor.set([0, 1, 0], i * 18 + j * 3);
    });
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    layers.markings = addMesh(g, new THREE.MeshStandardMaterial({ color: '#ecebe4', roughness: .7 }));
    layers.stylised.push(layers.markings);
  }

  // ---- landmarks ------------------------------------------------------------------
  const lmGroups = [];
  function buildOne(f) {
    const p = f.properties, kind = p.kind;
    const group = new THREE.Group();
    let L, W, local;
    if (f.geometry.type === 'Point') {
      const [e, n] = P(...f.geometry.coordinates);
      group.position.set(e, Y.road, -n); group.rotation.y = (p.heading || 0) * PI / 180;
      L = 10; W = p.span || 30; local = [[-5, -W / 2], [5, -W / 2], [5, W / 2], [-5, W / 2]];
    } else {
      const o = p.obb, [cx, cn] = P(o.lon, o.lat), a = o.angle * PI / 180, ca = Math.cos(a), sa = Math.sin(a);
      group.position.set(cx, kind === 'roundabout' ? Y.road : Y.land, -cn); group.rotation.y = a;
      L = o.length; W = o.width;
      local = ringPlan(f.geometry.coordinates[0]).map(([e, n]) => { const de = e - cx, dn = n - cn; return [de * ca + dn * sa, de * sa - dn * ca]; });
    }
    scene.add(group); group.updateMatrixWorld(true);
    const k = makeKit(group, M, local, hooks);
    if (kind === 'gate') buildGate(k, W); else buildLandmark(kind, k, L, W, p);
    const info = Object.assign({}, p, { _group: group, _top: Math.max(6, k.top), _L: L, _W: W, _center: group.position.clone() });
    lmById.set(p.id, info); api.landmarks.push(info); lmGroups.push(group);
    group.userData.lm = p.id;
  }
  function bakeLandmarks() {
    const buckets = new Map(), keep = [];
    for (const g of lmGroups) {
      g.updateMatrixWorld(true);
      const id = g.userData.lm;
      g.traverse(o => {
        if (!o.isMesh) return;
        if (o.userData.keep || Array.isArray(o.material)) { keep.push(o); o.userData.lm = id; return; }
        let geo = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
        geo.applyMatrix4(o.matrixWorld);
        for (const name of Object.keys(geo.attributes)) if (!['position', 'normal', 'uv'].includes(name)) geo.deleteAttribute(name);
        if (!geo.attributes.uv) geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(geo.attributes.position.count * 2), 2));
        const ids = new Float32Array(geo.attributes.position.count).fill(id);
        geo.setAttribute('lmid', new THREE.BufferAttribute(ids, 1));
        const list = buckets.get(o.material) || []; list.push(geo); buckets.set(o.material, list);
      });
    }
    for (const o of keep) { scene.attach(o); pickables.push(o); if (o.userData.anim === 'flag') flags.push({ m: o, base: o.geometry.attributes.position.array.slice() }); }
    for (const g of lmGroups) scene.remove(g);
    for (const [mat, list] of buckets) {
      const merged = mergeGeometries(list);
      const mesh = new THREE.Mesh(merged, mat);
      const shadowless = mat === M.water || mat === M.flowers;
      mesh.castShadow = !shadowless; mesh.receiveShadow = true; mesh.userData.landmarks = true;
      scene.add(mesh); pickables.push(mesh);
    }
  }

  // ---- plots ---------------------------------------------------------------------
  function padGeometry(items, y0, y1) {
    let tris = 0;
    for (const it of items) tris += it.tris.length + it.ring.length * 2;
    const pos = new Float32Array(tris * 9), nor = new Float32Array(tris * 9), col = new Float32Array(tris * 9), pid = new Float32Array(tris * 3);
    let v = 0;
    const put = (a, b, c, n, id) => {
      const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
      const cx = uy * vz - uz * vy, cy = uz * vx - ux * vz, cz = ux * vy - uy * vx;
      if (cx * n[0] + cy * n[1] + cz * n[2] < 0) { const t = b; b = c; c = t; }
      for (const q of [a, b, c]) { pos.set(q, v * 3); nor.set(n, v * 3); pid[v] = id; v++; }
    };
    for (const it of items) {
      it._v0 = v;
      const r = it.ring, up = [0, 1, 0];
      for (const t of it.tris) put([r[t[0]][0], y1, -r[t[0]][1]], [r[t[1]][0], y1, -r[t[1]][1]], [r[t[2]][0], y1, -r[t[2]][1]], up, it.idx);
      it._vTop = v - it._v0;
      for (let i = 0; i < r.length; i++) {
        const a = r[i], b = r[(i + 1) % r.length], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
        const n = [dy / L, 0, dx / L];
        const A0 = [a[0], y0, -a[1]], B0 = [b[0], y0, -b[1]], A1 = [a[0], y1, -a[1]], B1 = [b[0], y1, -b[1]];
        put(A0, B0, B1, n, it.idx); put(A0, B1, A1, n, it.idx);
      }
      it._vN = v - it._v0;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    g.setAttribute('pid', new THREE.BufferAttribute(pid, 1));
    return g;
  }
  function plotItem(f, idx, shrink = .3) {
    let ring = ringPlan(f.geometry.coordinates[0]);
    if (area2(ring) < 0) ring.reverse();
    const c = cen2(ring);
    ring = ring.map(([x, y]) => { const dx = x - c[0], dy = y - c[1], d = Math.hypot(dx, dy) || 1, s = Math.min(shrink, d * .1); return [x - dx / d * s, y - dy / d * s]; });
    const tris = THREE.ShapeUtils.triangulateShape(ring.map(p => new THREE.Vector2(p[0], p[1])), []);
    return { ring, tris, idx, c };
  }
  const plotItems = [];
  function buildPlots(features) {
    features.forEach((f, i) => {
      const p = f.properties, it = plotItem(f, i);
      p._i = i; p._c = it.c; p._ring = it.ring;
      plotItems.push(it); api.plots.push(p); byId.set(p.id, p); byNo.set(String(p.plot_no).toUpperCase(), p.id);
    });
    plotGeom = padGeometry(plotItems, Y.plotBase, Y.plotTop);
    plotMesh = new THREE.Mesh(plotGeom, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .78, metalness: 0 }));
    plotMesh.castShadow = true; plotMesh.receiveShadow = true; plotMesh.userData.plots = true;
    scene.add(plotMesh); pickables.push(plotMesh);
    recolor();
    // outlines
    let n = 0; for (const it of plotItems) n += it.ring.length;
    const lp = new Float32Array(n * 6); let k = 0;
    for (const it of plotItems) for (let i = 0; i < it.ring.length; i++) { const a = it.ring[i], b = it.ring[(i + 1) % it.ring.length]; lp.set([a[0], Y.plotTop + .02, -a[1], b[0], Y.plotTop + .02, -b[1]], k); k += 6; }
    const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.BufferAttribute(lp, 3));
    plotLines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: '#3d3024', transparent: true, opacity: .45 }));
    scene.add(plotLines);
    // spatial index for labels and coordinate search
    for (const p of api.plots) { const key = gridKey(p._c[0], p._c[1]); (grid.get(key) || grid.set(key, []).get(key)).push(p); }
    // optional BVH for fast picking
    import('three-mesh-bvh').then(m => {
      THREE.BufferGeometry.prototype.computeBoundsTree = m.computeBoundsTree; THREE.Mesh.prototype.raycast = m.acceleratedRaycast;
      plotGeom.computeBoundsTree(); for (const o of pickables) if (o.geometry && o.geometry !== plotGeom && o.geometry.attributes.position.count > 3000) o.geometry.computeBoundsTree();
    }).catch(() => {});
  }
  const grid = new Map(), CELL = 60, gridKey = (x, y) => Math.floor(x / CELL) + ',' + Math.floor(y / CELL);
  function plotColor(p, layer) {
    if (layer === 'sat') return new THREE.Color(p.built ? COLORS.sat.built : COLORS.sat.vacant);
    const c = new THREE.Color(layer === 'stat' ? (COLORS.stat[p.status] || COLORS.stat.Unknown) : (COLORS.cls[p.dev_class] || COLORS.cls.Low));
    return p.built ? c : c.lerp(new THREE.Color('#e9e1c8'), .38);
  }
  function recolor() {
    const col = plotGeom.attributes.color.array;
    plotItems.forEach((it, i) => {
      const c = plotColor(api.plots[i], api.layer), s = c.clone().multiplyScalar(.68);
      for (let v = 0; v < it._vN; v++) { const q = v < it._vTop ? c : s; col.set([q.r, q.g, q.b], (it._v0 + v) * 3); }
    });
    plotGeom.attributes.color.needsUpdate = true;
  }

  // ---- instanced trees, lamps, cars ------------------------------------------------
  function colored(geom, hex) {
    const g = geom.index ? geom.toNonIndexed() : geom; const c = new THREE.Color(hex), n = g.attributes.position.count, a = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) a.set([c.r, c.g, c.b], i * 3);
    g.setAttribute('color', new THREE.BufferAttribute(a, 3)); return g;
  }
  const treeGeo = {
    round: () => mergeGeometries([colored(new THREE.CylinderGeometry(.16, .26, 3.2, 6).translate(0, 1.6, 0), '#6b4a2e'), colored(new THREE.IcosahedronGeometry(2.4, 1).scale(1, .82, 1).translate(0, 4.6, 0), '#4f8a3a'), colored(new THREE.IcosahedronGeometry(1.6, 1).translate(.9, 5.6, .5), '#5d9a42')]),
    cone: () => mergeGeometries([colored(new THREE.CylinderGeometry(.13, .2, 1.8, 6).translate(0, .9, 0), '#5d4029'), colored(new THREE.ConeGeometry(1.5, 6.4, 9).translate(0, 4.6, 0), '#2f6b35')]),
    palm: () => { const parts = [colored(new THREE.CylinderGeometry(.17, .27, 7.4, 7).translate(0, 3.7, 0), '#8a6b45')]; for (let i = 0; i < 8; i++) { const g = new THREE.BoxGeometry(3.4, .08, .7).translate(1.7, 0, 0).rotateZ(-.38 - (i % 2) * .15).rotateY(i / 8 * 2 * PI).translate(0, 7.4, 0); parts.push(colored(g, i % 2 ? '#4f8f3a' : '#3f7d32')); } parts.push(colored(new THREE.SphereGeometry(.45, 8, 6).translate(0, 7.1, 0), '#6d5a2a')); return mergeGeometries(parts); }
  };
  function buildInstances() {
    const treeMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .92 });
    const r = rng(5), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
    for (const type of Object.keys(trees)) {
      const list = trees[type]; if (!list.length) continue;
      const im = new THREE.InstancedMesh(treeGeo[type](), treeMat, list.length);
      list.forEach((t, i) => { const sc = t[3] * (.85 + r() * .3); q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), r() * 2 * PI); im.setMatrixAt(i, m4.compose(p.set(t[0], t[1], t[2]), q, s.set(sc, sc * (.9 + r() * .25), sc))); im.setColorAt(i, c.setHSL(.27 + (r() - .5) * .06, .25 + r() * .2, .45 + r() * .15).multiplyScalar(1.9)); });
      im.castShadow = true; im.receiveShadow = true; scene.add(im);
    }
    // lamps
    const poleGeo = mergeGeometries([new THREE.CylinderGeometry(.08, .14, 9, 6).translate(0, 4.5, 0), new THREE.BoxGeometry(2.2, .12, .12).translate(1.05, 8.9, 0)]);
    const headGeo = new THREE.BoxGeometry(.85, .2, .38).translate(2.05, 8.78, 0);
    const parkPole = new THREE.CylinderGeometry(.06, .09, 3.8, 6).translate(0, 1.9, 0), parkHead = new THREE.SphereGeometry(.28, 10, 8).translate(0, 4.0, 0);
    const mk = (list, gp, gh) => {
      if (!list.length) return;
      const a = new THREE.InstancedMesh(gp, M.darkSteel, list.length), b = new THREE.InstancedMesh(gh, M.lampOn, list.length);
      list.forEach((l, i) => { q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), l[3]); m4.compose(p.set(l[0], l[1], l[2]), q, s.set(1, 1, 1)); a.setMatrixAt(i, m4); b.setMatrixAt(i, m4); });
      a.castShadow = true; scene.add(a, b);
    };
    mk(lamps.street, poleGeo, headGeo); mk(lamps.park, parkPole, parkHead);
    // parked cars
    if (staticCars.length) {
      const cm = new THREE.InstancedMesh(carGeometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .45, metalness: .3 }), staticCars.length);
      staticCars.forEach((t, i) => { q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), t[3]); cm.setMatrixAt(i, m4.compose(p.set(t[0], t[1] + .03, t[2]), q, s.set(1, 1, 1))); cm.setColorAt(i, c.set(t[4] || CAR_COLORS[(i * 7) % CAR_COLORS.length])); });
      cm.castShadow = true; scene.add(cm);
    }
  }
  const CAR_COLORS = ['#f2f2f2', '#c7c9cc', '#1e1e20', '#a3262a', '#2a4f8f', '#f2f2f2', '#6b6f75', '#d9c39a', '#ffffff'];
  function carGeometry() {
    return mergeGeometries([
      colored(new THREE.BoxGeometry(4.3, .8, 1.8).translate(0, .62, 0), '#ffffff'),
      colored(new THREE.BoxGeometry(2.3, .65, 1.62).translate(-.25, 1.33, 0), '#26313a'),
      ...[[-1.35, .9], [1.35, .9], [-1.35, -.9], [1.35, -.9]].map(([x, z]) => colored(new THREE.CylinderGeometry(.34, .34, .25, 10).rotateX(PI / 2).translate(x, .34, z), '#151515'))
    ]);
  }
  function buildCars(features) {
    const paths = [];
    for (const f of features) {
      const pr = f.properties; if (!['main', 'collector'].includes(pr.class)) continue;
      const pts = f.geometry.coordinates.map(c => P(c[0], c[1])); let len = 0; const cum = [0];
      for (let i = 1; i < pts.length; i++) { len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); cum.push(len); }
      if (len > 120) paths.push({ pts, cum, len, w: pr.width_m || 12, main: pr.class === 'main' });
    }
    const r = rng(11), cars = [];
    for (const pa of paths) {
      const n = Math.floor(pa.len / (pa.main ? 45 : 95));
      for (let i = 0; i < n; i++) {
        const dir = pa.main ? 1 : (r() < .5 ? 1 : -1);
        const lane = pa.main ? [-1, 0, 1][(r() * 3) | 0] * pa.w / 3 : dir * pa.w / 4;
        cars.push({ pa, s: r() * pa.len, v: (pa.main ? 11 : 8) + r() * 5, dir, lane });
      }
    }
    if (!cars.length) return;
    const body = new THREE.InstancedMesh(carGeometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .4, metalness: .35 }), cars.length);
    const lights = new THREE.InstancedMesh(mergeGeometries([new THREE.BoxGeometry(.1, .18, .35).translate(2.16, .72, .6), new THREE.BoxGeometry(.1, .18, .35).translate(2.16, .72, -.6)]), M.lampOn, cars.length);
    const c = new THREE.Color();
    cars.forEach((car, i) => body.setColorAt(i, c.set(CAR_COLORS[(i * 5) % CAR_COLORS.length])));
    body.castShadow = true; scene.add(body, lights);
    carSystem = { cars, body, lights };
    stepCars(0);
  }
  const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _p = new THREE.Vector3(), _s = new THREE.Vector3(1, 1, 1), _up = new THREE.Vector3(0, 1, 0);
  function stepCars(dt) {
    if (!carSystem) return;
    const { cars, body, lights } = carSystem;
    cars.forEach((car, i) => {
      const pa = car.pa; car.s = (car.s + car.v * dt * car.dir + pa.len) % pa.len;
      let k = 1; while (k < pa.cum.length - 1 && pa.cum[k] < car.s) k++;
      const a = pa.pts[k - 1], b = pa.pts[k], seg = pa.cum[k] - pa.cum[k - 1] || 1, t = (car.s - pa.cum[k - 1]) / seg;
      const dx = (b[0] - a[0]) / seg, dy = (b[1] - a[1]) / seg, x = a[0] + (b[0] - a[0]) * t - dy * car.lane, y = a[1] + (b[1] - a[1]) * t + dx * car.lane;
      _q.setFromAxisAngle(_up, Math.atan2(dy * car.dir, dx * car.dir));
      _m.compose(_p.set(x, Y.road, -y), _q, _s); body.setMatrixAt(i, _m); lights.setMatrixAt(i, _m);
    });
    body.instanceMatrix.needsUpdate = true; lights.instanceMatrix.needsUpdate = true;
  }

  // ---- labels --------------------------------------------------------------------
  const lmLabels = [], blockLabels = [], plotLabelPool = [];
  function label(text, cls, color) {
    const d = document.createElement('div'); d.className = cls; d.textContent = text; if (color) d.style.setProperty('--k', color);
    return new CSS2DObject(d);
  }
  function buildLabels() {
    for (const lm of api.landmarks) {
      if (lm.kind === 'roundabout' && !lm.monument) continue;
      const o = label(lm.name, 's3d-lbl', KIND_COLOR[lm.kind]);
      o.position.copy(lm._center).setY(lm._top + 4); o.userData.lm = lm; scene.add(o); lmLabels.push(o);
      o.element.addEventListener('click', e => { e.stopPropagation(); selectLandmark(lm.id); });
    }
    const sums = {};
    for (const p of api.plots) { const s = sums[p.block] || (sums[p.block] = [0, 0, 0]); s[0] += p._c[0]; s[1] += p._c[1]; s[2]++; }
    for (const b in sums) { const s = sums[b], o = label(b.toUpperCase(), 's3d-blk'); o.position.set(s[0] / s[2], 70, -s[1] / s[2]); scene.add(o); blockLabels.push(o); }
    for (let i = 0; i < 160; i++) { const o = label('', 's3d-pn'); o.visible = false; scene.add(o); plotLabelPool.push(o); }
  }
  let lastPlotLabelUpdate = 0;
  function updateLabels(now) {
    const dist = camera.position.distanceTo(controls.target);
    for (const o of blockLabels) o.visible = api.labels && dist > 650;
    for (const o of lmLabels) { const d = camera.position.distanceTo(o.position), lm = o.userData.lm; const major = ['hospital', 'gate', 'stadium', 'university', 'cinema', 'nala'].includes(lm.kind) || lm.monument === 'clocktower'; const minor = lm.kind === 'park' || lm.kind === 'roundabout'; o.visible = api.labels && (major ? dist < 3200 && d < 3600 : dist < (minor ? 700 : 1250) && d < (minor ? 900 : 1500)); }
    if (now - lastPlotLabelUpdate < 220) return;
    lastPlotLabelUpdate = now;
    let used = 0;
    if (api.labels && dist < 360) {
      const t = controls.target, R = Math.min(240, dist * .75), cx = t.x, cy = -t.z, near = [];
      for (let gx = Math.floor((cx - R) / CELL); gx <= Math.floor((cx + R) / CELL); gx++) for (let gy = Math.floor((cy - R) / CELL); gy <= Math.floor((cy + R) / CELL); gy++) {
        const list = grid.get(gx + ',' + gy); if (!list) continue;
        for (const p of list) { const d = Math.hypot(p._c[0] - cx, p._c[1] - cy); if (d < R) near.push([d, p]); }
      }
      near.sort((a, b) => a[0] - b[0]);
      for (const [, p] of near.slice(0, plotLabelPool.length)) { const o = plotLabelPool[used++]; o.element.textContent = p.plot_no; o.position.set(p._c[0], Y.plotTop + .4, -p._c[1]); o.visible = true; }
    }
    for (let i = used; i < plotLabelPool.length; i++) plotLabelPool[i].visible = false;
  }

  // ---- selection -------------------------------------------------------------------
  const selGroup = new THREE.Group(); scene.add(selGroup);
  const beamMat = new THREE.MeshBasicMaterial({ color: '#ffd84d', transparent: true, opacity: .28, blending: THREE.AdditiveBlending, depthWrite: false });
  const hoverLine = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#ffffff' })); hoverLine.visible = false; scene.add(hoverLine);
  function clearSelGroup() { while (selGroup.children.length) { const o = selGroup.children.pop(); if (o.geometry) o.geometry.dispose(); } }
  function beam(x, z, y0, h) { const b = new THREE.Mesh(new THREE.CylinderGeometry(.7, .7, h, 16, 1, true).translate(0, h / 2, 0), beamMat); b.position.set(x, y0, z); b.userData.beam = true; selGroup.add(b); }
  function select(id, fly = true) {
    const p = byId.get(+id); if (!p) return null;
    clearSelGroup(); api.selected = { plot: p.id };
    const it = plotItem({ geometry: { coordinates: [[...p._ring.map(([e, n]) => [e / KX + LON0, n / KY + LAT0])]] } }, 0, -.15);
    const g = padGeometry([it], Y.plotBase, Y.plotTop + .35); const col = g.attributes.color.array; for (let i = 0; i < col.length; i += 3) col.set([1, .85, .3], i);
    selGroup.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, emissive: '#ffb800', emissiveIntensity: .55, roughness: .5 })));
    beam(p._c[0], -p._c[1], Y.plotTop, 70);
    if (fly) flyTo(new THREE.Vector3(p._c[0], 0, -p._c[1]), 170);
    if (opts.onPick) opts.onPick(publicProps(p));
    return publicProps(p);
  }
  function selectLandmark(id, fly = true) {
    const lm = lmById.get(+id); if (!lm) return null;
    clearSelGroup(); api.selected = { landmark: lm.id };
    const box = new THREE.BoxGeometry(lm._L + 2, lm._top + 2, lm._W + 2).translate(0, (lm._top + 2) / 2, 0);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({ color: '#ffd84d' }));
    edges.position.copy(lm._center); edges.rotation.y = lm._group.rotation.y; selGroup.add(edges);
    beam(lm._center.x, lm._center.z, lm._top + 2, 60);
    if (fly) flyTo(lm._center.clone().setY(0), Math.max(110, Math.max(lm._L, lm._W) * 1.9 + lm._top * 1.5));
    const out = publicLm(lm);
    if (opts.onPick) opts.onPick(out);
    return out;
  }
  function clearSelection() { clearSelGroup(); api.selected = null; }
  const publicProps = p => { const o = {}; for (const k in p) if (k[0] !== '_') o[k] = p[k]; return o; };
  const publicLm = lm => Object.assign(publicProps(lm), { landmark: true, type_label: KIND_LABEL[lm.kind] || lm.kind, height_m: lm.kind === 'nala' ? null : Math.round(lm._top) });

  // ---- picking -------------------------------------------------------------------
  const ray = new THREE.Raycaster(); ray.firstHitOnly = true;
  const ndc = new THREE.Vector2();
  function pickAt(cx, cy) {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set((cx - r.left) / r.width * 2 - 1, -(cy - r.top) / r.height * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects(pickables, false);
    for (const h of hits) {
      const o = h.object;
      if (o.userData.plots && h.face) return { plot: api.plots[o.geometry.attributes.pid.array[h.face.a]] };
      if (o.userData.landmarks && h.face) return { lm: lmById.get(o.geometry.attributes.lmid.array[h.face.a]) };
      if (o.userData.lm) return { lm: lmById.get(o.userData.lm) };
    }
    return null;
  }
  let down = null, hoverT = 0;
  renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6 || !built) { down = null; return; }
    down = null;
    const h = pickAt(e.clientX, e.clientY);
    if (h && h.plot) select(h.plot.id, false);
    else if (h && h.lm) selectLandmark(h.lm.id, false);
    else { clearSelection(); if (opts.onPick) opts.onPick(null); }
  });
  renderer.domElement.addEventListener('pointermove', e => {
    if (!built || e.buttons) return;
    const now = performance.now(); if (now - hoverT < 70) return; hoverT = now;
    const h = pickAt(e.clientX, e.clientY);
    const r = renderer.domElement.getBoundingClientRect(), pos = { x: e.clientX - r.left, y: e.clientY - r.top };
    if (h && h.plot) {
      const ring = h.plot._ring, a = new Float32Array(ring.length * 3); ring.forEach((q, i) => a.set([q[0], Y.plotTop + .06, -q[1]], i * 3));
      hoverLine.geometry.setAttribute('position', new THREE.BufferAttribute(a, 3)); hoverLine.geometry.computeBoundingSphere(); hoverLine.visible = true;
      renderer.domElement.style.cursor = 'pointer';
      if (opts.onHover) opts.onHover(publicProps(h.plot), pos);
    } else if (h && h.lm) {
      hoverLine.visible = false; renderer.domElement.style.cursor = 'pointer';
      if (opts.onHover) opts.onHover(publicLm(h.lm), pos);
    } else { hoverLine.visible = false; renderer.domElement.style.cursor = ''; if (opts.onHover) opts.onHover(null, pos); }
  });
  renderer.domElement.addEventListener('pointerleave', () => { hoverLine.visible = false; if (opts.onHover) opts.onHover(null); });

  // ---- camera ------------------------------------------------------------------------
  let flight = null;
  const sph = new THREE.Spherical();
  function flyTo(target, dist, polar, azimuth, dur = 1.3) {
    const off = camera.position.clone().sub(controls.target); sph.setFromVector3(off);
    const from = { t: controls.target.clone(), r: sph.radius, phi: sph.phi, th: sph.theta };
    let th = azimuth == null ? sph.theta : azimuth; while (th - from.th > PI) th -= 2 * PI; while (th - from.th < -PI) th += 2 * PI;
    flight = { from, to: { t: target.clone(), r: dist, phi: polar == null ? Math.min(sph.phi, 1.05) : polar, th }, t0: performance.now(), dur: dur * 1000 };
  }
  function stepFlight(now) {
    if (!flight) return;
    const k = Math.min(1, (now - flight.t0) / flight.dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2, f = flight.from, t = flight.to;
    controls.target.lerpVectors(f.t, t.t, e);
    const r = Math.exp(Math.log(f.r) + (Math.log(t.r) - Math.log(f.r)) * e);
    sph.set(r, f.phi + (t.phi - f.phi) * e, f.th + (t.th - f.th) * e);
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sph));
    if (k >= 1) flight = null;
  }
  function reset(dur = 1.6) {
    const az = Math.atan2(-Math.cos(axisRad), Math.sin(axisRad)) + .35;  // from the south-west entrance, looking up the boulevard
    if (!dur) { sph.set(homeDist, .82, az); controls.target.copy(homeTarget); camera.position.copy(homeTarget).add(new THREE.Vector3().setFromSpherical(sph)); controls.update(); return; }
    flyTo(homeTarget, homeDist, .82, az, dur);
  }
  function zoomBy(f) { const t = controls.target, d = camera.position.distanceTo(t); flyTo(t.clone(), Math.max(controls.minDistance, Math.min(controls.maxDistance, d / f)), null, null, .5); }
  function flyToBlock(letter) {
    const ps = api.plots.filter(p => p.block.endsWith(' ' + String(letter).toUpperCase())); if (!ps.length) return false;
    let x = 0, y = 0; for (const p of ps) { x += p._c[0]; y += p._c[1]; } x /= ps.length; y /= ps.length;
    let r = 0; for (const p of ps) r = Math.max(r, Math.hypot(p._c[0] - x, p._c[1] - y));
    flyTo(new THREE.Vector3(x, 0, -y), Math.max(350, r * 1.9), .85);
    return true;
  }

  // ---- search ----------------------------------------------------------------------
  function search(q) {
    q = String(q || '').trim(); if (!q) return [];
    const m = q.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (m) {
      const lat = +m[1], lon = +m[2]; if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return [];
      const [e, n] = P(lon, lat); let best = null, bd = Infinity;
      for (const p of api.plots) { const d = Math.hypot(p._c[0] - e, p._c[1] - n); if (d < bd) { bd = d; best = p; } }
      return best && bd < 1500 ? [{ id: best.id, label: best.plot_no, sub: best.block + ' · ' + Math.round(bd) + ' m from the point' }] : [];
    }
    const n = q.toUpperCase().replace(/\s+/g, ''), out = [];
    const ex = byNo.get(n) || byNo.get(n.replace(/^([A-F])(\d+)$/, '$1-$2'));
    if (ex != null) { const p = byId.get(ex); out.push({ id: p.id, label: p.plot_no, sub: p.block + ' · ' + p.size + ' · ' + p.status }); }
    const bm = q.match(/^(?:block\s*)?([a-fA-F])$/);
    if (bm) out.push({ block: bm[1].toUpperCase(), label: 'Block ' + bm[1].toUpperCase(), sub: api.plots.filter(p => p.block.endsWith(' ' + bm[1].toUpperCase())).length + ' plots' });
    const words = q.toLowerCase().split(/\s+/);
    for (const lm of api.landmarks) {
      const hay = (lm.name + ' ' + (KIND_LABEL[lm.kind] || '') + ' ' + (lm.block || '')).toLowerCase();
      if (words.every(w => hay.includes(w) || (w.length === 1 && hay.includes('(' + w + ')')))) out.push({ lm: lm.id, label: lm.name, sub: (KIND_LABEL[lm.kind] || lm.kind) + (lm.block ? ' · ' + lm.block : '') });
      if (out.length >= 10) break;
    }
    if (out.length) return out.slice(0, 10);
    const pref = n.replace(/^([A-F])(\d)/, '$1-$2');
    for (const p of api.plots) { if (String(p.plot_no).toUpperCase().startsWith(pref)) { out.push({ id: p.id, label: p.plot_no, sub: p.block + ' · ' + p.size + ' · ' + p.status }); if (out.length >= 8) break; } }
    return out;
  }

  // ---- day / night, ground, labels --------------------------------------------------
  function setTime(t) {
    api.time = t === 'night' ? 'night' : 'day';
    const night = api.time === 'night';
    hemi.intensity = night ? .16 : 1.05; hemi.color.set(night ? '#5a6fa8' : '#d6e9ff'); hemi.groundColor.set(night ? '#1d1a14' : '#6b5b3b');
    sun.intensity = night ? .32 : 2.7; sun.color.set(night ? '#9fb4ff' : '#fff0d4');
    scene.environmentIntensity = night ? .06 : .45;
    skyU.top.value.set(night ? '#060b1a' : '#5d93d6'); skyU.hor.value.set(night ? '#1b2440' : '#dbe8f2'); skyU.bot.value.set(night ? '#0d0f14' : '#c9c3b1');
    scene.fog.color.set(night ? '#141b30' : '#dbe8f2');
    stars.visible = night;
    for (const m of M.night) m.emissiveIntensity = night ? (m === M.lampOn ? 4 : 1.3) : 0;
    for (const m of nightSigns) m.emissiveIntensity = night ? .7 : 0;
    M.water.emissiveIntensity = night ? .9 : .35;
    renderer.toneMappingExposure = night ? 1.1 : 1.0;
    if (night) ensureComposer();
  }
  let satTex = null;
  async function setGround(kind) {
    api.ground = kind === 'satellite' ? 'satellite' : 'plan';
    const sat = api.ground === 'satellite';
    if (sat && !layers.satellite) { status('loading', 'Loading satellite imagery…'); try { layers.satellite = await satelliteGround(); } catch (e) { console.warn(e); status('ready'); api.ground = 'plan'; return 'plan'; } status('ready'); }
    for (const o of layers.stylised) if (o) o.visible = !sat;
    if (layers.satellite) layers.satellite.visible = sat;
    plotMesh.material.transparent = sat; plotMesh.material.opacity = sat ? .55 : 1; plotMesh.material.depthWrite = !sat; plotMesh.material.needsUpdate = true;
    return api.ground;
  }
  async function satelliteGround() {
    // Esri World Imagery tiles stitched into one texture over the society (+ margin)
    let minE = Infinity, maxE = -Infinity, minN = Infinity, maxN = -Infinity;
    for (const [e, n] of boundaryPlan) { minE = Math.min(minE, e); maxE = Math.max(maxE, e); minN = Math.min(minN, n); maxN = Math.max(maxN, n); }
    const m = 700, lon0 = LON0 + (minE - m) / KX, lon1 = LON0 + (maxE + m) / KX, lat0 = LAT0 + (minN - m) / KY, lat1 = LAT0 + (maxN + m) / KY;
    const maxTex = Math.min(renderer.capabilities.maxTextureSize, 8192);
    let z = 17, tx0, tx1, ty0, ty1;
    const tile = (lon, lat, zz) => [Math.floor((lon + 180) / 360 * 2 ** zz), Math.floor((1 - Math.log(Math.tan(lat * PI / 180) + 1 / Math.cos(lat * PI / 180)) / PI) / 2 * 2 ** zz)];
    for (; z >= 14; z--) { [tx0, ty0] = tile(lon0, lat1, z); [tx1, ty1] = tile(lon1, lat0, z); if ((tx1 - tx0 + 1) * 256 <= maxTex && (ty1 - ty0 + 1) * 256 <= maxTex) break; }
    const nx = tx1 - tx0 + 1, ny = ty1 - ty0 + 1, c = document.createElement('canvas'); c.width = nx * 256; c.height = ny * 256;
    const g = c.getContext('2d'); g.fillStyle = '#6b6a5a'; g.fillRect(0, 0, c.width, c.height);
    const jobs = [];
    for (let x = tx0; x <= tx1; x++) for (let y = ty0; y <= ty1; y++) jobs.push(new Promise(res => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => { g.drawImage(im, (x - tx0) * 256, (y - ty0) * 256); res(); }; im.onerror = () => res(); im.src = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`; }));
    await Promise.all(jobs);
    const tLon = x => x / 2 ** z * 360 - 180, tLat = y => Math.atan(Math.sinh(PI * (1 - 2 * y / 2 ** z))) * 180 / PI;
    const [e0, n1] = P(tLon(tx0), tLat(ty0)), [e1, n0] = P(tLon(tx1 + 1), tLat(ty1 + 1));
    satTex = new THREE.CanvasTexture(c); satTex.colorSpace = THREE.SRGBColorSpace; satTex.anisotropy = 8;
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(e1 - e0, n1 - n0), new THREE.MeshStandardMaterial({ map: satTex, roughness: 1 }));
    plane.rotation.x = -PI / 2; plane.position.set((e0 + e1) / 2, .01, -(n0 + n1) / 2); plane.receiveShadow = true;
    const under = new THREE.Mesh(new THREE.PlaneGeometry(24000, 24000), new THREE.MeshStandardMaterial({ color: '#6f6d58', roughness: 1 })); under.rotation.x = -PI / 2; under.position.y = -.3;
    const grp = new THREE.Group(); grp.add(plane, under); grp.visible = false; scene.add(grp);
    return grp;
  }
  function setLabels(on) { api.labels = !!on; if (!api.labels) for (const o of [...lmLabels, ...blockLabels, ...plotLabelPool]) o.visible = false; lastPlotLabelUpdate = 0; }
  function setLayer(layer) { if (!COLORS[layer] || !plotGeom) { api.layer = layer; return; } api.layer = layer; recolor(); }

  // ---- mini-map and compass ----------------------------------------------------------
  let mini = null;
  function buildMinimap() {
    const wrap = document.createElement('div'); wrap.className = 's3d-mini';
    const c = document.createElement('canvas'); const S = 176; c.width = c.height = S * 2; c.style.width = c.style.height = S + 'px'; wrap.appendChild(c);
    const comp = document.createElement('button'); comp.className = 's3d-compass'; comp.title = 'Face north'; comp.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 2l4 10h-8z" fill="#e05a47"/><path d="M12 22l-4-10h8z" fill="#e8dfc8"/></svg>';
    el.appendChild(wrap); el.appendChild(comp);
    let minE = Infinity, maxE = -Infinity, minN = Infinity, maxN = -Infinity;
    for (const [e, n] of boundaryPlan) { minE = Math.min(minE, e); maxE = Math.max(maxE, e); minN = Math.min(minN, n); maxN = Math.max(maxN, n); }
    const pad = 40, sc = (S * 2 - 2 * pad) / Math.max(maxE - minE, maxN - minN), ox = S - (minE + maxE) / 2 * sc, oy = S + (minN + maxN) / 2 * sc;
    const toC = (e, n) => [ox + e * sc, oy - n * sc], toPlan = (x, y) => [(x - ox) / sc, (oy - y) / sc];
    const base = document.createElement('canvas'); base.width = base.height = S * 2; const g = base.getContext('2d');
    g.fillStyle = 'rgba(20,14,9,.88)'; g.fillRect(0, 0, S * 2, S * 2);
    g.beginPath(); boundaryPlan.forEach(([e, n], i) => { const [x, y] = toC(e, n); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); g.fillStyle = '#4f6b3c'; g.fill();
    const plotCol = { High: '#3fae5f', Medium: '#e0a93a', Low: '#c9573f' };
    for (const p of api.plots) { const [x, y] = toC(p._c[0], p._c[1]); g.fillStyle = plotCol[p.dev_class]; g.fillRect(x - .9, y - .9, 1.8, 1.8); }
    if (api.nala) { g.strokeStyle = '#3d9be0'; g.lineWidth = 3; g.beginPath(); api.nala.forEach(([e, n], i) => { const [x, y] = toC(e, n); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); }
    for (const lm of api.landmarks) { if (lm.kind === 'nala') continue; const [x, y] = toC(lm._center.x, -lm._center.z); g.fillStyle = KIND_COLOR[lm.kind] || '#fff'; g.beginPath(); g.arc(x, y, lm.kind === 'park' ? 3 : 4, 0, 2 * PI); g.fill(); }
    g.strokeStyle = '#f3ead8'; g.lineWidth = 2; g.beginPath(); boundaryPlan.forEach(([e, n], i) => { const [x, y] = toC(e, n); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); g.stroke();
    const ctx = c.getContext('2d');
    mini = () => {
      ctx.drawImage(base, 0, 0);
      const t = controls.target, [x, y] = toC(t.x, -t.z), d = camera.position.distanceTo(t), az = Math.atan2(camera.position.x - t.x, camera.position.z - t.z);
      const half = Math.min(S * .9, d * .45 * sc), dir = [-Math.sin(az), Math.cos(az)];
      ctx.fillStyle = 'rgba(255,216,77,.22)'; ctx.strokeStyle = '#ffd84d'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x, y);
      for (const s of [-.55, .55]) { const a = Math.atan2(dir[1], dir[0]) + s; ctx.lineTo(x + Math.cos(a) * half * 1.4, y - Math.sin(a) * half * 1.4); }
      ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#ffd84d'; ctx.beginPath(); ctx.arc(x, y, 5, 0, 2 * PI); ctx.fill();
      comp.style.transform = `rotate(${az + PI}rad)`;
    };
    c.addEventListener('click', e => { const r = c.getBoundingClientRect(), [pe, pn] = toPlan((e.clientX - r.left) * 2, (e.clientY - r.top) * 2); flyTo(new THREE.Vector3(pe, 0, -pn), Math.min(camera.position.distanceTo(controls.target), 900)); });
    comp.addEventListener('click', () => flyTo(controls.target.clone(), camera.position.distanceTo(controls.target), null, 0, .8));
  }

  // ---- loop ------------------------------------------------------------------------
  function resize() {
    const w = el.clientWidth || 800, h = el.clientHeight || 500;
    renderer.setSize(w, h, false); labelR.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    if (composer) { composer.setSize(w, h); bloom.setSize(w, h); }
  }
  new ResizeObserver(resize).observe(el); resize();
  let last = performance.now(), lastMini = 0, shadowD = 0;
  function loop(now) {
    requestAnimationFrame(loop);
    if (document.hidden) return;
    const dt = Math.min(.1, (now - last) / 1000); last = now;
    stepFlight(now);
    controls.update();
    sky.position.copy(camera.position); stars.position.copy(camera.position);
    // shadow frustum follows the view
    const t = controls.target, dist = camera.position.distanceTo(t), d = Math.max(110, Math.min(2600, dist * 1.05));
    if (Math.abs(d - shadowD) / d > .06) { shadowD = d; const sc = sun.shadow.camera; sc.left = -d; sc.right = d; sc.top = d; sc.bottom = -d; sc.near = 10; sc.far = d * 4 + 3000; sc.updateProjectionMatrix(); }
    sun.target.position.copy(t); sun.position.copy(t).addScaledVector(SUN_DIR, d * 1.6 + 600);
    if (built) {
      stepCars(dt);
      const tt = now / 1000;
      for (const f of flags) { const a = f.m.geometry.attributes.position, b = f.base; for (let i = 0; i < a.count; i++) { const x = b[i * 3]; a.array[i * 3 + 2] = b[i * 3 + 2] + Math.sin(x * 2.4 - tt * 4) * .14 * x / 2.4; } a.needsUpdate = true; }
      beamMat.opacity = .2 + .12 * Math.sin(tt * 3);
      updateLabels(now);
      if (mini && now - lastMini > 90) { lastMini = now; mini(); }
    }
    if (api.time === 'night' && composer) composer.render(); else renderer.render(scene, camera);
    labelR.render(scene, camera);
    frames++;
  }
  requestAnimationFrame(loop);

  Object.assign(api, {
    setLayer, setTime, setGround, setLabels, select, selectLandmark, clearSelection, reset, flyToBlock, search,
    zoomIn: () => zoomBy(1.7), zoomOut: () => zoomBy(1 / 1.7),
    get: id => { const p = byId.get(+id); return p ? publicProps(p) : null; },
    getLandmark: id => { const lm = lmById.get(+id); return lm ? publicLm(lm) : null; },
    rendered: () => built && frames > 3, requestRender: () => {}, resize
  });
  api.ready = build().catch(e => { console.error(e); status('error', 'The 3D model could not be built: ' + (e && e.message ? e.message : e) + '. Serve the site over http (python -m http.server), not file://.'); throw e; });
  return api;
}

// ---- helpers ---------------------------------------------------------------------------
function pipPlan(x, y, poly) {
  let ins = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins; }
  return ins;
}
function segDist(x, y, a, b) { const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)); return Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy); }

function farmTexture(axisRad) {
  const S = Math.min(4096, (navigator.hardwareConcurrency || 8) <= 4 ? 2048 : 4096), c = document.createElement('canvas'); c.width = c.height = S; const g = c.getContext('2d'), r = rng(42);
  g.fillStyle = '#8a9558'; g.fillRect(0, 0, S, S);
  g.save(); g.translate(S / 2, S / 2); g.rotate(-axisRad);
  const pal = ['#6e8d3d', '#7c9a45', '#86a24c', '#9aa45a', '#b2a568', '#a08a5a', '#6b8a3a', '#c0b273', '#5f7f35'];
  const k = S / 2048;
  for (let y = -S; y < S; y += (13 + r() * 6) * k) for (let x = -S; x < S;) { const w = (12 + r() * 20) * k; g.fillStyle = pal[(r() * pal.length) | 0]; g.fillRect(x, y, w - 1.2 * k, 13 * k); g.globalAlpha = .18; g.fillStyle = '#3f5a26'; for (let i = 0; i < 3; i++) g.fillRect(x + r() * w, y, .8 * k, 13 * k); g.globalAlpha = 1; x += w; }
  g.restore();
  for (let i = 0; i < 9000 * k * k; i++) { g.globalAlpha = .15; g.fillStyle = r() < .5 ? '#4d6a2c' : '#c9b98a'; g.fillRect(r() * S, r() * S, 2, 2); }
  g.globalAlpha = 1;
  for (let v = 0; v < 26; v++) { const x = r() * S, y = r() * S; if (Math.hypot(x - S / 2, y - S / 2) < 260) continue; const R = (10 + r() * 16) * k; for (let i = 0; i < 70 * k; i++) { const a = r() * 2 * PI, d = r() * R; g.fillStyle = r() < .7 ? '#a48c6c' : '#3f6a2e'; g.fillRect(x + Math.cos(a) * d, y + Math.sin(a) * d, (2 + r() * 3) * k, (2 + r() * 3) * k); } }
  g.strokeStyle = '#4f86a8'; g.lineWidth = 3; g.beginPath(); g.moveTo(0, S * .82); g.bezierCurveTo(S * .3, S * .76, S * .6, S * .9, S, S * .8); g.stroke();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

function injectCss() {
  if (document.getElementById('s3d-css')) return;
  const s = document.createElement('style'); s.id = 's3d-css';
  s.textContent = `
.s3d{position:relative;overflow:hidden}
.s3d-canvas{display:block;width:100%;height:100%;touch-action:none}
.s3d-labels{position:absolute;inset:0;pointer-events:none}
.s3d-lbl{pointer-events:auto;cursor:pointer;background:rgba(20,14,9,.82);color:#f3ead8;border-left:3px solid var(--k,#7bd08b);padding:3px 8px;border-radius:6px;font:600 11.5px "Plus Jakarta Sans","Segoe UI",sans-serif;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,.35);transform:translateY(-6px)}
.s3d-lbl:hover{background:#2a1f15}
.s3d-blk{color:#f3ead8;font:800 20px "Plus Jakarta Sans","Segoe UI",sans-serif;letter-spacing:.06em;text-shadow:0 2px 8px rgba(0,0,0,.85),0 0 2px #000}
.s3d-pn{color:#1d150d;background:rgba(243,234,216,.86);font:700 9.5px "Segoe UI",sans-serif;padding:0 3px;border-radius:3px}
.s3d-mini{position:absolute;right:14px;bottom:12px;border-radius:14px;overflow:hidden;border:1px solid rgba(227,207,165,.25);box-shadow:0 10px 24px rgba(0,0,0,.45);cursor:crosshair;z-index:3}
.s3d-mini canvas{display:block}
.s3d-compass{position:absolute;right:14px;top:14px;width:38px;height:38px;border-radius:50%;border:1px solid rgba(227,207,165,.3);background:rgba(20,14,9,.85);cursor:pointer;padding:6px;z-index:3}
.s3d-compass svg{width:100%;height:100%}
@media(max-width:760px){.s3d-mini{display:none}}`;
  document.head.appendChild(s);
}

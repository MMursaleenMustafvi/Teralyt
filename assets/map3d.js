/* Terralyt 3D map (CesiumJS).
 *
 *   const map = Map3D('cesium', { onPick, onStatus, layer: 'cls', selectId: 12 });
 *   map.setLayer('stat');  map.select(12);  map.reset();  map.search('B-12');
 *
 * Data comes from data/*.geojson (EPSG:4326):
 *   boundary.geojson  Polygon      society outline (sets the home view)
 *   roads.geojson     LineString   props: class (main|arterial|residential), width_m, name
 *   parks.geojson     Polygon      props: name, kind (park|amenity)
 *   plots.geojson     Polygon      props: id, plot_no, block, size, type, status, dev_class,
 *                                  built, storeys, height, height_source, source, confidence,
 *                                  lat, lon, accuracy
 * Plots are drawn as extruded polygons (height above ground), everything else is
 * clamped to the ground. Thousands of plots are batched into a few primitives so the
 * map stays smooth; colours are swapped per instance when the layer changes.
 *
 * Token: assets/config.js may set window.TERRALYT_CONFIG.cesiumToken. With a token the
 * map uses Cesium World Terrain + World Imagery; without one it falls back to
 * OpenStreetMap tiles on flat ground.
 */
function Map3D(elementId, opts) {
  opts = Object.assign({ dataUrl: 'data/', layer: 'cls', selectId: null, onPick: null, onHover: null, onStatus: null, skip: [] }, opts || {});
  const skip = name => opts.skip.indexOf(name) >= 0;   // debugging aid: skip a layer
  const C = window.Cesium;
  const el = typeof elementId === 'string' ? document.getElementById(elementId) : elementId;
  const status = (state, msg) => { if (opts.onStatus) opts.onStatus(state, msg); };

  const COLORS = {
    cls: { High: '#3fae5f', Medium: '#e0a93a', Low: '#c9573f' },
    stat: { Available: '#34c38f', Reserved: '#e0a93a', Sold: '#c9573f', Unknown: '#9aa5a0' },
    sat: { built: '#8c7b6a', vacant: '#b8ad92' }
  };
  const ROAD = { main: '#3b3733', arterial: '#4a443e', residential: '#5d564e' };
  const SELECT = '#ffd84d';

  const api = { viewer: null, plots: [], layer: opts.layer, selected: null, ready: null };
  if (!C) { status('error', 'CesiumJS failed to load. Check your internet connection and reload.'); api.ready = Promise.reject(new Error('no cesium')); return api; }

  const token = (window.TERRALYT_CONFIG && window.TERRALYT_CONFIG.cesiumToken) || '';
  if (token) C.Ion.defaultAccessToken = token;

  // ---- viewer ---------------------------------------------------------------
  let viewer, terrain = null;
  try {
    const base = token
      ? C.ImageryLayer.fromWorldImagery()
      : new C.ImageryLayer(new C.OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' }));
    if (token) terrain = C.Terrain.fromWorldTerrain();
    viewer = new C.Viewer(el, {
      baseLayer: base, terrain: terrain || undefined,
      animation: false, timeline: false, geocoder: false, homeButton: false, sceneModePicker: false,
      baseLayerPicker: false, navigationHelpButton: false, fullscreenButton: false, infoBox: false,
      selectionIndicator: false, shouldAnimate: false, requestRenderMode: true, maximumRenderTimeChange: Infinity,
      msaaSamples: 4, contextOptions: { webgl: { powerPreference: 'high-performance' } }
    });
  } catch (e) {
    status('error', 'Your browser could not start the 3D view (WebGL is required). ' + (e && e.message ? e.message : ''));
    api.ready = Promise.reject(e); return api;
  }
  api.viewer = viewer;
  const scene = viewer.scene;
  scene.globe.baseColor = C.Color.fromCssColorString('#2b2419');
  scene.globe.depthTestAgainstTerrain = !!terrain;
  scene.skyAtmosphere.show = true;
  scene.fog.enabled = true;
  scene.highDynamicRange = false;
  scene.screenSpaceCameraController.minimumZoomDistance = 40;
  scene.screenSpaceCameraController.maximumZoomDistance = 25000;
  const groundOK = C.GroundPrimitive.isSupported(scene);
  scene.renderError.addEventListener((s, err) => { console.error('Cesium render error', err); status('error', 'The 3D view stopped: ' + (err && err.message ? err.message : err)); });

  const css = s => C.Color.fromCssColorString(s);
  // lon/lat pairs -> Cartesian3, dropping consecutive points closer than ~0.4 m
  // (duplicate points make Cesium's corridor/polygon workers fail on normalize()).
  function toCart(ring, closeRing) {
    const out = [];
    let last = null;
    for (const c of ring) {
      if (last && Math.abs(c[0] - last[0]) < 4e-6 && Math.abs(c[1] - last[1]) < 4e-6) continue;
      out.push(C.Cartesian3.fromDegrees(c[0], c[1]));
      last = c;
    }
    if (closeRing && out.length > 1 && last && Math.abs(ring[0][0] - last[0]) < 4e-6 && Math.abs(ring[0][1] - last[1]) < 4e-6) out.pop();
    return out;
  }
  const fetchJson = name => fetch(opts.dataUrl + name + '.geojson', { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error(name + '.geojson: HTTP ' + r.status); return r.json(); });

  // ---- state ----------------------------------------------------------------
  let plotPrim = null, selPrim = null, labels = null, hoverId = null, boundarySphere = null, mainHeading = 0;
  const byId = new Map();     // id -> props (+ _center Cartesian3, _ring, _base)
  const byNo = new Map();     // 'B-12' -> id

  function plotColor(p, layer) {
    let hex;
    if (layer === 'stat') hex = COLORS.stat[p.status] || COLORS.stat.Unknown;
    else if (layer === 'sat') hex = p.built ? COLORS.sat.built : COLORS.sat.vacant;
    else hex = COLORS.cls[p.dev_class] || COLORS.cls.Low;
    const col = css(hex);
    // vacant plots are flat slabs: fade them so built ones read as "tall"
    return (!p.built && layer !== 'sat') ? C.Color.lerp(col, css('#d9cfb4'), 0.45, new C.Color()) : col;
  }

  // ---- build ----------------------------------------------------------------
  async function build() {
    status('loading', 'Loading map data…');
    const [boundary, roads, parks, plots] = await Promise.all([fetchJson('boundary'), fetchJson('roads'), fetchJson('parks'), fetchJson('plots')]);

    // society outline
    const bring = boundary.features[0].geometry.coordinates[0];
    const bpos = toCart(bring, true);
    boundarySphere = C.BoundingSphere.fromPoints(bpos);
    const bp = boundary.features[0].properties || {};
    api.society = { name: bp.name || 'Society', area_km2: bp.area_km2, source: bp.source };
    const outline = new C.GeometryInstance({ geometry: new C.GroundPolylineGeometry({ positions: bpos, width: 4, loop: true }), attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(css('#f3ead8')) } });
    scene.groundPrimitives.add(new C.GroundPolylinePrimitive({ geometryInstances: outline, appearance: new C.PolylineColorAppearance(), allowPicking: false }));

    // roads as ground corridors, widest first so main roads sit on top
    const order = { residential: 0, arterial: 1, main: 2 };
    const roadInst = [];
    let longest = null;
    for (const f of roads.features) {
      const p = f.properties, cls = p.class || 'residential';
      const pos = toCart(f.geometry.coordinates);
      if (pos.length < 2) continue;
      roadInst.push({ o: order[cls] || 0, inst: new C.GeometryInstance({ geometry: new C.CorridorGeometry({ positions: pos, width: p.width_m || 10, cornerType: C.CornerType.ROUNDED }), attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(css(ROAD[cls] || ROAD.residential)) } }) });
      if (cls === 'main') { const len = f.geometry.coordinates.length; if (!longest || len > longest.n) longest = { n: len, c: f.geometry.coordinates }; }
    }
    roadInst.sort((a, b) => a.o - b.o);
    if (!skip('roads')) addGround(roadInst.map(r => r.inst), false);
    // heading of the main boulevard, used for the home view
    if (longest) {
      const a = longest.c[0], b = longest.c[longest.c.length - 1];
      mainHeading = Math.atan2((b[0] - a[0]) * Math.cos(C.Math.toRadians(a[1])), b[1] - a[1]);
    }

    // parks and amenities
    labels = scene.primitives.add(new C.LabelCollection());
    const parkInst = [];
    for (const f of parks.features) {
      const p = f.properties, col = p.kind === 'park' ? '#4f9a5c' : '#8a7fb0';
      parkInst.push(new C.GeometryInstance({ geometry: new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(toCart(f.geometry.coordinates[0], true)) }), attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(css(col).withAlpha(0.85)) } }));
      const ctr = centroid(f.geometry.coordinates[0]);
      labels.add({ position: C.Cartesian3.fromDegrees(ctr[0], ctr[1], 2), text: p.name, font: '600 13px "Plus Jakarta Sans", Segoe UI, sans-serif', fillColor: C.Color.WHITE, outlineColor: css('#1a2a1e'), outlineWidth: 3, style: C.LabelStyle.FILL_AND_OUTLINE, heightReference: terrain ? C.HeightReference.CLAMP_TO_GROUND : C.HeightReference.NONE, verticalOrigin: C.VerticalOrigin.CENTER, distanceDisplayCondition: new C.DistanceDisplayCondition(0, 2600), disableDepthTestDistance: Number.POSITIVE_INFINITY });
    }
    if (!skip('parks')) addGround(parkInst, false);

    // plots
    api.plots = [];
    const blockSum = {};
    for (const f of plots.features) {
      const p = f.properties, ring = f.geometry.coordinates[0];
      p._ring = ring; p._base = 0;
      byId.set(p.id, p); byNo.set(String(p.plot_no).toUpperCase(), p.id);
      api.plots.push(p);
      const b = blockSum[p.block] || (blockSum[p.block] = { x: 0, y: 0, n: 0 });
      b.x += p.lon; b.y += p.lat; b.n++;
    }
    for (const k in blockSum) {
      const b = blockSum[k];
      labels.add({ position: C.Cartesian3.fromDegrees(b.x / b.n, b.y / b.n, 30), text: k.toUpperCase(), font: '800 22px "Plus Jakarta Sans", Segoe UI, sans-serif', fillColor: css('#f3ead8'), outlineColor: css('#14100c'), outlineWidth: 4, style: C.LabelStyle.FILL_AND_OUTLINE, distanceDisplayCondition: new C.DistanceDisplayCondition(900, 30000), disableDepthTestDistance: Number.POSITIVE_INFINITY, scaleByDistance: new C.NearFarScalar(1500, 1.1, 12000, 0.6) });
    }

    // ground height under each plot (only when real terrain is on)
    if (terrain) {
      status('loading', 'Sampling terrain heights…');
      try {
        const provider = await terrainProvider(terrain);
        if (provider) {
          const cartos = api.plots.map(p => C.Cartographic.fromDegrees(p.lon, p.lat));
          for (let i = 0; i < cartos.length; i += 800) await C.sampleTerrainMostDetailed(provider, cartos.slice(i, i + 800));
          api.plots.forEach((p, i) => { p._base = isFinite(cartos[i].height) ? cartos[i].height : 0; });
        }
      } catch (e) { console.warn('terrain sampling failed, using ellipsoid heights', e); }
    }
    if (!skip('plots')) buildPlotPrimitive();
    scene.requestRender();
    status('ready', api.plots.length + ' plots');
    reset(0);
    if (opts.selectId != null) select(opts.selectId, false);
    return api;
  }

  function addGround(instances, picking) {
    if (!instances.length) return;
    if (groundOK) scene.groundPrimitives.add(new C.GroundPrimitive({ geometryInstances: instances, appearance: new C.PerInstanceColorAppearance({ flat: true }), allowPicking: !!picking, classificationType: C.ClassificationType.TERRAIN }));
    else scene.primitives.add(new C.Primitive({ geometryInstances: instances, appearance: new C.PerInstanceColorAppearance({ flat: true }), allowPicking: !!picking }));
  }

  function buildPlotPrimitive() {
    if (plotPrim) { scene.primitives.remove(plotPrim); plotPrim = null; }
    const inst = [];
    for (const p of api.plots) {
      const h = Math.max(0.3, +p.height || 0.4);
      inst.push(new C.GeometryInstance({
        id: { plot: p.id },
        geometry: new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(toCart(p._ring, true)), height: p._base, extrudedHeight: p._base + h, vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT }),
        attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(plotColor(p, api.layer)) }
      }));
    }
    plotPrim = scene.primitives.add(new C.Primitive({ geometryInstances: inst, appearance: new C.PerInstanceColorAppearance({ translucent: false, closed: true }), allowPicking: true, releaseGeometryInstances: true }));
  }

  function terrainProvider(t) {
    return new Promise(res => {
      if (t.ready) return res(t.provider);
      t.readyEvent.addEventListener(p => res(p));
      t.errorEvent.addEventListener(() => res(null));
    });
  }

  function centroid(ring) {
    let x = 0, y = 0, n = ring.length - 1;
    for (let i = 0; i < n; i++) { x += ring[i][0]; y += ring[i][1]; }
    return [x / n, y / n];
  }

  // ---- layers -----------------------------------------------------------------
  function setLayer(layer) {
    if (!COLORS[layer] || layer === api.layer) return;
    api.layer = layer;
    if (!plotPrim) return;
    if (!plotPrim.ready) { plotPrim.readyPromise ? plotPrim.readyPromise.then(() => recolor()) : setTimeout(recolor, 300); return; }
    recolor();
  }
  function recolor() {
    if (!plotPrim || !plotPrim.ready) { setTimeout(recolor, 200); return; }
    for (const p of api.plots) {
      const a = plotPrim.getGeometryInstanceAttributes({ plot: p.id });
      if (a) a.color = C.ColorGeometryInstanceAttribute.toValue(plotColor(p, api.layer));
    }
    scene.requestRender();
  }

  // ---- selection ----------------------------------------------------------------
  function select(id, fly) {
    const p = byId.get(+id);
    if (!p) return null;
    api.selected = p.id;
    if (selPrim) { scene.primitives.remove(selPrim); selPrim = null; }
    const h = Math.max(0.3, +p.height || 0.4) + 0.15;
    selPrim = scene.primitives.add(new C.Primitive({
      geometryInstances: [
        new C.GeometryInstance({ id: { plot: p.id }, geometry: new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(toCart(p._ring, true)), height: p._base - 0.05, extrudedHeight: p._base + h, vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT }), attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(css(SELECT)) } })
      ],
      appearance: new C.PerInstanceColorAppearance({ translucent: false, closed: true }), asynchronous: false
    }));
    if (fly !== false) {
      const c = C.Cartesian3.fromDegrees(p.lon, p.lat, p._base);
      viewer.camera.flyToBoundingSphere(new C.BoundingSphere(c, 60), { duration: 1.4, offset: new C.HeadingPitchRange(viewer.camera.heading, C.Math.toRadians(-42), 230) });
    }
    scene.requestRender();
    if (opts.onPick) opts.onPick(publicProps(p));
    return publicProps(p);
  }
  function clearSelection() {
    api.selected = null;
    if (selPrim) { scene.primitives.remove(selPrim); selPrim = null; scene.requestRender(); }
  }
  function publicProps(p) { const o = {}; for (const k in p) if (k[0] !== '_') o[k] = p[k]; return o; }

  // ---- camera -------------------------------------------------------------------
  function reset(duration) {
    if (!boundarySphere) return;
    // look along the main boulevard from the south-west, tilted so the blocks read as 3D
    viewer.camera.flyToBoundingSphere(boundarySphere, { duration: duration == null ? 1.6 : duration, offset: new C.HeadingPitchRange(mainHeading - C.Math.toRadians(90) * 0 + C.Math.toRadians(0), C.Math.toRadians(-48), boundarySphere.radius * 2.35) });
  }
  function zoomBy(f) {
    const h = viewer.camera.positionCartographic.height;
    if (f > 1) viewer.camera.zoomIn(h * (1 - 1 / f)); else viewer.camera.zoomOut(h * (1 / f - 1));
    scene.requestRender();
  }
  function flyToBlock(letter) {
    const ps = api.plots.filter(p => p.block.endsWith(' ' + letter.toUpperCase()));
    if (!ps.length) return false;
    const sphere = C.BoundingSphere.fromPoints(ps.map(p => C.Cartesian3.fromDegrees(p.lon, p.lat, p._base)));
    viewer.camera.flyToBoundingSphere(sphere, { duration: 1.4, offset: new C.HeadingPitchRange(viewer.camera.heading, C.Math.toRadians(-50), sphere.radius * 2.4) });
    return true;
  }

  // ---- search -----------------------------------------------------------------
  function search(q) {
    q = String(q || '').trim();
    if (!q) return [];
    const m = q.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (m) {
      const lat = +m[1], lon = +m[2];
      if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return [];
      let best = null, bd = Infinity;
      for (const p of api.plots) { const d = Math.hypot((p.lat - lat) * 111320, (p.lon - lon) * 94900); if (d < bd) { bd = d; best = p; } }
      return best && bd < 1500 ? [{ id: best.id, label: best.plot_no, sub: best.block + ' · ' + Math.round(bd) + ' m from the point' }] : [];
    }
    const n = q.toUpperCase().replace(/\s+/g, '');
    const exact = byNo.get(n) || byNo.get(n.replace(/^([A-F])(\d+)$/, '$1-$2'));
    const out = [];
    if (exact != null) { const p = byId.get(exact); out.push({ id: p.id, label: p.plot_no, sub: p.block + ' · ' + p.size + ' · ' + p.status }); }
    const bm = q.match(/^(?:block\s*)?([a-fA-F])$/);
    if (bm) out.push({ block: bm[1].toUpperCase(), label: 'Block ' + bm[1].toUpperCase(), sub: api.plots.filter(p => p.block.endsWith(' ' + bm[1].toUpperCase())).length + ' plots' });
    if (out.length) return out;
    const pref = n.replace(/^([A-F])(\d)/, '$1-$2');
    for (const p of api.plots) { if (String(p.plot_no).toUpperCase().startsWith(pref)) { out.push({ id: p.id, label: p.plot_no, sub: p.block + ' · ' + p.size + ' · ' + p.status }); if (out.length >= 8) break; } }
    return out;
  }

  // ---- picking ------------------------------------------------------------------
  const handler = new C.ScreenSpaceEventHandler(scene.canvas);
  handler.setInputAction(e => {
    const picked = scene.pick(e.position);
    const id = picked && picked.id && picked.id.plot;
    if (id != null) select(id, false); else { clearSelection(); if (opts.onPick) opts.onPick(null); }
  }, C.ScreenSpaceEventType.LEFT_CLICK);
  let hoverT = 0;
  handler.setInputAction(e => {
    const now = performance.now(); if (now - hoverT < 40) return; hoverT = now;
    const picked = scene.pick(e.endPosition);
    const id = picked && picked.id && picked.id.plot;
    if (id === hoverId) return;
    hoverId = id == null ? null : id;
    scene.canvas.style.cursor = hoverId ? 'pointer' : '';
    if (opts.onHover) opts.onHover(hoverId ? publicProps(byId.get(hoverId)) : null, e.endPosition);
  }, C.ScreenSpaceEventType.MOUSE_MOVE);

  Object.assign(api, {
    setLayer, select, clearSelection, reset, zoomIn: () => zoomBy(1.6), zoomOut: () => zoomBy(1 / 1.6), flyToBlock, search,
    get: id => { const p = byId.get(+id); return p ? publicProps(p) : null },
    hasTerrain: !!terrain, hasToken: !!token,
    // true once plots are built and the globe has no pending tiles (used by tests)
    rendered: () => !!((skip('plots') || (plotPrim && plotPrim.ready)) && scene.globe.tilesLoaded),
    requestRender: () => scene.requestRender()
  });
  api.ready = build().catch(e => { console.error(e); status('error', 'Map data could not be loaded. ' + (e && e.message ? e.message : '') + ' Serve the site over http (python -m http.server), not file://.'); throw e; });
  return api;
}

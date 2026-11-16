// Map data for the React pages. The 3D map reads the full GeoJSON itself (src/map/society3d.js); the other pages use
// the small files from tools/make_index.py: data/plots_index.json (every plot, no outline) and data/outlines/<block>.json.
export const BASE = import.meta.env.BASE_URL;
export const DATA_URL = BASE + 'data/';
export const BLOCKS = ['A', 'B', 'C', 'D', 'E', 'F', 'X'];
export const SIZES = ['5 Marla', '10 Marla', '20 Marla', 'Commercial'];
export const STATUSES = ['Available', 'Reserved', 'Sold', 'Unknown'];
export const SOCIETY = { name: 'FDA City', city: 'Faisalabad', centre: [31.525, 73.088] };

const cache = {};
function getJSON(name) {
  if (!cache[name]) {
    cache[name] = fetch(DATA_URL + name, { cache: 'no-cache' })
      .then(r => { if (!r.ok) throw new Error(name + ': HTTP ' + r.status); return r.json(); })
      .catch(e => { delete cache[name]; throw e; });
  }
  return cache[name];
}

export const norm = s => String(s == null ? '' : s).toUpperCase().replace(/[\s_]+/g, '');

let plotsP = null;
/** every plot: { id, no, num, sub, blk, size, type, status, dev, built, storeys, height, marla, area, lat, lon, bshare, src, conf, layout, numsrc } */
export function loadPlots() {
  if (!plotsP) {
    plotsP = getJSON('plots_index.json').then(idx => {
      const F = idx.fields, D = idx.dict || {};
      const list = idx.rows.map(r => {
        const o = {};
        F.forEach((k, i) => { let v = r[i]; if (D[k] && v != null) v = D[k][v]; o[k] = v; });
        o.built = !!o.built;
        return o;
      });
      const byId = new Map(list.map(p => [p.id, p]));
      const byNo = new Map(); for (const p of list) if (!byNo.has(norm(p.no))) byNo.set(norm(p.no), p);
      return { list, byId, byNo };
    }).catch(e => { plotsP = null; throw e; });
  }
  return plotsP;
}

export const loadOutlines = blk => getJSON('outlines/' + blk + '.json');
export const loadRoads = () => getJSON('roads.geojson');
export const loadBoundary = () => getJSON('boundary.geojson');

const KIND_LABEL = { highschool: 'High school', postoffice: 'Post office, police and telephone exchange', community: 'Community centre', hotel: 'Hotel site', firestation: 'Fire brigade', office: 'Office', shops: 'Shops', dispensary: 'Dispensary', homes: 'FDA City Homes', metro: 'Metro store', sewerage: 'Sewerage works', nala: 'Storm drain (nalla)', mosque: 'Mosque', school: 'School', playground: 'Playground', commercial: 'Commercial', park: 'Park', hospital: 'Hospital', sports: 'Sports', civic: 'Public building', university: 'University', stadium: 'Stadium', cinema: 'Cinema', multipurpose: 'Multi-purpose', site: 'Reserved site', grid: 'Grid station', graveyard: 'Graveyard', cng: 'CNG station', shrine: 'Shrine', gate: 'Main gate', roundabout: 'Roundabout' };
export const kindLabel = k => KIND_LABEL[k] || 'Facility';

function centre(g) {
  if (!g) return null;
  if (g.type === 'Point') return g.coordinates;
  const ring = g.type === 'Polygon' ? g.coordinates[0] : g.type === 'MultiPolygon' ? g.coordinates[0][0] : g.type === 'LineString' ? g.coordinates : null;
  if (!ring || !ring.length) return null;
  let x = 0, y = 0; for (const c of ring) { x += c[0]; y += c[1]; }
  return [x / ring.length, y / ring.length];
}
let lmP = null;
/** facilities on the official map: { id, name, kind, label, block, kanal, proposed, lon, lat } (outside-society ones dropped) */
export function loadLandmarks() {
  if (!lmP) {
    lmP = getJSON('landmarks.geojson').then(d => d.features.filter(f => !f.properties.outside).map(f => {
      const p = f.properties, c = centre(f.geometry) || [0, 0];
      return { id: p.id, name: p.name, kind: p.kind, label: kindLabel(p.kind), block: p.block, kanal: p.area_kanal, proposed: !!p.proposed, lon: c[0], lat: c[1] };
    }).filter(l => l.lon)).catch(e => { lmP = null; throw e; });
  }
  return lmP;
}

// metres between two lat/lon points (equirectangular, fine within a society)
export function distM(lat1, lon1, lat2, lon2) {
  const k = 111320, dx = (lon2 - lon1) * k * Math.cos((lat1 + lat2) / 2 * Math.PI / 180), dy = (lat2 - lat1) * k;
  return Math.hypot(dx, dy);
}

const COORD = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;
/**
 * Search plots, facilities and blocks. Plot numbers match in any spelling (B-12, b12, B 12); a bare number matches the
 * number printed on the plan in every block; "lat, lon" finds the nearest plots.
 * Returns { kind: 'coords'|'text'|'invalid'|'empty', items: [{ type: 'plot'|'landmark'|'block'|'society', ... }] }
 */
export function search(db, lms, q, limit = 60) {
  q = String(q || '').trim();
  if (!q) return { kind: 'empty', items: [] };
  const m = q.match(COORD);
  if (m) {
    const lat = +m[1], lon = +m[2];
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return { kind: 'invalid', items: [] };
    const near = db.list.map(p => ({ p, d: distM(lat, lon, p.lat, p.lon) })).filter(x => x.d < 400).sort((a, b) => a.d - b.d).slice(0, limit);
    return { kind: 'coords', lat, lon, items: near.map(x => ({ type: 'plot', plot: x.p, dist: x.d })) };
  }
  if (/^\d+[.,]\d*\s*,/.test(q) || /^-?\d+\.\d+$/.test(q)) return { kind: 'invalid', items: [] };
  const Q = norm(q), lower = q.toLowerCase(), items = [];
  if ('FDACITY'.startsWith(Q) || Q.startsWith('FDA') || lower.includes('society')) items.push({ type: 'society' });
  const bm = Q.match(/^(?:BLOCK)?([A-FX])$/);
  if (bm) items.push({ type: 'block', blk: bm[1] });
  const exact = db.byNo.get(Q);
  const seen = new Set();
  const addPlot = p => { if (!seen.has(p.id) && items.length < limit) { seen.add(p.id); items.push({ type: 'plot', plot: p }); } };
  if (exact) addPlot(exact);
  const pm = Q.match(/^(?:BLOCK)?([A-FX])-?(\d+)(.*)$/);
  if (pm) {
    const key = pm[1] + '-' + pm[2], rest = pm[3];
    for (const p of db.list) {
      if (p.blk !== pm[1]) continue;
      const n = norm(p.no);                    // A-14 must not match A-140
      if (n.startsWith(key) && !/\d/.test(n[key.length] || '') && n.slice(key.length).startsWith(rest)) addPlot(p);
    }
    if (items.length < 3) for (const p of db.list) if (p.blk === pm[1] && String(p.num) === pm[2]) addPlot(p);
  } else if (/^\d+$/.test(Q)) {
    for (const p of db.list) if (String(p.num) === Q) addPlot(p);
  }
  for (const l of lms || []) if (items.length < limit && (l.name.toLowerCase().includes(lower) || l.label.toLowerCase().includes(lower))) items.push({ type: 'landmark', lm: l });
  if (!bm && !pm && !/^\d+$/.test(Q) && items.length < limit) {
    for (const p of db.list) { if (items.length >= limit) break; if (norm(p.no).includes(Q)) addPlot(p); }
  }
  return { kind: 'text', items };
}

/** counts per block, size, status, development class and built for a list of plots */
export function summarise(list, statusOf = p => p.status) {
  const s = { total: list.length, built: 0, size: {}, status: {}, dev: {}, block: {} };
  for (const p of list) {
    if (p.built) s.built++;
    s.size[p.size] = (s.size[p.size] || 0) + 1;
    const st = statusOf(p); s.status[st] = (s.status[st] || 0) + 1;
    s.dev[p.dev] = (s.dev[p.dev] || 0) + 1;
    s.block[p.blk] = (s.block[p.blk] || 0) + 1;
  }
  return s;
}

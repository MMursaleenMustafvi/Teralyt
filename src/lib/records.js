// Plot status updates, plot records, saved and viewed plots, dataset reviews. Kept in the browser (store.js) until
// the backend exists; every change goes to the audit trail with who and when.
import { get, set, update, useStored, now, audit } from './store.js';

// ---- plot status (Society Head) ----
export const useStatusOverrides = () => useStored('status', {});
export function statusOf(p, ov = get('status', {})) { return (ov[p.id] && ov[p.id].status) || p.status; }
/** where the status shown comes from: a Society Head update, or the sample value in the data */
export function statusSource(p, ov = get('status', {})) {
  const o = ov[p.id];
  if (o) return { source: `Society Head record (${o.by}, ${new Date(o.at).toLocaleDateString()})`, confidence: 'High', updated: true, note: o.note };
  return { source: p.src || 'Sample value (no society record yet)', confidence: p.conf || 'Low', updated: false };
}
export function changeStatus(user, p, to, note) {
  const from = statusOf(p);
  if (!['Available', 'Reserved', 'Sold'].includes(to)) return { ok: false, msg: 'Choose Available, Reserved or Sold.' };
  if (from === to) return { ok: false, msg: `Plot ${p.no} is already ${to}.` };
  if (from === 'Sold' && to === 'Available') return { ok: false, msg: 'Rejected: a sold plot cannot be marked Available without an administrator\'s approval.' };
  const at = now();
  update('status', {}, o => ({ ...o, [p.id]: { status: to, by: user.name, at, note: note || '' } }));
  update('statusLog', [], l => [{ id: p.id, no: p.no, from, to, by: user.name, at, note: note || '' }, ...l].slice(0, 300));
  audit(user.name, 'Changed plot status', `${p.no}: ${from} → ${to}${note ? ' (' + note + ')' : ''}`);
  return { ok: true, msg: `Saved. Plot ${p.no} is now ${to}. Logged ${new Date(at).toLocaleString()} by ${user.name}.`, from };
}
export const useStatusLog = () => useStored('statusLog', []);

// ---- plot records (Society Head): added and removed records ----
export const useRecords = () => useStored('records', { added: [], removed: {} });
export function addRecord(user, rec) {
  update('records', { added: [], removed: {} }, r => ({ ...r, added: [{ ...rec, by: user.name, at: now() }, ...r.added] }));
  audit(user.name, 'Added plot record', `${rec.no} (Block ${rec.blk}, ${rec.size})`);
}
export function removeRecord(user, p, reason) {
  update('records', { added: [], removed: {} }, r => ({ ...r, removed: { ...r.removed, [p.id]: { by: user.name, at: now(), reason } } }));
  audit(user.name, 'Removed plot record', `${p.no}${reason ? ' (' + reason + ')' : ''}`);
}
export function restoreRecord(user, p) {
  update('records', { added: [], removed: {} }, r => { const rm = { ...r.removed }; delete rm[p.id]; return { ...r, removed: rm }; });
  audit(user.name, 'Restored plot record', p.no);
}

// ---- saved, viewed, searched (End User) ----
const who = s => (s && s.email) || 'guest';
export const useSaved = session => useStored('saved:' + who(session), []);
export function toggleSaved(session, id) {
  const k = 'saved:' + who(session), l = get(k, []);
  set(k, l.includes(id) ? l.filter(x => x !== id) : [id, ...l].slice(0, 100));
  return !l.includes(id);
}
export const useViewed = () => useStored('viewed', []);
export function markViewed(id) { update('viewed', [], l => [id, ...l.filter(x => x !== id)].slice(0, 12)); }
export const useRecent = () => useStored('recent', []);
export function addRecent(q) { q = String(q || '').trim(); if (q) update('recent', [], l => [q, ...l.filter(x => x !== q)].slice(0, 8)); }

// ---- datasets the platform uses, with their review state (System Administrator) ----
export const DATASETS = [
  { id: 'plan', name: 'Plot outlines and numbers', source: 'FDA City plan as published on emap.pk (a third-party redraw), registered to the real streets (0.65 m median error)', date: '2026-11', confidence: 'Medium', state: 'Pending', note: 'Ask the FDA for the original plan (CAD or PDF) to verify.' },
  { id: 'blockmaps', name: 'Parks, mosques, schools and other sites', source: 'Official FDA City block maps (fdacity.pk), georeferenced at the roundabouts', date: '2026-11', confidence: 'Medium', state: 'Verified' },
  { id: 'osm', name: 'Street centre lines', source: 'OpenStreetMap contributors (ODbL)', date: '2026-11', confidence: 'High', state: 'Verified' },
  { id: 'service', name: 'Service roads and road widths', source: 'Google Maps road map (which roads exist) and Google satellite imagery (position, width), zoom 19', date: '2026-11', confidence: 'High', state: 'Verified' },
  { id: 'buildings', name: 'Houses standing today (built / vacant)', source: 'Google Open Buildings 2023 and Microsoft ML Buildings, via Overture Maps', date: '2023', confidence: 'Medium', state: 'Verified', note: 'Houses built after 2023 are missing.' },
  { id: 'nala', name: 'Barani Nala (storm drain)', source: 'Traced on Esri World Imagery (2020)', date: '2026-11', confidence: 'Medium', state: 'Verified' },
  { id: 'status', name: 'Plot status (Available, Reserved, Sold)', source: '', date: '', confidence: 'Low', state: 'Flagged', note: 'Sample values until the society\'s records arrive; Society Head updates are kept separately.' },
  { id: 'heights', name: 'Storeys and building heights', source: 'Assumed (3.5 m per storey)', date: '', confidence: 'Low', state: 'Flagged', note: 'Label as assumed until measured.' },
  { id: 'sentinel', name: 'Satellite history for the development model', source: 'Sentinel-2 (Copernicus) yearly composites 2016 to 2025', date: '', confidence: 'High', state: 'Pending', note: 'Part of the AI model work (not loaded yet).' },
  { id: 'textures', name: '3D map textures', source: 'ambientCG and Poly Haven photographs (CC0)', date: '2026-11', confidence: 'High', state: 'Verified' }
];
export const useDatasetStates = () => useStored('datasets', {});
export function reviewDataset(user, ds, state, note) {
  update('datasets', {}, d => ({ ...d, [ds.id]: { state, by: user.name, at: now(), note: note || '' } }));
  audit(user.name, state === 'Verified' ? 'Verified dataset' : state === 'Flagged' ? 'Flagged dataset' : 'Set dataset to pending', ds.name + (note ? ' (' + note + ')' : ''));
}

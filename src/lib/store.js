// Small persistent store in the browser (localStorage), shared by all pages and kept in step across tabs.
// Until the backend exists, everything a user changes (status updates, records, saved plots, accounts, data reviews)
// is kept here and labelled as such on the pages.
import { useSyncExternalStore } from 'react';

const PREFIX = 'terralyt:';
const mem = new Map();
const subs = new Set();
const emit = () => subs.forEach(f => f());

function read(key, fallback) {
  try { const v = localStorage.getItem(PREFIX + key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
}
export function get(key, fallback = null) {
  if (!mem.has(key)) mem.set(key, read(key, fallback));
  const v = mem.get(key);
  return v == null ? fallback : v;
}
export function set(key, value) {
  mem.set(key, value);
  try { localStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch (e) { /* storage full or blocked: keep in memory */ }
  emit();
}
export function update(key, fallback, fn) { set(key, fn(get(key, fallback))); }
export function remove(key) { mem.delete(key); try { localStorage.removeItem(PREFIX + key); } catch (e) { /* ignore */ } emit(); }

function subscribe(f) { subs.add(f); return () => subs.delete(f); }
if (typeof window !== 'undefined') {
  window.addEventListener('storage', e => { if (e.key && e.key.startsWith(PREFIX)) { mem.delete(e.key.slice(PREFIX.length)); emit(); } });
}
/** React hook: the stored value, re-rendering when it changes (in this tab or another) */
export function useStored(key, fallback = null) {
  const v = useSyncExternalStore(subscribe, () => get(key, null));
  return v == null ? fallback : v;
}

export const now = () => new Date().toISOString();
export const fmtTime = iso => { try { return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return iso; } };
export function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) return Math.round(s / 3600) + ' h ago';
  return Math.round(s / 86400) + ' days ago';
}

// ---- audit trail: every change anyone makes ----
export function audit(by, action, detail) {
  update('audit', [], l => [{ at: now(), by, action, detail }, ...l].slice(0, 500));
}

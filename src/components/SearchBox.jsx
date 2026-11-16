import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadPlots, loadLandmarks, search } from '../lib/data.js';
import { addRecent, useRecent, statusOf } from '../lib/records.js';

/** where a search result leads */
export function resultLink(it) {
  if (it.type === 'plot') return '/plot/' + it.plot.id;
  if (it.type === 'landmark') return '/map?lm=' + it.lm.id;
  if (it.type === 'block') return '/search?blk=' + it.blk;
  return '/map';
}
export function resultText(it) {
  if (it.type === 'plot') { const p = it.plot; return [p.no, `Block ${p.blk} · ${p.size} · ${p.built ? 'built' : 'vacant'} · ${statusOf(p)}${it.dist != null ? ' · ' + Math.round(it.dist) + ' m away' : ''}`]; }
  if (it.type === 'landmark') return [it.lm.name, `${it.lm.label}${it.lm.block ? ' · ' + it.lm.block : ''}${it.lm.proposed ? ' · proposed' : ''}`];
  if (it.type === 'block') return ['Block ' + it.blk, 'All plots in the block'];
  return ['FDA City', 'Housing society, Faisalabad · open the 3D map'];
}

/** search input with live suggestions (plots, facilities, blocks, coordinates) and recent searches */
export default function SearchBox({ placeholder = 'Search plot (B-12), block, mosque, school or lat, lon…', initial = '', onSearch, big, id }) {
  const nav = useNavigate(), wrap = useRef(null);
  const [q, setQ] = useState(initial), [open, setOpen] = useState(false), [hi, setHi] = useState(-1);
  const [db, setDb] = useState(null), [lms, setLms] = useState(null), [err, setErr] = useState(null);
  const recent = useRecent();
  const load = () => { if (!db && !err) Promise.all([loadPlots(), loadLandmarks()]).then(([d, l]) => { setDb(d); setLms(l); }, setErr); };
  useEffect(() => { const f = e => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); }; document.addEventListener('mousedown', f); return () => document.removeEventListener('mousedown', f); }, []);
  useEffect(() => { setQ(initial); }, [initial]);

  let head = '', items = [];
  if (!q.trim()) {
    head = recent.length ? 'Recent searches' : 'Try';
    items = (recent.length ? recent : ['FDA City', 'A-14', 'Jamia Mosque', 'Block X', '31.5150, 73.0720']).slice(0, 5).map(t => ({ type: 'query', q: t }));
  } else if (db) {
    const r = search(db, lms, q, 8);
    head = r.kind === 'invalid' ? 'Coordinates need latitude, longitude (for example 31.5150, 73.0720)' : r.items.length ? (r.kind === 'coords' ? 'Nearest plots' : 'Results') : 'No result found. Check the spelling or try a nearby plot number.';
    items = r.items;
  } else head = err ? 'Search is not available (data did not load).' : 'Loading plots…';

  const go = it => {
    setOpen(false);
    if (it.type === 'query') { setQ(it.q); setOpen(true); load(); return; }
    addRecent(q.trim() || resultText(it)[0]);
    nav(resultLink(it));
  };
  const submit = () => {
    const t = q.trim(); if (!t) return;
    if (hi >= 0 && items[hi]) return go(items[hi]);
    addRecent(t); setOpen(false);
    if (onSearch) onSearch(t); else nav('/search?q=' + encodeURIComponent(t));
  };
  const key = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setHi(h => Math.min(items.length - 1, h + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => Math.max(-1, h - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); submit(); }
    else if (e.key === 'Escape') setOpen(false);
  };
  return (
    <div className={'sw' + (big ? ' big' : '')} ref={wrap}>
      <input id={id} value={q} placeholder={placeholder} autoComplete="off" aria-label="Search"
        onFocus={() => { setOpen(true); load(); }} onChange={e => { setQ(e.target.value); setHi(-1); setOpen(true); load(); }} onKeyDown={key} />
      <div className={'dd' + (open ? ' on' : '')}>
        {head && <div className="h">{head}</div>}
        {items.map((it, i) => {
          const [t, s] = it.type === 'query' ? [it.q, recent.length ? 'Recent' : 'Example'] : resultText(it);
          return <a key={i} href="#" className={i === hi ? 'hi' : ''} onMouseDown={e => { e.preventDefault(); go(it); }}><span>{t}</span><small>{s}</small></a>;
        })}
      </div>
    </div>
  );
}

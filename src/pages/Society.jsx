import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import { Badge, Spinner, ErrorBox, useAsync, useTitle, Pager, fmtNum } from '../components/ui.jsx';
import { loadPlots, loadOutlines, search, BLOCKS, SIZES, STATUSES, norm } from '../lib/data.js';
import { useSession } from '../lib/auth.js';
import { statusOf, statusSource, changeStatus, useStatusOverrides, useStatusLog, useRecords, addRecord, removeRecord, restoreRecord } from '../lib/records.js';
import { ago, fmtTime } from '../lib/store.js';

const KEEP_NOTE = 'Changes are kept in this browser until the backend is connected; each one is logged with your name and the time.';

// ---- overview ----
export function ShDashboard() {
  useTitle('Society Head');
  const [db, err] = useAsync(loadPlots), ov = useStatusOverrides(), log = useStatusLog(), rec = useRecords();
  const sum = useMemo(() => {
    if (!db) return null;
    const by = {}; for (const b of BLOCKS) by[b] = { n: 0, built: 0, Available: 0, Reserved: 0, Sold: 0, Unknown: 0 };
    const tot = { n: 0, built: 0, Available: 0, Reserved: 0, Sold: 0, Unknown: 0 };
    for (const p of db.list) { const st = statusOf(p, ov); for (const t of [by[p.blk], tot]) { t.n++; t[st]++; if (p.built) t.built++; } }
    return { by, tot };
  }, [db, ov]);
  return (
    <AppShell>
      <h1>FDA City overview</h1>
      <p className="mut">Plot records and status for the whole society. {Object.keys(ov).length ? `${Object.keys(ov).length} plot status${Object.keys(ov).length > 1 ? 'es' : ''} updated by the society so far; the rest are sample values.` : 'All statuses are sample values until you update them from the society\'s records.'}</p>
      {err && <ErrorBox error={err} />}
      {!sum && !err && <Spinner />}
      {sum && <>
        <div className="grid g4">
          <div className="card"><div className="stat">{fmtNum(sum.tot.n)}</div><span className="mut">Total plots</span></div>
          <div className="card"><div className="stat st-a">{fmtNum(sum.tot.Available)}</div><span className="mut">Available</span></div>
          <div className="card"><div className="stat st-r">{fmtNum(sum.tot.Reserved)}</div><span className="mut">Reserved</span></div>
          <div className="card"><div className="stat st-s">{fmtNum(sum.tot.Sold)}</div><span className="mut">Sold</span></div>
        </div><br />
        <div className="grid g2">
          <div className="card"><h3>Recent status updates</h3>
            {log.length ? <table className="tbl"><thead><tr><th>Plot</th><th>Change</th><th>By</th><th>When</th></tr></thead><tbody>{log.slice(0, 8).map((u, i) => <tr key={i}><td><Link to={'/plot/' + u.id}>{u.no}</Link></td><td><Badge t={u.from} /> → <Badge t={u.to} /></td><td>{u.by}</td><td title={fmtTime(u.at)}>{ago(u.at)}</td></tr>)}</tbody></table>
              : <p className="mut">No status updated yet.</p>}
            <p><Link className="btn" to="/society/status">Update plot status</Link> <Link className="btn o" to="/society/records">Manage records</Link></p></div>
          <div className="card"><h3>By block</h3><div className="tblw"><table className="tbl"><thead><tr><th>Block</th><th>Plots</th><th>Built</th><th>Available</th><th>Reserved</th><th>Sold</th><th>Unknown</th></tr></thead>
            <tbody>{BLOCKS.map(b => { const x = sum.by[b]; return <tr key={b}><td><Link to={'/search?blk=' + b}>Block {b}</Link></td><td>{fmtNum(x.n)}</td><td>{fmtNum(x.built)}</td><td>{fmtNum(x.Available)}</td><td>{fmtNum(x.Reserved)}</td><td>{fmtNum(x.Sold)}</td><td>{fmtNum(x.Unknown)}</td></tr>; })}</tbody></table></div>
            <p className="mut small">{rec.added.length} record{rec.added.length === 1 ? '' : 's'} added · {Object.keys(rec.removed).length} removed by the society.</p></div>
        </div>
      </>}
    </AppShell>
  );
}

// ---- plot picker: type a plot number, choose from the matches ----
function PlotPicker({ db, value, onPick }) {
  const [q, setQ] = useState(value ? value.no : ''), [open, setOpen] = useState(false);
  const items = q.trim() ? search(db, [], q, 8).items.filter(i => i.type === 'plot') : [];
  return (
    <div className="sw">
      <input value={q} placeholder="Plot number, for example A-14 or B 205" onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={e => { setQ(e.target.value); setOpen(true); const exact = db.byNo.get(norm(e.target.value)); onPick(exact || null); }} />
      <div className={'dd' + (open && q.trim() ? ' on' : '')}>
        {items.length ? items.map(({ plot: p }) => <a key={p.id} href="#" onMouseDown={e => { e.preventDefault(); setQ(p.no); setOpen(false); onPick(p); }}><span>{p.no}</span><small>Block {p.blk} · {p.size} · {statusOf(p)}</small></a>) : <div className="h">No plot with this number.</div>}
      </div>
    </div>
  );
}

// ---- update a plot's status ----
export function ShStatus() {
  useTitle('Update plot status');
  const [q] = useSearchParams(), s = useSession(), ov = useStatusOverrides(), log = useStatusLog();
  const [db, err] = useAsync(loadPlots);
  const [plot, setPlot] = useState(null), [to, setTo] = useState('Sold'), [note, setNote] = useState(''), [msg, setMsg] = useState(null);
  const pre = db && !plot && q.get('id') ? db.byId.get(+q.get('id')) : null;
  const p = plot || pre;
  const save = e => {
    e.preventDefault();
    if (!p) return setMsg({ ok: false, msg: 'Choose a plot first.' });
    const r = changeStatus(s, p, to, note.trim());
    setMsg(r); if (r.ok) setNote('');
  };
  return (
    <AppShell>
      <h1>Update plot status</h1>
      <p className="mut">Record a plot as Available, Reserved or Sold from the society's own records. {KEEP_NOTE}</p>
      {err && <ErrorBox error={err} />}
      {!db && !err && <Spinner />}
      {db && <div className="grid g2">
        <form className="card" onSubmit={save}>
          <label>Plot</label><PlotPicker key={pre ? pre.id : 'none'} db={db} value={pre} onPick={x => { setPlot(x); setMsg(null); }} />
          {p && (() => { const so = statusSource(p, ov); return <div className="curst"><b>{p.no}</b> · Block {p.blk} · {p.size} · now <Badge t={statusOf(p, ov)} /><br /><small className="mut">Source: {so.source} · Confidence: {so.confidence}</small></div>; })()}
          <label htmlFor="ns">New status</label><select id="ns" value={to} onChange={e => setTo(e.target.value)}>{['Available', 'Reserved', 'Sold'].map(x => <option key={x}>{x}</option>)}</select>
          <label htmlFor="nt">Reference or note (optional)</label><input id="nt" value={note} maxLength={140} placeholder="For example: allotment letter 2026/118, transfer on 12 Nov" onChange={e => setNote(e.target.value)} />
          {msg && <p className={msg.ok ? 'fok' : 'ferr'} role="status">{msg.msg}</p>}
          <button className="btn">Save status</button>
          <p className="mut small">Rule: a Sold plot cannot be set back to Available without an administrator's approval. The new status appears on the 3D map and the plot page at once.</p>
        </form>
        <div className="card"><h3>Your recent updates</h3>
          {log.filter(x => x.by === s.name).length ? <table className="tbl"><thead><tr><th>Plot</th><th>Change</th><th>Note</th><th>When</th></tr></thead><tbody>{log.filter(x => x.by === s.name).slice(0, 12).map((u, i) => <tr key={i}><td><Link to={'/plot/' + u.id}>{u.no}</Link></td><td><Badge t={u.from} /> → <Badge t={u.to} /></td><td>{u.note || '–'}</td><td title={fmtTime(u.at)}>{ago(u.at)}</td></tr>)}</tbody></table> : <p className="mut">None yet.</p>}
        </div>
      </div>}
    </AppShell>
  );
}

// ---- plot records: list, add with boundary check, remove ----
const PIP = (x, y, r) => { let ins = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const [xi, yi] = r[i], [xj, yj] = r[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) ins = !ins; } return ins; };
function checkBoundary(text) {
  if (!text.trim()) return { ok: true, ring: null };
  let g; try { g = JSON.parse(text); } catch (e) { return { ok: false, msg: 'Boundary is not valid GeoJSON (JSON could not be read).' }; }
  if (g.type === 'Feature') g = g.geometry;
  if (!g || g.type !== 'Polygon' || !Array.isArray(g.coordinates) || !Array.isArray(g.coordinates[0])) return { ok: false, msg: 'Boundary must be a GeoJSON Polygon.' };
  const ring = g.coordinates[0];
  if (ring.length < 4) return { ok: false, msg: 'A polygon needs at least 3 corners (4 positions, the last repeating the first).' };
  const [a, b] = [ring[0], ring[ring.length - 1]];
  if (a[0] !== b[0] || a[1] !== b[1]) return { ok: false, msg: 'The polygon must be closed: repeat the first position at the end.' };
  if (!ring.every(c => Array.isArray(c) && Math.abs(c[0] - 73.08) < .06 && Math.abs(c[1] - 31.52) < .06)) return { ok: false, msg: 'Positions must be longitude, latitude inside FDA City (about 73.08, 31.52).' };
  return { ok: true, ring: ring.slice(0, -1) };
}
export function ShRecords() {
  useTitle('Society & plot records');
  const s = useSession(), rec = useRecords(), ov = useStatusOverrides();
  const [db, err] = useAsync(loadPlots);
  const [blk, setBlk] = useState('A'), [qq, setQq] = useState(''), [page, setPage] = useState(0), [showRemoved, setShowRemoved] = useState(false);
  const [f, setF] = useState({ no: '', blk: 'A', size: '10 Marla', area: '', boundary: '' }), [msg, setMsg] = useState(null), [busy, setBusy] = useState(false);
  const rows = useMemo(() => {
    if (!db) return [];
    const Q = norm(qq);
    return db.list.filter(p => p.blk === blk && (!Q || norm(p.no).includes(Q)) && (showRemoved ? rec.removed[p.id] : true));
  }, [db, blk, qq, showRemoved, rec]);
  const PER = 20, pages = Math.ceil(rows.length / PER);
  const ch = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  const add = async e => {
    e.preventDefault(); setMsg(null);
    const no = f.no.trim().toUpperCase().replace(/\s+/g, '');
    if (!/^[A-FX]-?\d{1,4}[A-Z]?$/.test(no)) return setMsg({ ok: false, msg: 'Plot number: the block letter and the number, for example D-108.' });
    const full = no.includes('-') ? no : no[0] + '-' + no.slice(1);
    if (full[0] !== f.blk) return setMsg({ ok: false, msg: `Plot ${full} does not belong to Block ${f.blk}.` });
    if (db.byNo.get(full) || rec.added.some(r => r.no === full)) return setMsg({ ok: false, msg: `Rejected: plot ${full} already exists.` });
    const num = full.slice(2).replace(/[A-Z]$/, ''), same = db.list.filter(x => x.blk === f.blk && String(x.num) === num);
    if (same.length) return setMsg({ ok: false, msg: `Rejected: Block ${f.blk} already has plot number ${num} (${same.slice(0, 3).map(x => x.no).join(', ')}${same.length > 3 ? '…' : ''}). The plan repeats numbers in sub-blocks; check the society register.` });
    const area = +f.area; if (!(area > 50 && area < 20000)) return setMsg({ ok: false, msg: 'Area in square metres, between 50 and 20,000 (5 marla is about 126 m²).' });
    const b = checkBoundary(f.boundary); if (!b.ok) return setMsg(b);
    if (b.ring) {
      setBusy(true);
      const outl = await loadOutlines(f.blk).catch(() => ({})); setBusy(false);
      for (const [id, r] of Object.entries(outl)) {
        if (b.ring.some(([x, y]) => PIP(x, y, r)) || r.some(([x, y]) => PIP(x, y, b.ring))) { const o = db.byId.get(+id); return setMsg({ ok: false, msg: `Rejected: the boundary overlaps plot ${o ? o.no : id}.` }); }
      }
    }
    addRecord(s, { no: full, blk: f.blk, size: f.size, area, ring: b.ring });
    setMsg({ ok: true, msg: `Record ${full} saved and logged.` }); setF(x => ({ ...x, no: '', area: '', boundary: '' }));
  };
  return (
    <AppShell>
      <h1>Society &amp; plot records</h1>
      <p className="mut">Check the plot list against the society's register, add plots the plan lacks and remove wrong ones. {KEEP_NOTE}</p>
      {err && <ErrorBox error={err} />}
      {!db && !err && <Spinner />}
      {db && <div className="grid g2 recgrid">
        <div className="card">
          <div className="filters">
            <div><label htmlFor="rb">Block</label><select id="rb" value={blk} onChange={e => { setBlk(e.target.value); setPage(0); }}>{BLOCKS.map(b => <option key={b} value={b}>Block {b}</option>)}</select></div>
            <div><label htmlFor="rq">Plot number</label><input id="rq" value={qq} placeholder="Filter, e.g. 14" onChange={e => { setQq(e.target.value); setPage(0); }} /></div>
            <div><label className="chk" style={{ marginTop: 28 }}><input type="checkbox" checked={showRemoved} onChange={e => { setShowRemoved(e.target.checked); setPage(0); }} /> Removed only</label></div>
          </div>
          <p className="mut small">{fmtNum(rows.length)} plots</p>
          <div className="tblw"><table className="tbl"><thead><tr><th>Plot</th><th>Size</th><th>Area</th><th>Status</th><th /></tr></thead>
            <tbody>{rows.slice(page * PER, page * PER + PER).map(p => { const rm = rec.removed[p.id]; return (
              <tr key={p.id} className={rm ? 'removed' : ''}><td><Link to={'/plot/' + p.id}>{p.no}</Link></td><td>{p.size}</td><td>{Math.round(p.area)} m²</td><td><Badge t={statusOf(p, ov)} /></td>
                <td className="acts">{rm ? <><span className="mut" title={rm.reason}>Removed {ago(rm.at)}</span> · <a href="#/society/records" onClick={e => { e.preventDefault(); restoreRecord(s, p); }}>Restore</a></>
                  : <><Link to={'/society/status?id=' + p.id}>Status</Link> · <a href="#/society/records" onClick={e => { e.preventDefault(); const why = window.prompt('Why remove plot ' + p.no + '? (for the log)', 'Not in the society register'); if (why !== null) removeRecord(s, p, why); }}>Remove</a></>}</td></tr>); })}</tbody></table></div>
          <Pager page={page} pages={pages} onPage={setPage} />
        </div>
        <div className="grid">
          <form className="card" onSubmit={add}><h3>Add a plot record</h3>
            <label htmlFor="ano">Plot number</label><input id="ano" value={f.no} placeholder="D-108" onChange={ch('no')} />
            <div className="row2"><div><label htmlFor="abl">Block</label><select id="abl" value={f.blk} onChange={ch('blk')}>{BLOCKS.map(b => <option key={b}>{b}</option>)}</select></div>
              <div><label htmlFor="asz">Size</label><select id="asz" value={f.size} onChange={ch('size')}>{SIZES.map(z => <option key={z}>{z}</option>)}</select></div></div>
            <label htmlFor="aar">Area (m²)</label><input id="aar" inputMode="decimal" value={f.area} placeholder="253" onChange={ch('area')} />
            <label htmlFor="abd">Boundary (GeoJSON Polygon, optional)</label><textarea id="abd" rows="4" value={f.boundary} placeholder='{"type":"Polygon","coordinates":[[[73.08,31.52],[73.0802,31.52],[73.0802,31.5202],[73.08,31.5202],[73.08,31.52]]]}' onChange={ch('boundary')} />
            {msg && <p className={msg.ok ? 'fok' : 'ferr'} role="status">{msg.msg}</p>}
            <button className="btn" disabled={busy}>{busy ? 'Checking the boundary…' : 'Save record'}</button>
            <p className="mut small">The plot number must be new, and a boundary must not overlap any plot already on the plan.</p></form>
          {rec.added.length > 0 && <div className="card"><h3>Records added</h3><table className="tbl"><thead><tr><th>Plot</th><th>Size</th><th>By</th><th>When</th></tr></thead><tbody>{rec.added.map((r, i) => <tr key={i}><td>{r.no}</td><td>{r.size} · {Math.round(r.area)} m²{r.ring ? ' · boundary' : ''}</td><td>{r.by}</td><td>{ago(r.at)}</td></tr>)}</tbody></table></div>}
        </div>
      </div>}
    </AppShell>
  );
}

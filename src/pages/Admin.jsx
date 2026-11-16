import { useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import { Badge, useAsync, useTitle, fmtNum, Pager } from '../components/ui.jsx';
import { loadPlots, loadLandmarks } from '../lib/data.js';
import { useSession, ROLES, addUser, setUser, removeUser, passwordProblem } from '../lib/auth.js';
import { DATASETS, useDatasetStates, reviewDataset, useStatusLog } from '../lib/records.js';
import { useStored, ago, fmtTime, set } from '../lib/store.js';

const stateBadge = st => <Badge t={st === 'Verified' ? 'Available' : st === 'Flagged' ? 'Sold' : 'Reserved'}>{st}</Badge>;
const useDatasets = () => { const st = useDatasetStates(); return DATASETS.map(d => ({ ...d, ...(st[d.id] || {}), state: (st[d.id] && st[d.id].state) || d.state })); };

function AuditTable({ limit = 12, filter }) {
  const log = useStored('audit', []), [page, setPage] = useState(0);
  const rows = filter ? log.filter(filter) : log, pages = Math.ceil(rows.length / limit);
  if (!rows.length) return <p className="mut">Nothing logged yet.</p>;
  return <>
    <div className="tblw"><table className="tbl"><thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead>
      <tbody>{rows.slice(page * limit, page * limit + limit).map((a, i) => <tr key={i}><td title={fmtTime(a.at)}>{ago(a.at)}</td><td>{a.by}</td><td>{a.action}</td><td>{a.detail}</td></tr>)}</tbody></table></div>
    <Pager page={page} pages={pages} onPage={setPage} />
  </>;
}

export function AdminDashboard() {
  useTitle('Admin dashboard');
  const [db] = useAsync(loadPlots), [lms] = useAsync(loadLandmarks), users = useStored('users', []), ds = useDatasets(), log = useStatusLog();
  const pending = users.filter(u => u.status === 'Pending'), review = ds.filter(d => d.state !== 'Verified');
  return (
    <AppShell>
      <h1>System overview</h1>
      <div className="grid g4">
        <div className="card"><div className="stat">1</div><span className="mut">Society (FDA City pilot)</span></div>
        <div className="card"><div className="stat">{db ? fmtNum(db.list.length) : '…'}</div><span className="mut">Plots · {lms ? lms.length : '…'} facilities</span></div>
        <div className="card"><div className="stat">{users.length}</div><span className="mut">User accounts{pending.length ? ` · ${pending.length} waiting for approval` : ''}</span></div>
        <div className="card"><div className="stat" style={{ color: db ? '#7bd08b' : '#f0c26a' }}>{db ? 'Online' : 'Checking…'}</div><span className="mut">Map data</span></div>
      </div><br />
      <div className="grid g2">
        <div className="card"><h3>Datasets awaiting review</h3><p>{review.length} of {ds.length} datasets are pending or flagged.</p>
          <ul className="plain">{review.slice(0, 4).map(d => <li key={d.id}>{stateBadge(d.state)} {d.name}</li>)}</ul><Link className="btn" to="/admin/data">Review data</Link></div>
        <div className="card"><h3>User management</h3><p>{pending.length ? `${pending.length} Society Head account${pending.length > 1 ? 's' : ''} waiting for approval.` : 'Add, edit or remove accounts and roles.'}</p>
          <p className="mut small">{log.length} plot status update{log.length === 1 ? '' : 's'} logged by Society Heads.</p><Link className="btn o" to="/admin/system">Manage system</Link></div>
      </div>
      <div className="card"><h3>Recent activity</h3><AuditTable limit={8} /></div>
    </AppShell>
  );
}

export function AdminData() {
  useTitle('Track & verify data');
  const s = useSession(), ds = useDatasets();
  const act = (d, state) => { const note = window.prompt(`${state === 'Verified' ? 'Verify' : state === 'Flagged' ? 'Flag' : 'Set to pending'}: ${d.name}\nNote for the audit trail (optional):`, ''); if (note !== null) reviewDataset(s, d, state, note.trim()); };
  return (
    <AppShell>
      <h1>Track &amp; verify data sources</h1>
      <p className="mut">Every dataset the map uses, where it comes from, how old it is and how far it can be trusted. Verify or flag each one; every decision is logged.</p>
      <div className="card"><div className="tblw"><table className="tbl ds"><thead><tr><th>Dataset</th><th>Source</th><th>Date</th><th>Confidence</th><th>Review</th><th /></tr></thead>
        <tbody>{ds.map(d => <tr key={d.id}><td><b>{d.name}</b>{d.note && <><br /><small className="mut">{d.note}</small></>}</td>
          <td>{d.source || <span className="warn">Source information not recorded</span>}</td><td>{d.date || '–'}</td><td><Badge t={d.confidence} /></td>
          <td>{stateBadge(d.state)}{d.by && <><br /><small className="mut">{d.by}, {ago(d.at)}</small></>}</td>
          <td className="acts"><a href="#/admin/data" onClick={e => { e.preventDefault(); act(d, 'Verified'); }}>Verify</a> · <a href="#/admin/data" onClick={e => { e.preventDefault(); act(d, 'Flagged'); }}>Flag</a> · <a href="#/admin/data" onClick={e => { e.preventDefault(); act(d, 'Pending'); }}>Pending</a></td></tr>)}</tbody></table></div></div>
      <div className="card"><h3>Audit trail</h3><AuditTable limit={15} /></div>
    </AppShell>
  );
}

export function AdminSystem() {
  useTitle('Manage system');
  const s = useSession(), users = useStored('users', []);
  const [f, setF] = useState({ name: '', email: '', role: 'user', password: '' }), [msg, setMsg] = useState(null);
  const ch = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  const add = async e => { e.preventDefault(); const r = await addUser(s.name, f); setMsg(r.ok ? { ok: true, msg: `Account for ${f.name} added. Change logged.` } : r); if (r.ok) setF({ name: '', email: '', role: 'user', password: '' }); };
  const reset = async u => {
    const pw = window.prompt(`New temporary password for ${u.name} (8+ characters, letters and a number):`, '');
    if (pw === null) return; const pp = passwordProblem(pw); if (pp) { window.alert(pp); return; }
    const enc = new TextEncoder().encode('terralyt:' + pw), buf = window.crypto && crypto.subtle ? await crypto.subtle.digest('SHA-256', enc) : null;
    if (!buf) { window.alert('Password reset needs a secure page (localhost or https).'); return; }
    setUser(s.name, u.id, { hash: [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('') }, 'Reset password');
  };
  return (
    <AppShell>
      <h1>Manage system</h1>
      <p className="mut">User accounts and roles. Accounts are kept in this browser until the backend is connected.</p>
      <div className="grid g2" style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(260px,1fr)' }}>
        <div className="card"><h3>User accounts</h3><div className="tblw"><table className="tbl"><thead><tr><th>Name</th><th>Role</th><th>Status</th><th>Last log in</th><th /></tr></thead>
          <tbody>{users.map(u => { const me = u.id === s.id; return (
            <tr key={u.id}><td><b>{u.name}</b><br /><small className="mut">{u.email}</small></td>
              <td>{me ? ROLES[u.role] : <select className="mini" value={u.role} onChange={e => setUser(s.name, u.id, { role: e.target.value }, 'Changed role to ' + ROLES[e.target.value])}>{Object.entries(ROLES).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>}</td>
              <td><Badge t={u.status === 'Active' ? 'Available' : u.status === 'Pending' ? 'Reserved' : 'Sold'}>{u.status}</Badge></td>
              <td>{u.lastLogin ? ago(u.lastLogin) : '–'}</td>
              <td className="acts">{me ? <span className="mut">You</span> : <>
                {u.status === 'Pending' && <><a href="#/admin/system" onClick={e => { e.preventDefault(); setUser(s.name, u.id, { status: 'Active' }, 'Approved account'); }}>Approve</a> · </>}
                {u.status === 'Active' && <><a href="#/admin/system" onClick={e => { e.preventDefault(); setUser(s.name, u.id, { status: 'Disabled' }, 'Disabled account'); }}>Disable</a> · </>}
                {u.status === 'Disabled' && <><a href="#/admin/system" onClick={e => { e.preventDefault(); setUser(s.name, u.id, { status: 'Active' }, 'Enabled account'); }}>Enable</a> · </>}
                <a href="#/admin/system" onClick={e => { e.preventDefault(); reset(u); }}>Reset password</a> · <a href="#/admin/system" onClick={e => { e.preventDefault(); if (window.confirm('Remove the account of ' + u.name + '?')) removeUser(s.name, u.id); }}>Remove</a></>}</td></tr>); })}</tbody></table></div></div>
        <form className="card" onSubmit={add}><h3>Add user</h3>
          <label htmlFor="un">Name</label><input id="un" value={f.name} onChange={ch('name')} />
          <label htmlFor="ue">Email</label><input id="ue" type="email" value={f.email} onChange={ch('email')} />
          <label htmlFor="ur">Role</label><select id="ur" value={f.role} onChange={ch('role')}>{Object.entries(ROLES).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>
          <label htmlFor="up">Temporary password</label><input id="up" type="text" value={f.password} placeholder="8+ characters with a number" onChange={ch('password')} />
          {msg && <p className={msg.ok ? 'fok' : 'ferr'}>{msg.msg}</p>}
          <button className="btn">Add user</button></form>
      </div>
      <div className="card"><h3>Account activity</h3><AuditTable limit={10} filter={a => /user|account|password|role|Logged|Signed/i.test(a.action)} /></div>
      <div className="card"><h3>Demo data</h3><p className="mut">Clear everything this browser has stored (status updates, records, saved plots, reviews, the audit trail and the extra accounts) and start again with the three demo accounts.</p>
        <button className="btn o" onClick={() => { if (window.confirm('Clear all locally stored demo data?')) { for (const k of Object.keys(localStorage)) if (k.startsWith('terralyt:')) localStorage.removeItem(k); set('session', null); location.reload(); } }}>Reset demo data</button></div>
    </AppShell>
  );
}

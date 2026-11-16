import { Link } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import SearchBox from '../components/SearchBox.jsx';
import { Badge, Spinner, ErrorBox, useAsync, useTitle, fmtNum } from '../components/ui.jsx';
import { BASE, loadPlots } from '../lib/data.js';
import { useSession } from '../lib/auth.js';
import { statusOf, useStatusOverrides, useStatusLog, useSaved, toggleSaved, useViewed, useRecent } from '../lib/records.js';
import { ago } from '../lib/store.js';

export default function Dashboard() {
  useTitle('Dashboard');
  const s = useSession(), saved = useSaved(s), viewed = useViewed(), recent = useRecent(), ov = useStatusOverrides(), log = useStatusLog();
  const [db, err] = useAsync(loadPlots);
  const savedPlots = db ? saved.map(id => db.byId.get(id)).filter(Boolean) : [];
  const updates = log.filter(x => saved.includes(x.id)).slice(0, 6);
  const built = db ? db.list.filter(p => p.built).length : 0;
  return (
    <AppShell>
      <h1>Welcome back, {(s && s.name || 'there').split(' ')[0]}</h1>
      <p className="mut">Here is what is new in FDA City.</p>
      <div className="grid g4">
        <div className="card"><div className="stat">{saved.length}</div><span className="mut">Saved plots</span></div>
        <div className="card"><div className="stat">{viewed.length}</div><span className="mut">Recently viewed</span></div>
        <div className="card"><div className="stat">{updates.length}</div><span className="mut">Status updates on saved plots</span></div>
        <div className="card"><div className="stat">{db ? (built / db.list.length * 100).toFixed(1) + '%' : '…'}</div><span className="mut">Plots built today (2023 footprints)</span></div>
      </div><br />
      <div className="grid g2">
        <Link className="m3 dimg" to="/map" title="Open the 3D map"><img src={BASE + 'img/hero-3d.jpg'} alt="FDA City in 3D" /><span>Open the 3D map →</span></Link>
        <div className="grid">
          <div className="card"><h3>Find a plot</h3><SearchBox placeholder="Plot number, block, facility or coordinates" />
            {recent.length > 0 && <div className="chiprow">{recent.slice(0, 5).map(t => <Link key={t} className="chip3" to={'/search?q=' + encodeURIComponent(t)}>{t}</Link>)}</div>}</div>
          <div className="card"><h3>Status updates</h3>{updates.length ? updates.map((u, i) => <div className="kv" key={i}><span><Link to={'/plot/' + u.id}>{u.no}</Link> · {ago(u.at)}</span><span><Badge t={u.from} /> → <Badge t={u.to} /></span></div>) : <p className="mut" style={{ margin: 0 }}>No changes on your saved plots yet. Save plots to follow their status.</p>}</div>
        </div>
      </div>
      {err && <ErrorBox error={err} />}
      {!db && !err && <Spinner />}
      {db && (
        <div className="card">
          <h3>Saved plots</h3>
          {savedPlots.length ? (
            <div className="tblw"><table className="tbl"><thead><tr><th>Plot</th><th>Block</th><th>Size</th><th>Building</th><th>Status</th><th>Development</th><th /></tr></thead>
              <tbody>{savedPlots.map(p => <tr key={p.id}><td><Link to={'/plot/' + p.id}><b>{p.no}</b></Link></td><td>{p.blk}</td><td>{p.size}</td><td>{p.built ? 'House' : 'Vacant'}</td><td><Badge t={statusOf(p, ov)} /></td><td><Badge t={p.dev} /></td>
                <td className="acts"><Link to={'/map?id=' + p.id}>3D map</Link> · <a href="#/dashboard" onClick={e => { e.preventDefault(); toggleSaved(s, p.id); }}>Remove</a></td></tr>)}</tbody></table></div>
          ) : <p className="mut">You have not saved a plot yet. Open a plot and press <b>Save plot</b>.</p>}
          {viewed.length > 0 && <><h3 style={{ marginTop: 16 }}>Recently viewed</h3><div className="chiprow">{viewed.map(id => db.byId.get(id)).filter(Boolean).map(p => <Link key={p.id} className="chip3" to={'/plot/' + p.id}>{p.no}</Link>)}</div></>}
          <p style={{ marginTop: 14 }}><Link className="btn" to="/search">Search plots</Link> <Link className="btn o" to="/trends">Trends &amp; forecast</Link> <span className="mut small">{fmtNum(db.list.length)} plots in Blocks A to F and X</span></p>
        </div>
      )}
    </AppShell>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import SearchBox from '../components/SearchBox.jsx';
import PlotMap from '../components/PlotMap.jsx';
import { Badge, Spinner, ErrorBox, useAsync, useTitle } from '../components/ui.jsx';
import { loadPlots, loadLandmarks, loadOutlines, loadRoads, distM } from '../lib/data.js';
import { statusOf, statusSource, useStatusOverrides, useStatusLog, useSaved, toggleSaved, markViewed, useViewed } from '../lib/records.js';
import { useSession } from '../lib/auth.js';
import { fmtTime } from '../lib/store.js';

const NEAR = [['Mosque', ['mosque']], ['Park', ['park', 'playground']], ['School', ['school', 'highschool', 'university']], ['Hospital or dispensary', ['hospital', 'dispensary']], ['Shops', ['commercial', 'shops', 'metro']], ['Main gate', ['gate']]];

function NoPlot() {
  const viewed = useViewed(), [data] = useAsync(loadPlots);
  return (
    <AppShell>
      <h1>Plot details</h1>
      <div className="card"><p className="mut" style={{ marginTop: 0 }}>Search for a plot to see its details, or open one from the 3D map.</p><SearchBox big placeholder="Plot number (A-14), block or coordinates" /></div>
      {data && viewed.length > 0 && <div className="card"><h3>Recently viewed</h3><div className="chiprow">{viewed.map(id => data.byId.get(id)).filter(Boolean).map(p => <Link key={p.id} className="chip3" to={'/plot/' + p.id}>{p.no}</Link>)}</div></div>}
    </AppShell>
  );
}

export default function Plot() {
  const { id: pid } = useParams(), [q] = useSearchParams(), id = +(pid || q.get('id') || 0);
  const [data, err] = useAsync(() => Promise.all([loadPlots(), loadLandmarks()]));
  const p = data && data[0].byId.get(id);
  useTitle(p ? 'Plot ' + p.no : 'Plot details');
  const ov = useStatusOverrides(), log = useStatusLog(), s = useSession(), saved = useSaved(s);
  const [outl, setOutl] = useState(null), [roads, setRoads] = useState(null), [copied, setCopied] = useState(false);
  useEffect(() => { if (p) { markViewed(p.id); loadOutlines(p.blk).then(setOutl, () => setOutl({})); loadRoads().then(setRoads, () => {}); } }, [p && p.id]); // eslint-disable-line
  const near = useMemo(() => {
    if (!p || !data) return [];
    return NEAR.map(([t, kinds]) => {
      const c = data[1].filter(l => kinds.includes(l.kind)).map(l => ({ l, d: distM(p.lat, p.lon, l.lat, l.lon) })).sort((a, b) => a.d - b.d)[0];
      return c ? { t, ...c } : null;
    }).filter(Boolean);
  }, [p, data]);
  if (!id) return <NoPlot />;
  if (err) return <AppShell><ErrorBox error={err} /></AppShell>;
  if (!data) return <AppShell><Spinner text="Loading the plot…" /></AppShell>;
  if (!p) return <AppShell><h1>Plot not found</h1><div className="card"><p>There is no plot with number {id}. Search for it instead.</p><SearchBox big /></div></AppShell>;

  const st = statusOf(p, ov), so = statusSource(p, ov), isSaved = saved.includes(p.id), hist = log.filter(x => x.id === p.id);
  const share = () => { const u = location.href; (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }, () => window.prompt('Copy this link', u)); };
  return (
    <AppShell>
      <div className="phead">
        <div><h1>Plot {p.no}</h1><p className="mut">Block {p.blk} · {p.size} · {p.type}{p.sub ? ' · sub-block ' + p.sub + ' (estimated)' : ''}</p></div>
        <div className="pacts">
          <button className={'btn ' + (isSaved ? 'act' : 'o')} onClick={() => toggleSaved(s, p.id)}>{isSaved ? '★ Saved' : '☆ Save plot'}</button>
          <Link className="btn" to={'/map?id=' + p.id}>Open in 3D map</Link>
          <Link className="btn o" to={'/trends?id=' + p.id}>Trends &amp; forecast</Link>
          <button className="btn o" onClick={share}>{copied ? 'Link copied' : 'Share'}</button>
        </div>
      </div>
      <div className="grid g2 pgrid">
        <div className="card mapcard">{outl ? <PlotMap plot={p} outlines={outl} roads={roads} landmarks={data[1]} byId={data[0].byId} statusOf={x => statusOf(x, ov)} /> : <Spinner text="Drawing the plot…" />}
          <p className="mut small">Green: this plot. Brown: neighbouring plots (darker where a house stands today). Grey: streets. Outline from the FDA City plan, fitted to the real streets.</p></div>
        <div className="grid">
          <div className="card">
            <h3>Status and rating</h3>
            <div className="kv"><span>Sale status</span><Badge t={st} /></div>
            <div className="kv"><span>Source</span><b>{st === 'Unknown' && !so.updated ? 'Not recorded' : so.source}</b></div>
            <div className="kv"><span>Confidence</span><b>{so.confidence}</b></div>
            {st === 'Unknown' && <div className="note">Status Unknown. Contact the society office for confirmation.</div>}
            {!so.updated && st !== 'Unknown' && <p className="mut small">Sample value until the society's records are loaded. Plot status comes from verified records, never from satellite imagery alone.</p>}
            <div className="kv"><span>Area development</span><Badge t={p.dev} /></div>
            <p className="mut small">{p.bshare != null ? `${Math.round(p.bshare * 100)}% of the plots within 150 m have a house on them (building footprints, 2023).` : ''}</p>
          </div>
          <div className="card">
            <h3>Nearby</h3>
            {near.map(n => <div className="kv" key={n.t}><span>{n.t}</span><b><Link to={'/map?lm=' + n.l.id}>{n.l.name}</Link> · {n.d < 1000 ? Math.round(n.d / 10) * 10 + ' m' : (n.d / 1000).toFixed(1) + ' km'}</b></div>)}
            <p className="mut small">Straight-line distance from the centre of the plot.</p>
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Plot facts</h3>
        <table className="kv2"><tbody>
          <tr><th>Plot number</th><td>{p.num ? <>{p.num} <span className="mut">({p.numsrc})</span></> : <span className="mut">{p.numsrc || 'Not known'}</span>}</td></tr>
          <tr><th>Block</th><td>Block {p.blk}{p.sub ? ', sub-block ' + p.sub + ' (estimated)' : ''}</td></tr>
          <tr><th>Size</th><td>{p.size} · about {Math.round(p.area)} m²{p.marla ? ` (about ${p.marla} marla)` : ''}</td></tr>
          <tr><th>Use</th><td>{p.type}</td></tr>
          <tr><th>Building</th><td>{p.built ? `House standing today · ${p.storeys} storey${p.storeys > 1 ? 's' : ''} · about ${p.height} m (assumed)` : 'Vacant plot'}</td></tr>
          <tr><th>Built / vacant from</th><td>Building footprints detected on satellite imagery (2023)</td></tr>
          <tr><th>Coordinates</th><td>{p.lat.toFixed(6)}, {p.lon.toFixed(6)} · <a href={`https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`} target="_blank" rel="noreferrer">open in Google Maps</a></td></tr>
          <tr><th>Outline</th><td>{p.layout}</td></tr>
        </tbody></table>
      </div>
      {hist.length > 0 && <div className="card"><h3>Status history</h3><table className="tbl"><thead><tr><th>When</th><th>Change</th><th>By</th><th>Note</th></tr></thead><tbody>{hist.map((h, i) => <tr key={i}><td>{fmtTime(h.at)}</td><td><Badge t={h.from} /> → <Badge t={h.to} /></td><td>{h.by}</td><td>{h.note || '–'}</td></tr>)}</tbody></table></div>}
      <div className="note">Heights are assumed at 3.5 m per storey. The plot number is the one printed on the FDA City plan (read from the plan published on emap.pk); where the plan repeats a number inside a block, the estimated sub-block is added.</div>
    </AppShell>
  );
}

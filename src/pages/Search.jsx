import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import SearchBox from '../components/SearchBox.jsx';
import { Badge, Spinner, ErrorBox, useAsync, useTitle, Pager, fmtNum } from '../components/ui.jsx';
import { loadPlots, loadLandmarks, search, BLOCKS, SIZES, STATUSES } from '../lib/data.js';
import { statusOf, useStatusOverrides, addRecent } from '../lib/records.js';

const PER = 25;

export default function Search() {
  useTitle('Search');
  const [q, setQ] = useSearchParams();
  const [data, err] = useAsync(() => Promise.all([loadPlots(), loadLandmarks()]));
  const ov = useStatusOverrides();
  const text = q.get('q') || '', f = { blk: q.get('blk') || '', size: q.get('size') || '', status: q.get('status') || '', built: q.get('built') || '', dev: q.get('dev') || '', sort: q.get('sort') || '' };
  const page = +(q.get('page') || 0);
  const setP = (k, v) => { const n = new URLSearchParams(q); if (v) n.set(k, v); else n.delete(k); if (k !== 'page') n.delete('page'); setQ(n, { replace: true }); };

  const res = useMemo(() => {
    if (!data) return null;
    const [db, lms] = data;
    const r = text ? search(db, lms, text, 5000) : { kind: 'filter', items: db.list.map(p => ({ type: 'plot', plot: p })) };
    const keep = it => it.type !== 'plot' || ((!f.blk || it.plot.blk === f.blk) && (!f.size || it.plot.size === f.size) && (!f.status || statusOf(it.plot, ov) === f.status)
      && (!f.built || (f.built === 'built') === it.plot.built) && (!f.dev || it.plot.dev === f.dev));
    const items = r.items.filter(keep);
    let plots = items.filter(i => i.type === 'plot');
    const others = items.filter(i => i.type !== 'plot');
    if (f.sort === 'area') plots = [...plots].sort((a, b) => (b.plot.area || 0) - (a.plot.area || 0));
    else if (f.sort === 'dev') plots = [...plots].sort((a, b) => (b.plot.bshare || 0) - (a.plot.bshare || 0));
    else if (f.sort === 'no') plots = [...plots].sort((a, b) => a.plot.blk.localeCompare(b.plot.blk) || (a.plot.num || 0) - (b.plot.num || 0));
    return { kind: r.kind, plots, others, filtered: !!(f.blk || f.size || f.status || f.built || f.dev) };
  }, [data, text, f.blk, f.size, f.status, f.built, f.dev, f.sort, ov]);

  const pages = res ? Math.ceil(res.plots.length / PER) : 0;
  const Sel = ({ k, label, opts, all = 'All' }) => (
    <div><label htmlFor={'f-' + k}>{label}</label><select id={'f-' + k} value={f[k]} onChange={e => setP(k, e.target.value)}><option value="">{all}</option>{opts.map(o => Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o} value={o}>{o}</option>)}</select></div>
  );
  return (
    <AppShell>
      <h1>Search FDA City</h1>
      <p className="mut">Find a plot by its number (A-14, B 205), a whole block, a facility (mosque, school, park) or coordinates (31.5150, 73.0720). Filter to narrow the list.</p>
      <div className="card">
        <SearchBox big initial={text} placeholder="Plot number, block, facility or latitude, longitude" onSearch={t => { addRecent(t); setP('q', t); }} />
        <div className="filters">
          <Sel k="blk" label="Block" opts={BLOCKS.map(b => [b, 'Block ' + b])} />
          <Sel k="size" label="Plot size" opts={SIZES} />
          <Sel k="status" label="Status" opts={STATUSES} />
          <Sel k="built" label="Building" opts={[['built', 'House standing'], ['vacant', 'Vacant']]} />
          <Sel k="dev" label="Development" opts={['High', 'Medium', 'Low']} />
          <Sel k="sort" label="Sort by" all="Best match" opts={[['no', 'Plot number'], ['area', 'Largest first'], ['dev', 'Most developed area']]} />
        </div>
        {(text || res?.filtered) && <button className="btn o sm" onClick={() => setQ(new URLSearchParams(), { replace: true })}>Clear search and filters</button>}
      </div>
      {err && <ErrorBox error={err} />}
      {!data && !err && <Spinner text="Loading 13,000 plots…" />}
      {res && (
        <>
          {res.kind === 'invalid' && <div className="note">Invalid coordinates. Use latitude, longitude, for example 31.5150, 73.0720.</div>}
          {res.kind === 'coords' && !res.plots.length && <div className="note">No plot within 400 m of these coordinates. FDA City lies around 31.52 N, 73.08 E.</div>}
          {res.others.length > 0 && (
            <div className="rescards">{res.others.map((it, i) => it.type === 'landmark'
              ? <Link key={i} className="card rc" to={'/map?lm=' + it.lm.id}><b>{it.lm.name}</b><span className="mut">{it.lm.label}{it.lm.block ? ' · ' + it.lm.block : ''}{it.lm.kanal ? ' · ' + it.lm.kanal + ' kanal' : ''}{it.lm.proposed ? ' · proposed' : ''}</span><span className="go">Show on 3D map →</span></Link>
              : it.type === 'block' ? <a key={i} className="card rc" href={'#/search?blk=' + it.blk} onClick={e => { e.preventDefault(); setQ(new URLSearchParams({ blk: it.blk }), { replace: true }); }}><b>Block {it.blk}</b><span className="mut">List every plot in the block</span><span className="go">Show plots →</span></a>
                : <Link key={i} className="card rc" to="/map"><b>FDA City</b><span className="mut">Housing society, Faisalabad · {fmtNum(data[0].list.length)} plots</span><span className="go">Open the 3D map →</span></Link>)}</div>
          )}
          {(text || res.filtered || res.plots.length) ? (
            <div className="card">
              <p className="mut" style={{ marginTop: 0 }}>{res.plots.length ? `${fmtNum(res.plots.length)} plot${res.plots.length > 1 ? 's' : ''}` : (text ? 'No plot found. Check the spelling or try a nearby plot number.' : 'No plot matches these filters.')}</p>
              {res.plots.length > 0 && (
                <div className="tblw"><table className="tbl">
                  <thead><tr><th>Plot</th><th>Block</th><th>Size</th><th>Building</th><th>Status</th><th>Development</th>{res.kind === 'coords' && <th>Distance</th>}<th /></tr></thead>
                  <tbody>{res.plots.slice(page * PER, page * PER + PER).map(({ plot: p, dist }) => (
                    <tr key={p.id}><td><Link to={'/plot/' + p.id}><b>{p.no}</b></Link></td><td>{p.blk}</td><td>{p.size}{p.marla ? <small className="mut"> · {p.marla} marla</small> : null}</td><td>{p.built ? 'House' : 'Vacant'}</td><td><Badge t={statusOf(p, ov)} /></td><td><Badge t={p.dev} /></td>{res.kind === 'coords' && <td>{Math.round(dist)} m</td>}
                      <td className="acts"><Link to={'/plot/' + p.id}>Details</Link> · <Link to={'/map?id=' + p.id}>3D map</Link></td></tr>))}</tbody>
                </table></div>
              )}
              <Pager page={page} pages={pages} onPage={n => setP('page', String(n))} />
            </div>
          ) : null}
          {!text && !res.filtered && <p className="mut">Showing all plots. Type above or use the filters.</p>}
        </>
      )}
    </AppShell>
  );
}

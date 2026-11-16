import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import TrendChart, { INDICATORS, SAMPLE, project } from '../components/TrendChart.jsx';
import { Spinner, ErrorBox, useAsync, useTitle, fmtNum } from '../components/ui.jsx';
import { loadPlots, BLOCKS } from '../lib/data.js';

export default function Trends() {
  useTitle('Trends & forecast');
  const [q, setQ] = useSearchParams();
  const [db, err] = useAsync(loadPlots);
  const ind = Math.max(0, INDICATORS.findIndex(x => x.key === (q.get('ind') || 'built'))), I = INDICATORS[ind];
  const id = +(q.get('id') || 0), blk = q.get('blk') || '';
  const plot = db && id ? db.byId.get(id) : null;
  const scope = plot ? `Plot ${plot.no} and the area round it` : blk ? `Block ${blk}` : 'FDA City (whole society)';
  const set = (k, v) => { const n = new URLSearchParams(q); if (v) n.set(k, v); else n.delete(k); if (k === 'blk') n.delete('id'); setQ(n, { replace: true }); };
  // real today: share of plots with a house (building footprints, 2023), per block and for the society
  const real = useMemo(() => {
    if (!db) return null;
    const by = {}; for (const b of BLOCKS) by[b] = { n: 0, built: 0 };
    for (const p of db.list) { by[p.blk].n++; if (p.built) by[p.blk].built++; }
    const tot = db.list.length, built = db.list.filter(p => p.built).length;
    return { by, tot, built };
  }, [db]);
  const h = SAMPLE[I.key], pr = project(h);
  return (
    <AppShell>
      <h1>Historical trends &amp; 5-year forecast</h1>
      <p className="mut">How built up the society is, how green, and where it may be in 2030. Choose what to look at.</p>
      <div className="card">
        <div className="filters">
          <div><label htmlFor="t-ind">Indicator</label><select id="t-ind" value={I.key} onChange={e => set('ind', e.target.value)}>{INDICATORS.map(x => <option key={x.key} value={x.key}>{x.label}</option>)}</select></div>
          <div><label htmlFor="t-blk">Area</label><select id="t-blk" value={plot ? 'plot' : blk} onChange={e => set('blk', e.target.value === 'plot' ? '' : e.target.value)}>
            <option value="">Whole society</option>{BLOCKS.map(b => <option key={b} value={b}>Block {b}</option>)}{plot && <option value="plot">Plot {plot.no}</option>}</select></div>
        </div>
        <h3 style={{ marginTop: 6 }}>{I.label} · {scope}</h3>
        <div className="samplebar"><b>Sample values.</b> The development model (satellite history 2016 to 2025 and the 5-year forecast) is not connected yet; this chart shows how its results will appear.</div>
        <TrendChart key={I.key + blk + id} series={h} fmt={I.fmt} />
        <div className="fst"><div><b>{I.fmt(h[6])}</b><span>Observed 2025</span></div><div><b>{I.fmt(pr.f[4])}</b><span>Estimate 2030</span></div><div><b>± {ind ? (pr.sp * 5).toFixed(2) : Math.round(pr.sp * 5) + ' pts'}</b><span>Uncertainty by 2030</span></div></div>
        <span className="b High">Observed 2019–2025</span> <span className="b Medium">Forecast 2026–2030 (model estimate)</span>
      </div>
      <div className="note"><b>Model estimate, not a guarantee.</b> The shaded band shows the uncertainty range and widens further into the future.</div>
      {err && <ErrorBox error={err} />}
      {!db && !err && <Spinner />}
      {real && (
        <div className="card">
          <h3>Built today (real data)</h3>
          <p className="mut" style={{ marginTop: 0 }}>Share of plots with a house standing on them, from building footprints detected on satellite imagery (2023). Society: <b>{fmtNum(real.built)}</b> of {fmtNum(real.tot)} plots ({(real.built / real.tot * 100).toFixed(1)}%).</p>
          <div className="bars2">{BLOCKS.map(b => { const x = real.by[b], v = x.n ? x.built / x.n : 0; return (
            <a key={b} href={'#/trends?blk=' + b} className={blk === b ? 'on' : ''} onClick={e => { e.preventDefault(); set('blk', b); }}>
              <span>Block {b}</span><i style={{ width: Math.max(3, v * 100 * 6) + 'px' }} /><b>{(v * 100).toFixed(1)}%</b><small className="mut">{fmtNum(x.built)} of {fmtNum(x.n)}</small></a>); })}</div>
          {plot && <p className="mut">Around plot {plot.no}: {Math.round((plot.bshare || 0) * 100)}% of the plots within 150 m are built. <Link to={'/plot/' + plot.id}>Plot details</Link></p>}
        </div>
      )}
    </AppShell>
  );
}

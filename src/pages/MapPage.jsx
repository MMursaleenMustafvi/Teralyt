import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import { Badge, useTitle } from '../components/ui.jsx';
import { Society3D } from '../map/society3d.js';
import { useStatusOverrides, statusSource } from '../lib/records.js';
import '../styles/map.css';

const LG = {
  real: [['#b3a079', 'Plot (vacant land)'], ['#e6d8bd', 'House (built today)'], ['#3f8f3f', 'Park'], ['#3a3b3e', 'Road'], ['#3c8fba', 'Nalla']],
  size: [['#8fd16a', '5 Marla'], ['#ee8fb8', '10 Marla'], ['#7fa6e6', '20 Marla'], ['#f0a040', 'Commercial']],
  cls: [['#3fae5f', 'High'], ['#e0a93a', 'Medium'], ['#c9573f', 'Low']],
  stat: [['#34c38f', 'Available'], ['#e0a93a', 'Reserved'], ['#c9573f', 'Sold'], ['#9aa5a0', 'Unknown']],
  sat: [['#9c8a72', 'Built'], ['#ddd2b2', 'Vacant']]
};
const LAYERS = [['real', 'Realistic'], ['cls', 'Development'], ['stat', 'Plot status'], ['sat', 'Built / vacant'], ['size', 'Plot size']];
const TIMES = ['day', 'evening', 'night'], TLAB = { day: 'Day', evening: 'Evening', night: 'Night' };
const QLAB = { auto: 'Auto', high: 'High', fast: 'Fast' };
const QTIP = { auto: 'Auto: soft shading in corners (ambient occlusion) when this device is fast enough. Click for High', high: 'High: ambient occlusion on, details drawn further out. Click for Fast', fast: 'Fast: no ambient occlusion, details only close by. Click for Auto' };
const SIZES = [['5 Marla', '#8fd16a'], ['10 Marla', '#ee8fb8'], ['20 Marla', '#7fa6e6'], ['Commercial', '#f0a040']], STS = ['Available', 'Reserved', 'Sold', 'Unknown'];
const QUICK = [['FDA City Main Gate', 'Main gate'], ['Markazi Park', 'Central Park'], ['Jamia Mosque (B)', 'Mosque'], ['Boys High School', 'High school'], ['FDA City Hospital', 'Hospital'], ['Five Star Hotel site', 'Hotel site'], ['Barani Nala', 'Nalla'], ['Area for FDA City Homes', 'FDA City Homes'], ['Site for Grid Station (Block X)', 'Block X'], ['Fire Brigade', 'Fire brigade'], ['Metro Store', 'Metro']];
const TOUR = [
  ['FDA City Main Gate', 'lm', 'The main gate stands across the Main Entrance Road, where it leaves Sargodha Road. Its position is measured on satellite imagery.'],
  ['Main Boulevard (202 ft)', null, 'The 202 ft main boulevard: two carriageways of two lanes each with a planted median, paved strips and service roads on both sides, and commercial plots along it.'],
  ['Markazi Park', 'lm', 'Block A: Markazi Park, the 74.76 kanal central park, with the community centre inside it.'],
  ['Boys High School', 'lm', 'Next to the park the official map places the Girls and Boys High Schools, with the post office, police station and telephone exchange between them.'],
  ['Five Star Hotel site', 'lm', 'South of the park: the site reserved for a five star hotel, the commercial zone, the Block A hospital and the fire brigade.'],
  ['Jamia Mosque (B)', 'lm', 'Every block has a central complex. In Block B: Jamia Mosque (5 kanal), primary school (13.9 kanal), a 25.5 kanal playground, dispensary and commercial area.'],
  ['Barani Nala', 'lm', 'The Barani Nala storm drain crosses Block B and runs along Block F. No plots are placed on the channel or its banks.'],
  ['Site for Grid Station (Block X)', 'lm', 'Block X, in the north-east, is laid out on the newer FDA City plan: about 1,640 plots, two primary schools, three masjids, parks, a 48 kanal grid station site and two government housing sites.'],
  ['Jamia Mosque (D)', 'lm', 'Block D centre: Jamia Mosque, primary school, 24.9 kanal playground and commercial area.'],
  ['FDA City Hospital', 'lm', 'The Area for FDA City Homes has a hospital, sports complex, public building, school and playground E-6.'],
  ['Metro Store', null, 'At the main entrance from Sargodha Road stands the Metro store, shown on the official plan.']
];
const CES = 'https://cesium.com/downloads/cesiumjs/releases/1.119/Build/Cesium/';
const loadScript = src => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
const FS_IN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>;
const FS_OUT = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></svg>;

function Idle({ model, view, ready }) {
  return (<>
    <h3>Select a plot or building</h3>
    <p className="mut">Click any plot, mosque, school, park or other building on the map, or search above, to see its details.</p>
    <div className="prov"><span><b>Society</b> FDA City, Faisalabad</span><span><b>Plots</b> {ready ? model.plots.length.toLocaleString() : '…'}</span><span><b>Landmarks</b> {ready ? model.landmarks.length : '…'}</span><span><b>Blocks</b> A–F and X</span></div>
    {view === 'model' && <><p className="mut" style={{ margin: '14px 0 0', fontSize: 12.5 }}>Quick tour</p>
      <div className="lmchips">{QUICK.map(([q, t]) => <button key={q} onClick={() => { const r = model && model.search(q).find(x => x.lm); if (r) model.selectLandmark(r.lm); }}>{t}</button>)}</div></>}
  </>);
}

function Details({ p }) {
  if (p.landmark) return (<>
    <h3>{p.name}</h3><p className="mut">{p.type_label}{p.block ? ' · ' + p.block : ''}{p.area_kanal ? ' · about ' + p.area_kanal + ' kanal' : ''}</p>
    {p.proposed && <div className="note">Proposed facility shown on the official FDA City map. It is not built yet.</div>}
    <table className="kv2"><tbody>
      <tr><th>Facility</th><td>{p.type_label}</td></tr>{p.block && <tr><th>Block</th><td>{p.block}</td></tr>}
      {p.area_kanal ? <tr><th>Site area</th><td>about {p.area_kanal} kanal ({Math.round(p.area_kanal * 505.857).toLocaleString()} m²)</td></tr> : null}
      {p.height_m ? <tr><th>Model height</th><td>about {p.height_m} m</td></tr> : null}
      {p.length_m ? <tr><th>Length in society</th><td>about {(p.length_m / 1000).toFixed(1)} km</td></tr> : null}
      <tr><th>Position</th><td>{p.accuracy}</td></tr></tbody></table>
    <p className="mut" style={{ fontSize: 12.5, marginTop: 12 }}>{p.source}. {p.kind === 'nala' ? 'The channel is drawn at about 7 m wide with banks, and with bridges where roads cross it. No plots are placed on it or its banks.' : 'The 3D building is an illustrative model of the facility, not a survey of the real structure.'}</p>
  </>);
  const unk = p.status === 'Unknown';
  const so = statusSource({ id: p.id, src: p.source, conf: p.confidence });
  const bld = p.built ? `House standing · ${p.storeys} ${p.storeys > 1 ? 'storeys' : 'storey'} · ${p.height} m (${p.height_source})` : 'Vacant plot';
  return (<>
    <h3>Plot {p.plot_no}</h3><p className="mut">{p.block} · {p.size} · {p.type}</p>
    <p>Status <Badge t={p.status} /><br /><span className="mut">Source: {so.updated ? so.source : p.source} · Confidence: {so.updated ? so.confidence : p.confidence}</span></p>
    {unk && <div className="note">Status Unknown. Contact the society office for confirmation.</div>}
    <p>Development <Badge t={p.dev_class} /> <span className="mut">area class{p.built_share_150m != null ? ' · ' + Math.round(p.built_share_150m * 100) + '% of plots within 150 m are built' : ''}</span></p>
    <table className="kv2"><tbody>
      <tr><th>Building</th><td>{bld}</td></tr>
      <tr><th>Plot number</th><td>{p.plot_number ? <>{p.plot_number} <span className="mut">({p.number_source})</span></> : <span className="mut">{p.number_source || 'Not known'}</span>}</td></tr>
      {p.sub_block && <tr><th>Sub-block</th><td>{p.sub_block} <span className="mut">(estimated from the nearest park)</span></td></tr>}
      <tr><th>Plot area</th><td>about {Math.round(p.area_m2)} m²{p.marla ? ` (about ${p.marla} marla)` : ''}</td></tr>
      <tr><th>Coordinates</th><td>{(+p.lat).toFixed(5)}, {(+p.lon).toFixed(5)}</td></tr>
      <tr><th>Outline</th><td>{p.layout} ({p.accuracy})</td></tr>
      <tr><th>Built / vacant</th><td>{p.built ? 'Built' : 'Vacant'} · from building footprints detected on satellite imagery</td></tr></tbody></table>
    <p style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}><Link className="btn" to={'/plot/' + p.id}>Plot details</Link><Link className="btn o" to={'/trends?id=' + p.id}>Trends &amp; forecast</Link></p>
    <p className="mut" style={{ fontSize: 12.5 }}>{so.updated ? 'Status recorded by the Society Head.' : 'The status shown is a sample value until society records are loaded: plot status must come from verified records, never from satellite imagery.'} The plot number is the one printed on the FDA City plan (read from the plan published on emap.pk); where the plan repeats a number inside a block, a letter is added. Heights are assumed at 3.5 m per storey.</p>
  </>);
}

function BlockPanel({ b, model, onRefresh }) {
  const bar = (m, tot) => Object.entries(m).sort((x, y) => y[1] - x[1]).map(([k, v]) => <div key={k}><span>{k}</span><i style={{ width: Math.max(4, Math.round(v / tot * 150)) + 'px' }} />{v.toLocaleString()}</div>);
  const on = model.filter.block === b.block;
  return (<>
    <h3>Block {b.block}</h3><p className="mut">{b.plots.toLocaleString()} plots · {b.parks} parks · {b.mosques} mosques</p>
    <p className="mut" style={{ margin: '10px 0 2px' }}>Plot sizes</p><div className="bars">{bar(b.size, b.plots)}</div>
    <p className="mut" style={{ margin: '10px 0 2px' }}>Status (sample records)</p><div className="bars">{bar(b.status, b.plots)}</div>
    {b.facilities.length > 0 && <><p className="mut" style={{ margin: '10px 0 2px' }}>Facilities</p><p style={{ fontSize: 13 }}>{b.facilities.join(' · ')}</p></>}
    <p style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}><button className="btn o" onClick={() => { model.setFilter({ block: on ? null : b.block }); onRefresh(); }}>{on ? 'Show all blocks' : 'Highlight only Block ' + b.block}</button><Link className="btn o" to={'/search?blk=' + b.block}>List the plots</Link></p>
  </>);
}

export default function MapPage() {
  useTitle('3D map');
  const [q] = useSearchParams();
  const modelEl = useRef(null), cesEl = useRef(null), stageRef = useRef(null), tipRef = useRef(null);
  const modelRef = useRef(null), earthRef = useRef(null), viewRef = useRef('model'), tourRef = useRef(null), tourNext = useRef(null);
  const ov = useStatusOverrides();
  const [view, setView] = useState('model'), [layer, setLayer] = useState(LAYERS.some(l => l[0] === q.get('layer')) ? q.get('layer') : 'real');
  const [st, setSt] = useState({ state: 'loading', msg: 'Starting 3D view…' }), [ready, setReady] = useState(false);
  const [panel, setPanel] = useState(null), [, bump] = useState(0);
  const [time, setTimeS] = useState('day'), [ground, setGround] = useState('plan'), [labels, setLabels] = useState(true), [quality, setQuality] = useState(['auto', 'high', 'fast'].includes(q.get('quality')) ? q.get('quality') : 'auto');
  const [sizes, setSizes] = useState(SIZES.map(s => s[0])), [stats, setStats] = useState(STS), [count, setCount] = useState('');
  const [fs, setFs] = useState(false), [pseudo, setPseudo] = useState(false), [cap, setCap] = useState(null), [touring, setTouring] = useState(false);
  const [mq, setMq] = useState(''), [res, setRes] = useState(null);
  const active = () => (viewRef.current === 'earth' && earthRef.current ? earthRef.current : modelRef.current);
  const status = (state, msg) => setSt({ state, msg });

  // ---- create the 3D model once; dispose it when the page is left ----
  useEffect(() => {
    if (window.TerralytBG) window.TerralytBG.paused = true;              // free the GPU for the map
    const pick = p => setPanel(p ? { kind: 'pick', p } : null);
    const hover = (p, pos) => { const t = tipRef.current; if (!t) return; if (!p || !pos) { t.hidden = true; return; } t.hidden = false; t.textContent = p.landmark ? p.name : p.plot_no + ' · ' + p.status + ' · ' + p.dev_class; t.style.left = pos.x + 'px'; t.style.top = pos.y + 'px'; };
    const model = Society3D(modelEl.current, { audit: q.get('audit') === '1', quality: q.get('quality'), onPick: pick, onHover: hover, onBlock: b => setPanel({ kind: 'block', b }), onStatus: (s, m) => { if (viewRef.current === 'model') status(s, m); }, layer });
    modelRef.current = model; window.__map = model;
    model.ready.then(() => {
      setReady(true);
      const t = q.get('time'); if (TIMES.includes(t) && t !== 'day') { model.setTime(t); setTimeS(t); }
      if (q.get('ground') === 'satellite') model.setGround('satellite').then(g => setGround(g));
      const id = q.get('id'), pn = q.get('plot'), lm = q.get('lm'), blk = q.get('block');
      if (id) model.select(id); else if (pn) { const r = model.search(pn); if (r[0] && r[0].id != null) model.select(r[0].id); } else if (lm) model.selectLandmark(lm); else if (blk) { model.flyToBlock(blk); setPanel({ kind: 'block', b: model.blockStats(blk) }); }
      else if (model.intro && !q.get('view')) model.intro();          // opening flight down to the society
      if (q.get('view') === 'earth') switchView('earth');
    }).catch(() => {});
    const onKey = e => {
      if (e.target && e.target.closest && e.target.closest('input,textarea,select')) return;
      if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); toggleFullscreen(); }
      else if (e.key === 'Escape' && stageRef.current && stageRef.current.classList.contains('pseudo')) { setPseudo(false); setFs(false); }
    };
    const onFs = () => { const on = (document.fullscreenElement || document.webkitFullscreenElement) === stageRef.current; setFs(on); if (!on) setPseudo(false); };
    addEventListener('keydown', onKey); document.addEventListener('fullscreenchange', onFs); document.addEventListener('webkitfullscreenchange', onFs);
    window.__fs = toggleFullscreen;
    return () => {
      removeEventListener('keydown', onKey); document.removeEventListener('fullscreenchange', onFs); document.removeEventListener('webkitfullscreenchange', onFs);
      tourRef.current = null;
      if (model.dispose) model.dispose();
      if (earthRef.current && earthRef.current.destroy) earthRef.current.destroy();
      modelRef.current = null; earthRef.current = null; window.__map = null;
      if (window.TerralytBG) window.TerralytBG.paused = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Society Head status updates (kept in the browser) show on the map
  useEffect(() => {
    const m = modelRef.current; if (!ready || !m || !m.setPlotStatus) return;
    for (const [id, o] of Object.entries(ov)) m.setPlotStatus(+id, o.status, `Society Head record (${o.by}, ${new Date(o.at).toLocaleDateString()})`, 'High');
  }, [ready, ov]);
  // the size of the map changes with full screen
  useEffect(() => { const m = modelRef.current; if (m && m.resize) setTimeout(() => m.resize(), 50); }, [fs, pseudo]);

  async function openEarth() {
    if (earthRef.current) return earthRef.current;
    status('loading', 'Loading CesiumJS…');
    window.CESIUM_BASE_URL = CES;
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = CES + 'Widgets/widgets.css'; document.head.appendChild(l);
    try { if (!window.Cesium) await loadScript(CES + 'Cesium.js'); } catch (e) { status('error', 'CesiumJS did not load from the CDN. Check the internet connection.'); return null; }
    // Cesium ion token: VITE_CESIUM_TOKEN in .env.local (git-ignored); without one the map uses OpenStreetMap tiles on flat ground
    if (!window.TERRALYT_CONFIG) window.TERRALYT_CONFIG = { cesiumToken: import.meta.env.VITE_CESIUM_TOKEN || '' };
    const { Map3D } = await import('../map/map3d.js');
    const earth = Map3D(cesEl.current, { onPick: p => setPanel(p ? { kind: 'pick', p } : null), onHover: () => {}, onStatus: (s, m) => { if (viewRef.current === 'earth') status(s, m); }, layer: layer === 'real' || layer === 'size' ? 'cls' : layer });
    earthRef.current = earth; window.__earth = earth;
    return earth;
  }
  async function switchView(v) {
    if (v === viewRef.current) return;
    viewRef.current = v; setView(v); if (tipRef.current) tipRef.current.hidden = true;
    if (v !== 'model' && tourRef.current) stopTour();
    if (v === 'earth') { const e = await openEarth(); if (e) e.ready.then(() => { status('ready'); e.setLayer(layer === 'real' || layer === 'size' ? 'cls' : layer); const s = modelRef.current && modelRef.current.selected; if (s && s.plot) e.select(s.plot); }).catch(() => {}); }
    else { const m = modelRef.current; status(m.rendered() ? 'ready' : 'loading', 'Building 3D model…'); setTimeout(() => m.resize(), 30); setPanel(null); }
  }
  const pickLayer = l => { setLayer(l); modelRef.current.setLayer(l); if (earthRef.current) earthRef.current.setLayer(l === 'real' || l === 'size' ? 'cls' : l); };
  const nextTime = () => { const t = TIMES[(TIMES.indexOf(time) + 1) % 3]; modelRef.current.setTime(t); setTimeS(t); };
  const toggleGround = async () => { const g = await modelRef.current.setGround(ground !== 'satellite' ? 'satellite' : 'plan'); setGround(g); };
  const toggleLabels = () => { modelRef.current.setLabels(!labels); setLabels(!labels); };
  const nextQuality = () => { const order = ['auto', 'high', 'fast'], n = order[(order.indexOf(quality) + 1) % 3]; setQuality(modelRef.current.setQuality(n)); };
  const applyFilter = (sz, stt) => { const n = modelRef.current.setFilter({ sizes: sz.length === 4 ? null : new Set(sz), statuses: stt.length === 4 ? null : new Set(stt) }); setCount(sz.length < 4 || stt.length < 4 ? '· ' + n.toLocaleString() + ' plots match' : ''); };
  const toggleSize = s => { const n = sizes.includes(s) ? sizes.filter(x => x !== s) : [...sizes, s]; setSizes(n); applyFilter(n, stats); };
  const toggleSt = s => { const n = stats.includes(s) ? stats.filter(x => x !== s) : [...stats, s]; setStats(n); applyFilter(sizes, n); };
  function stopTour() { tourRef.current = null; setTouring(false); setCap(null); if (tourNext.current) tourNext.current(); }
  async function runTour() {
    if (tourRef.current) { stopTour(); return; }
    const me = tourRef.current = {}; setTouring(true); const m = modelRef.current;
    for (let i = 0; i < TOUR.length && tourRef.current === me; i++) {
      const [name, , text] = TOUR[i], r = m.search(name).find(x => x.lm);
      if (r) m.selectLandmark(r.lm); else if (name.startsWith('Main')) m.reset(2);
      setCap({ i, name, text });
      await new Promise(res => { const t = setTimeout(res, 7000); tourNext.current = () => { clearTimeout(t); res(); }; });
    }
    if (tourRef.current === me) { stopTour(); m.reset(); }
  }
  const toggleFullscreen = useCallback(async () => {
    const stage = stageRef.current; if (!stage) return;
    if (stage.classList.contains('fs')) { if (document.fullscreenElement || document.webkitFullscreenElement) (document.exitFullscreen || document.webkitExitFullscreen).call(document); else { setPseudo(false); setFs(false); } return; }
    const req = stage.requestFullscreen || stage.webkitRequestFullscreen;
    if (req) { try { await req.call(stage); return; } catch (e) { /* fall back below */ } }
    setPseudo(true); setFs(true);                // no Fullscreen API (e.g. Safari on iPhone): fill the browser window instead
  }, []);
  // search inside the map (its own plots and facilities)
  const doSearch = v => { setMq(v); const a = active(); if (!a || !a.plots || !a.plots.length || !v.trim()) { setRes(null); return; } setRes(a.search(v.trim())); };
  const goRes = r => { setRes(null); const a = active(); if (r.id != null) a.select(r.id); else if (r.lm != null && a.selectLandmark) a.selectLandmark(r.lm); else if (r.block) a.flyToBlock(r.block); };

  const legKey = view === 'earth' && (layer === 'real' || layer === 'size') ? 'cls' : layer;
  const searchBox = (
    <div className="sw msw">
      <input value={mq} placeholder="Find plot (B-12), block, mosque, school, park D-3, or lat, lon" autoComplete="off" onChange={e => doSearch(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (res && res[0]) goRes(res[0]); } else if (e.key === 'Escape') setRes(null); }} onBlur={() => setTimeout(() => setRes(null), 150)} />
      <div className={'dd' + (res ? ' on' : '')}>{res && (res.length ? <><div className="h">Results</div>{res.map((r, i) => <a key={i} href="#" onMouseDown={e => { e.preventDefault(); goRes(r); }}><span>{r.label}</span><small>{r.sub}</small></a>)}</> : <div className="h">No result found. Check the spelling or try a nearby plot number.</div>)}</div>
    </div>
  );
  const side = (
    <div className={'card' + (panel ? ' sel' : '')} id="side">
      {!panel && <Idle model={modelRef.current} view={view} ready={ready} />}
      {panel && panel.kind === 'pick' && <Details p={panel.p} />}
      {panel && panel.kind === 'block' && <BlockPanel b={panel.b} model={modelRef.current} onRefresh={() => bump(x => x + 1)} />}
    </div>
  );
  return (
    <AppShell wide>
      <h1>FDA City · 3D map</h1>
      <p className="mut">Left-drag to pan, scroll to zoom. To turn and tilt: right-drag, Shift + drag, the arrow keys, or the buttons under the compass. Click any plot or building for details. Press F or the ⛶ button for full screen.</p>
      <div className="vt" role="tablist"><button className={view === 'model' ? 'act' : ''} role="tab" onClick={() => switchView('model')}>3D society model</button><button className={view === 'earth' ? 'act' : ''} role="tab" onClick={() => switchView('earth')}>Real-world map (CesiumJS)</button></div>
      <div className="tools">
        {LAYERS.map(([k, t]) => <button key={k} className={'btn ' + (layer === k ? 'act' : 'o')} onClick={() => pickLayer(k)}>{t}</button>)}
        <span className="sep" />
        {view === 'model' && <>
          <button className={'btn ' + (time === 'day' ? 'o' : 'act')} title={`Now: ${TLAB[time]}. Click for ${TLAB[TIMES[(TIMES.indexOf(time) + 1) % 3]].toLowerCase()}`} onClick={nextTime}>{TLAB[TIMES[(TIMES.indexOf(time) + 1) % 3]]}</button>
          <button className={'btn ' + (ground === 'satellite' ? 'act' : 'o')} title="Show today's satellite photo under the plan" onClick={toggleGround}>{ground === 'satellite' ? '3D model ground' : 'Satellite photo'}</button>
          <button className={'btn ' + (touring ? 'act' : 'o')} title="Fly through the main places of FDA City" onClick={runTour}>{touring ? '■ Stop tour' : '▶ Tour'}</button>
          <button className={'btn ' + (labels ? 'o' : 'act')} onClick={toggleLabels}>{labels ? 'Labels on' : 'Labels off'}</button>
          <button className={'btn ' + (quality === 'auto' ? 'o' : 'act')} id="gq" title={QTIP[quality]} onClick={nextQuality}>Graphics: {QLAB[quality]}</button>
        </>}
        <button className="btn o" onClick={() => active().reset()}>Reset view</button>
        <button className="btn o" aria-label="Zoom in" onClick={() => active().zoomIn()}>+</button><button className="btn o" aria-label="Zoom out" onClick={() => active().zoomOut()}>−</button>
        {!fs && searchBox}
      </div>
      <div className="blk">Jump to block {['A', 'B', 'C', 'D', 'E', 'F', 'X'].map(b => <button key={b} className="btn o" onClick={() => { active().flyToBlock(b); if (active() === modelRef.current) setPanel({ kind: 'block', b: modelRef.current.blockStats(b) }); }}>{b}</button>)}</div>
      {view === 'model' && <div className="flt">Show {SIZES.map(([s, c]) => <button key={s} className={'chip2' + (sizes.includes(s) ? ' on' : '')} onClick={() => toggleSize(s)}><i style={{ background: c }} />{s}</button>)}<span className="sep" />{STS.map(s => <button key={s} className={'chip2' + (stats.includes(s) ? ' on' : '')} onClick={() => toggleSt(s)}>{s}</button>)}<span>{count}</span></div>}
      <div className="grid mapgrid">
        <div className={'stage' + (fs ? ' fs' : '') + (pseudo ? ' pseudo' : '')} id="stage" ref={stageRef}>
          <div id="model" ref={modelEl} hidden={view !== 'model'} />
          <div id="cesium" ref={cesEl} hidden={view !== 'earth'} />
          <div className={'st ' + st.state} id="st" hidden={st.state === 'ready'}>{st.state === 'error' ? <div><b>3D map unavailable</b>{st.msg}</div> : <div><span className="sp" />{st.msg}</div>}</div>
          <div id="tip" ref={tipRef} hidden />
          {view === 'model' && <span className="hint" id="hint">{ground === 'satellite' ? 'Plan over today\'s satellite photo' : 'Plots and numbers from the FDA City plan, fitted to the real streets · houses and road widths from satellite imagery'}</span>}
          {view === 'model' && ground === 'satellite' && <div className="attr" id="attr">Satellite imagery © Esri, Maxar, Earthstar Geographics</div>}
          {cap && <div className="cap" id="cap"><b>{cap.i + 1} / {TOUR.length} · {cap.name}</b>{cap.text}<div className="row"><button onClick={() => tourNext.current && tourNext.current()}>Next</button><button onClick={stopTour}>Stop</button></div></div>}
          <div className="leg" id="lg">{LG[legKey].map(([c, t]) => <span key={t}><i style={{ background: c }} />{t}</span>)}</div>
          <button className="fsb" id="fsb" title={fs ? 'Exit full screen (Esc)' : 'Full screen (F)'} aria-label={fs ? 'Exit full screen (Esc)' : 'Full screen (F)'} onClick={toggleFullscreen}>{fs ? FS_OUT : FS_IN}</button>
          {fs && searchBox}
          {fs && side}
        </div>
        {!fs && side}
      </div>
      <div className="note"><b>Data sources.</b> Plots, plot numbers, parks, mosques, schools and all named sites: the FDA City plan and block maps, fitted to the real streets. Street centrelines: OpenStreetMap. Road widths, service roads, roundabouts and the Barani Nala: measured on satellite imagery. Houses, built / vacant and the development class: building footprints detected on satellite imagery (Google Open Buildings, Microsoft, via Overture Maps, 2023). Plot status and storeys are sample values unless a Society Head has recorded them. Buildings are illustrative 3D models.</div>
    </AppShell>
  );
}

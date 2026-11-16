import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Logo, Badge, Footer, useTitle, fmtNum } from '../components/ui.jsx';
import SearchBox from '../components/SearchBox.jsx';
import TrendChart, { INDICATORS, SAMPLE, project } from '../components/TrendChart.jsx';
import { BASE, loadPlots, loadLandmarks } from '../lib/data.js';
import { useSession, logout, HOME } from '../lib/auth.js';
import { statusOf, statusSource } from '../lib/records.js';

const scrollTo = id => e => { if (e) e.preventDefault(); const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth' }); };
const LAYERS = [['cls', 'Development', 'High / Medium / Low development of the area round each plot'], ['stat', 'Status', 'Available / Reserved / Sold (sample records)'], ['real', 'Realistic', 'Houses standing today on their real footprints']];

function Count({ n, suffix = '', on }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!on || !n) return;
    const s = performance.now(); let raf;
    const f = t => { const k = Math.min(1, (t - s) / 1400); setV(Math.round(n * (1 - Math.pow(1 - k, 3)))); if (k < 1) raf = requestAnimationFrame(f); };
    raf = requestAnimationFrame(f); return () => cancelAnimationFrame(raf);
  }, [n, on]);
  return <>{fmtNum(v)}{suffix}</>;
}

export default function Home() {
  useTitle('');
  const s = useSession();
  const [db, setDb] = useState(null), [lms, setLms] = useState([]), [seen, setSeen] = useState({}), [ind, setInd] = useState(0), [layer, setLayer] = useState('cls'), [ci, setCi] = useState(0);
  useEffect(() => { loadPlots().then(setDb, () => {}); loadLandmarks().then(setLms, () => {}); }, []);
  // full-screen sections that snap on large screens, revealed as they scroll in (classes in style.css)
  const root = useRef(null);
  useEffect(() => {
    const mq = matchMedia('(min-width:901px) and (min-height:561px)'), sn = () => document.documentElement.classList.toggle('snap', mq.matches);
    sn(); mq.addEventListener('change', sn);
    const io = new IntersectionObserver(es => es.forEach(e => {
      const el = e.target;
      if (e.intersectionRatio >= .4) { el.classList.add('in'); setSeen(x => (x[el.id] ? x : { ...x, [el.id]: true })); document.querySelectorAll('.dots a').forEach(d => d.classList.toggle('on', d.dataset.s === el.id)); }
      else if (e.intersectionRatio < .05) el.classList.remove('in');
    }), { threshold: [0, .05, .4, .7] });
    root.current.querySelectorAll('.sc').forEach(x => io.observe(x));
    return () => { io.disconnect(); mq.removeEventListener('change', sn); document.documentElement.classList.remove('snap'); };
  }, []);
  // search preview: cycle through real plots with houses on them
  const picks = db ? db.list.filter(p => p.built && p.num).filter((p, i) => i % 37 === 0).slice(0, 8) : [];
  useEffect(() => { const t = setInterval(() => setCi(i => i + 1), 3600); return () => clearInterval(t); }, []);
  const p = picks.length ? picks[ci % picks.length] : null;
  const built = db ? db.list.filter(x => x.built).length : 0;
  const I = INDICATORS[ind], h = SAMPLE[I.key], pr = project(h);
  const SECTIONS = [['hero', 'Home'], ['features', 'Features'], ['search', 'Search'], ['forecast', 'Forecast'], ['map3d', '3D Map'], ['start', 'Get started']];
  return (
    <div ref={root}>
      <div className="nav fx">
        <a className="brand" href="#/" onClick={scrollTo('hero')}><Logo />Terralyt</a>
        <div className="l">{SECTIONS.slice(1, 5).map(([id, t]) => <a key={id} href={'#/' + id} onClick={scrollTo(id)}>{t}</a>)}</div>
        <div>{s ? <><Link className="btn o" to={HOME[s.role]}>Dashboard</Link> <button className="btn" onClick={() => logout()}>Log out</button></> : <><Link className="btn o" to="/login">Log in</Link> <Link className="btn" to="/signup">Get started</Link></>}</div>
      </div>
      <nav className="dots">{SECTIONS.map(([id, t], i) => <a key={id} data-s={id} href={'#/' + id} className={i ? '' : 'on'} onClick={scrollTo(id)}><span>{t}</span></a>)}</nav>

      <section className="sc" id="hero"><div className="hg"><div>
        <span className="tag rv"><i />Pilot live in FDA City, Faisalabad</span>
        <h1 className="rv" style={{ '--i': 1 }}>Know a society <em>before</em> you ever visit it.</h1>
        <p className="rv" style={{ '--i': 2 }}>Satellite data, a 3D map of every plot and an honest 5-year forecast, so buyers and overseas Pakistanis can judge a housing society from anywhere.</p>
        <div className="hs rv" style={{ '--i': 3 }}><svg viewBox="0 0 24 24" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg><SearchBox id="hq" placeholder="Search plot, block or coordinates…" /><Link className="btn" to="/search">Search</Link></div>
        <div className="cta2 rv" style={{ '--i': 4 }}><Link className="btn w" to="/map">Explore the 3D map</Link><a className="btn gh" href="#/forecast" onClick={scrollTo('forecast')}>See a forecast</a></div>
        <div className="kp rv" style={{ '--i': 5 }}>
          <div><b><Count n={db ? db.list.length : 0} on={seen.hero} /></b><span>Plots mapped</span></div>
          <div><b><Count n={built} on={seen.hero} /></b><span>Plots built today</span></div>
          <div><b><Count n={lms.length} on={seen.hero} /></b><span>Facilities</span></div>
        </div></div>
        <div className="v3 rv" style={{ '--i': 2 }}>
          <img className="bob heroimg" src={BASE + 'img/hero-3d.jpg'} alt="The 3D model of FDA City with its plots, houses, parks and main boulevard" />
          <svg className="orb" viewBox="0 0 1000 620"><g transform="rotate(-14 500 320)"><ellipse cx="500" cy="320" rx="440" ry="150" fill="none" stroke="rgba(227,207,165,.35)" strokeDasharray="3 9" /><g><rect x="-9" y="-5" width="18" height="10" rx="2" fill="#e3cfa5" /><rect x="-30" y="-3" width="18" height="6" fill="#3a8a55" /><rect x="12" y="-3" width="18" height="6" fill="#3a8a55" /><path d="M0 5L-26 60L26 60z" fill="rgba(123,208,139,.2)" /><animateMotion dur="14s" repeatCount="indefinite" path="M60,320 a440,150 0 1,0 880,0 a440,150 0 1,0 -880,0" /></g></g></svg>
          <div className="fc" style={{ left: 14, top: 16 }}><img src={BASE + 'globe.png'} alt="" /><div><b>FDA City</b>{db ? fmtNum(db.list.length) + ' plots in 7 blocks' : 'Faisalabad'}</div></div>
          <div className="fc" style={{ right: 14, bottom: 16, animationDelay: '-2s' }}><div><b>2030 forecast</b>Model estimate · not a guarantee</div></div>
        </div></div>
        <a className="cue" href="#/features" onClick={scrollTo('features')}>Scroll<svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg></a>
      </section>

      <section className="sc" id="features"><div className="fgrid"><div><span className="tag rv"><i />Features</span><h2 className="rv" style={{ '--i': 1 }}>Everything to judge a society remotely</h2><p className="lead rv" style={{ '--i': 2 }}>Evidence from satellites, shown on a map you can actually move around in.</p><div className="globe rv" style={{ '--i': 3 }}><img src={BASE + 'globe.png'} alt="Satellite view of a planned society" /><i /><i /></div></div>
        <div className="fcards">{[
          [<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>, 'Smart search', 'By plot number, block, facility or coordinates, with live suggestions.'],
          [<><path d="M12 2l9 5v10l-9 5-9-5V7z" /><path d="M12 12l9-5M12 12v10M12 12L3 7" /></>, 'Real 3D map', 'Every plot from the FDA City plan, houses on their real footprints, day and night.'],
          [<><path d="M3 20h18M6 16V9M11 16V5M16 16v-5M21 16V8" /></>, 'Development rating', 'Low, Medium or High from how much is built around each plot.'],
          [<><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></>, 'Trends and forecast', 'Past change plus a 5-year estimate with an uncertainty range.'],
          [<><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="9" /></>, 'Status with proof', 'Available, Reserved or Sold, always with its source and confidence.'],
          [<><rect x="4" y="11" width="16" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></>, 'Verified data', 'Administrators verify every dataset, and every change is logged.']
        ].map(([ic, t, d], i) => <div key={t} className="card fcd rv" style={{ '--i': i + 2 }}><div className="ic"><svg viewBox="0 0 24 24">{ic}</svg></div><h3>{t}</h3><p className="mut">{d}</p></div>)}</div></div></section>

      <section className="sc" id="search"><div className="two"><div><span className="tag rv"><i />Search</span><h2 className="rv" style={{ '--i': 1 }}>Find any plot in seconds</h2><p className="lead rv" style={{ '--i': 2 }}>Type a plot number, a block, a facility or coordinates. Partial matches work, and suggestions appear as you type.</p>
        <div className="hs big rv" style={{ '--i': 3 }}><svg viewBox="0 0 24 24" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg><SearchBox id="sq" placeholder="Try A-14, Block X, Jamia Mosque or 31.5150, 73.0720" /><Link className="btn" to="/search">Search</Link></div>
        <div className="chips rv" style={{ '--i': 4 }}>{['A-14', 'Block X', 'Jamia Mosque', 'Markazi Park', '31.5150, 73.0720'].map(t => <Link key={t} className="chip3" to={'/search?q=' + encodeURIComponent(t)}>{t}</Link>)}</div></div>
        <div className="rv" style={{ '--i': 3 }}><div className="card pcard">{p ? (() => { const so = statusSource(p); return (
          <div className="swp" key={p.id}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}><div><div className="mut">Block {p.blk} · {p.size}</div><h3 style={{ fontSize: 'clamp(24px,4.6vh,34px)' }}>{p.no}</h3></div><Badge t={p.dev} /></div>
            <div className="kv"><span>Sale status</span><Badge t={statusOf(p)} /></div><div className="kv"><span>Building</span><b>{p.built ? 'House standing today' : 'Vacant'}</b></div><div className="kv"><span>Source</span><b>{so.source}</b></div><div className="kv"><span>Coordinates</span><b>{p.lat.toFixed(5)}, {p.lon.toFixed(5)}</b></div>
            <p style={{ margin: '14px 0 0' }}><Link className="btn" to={'/plot/' + p.id}>Open plot details</Link></p></div>); })() : <p className="mut">Loading plots…</p>}</div></div></div></section>

      <section className="sc" id="forecast"><div className="two"><div><span className="tag rv"><i />Trends &amp; forecast</span><h2 className="rv" style={{ '--i': 1 }}>See where it has been, and where it may go</h2><p className="lead rv" style={{ '--i': 2 }}>Satellite history since 2019 and a 5-year projection. Every forecast is a model estimate with an uncertainty range, never a guarantee.</p>
        <div className="tools rv" style={{ '--i': 3 }}>{INDICATORS.map((x, i) => <button key={x.key} className={'btn ' + (i === ind ? 'act' : 'o')} onClick={() => setInd(i)}>{x.label}</button>)}</div>
        <div className="fst rv" style={{ '--i': 4 }}><div><b>{I.fmt(h[6])}</b><span>Observed 2025</span></div><div><b>{I.fmt(pr.f[4])}</b><span>Estimate 2030</span></div><div><b>± {ind ? (pr.sp * 5).toFixed(2) : Math.round(pr.sp * 5) + ' pts'}</b><span>Uncertainty</span></div></div>
        <p className="mut sample rv" style={{ '--i': 5 }}>Sample values: the development model is not connected yet.</p></div>
        <div className="card rv" style={{ '--i': 3 }}><div className="fcw" key={ind}>{seen.forecast && <TrendChart series={h} fmt={I.fmt} />}</div></div></div></section>

      <section className="sc" id="map3d"><div className="two3"><div><span className="tag rv"><i />3D map</span><h2 className="rv" style={{ '--i': 1 }}>Walk the society in 3D</h2><p className="lead rv" style={{ '--i': 2 }}>Every plot of the FDA City plan, the houses standing today, parks, mosques and schools. Drag to turn, scroll to zoom, click a plot.</p>
        <div className="tools rv" style={{ '--i': 3 }}>{LAYERS.map(([k, t]) => <button key={k} className={'btn ' + (k === layer ? 'act' : 'o')} onClick={() => setLayer(k)}>{t}</button>)}</div>
        <div className="card rv" style={{ '--i': 4 }}><h3>{LAYERS.find(x => x[0] === layer)[1]} view</h3><p className="mut" style={{ margin: '0 0 12px' }}>{LAYERS.find(x => x[0] === layer)[2]}.</p><Link className="btn" to={'/map?layer=' + layer}>Open this view in 3D</Link></div></div>
        <div className="v3 m rv" style={{ '--i': 2 }}><img key={layer} className="layerimg" src={BASE + 'img/layer-' + layer + '.jpg'} alt={'3D map, ' + layer + ' view'} /></div></div></section>

      <section className="sc last" id="start"><div className="mid"><img className="f rv" src={BASE + 'logo-full.png'} alt="Terralyt" /><h2 className="rv" style={{ '--i': 1 }}>See FDA City in 3D</h2><p className="lead rv" style={{ '--i': 2, textAlign: 'center' }}>Forecasts are model estimates, never guarantees. Plot status always shows its source.</p><div className="cta2 rv" style={{ '--i': 3 }}><Link className="btn w" to="/map">Open the full map</Link><Link className="btn gh" to="/signup">Create an account</Link></div></div>
        <Footer big /></section>
    </div>
  );
}

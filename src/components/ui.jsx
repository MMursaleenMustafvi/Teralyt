import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BASE } from '../lib/data.js';

export const Logo = ({ className = 'lg' }) => <img className={className} src={BASE + 'logo-icon.png'} alt="Terralyt" />;

/** coloured pill for a status or development class (High, Medium, Low, Available, Reserved, Sold, Unknown) */
export const Badge = ({ t, children }) => <span className={'b ' + (t || '')}>{children || t}</span>;

export function Footer({ big }) {
  if (!big) return (
    <footer className="ft s"><span><Logo />© 2026 Terralyt · Final Year Project</span>
      <span className="fl"><Link to="/">Home</Link><Link to="/map">3D Map</Link><Link to="/trends">Forecast</Link></span>
      <span>Forecasts are estimates, not guarantees</span></footer>);
  return (
    <footer className="ft"><div className="ftg">
      <div><div className="fb"><Logo /><b>Terralyt</b></div><p>Geospatial intelligence for housing societies in Pakistan. Satellite evidence, a 3D map and honest forecasts.</p></div>
      <div><h4>Product</h4><Link to="/map">3D Map</Link><Link to="/search">Search</Link><Link to="/trends">Trends &amp; Forecast</Link><a href="#/" onClick={e => { const el = document.getElementById('features'); if (el) { e.preventDefault(); el.scrollIntoView({ behavior: 'smooth' }); } }}>Features</a></div>
      <div><h4>Access</h4><Link to="/login">Log in</Link><Link to="/signup">Sign up</Link><Link to="/login?role=head">Society Head</Link><Link to="/login?role=admin">Administrator</Link></div>
      <div><h4>Project</h4><span>Final Year Project · 2026</span><span>Supervisor: Ms. Mahzaib Younas</span><span>Taha · Mursaleen · Rahmeen</span></div>
    </div><div className="ftb"><span>© 2026 Terralyt · Final Year Project</span><span>Forecasts are model estimates, not guarantees.</span></div></footer>);
}

export const Spinner = ({ text = 'Loading…' }) => <div className="loadbox"><span className="sp" />{text}</div>;
export const ErrorBox = ({ error }) => <div className="note err"><b>Could not load the data.</b> {String(error && error.message ? error.message : error)}. Run the site with <code>npm run dev</code> and reload.</div>;

/** run an async loader once; returns [data, error] */
export function useAsync(fn, deps = []) {
  const [state, setState] = useState([null, null]);
  useEffect(() => {
    let live = true;
    fn().then(d => live && setState([d, null]), e => live && setState([null, e]));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

/** page title in the browser tab */
export function useTitle(t) { useEffect(() => { document.title = t ? t + ' · Terralyt' : 'Terralyt · Geospatial Intelligence for Housing Societies'; }, [t]); }

export function Pager({ page, pages, onPage }) {
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn o sm" disabled={page <= 0} onClick={() => onPage(page - 1)}>Previous</button>
      <span className="mut">Page {page + 1} of {pages}</span>
      <button className="btn o sm" disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>Next</button>
    </div>
  );
}

export const fmtNum = n => (n == null ? '–' : Number(n).toLocaleString());
export const pct = (a, b) => (b ? Math.round(a / b * 100) : 0) + '%';

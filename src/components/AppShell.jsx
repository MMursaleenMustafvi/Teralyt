import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Logo, Footer } from './ui.jsx';
import SearchBox from './SearchBox.jsx';
import { useSession, logout, HOME, ROLES } from '../lib/auth.js';
import { useViewed } from '../lib/records.js';

const IC = [
  <><rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" /><rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" /></>,
  <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>,
  <><path d="M12 2l9 5v10l-9 5-9-5V7z" /><path d="M12 12l9-5M12 12v10M12 12L3 7" /></>,
  <><path d="M12 21s7-6 7-11a7 7 0 10-14 0c0 5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></>,
  <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></>,
  <><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="9" /></>,
  <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
  <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></>
];
const Icon = ({ i }) => <svg viewBox="0 0 24 24">{IC[i]}</svg>;

function navFor(role, lastPlot) {
  const plot = lastPlot ? '/plot/' + lastPlot : '/plot';
  if (role === 'head') return [['/society', 'Dashboard', 'Dashboard', 0], ['/society/status', 'Status', 'Update Plot Status', 5], ['/society/records', 'Records', 'Society & Plot Records', 6], ['/map', '3D Map', '3D Map', 2], [plot, 'Plot', 'Plot Details', 3]];
  if (role === 'admin') return [['/admin', 'Dashboard', 'Dashboard', 0], ['/admin/data', 'Data', 'Track & Verify Data', 5], ['/admin/system', 'System', 'Manage System', 7], ['/map', '3D Map', '3D Map', 2]];
  const base = [['/search', 'Search', 'Search', 1], ['/map', '3D Map', '3D Map', 2], [plot, 'Plot', 'Plot Details', 3], ['/trends', 'Trends', 'Trends & Forecast', 4]];
  return role === 'user' ? [['/dashboard', 'Dashboard', 'Dashboard', 0], ...base] : base;
}

/** the signed-in layout: side menu (desktop), top bar with search and account menu, bottom bar (phones) */
export default function AppShell({ children, wide }) {
  const s = useSession(), nav = useNavigate(), loc = useLocation(), viewed = useViewed();
  const role = s ? s.role : 'guest', items = navFor(role, viewed[0]);
  const [menu, setMenu] = useState(false), um = useRef(null);
  useEffect(() => { const f = e => { if (um.current && !um.current.contains(e.target)) setMenu(false); }; document.addEventListener('mousedown', f); return () => document.removeEventListener('mousedown', f); }, []);
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [loc.pathname]);
  const out = e => { e.preventDefault(); logout(); nav('/'); };
  const isOn = to => to === loc.pathname || (to.startsWith('/plot') && loc.pathname.startsWith('/plot')) || (to !== '/' && to.length > 1 && loc.pathname === to);
  return (
    <>
      <div className="shell">
        <aside className="side">
          <Link className="brand" to="/"><Logo /><span>Terralyt<small>FDA City · Pilot</small></span></Link>
          {items.map(([to, , full, ic]) => <NavLink key={full} className={() => 'n' + (isOn(to) ? ' on' : '')} to={to}><Icon i={ic} />{full}</NavLink>)}
          {s ? <a className="out" href="#" onClick={out}><svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>Log out</a>
            : <Link className="out" to={'/login?next=' + encodeURIComponent(loc.pathname + loc.search)}><svg viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" /></svg>Log in</Link>}
        </aside>
        <div className="main">
          <div className="top">
            <Link className="mb" to="/"><Logo />Terralyt</Link>
            <SearchBox id="tsq" placeholder="Search plot, block, facility or coordinates…" />
            {s ? (
              <div className={'um' + (menu ? ' open' : '')} ref={um}>
                <button className="chip" onClick={() => setMenu(m => !m)} aria-haspopup="true" aria-expanded={menu}><span className="av">{(s.name || '?')[0].toUpperCase()}</span><span className="unm">{s.name}</span></button>
                <div className="menu"><div className="mh">Signed in as<br /><b style={{ color: 'var(--cr)' }}>{s.name}</b><br /><small>{ROLES[s.role]}</small></div>
                  <Link to={HOME[s.role]}>Dashboard</Link><Link to="/">Home page</Link><a className="lo" href="#" onClick={out}>Log out</a></div>
              </div>
            ) : <div className="gbtn"><Link className="btn o sm" to={'/login?next=' + encodeURIComponent(loc.pathname + loc.search)}>Log in</Link><Link className="btn sm" to="/signup">Sign up</Link></div>}
          </div>
          <div className={'pgw' + (wide ? ' wide' : '')}><div className="pg">{children}</div></div>
          <Footer />
        </div>
      </div>
      <nav className="bnav">{items.map(([to, short, , ic]) => <NavLink key={short} className={() => (isOn(to) ? 'on' : '')} to={to}><Icon i={ic} />{short}</NavLink>)}</nav>
    </>
  );
}

/** pages for one role only: anyone else goes to the login page first */
export function RequireRole({ role, children }) {
  const s = useSession(), loc = useLocation();
  if (!s) return <Navigate to={'/login?role=' + role + '&next=' + encodeURIComponent(loc.pathname + loc.search)} replace />;
  if (s.role !== role) return <AppShell><div className="card"><h2>Not available for your account</h2><p className="mut">This page is for the {ROLES[role]}. You are signed in as {ROLES[s.role]}.</p><Link className="btn" to={HOME[s.role]}>Go to your dashboard</Link></div></AppShell>;
  return children;
}

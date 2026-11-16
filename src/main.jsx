import { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Routes, Route, Navigate, useParams, useSearchParams } from 'react-router-dom';
import './styles/style.css';
import './styles/app.css';
import AppShell, { RequireRole } from './components/AppShell.jsx';
import { Spinner } from './components/ui.jsx';
import { ensureAccounts } from './lib/auth.js';
import Home from './pages/Home.jsx';
import Login from './pages/Login.jsx';
import Signup from './pages/Signup.jsx';
import Search from './pages/Search.jsx';
import Plot from './pages/Plot.jsx';
import Trends from './pages/Trends.jsx';
import Dashboard from './pages/Dashboard.jsx';
import { ShDashboard, ShStatus, ShRecords } from './pages/Society.jsx';
import { AdminDashboard, AdminData, AdminSystem } from './pages/Admin.jsx';
import NotFound from './pages/NotFound.jsx';

// the 3D map (three.js, CesiumJS) is loaded only when its page is opened
const MapPage = lazy(() => import('./pages/MapPage.jsx'));
const MapLoading = () => <AppShell wide><Spinner text="Loading the 3D map…" /></AppShell>;

// old page names (map.html?id=12, plot.html?id=12) still work
function Legacy({ to }) { const [q] = useSearchParams(); const id = q.get('id'); return <Navigate to={to === '/plot' && id ? '/plot/' + id : to + (q.toString() ? '?' + q : '')} replace />; }
function PlotRoute() { const { id } = useParams(); return <Plot key={id || 'none'} />; }

ensureAccounts();
createRoot(document.getElementById('root')).render(
  <HashRouter>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/search" element={<Search />} />
      <Route path="/plot" element={<PlotRoute />} />
      <Route path="/plot/:id" element={<PlotRoute />} />
      <Route path="/trends" element={<Trends />} />
      <Route path="/map" element={<Suspense fallback={<MapLoading />}><MapPage /></Suspense>} />
      <Route path="/dashboard" element={<RequireRole role="user"><Dashboard /></RequireRole>} />
      <Route path="/society" element={<RequireRole role="head"><ShDashboard /></RequireRole>} />
      <Route path="/society/status" element={<RequireRole role="head"><ShStatus /></RequireRole>} />
      <Route path="/society/records" element={<RequireRole role="head"><ShRecords /></RequireRole>} />
      <Route path="/admin" element={<RequireRole role="admin"><AdminDashboard /></RequireRole>} />
      <Route path="/admin/data" element={<RequireRole role="admin"><AdminData /></RequireRole>} />
      <Route path="/admin/system" element={<RequireRole role="admin"><AdminSystem /></RequireRole>} />
      <Route path="/map.html" element={<Legacy to="/map" />} />
      <Route path="/plot.html" element={<Legacy to="/plot" />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  </HashRouter>
);

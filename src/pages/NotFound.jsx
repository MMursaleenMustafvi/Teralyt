import { Link } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import SearchBox from '../components/SearchBox.jsx';
import { useTitle } from '../components/ui.jsx';

export default function NotFound() {
  useTitle('Page not found');
  return (
    <AppShell>
      <h1>Page not found</h1>
      <div className="card"><p>This page does not exist. Search for a plot, or go to the 3D map.</p><SearchBox big />
        <p style={{ marginTop: 14 }}><Link className="btn" to="/map">Open the 3D map</Link> <Link className="btn o" to="/">Home page</Link></p></div>
    </AppShell>
  );
}

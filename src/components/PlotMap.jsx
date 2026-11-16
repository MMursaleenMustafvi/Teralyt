// A small drawn map of one plot: its outline, the neighbouring plots (houses darker), nearby streets and facilities.
// Local metres around the plot (equirectangular, fine within a society).
const KX = 111320 * Math.cos(31.525 * Math.PI / 180), KY = 111320;
const ROADW = { main: 11, service: 7.5, divider: 9, divider_half: 9, road110: 9, road85: 8, collector: 6.5, residential: 5, roundabout: 12, arterial: 10, highway: 12 };

export default function PlotMap({ plot, outlines, roads, landmarks, byId, statusOf, R = 75 }) {
  const lon0 = plot.lon, lat0 = plot.lat;
  const P = ([lon, lat]) => [(lon - lon0) * KX, -(lat - lat0) * KY];
  const W = 600, H = 420, sc = Math.min(W, H) / (2 * R), T = ([x, y]) => [W / 2 + x * sc, H / 2 + y * sc];
  const pts = ring => ring.map(c => T(P(c)).map(v => v.toFixed(1)).join(',')).join(' ');
  const near = c => { const [x, y] = P(c); return Math.abs(x) < R * 1.6 && Math.abs(y) < R * 1.2; };
  const mine = outlines && outlines[plot.id];
  const others = outlines ? Object.entries(outlines).filter(([id, r]) => +id !== plot.id && r.length && near(r[0])) : [];
  const lines = (roads ? roads.features : []).filter(f => f.geometry.type === 'LineString' && f.geometry.coordinates.some(near));
  const lms = (landmarks || []).filter(l => near([l.lon, l.lat]));
  return (
    <svg className="plotmap" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={'Map of plot ' + plot.no + ' and its neighbours'}>
      <rect width={W} height={H} fill="#2a2418" />
      {lines.map((f, i) => <polyline key={'r' + i} points={f.geometry.coordinates.map(c => T(P(c)).join(',')).join(' ')} fill="none" stroke="#4a4842" strokeWidth={(ROADW[f.properties.class] || 5) * sc} strokeLinecap="round" strokeLinejoin="round" />)}
      {others.map(([id, r]) => { const q = byId && byId.get(+id), st = q && statusOf ? statusOf(q) : ''; return <polygon key={id} points={pts(r)} fill={q && q.built ? '#8c7c66' : '#5f5440'} stroke="#2a2418" strokeWidth="1.2"><title>{q ? `${q.no} · ${q.size} · ${q.built ? 'built' : 'vacant'} · ${st}` : ''}</title></polygon>; })}
      {mine && <polygon points={pts(mine)} fill="rgba(123,208,139,.55)" stroke="#9ff0b0" strokeWidth="3" />}
      {lms.map(l => { const [x, y] = T(P([l.lon, l.lat])); return <g key={'l' + l.id}><circle cx={x} cy={y} r="6" fill="#3f8f3f" stroke="#e9f5e0" strokeWidth="2" /><text x={x + 9} y={y + 4} fontSize="12" fill="#e9f5e0">{l.name.length > 28 ? l.name.slice(0, 27) + '…' : l.name}</text></g>; })}
      {mine && (() => { const [x, y] = T(P([plot.lon, plot.lat])); return <text x={x} y={y + 5} fontSize="15" fontWeight="800" textAnchor="middle" fill="#0f2414">{plot.no.replace(/\s*\(.*\)/, '')}</text>; })()}
      <g transform={`translate(${W - 92},${H - 26})`}><rect width="70" height="5" fill="#e3cfa5" /><text x="35" y="-5" fontSize="11" textAnchor="middle" fill="#e3cfa5">{Math.round(70 / sc)} m</text></g>
      <g transform={`translate(${W - 30},34)`}><path d="M0 -18 L7 4 L0 0 L-7 4 Z" fill="#e3cfa5" /><text y="18" fontSize="11" textAnchor="middle" fill="#e3cfa5">N</text></g>
    </svg>
  );
}

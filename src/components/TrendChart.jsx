// Observed series (2019 to 2025) and a 5-year projection with a widening uncertainty band.
// Until the development model is connected the series are SAMPLE values; pages say so next to the chart.
export const INDICATORS = [
  { key: 'built', label: 'Built-up %', fmt: v => Math.round(v) + '%' },
  { key: 'ndvi', label: 'NDVI (vegetation)', fmt: v => v.toFixed(2) },
  { key: 'ndbi', label: 'NDBI (built-up index)', fmt: v => v.toFixed(2) }
];
export const SAMPLE = { built: [18, 24, 31, 38, 44, 51, 57], ndvi: [.52, .47, .41, .36, .31, .28, .25], ndbi: [.05, .1, .16, .2, .26, .3, .33] };

export function project(h) {
  const sl = (h[h.length - 1] - h[0]) / (h.length - 1), last = h[h.length - 1];
  const f = [1, 2, 3, 4, 5].map(i => last + sl * i * .8);
  const mn = Math.min(...h, ...f) * .8, mx = Math.max(...h, ...f) * 1.15, sp = Math.abs(mx - mn) * .03;
  return { f, mn, mx, sp };
}

export default function TrendChart({ series, fmt, height = 310, start = 2019 }) {
  const h = series, { f, mn, mx, sp } = project(h), n = h.length;
  const X = i => 50 + i * (600 / (n + 4)), Y = v => 260 - (v - mn) / (mx - mn || 1) * 220;
  const hp = h.map((v, i) => X(i) + ',' + Y(v)).join(' ');
  let up = '', lo = '';
  f.forEach((v, i) => { up += X(n + i) + ',' + Y(v + sp * (i + 1)) + ' '; lo = X(n + i) + ',' + Y(v - sp * (i + 1)) + ' ' + lo; });
  return (
    <svg viewBox={`0 0 700 ${height}`} className="tchart" role="img" aria-label="Observed values and 5-year estimate">
      <defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#6cc27f" stopOpacity=".35" /><stop offset="1" stopColor="#6cc27f" stopOpacity="0" /></linearGradient></defs>
      {[0, 1, 2, 3].map(i => <line key={i} x1="50" x2="650" y1={40 + i * 73} y2={40 + i * 73} stroke="rgba(227,207,165,.1)" />)}
      <polygon className="fa" points={`${hp} ${X(n - 1)},260 ${X(0)},260`} fill="url(#ga)" />
      <polygon className="fb2" points={up + lo} fill="#e0a93a" />
      <polyline className="ln" pathLength="1" fill="none" stroke="#7bd08b" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" points={hp} />
      <polyline className="fd" fill="none" stroke="#e0a93a" strokeWidth="4" strokeDasharray="7 7" points={`${X(n - 1)},${Y(h[n - 1])} ${f.map((v, i) => X(n + i) + ',' + Y(v)).join(' ')}`} />
      {h.map((v, i) => <circle key={i} className="dt" style={{ animationDelay: i * .22 + 's' }} cx={X(i)} cy={Y(v)} r="5" fill="#14240f" stroke="#7bd08b" strokeWidth="2.5"><title>{start + i}: {fmt(v)}</title></circle>)}
      {[...h, ...f].map((v, i) => <text key={i} x={X(i)} y="290" fontSize="12" textAnchor="middle" fill="#b3a283">{start + i}</text>)}
      <line x1={X(n - .5)} x2={X(n - .5)} y1="26" y2="260" stroke="rgba(227,207,165,.3)" strokeDasharray="3 6" />
      <text x={X(n - .3)} y="40" fontSize="12" fill="#e0a93a">Forecast (estimate)</text>
    </svg>
  );
}

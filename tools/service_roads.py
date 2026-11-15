"""Find the service roads beside the main road (202 ft boulevard and main entrance road) that OpenStreetMap does not map.

Which service roads exist comes from Google Maps: its road map (zoom 19) draws a separate "Service Road" band beside each
main carriageway wherever one is built. Where it runs is measured on Google satellite imagery (zoom 19, about 0.25 m):
the band of asphalt beside the main carriageway, beyond the paved strip. Google's road drawing is a few metres off the
photo here, so it only decides where a service road exists and roughly where to look.

Every main carriageway (an OpenStreetMap one-way line, already moved onto the asphalt by align_roads.py) is walked every
4 m. Across it, on the side away from the other carriageway, both images are sampled out to 40 m and averaged over 8 m
along the road. Where Google shows a separate band, the asphalt band nearest to it on the photo gives the centre line and
the width. Offsets are smoothed along the road; pieces shorter than 40 m are dropped, gaps under 30 m (side streets)
are bridged, and stretches where OpenStreetMap already has the service road are left to OpenStreetMap. Where Google
draws the service road running into the main carriageway (the slip roads at the gate), the line follows it in.

Writes tools/source/service_roads.geojson; make_data.py adds these lines as class 'service'. Run after make_data.py
(it reads the road classes from data/roads.geojson), then run make_data.py again.

usage: python -I tools/service_roads.py [--debug DIR]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from shapely.geometry import LineString, Point

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from make_data import xy, ll, WIDTH, shift_line, road_offsets, LON0, LAT0, KX, KY  # noqa: E402
import overlay  # noqa: E402

Z = 19
STEP = 4.0
T = np.arange(-12.0, 40.0 + 1e-6, 0.25)       # across, positive = away from the other carriageway
S = np.arange(-4.0, 4.0 + 1e-6, 1.0)           # along, averaged
_tiles = {}


def sample(base, X, Y):
    lon, lat = LON0 + X / KX, LAT0 + Y / KY
    n = 256 * 2 ** Z
    gx = (lon + 180) / 360 * n
    gy = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n
    tx, ty = (gx // 256).astype(int), (gy // 256).astype(int)
    out = np.zeros(X.shape + (3,), np.int16)
    for key in set(zip(tx.ravel(), ty.ravel())):
        k = (base,) + key
        if k not in _tiles:
            for attempt in range(4):
                try:
                    _tiles[k] = np.asarray(overlay.tile(base, Z, *key)).astype(np.int16)
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 3:
                        raise
        m = (tx == key[0]) & (ty == key[1])
        out[m] = _tiles[k][(gy[m] % 256).astype(int), (gx[m] % 256).astype(int)]
    return out


def asphalt(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    v = rgb.mean(-1)
    return ((mx - mn) < 30) & (v > 90) & (v < 190) & ((rgb[..., 0] - rgb[..., 2]) < 12)   # not trees, grass, brick paving, sand


def gmap_road(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    fill = (b - r >= 12) & (b - r <= 48) & (r > 110) & (r < 215) & (g > r)            # Google's blue-grey road fill
    text = (np.abs(r - g) < 14) & (np.abs(g - b) < 14) & ((r > 238) | (r < 110))       # white labels / grey arrows inside a band
    return fill, text


def runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def station(P, u, n):
    """status ('S' service band, '.' none, 'x' side street, 'm' merging into the main road), offset, width"""
    TT, SS = np.meshgrid(T, S)
    X = P[0] + n[0] * TT + u[0] * SS
    Y = P[1] + n[1] * TT + u[1] * SS
    fill, text = gmap_road(sample("mapnl", X, Y))
    gfrac = fill.mean(0)
    band = (gfrac + 0.6 * (text.mean(0) * (gfrac > 0.2))) > 0.45
    sat = asphalt(sample("sat", X, Y)).mean(0)
    rs = [(T[a], T[b] + 0.25) for a, b in runs(band) if T[b] - T[a] >= 1.5]
    if not rs:
        return ".", np.nan, np.nan, None
    main = min(rs, key=lambda r: 0 if r[0] <= 0 <= r[1] else min(abs(r[0]), abs(r[1])))
    if main[0] > 6 or main[1] < -6:
        return ".", np.nan, np.nan, None
    if main[1] > 30:
        return "x", np.nan, np.nan, None
    after = [r for r in rs if r[0] > main[1] + 0.5 and r[0] < 30]
    gw = main[1] - main[0]
    if after:
        svc = after[0]
        if svc[1] - svc[0] < 2.5:
            return ".", np.nan, np.nan, None
        if svc[1] > 38:
            return "x", np.nan, np.nan, None
        gm = main[1] - 4.25 if gw > 11 else (main[0] + main[1]) / 2     # Google's main carriageway centre
        rel = (svc[0] + svc[1]) / 2 - gm
        status = "S"
    elif 12.5 < gw < 24:
        rel = gw - 8.5                                                # one wide band: the service road runs into the carriageway
        status = "m"
    else:
        return ".", np.nan, np.nan, None
    # the asphalt band on the photo nearest to Google's position
    lo = WIDTH["main"] / 2 + 0.5
    best, bo, bw = -1, None, None
    for w in (5.0, 6.0, 7.0, 8.0):
        for o in np.arange(max(rel - 4.5, lo + w / 2), rel + 4.5 + 1e-6, 0.25):
            inside = (T >= o - w / 2) & (T <= o + w / 2)
            flank = ((T >= o - w / 2 - 2.0) & (T < o - w / 2)) | ((T > o + w / 2) & (T <= o + w / 2 + 2.0))
            if not inside.any():
                continue
            sc = sat[inside].mean() - 0.6 * sat[flank].mean() + 0.02 * w
            if sc > best:
                best, bo, bw = sc, o, w
    if bo is not None and sat[(T >= bo - bw / 2) & (T <= bo + bw / 2)].mean() > 0.5:
        return status, float(bo), float(bw), rel
    return status, float(rel), np.nan, rel


def median_filter(v, k):
    out = v.copy()
    for i in range(len(v)):
        w = v[max(0, i - k):i + k + 1]
        w = w[~np.isnan(w)]
        out[i] = np.median(w) if len(w) >= max(2, k // 2) else np.nan
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", default=None)
    a = ap.parse_args()
    roads = json.load(open(os.path.join(ROOT, "data", "roads.geojson"), encoding="utf-8"))["features"]
    main_ids = sorted({f["properties"]["osm_id"] for f in roads if f["properties"]["class"] == "main" and f["properties"].get("osm_id")})
    osm_svc = [LineString([xy(*c) for c in f["geometry"]["coordinates"]]) for f in roads if f["properties"]["class"] == "service"]
    rings = [LineString([xy(*c) for c in f["geometry"]["coordinates"]]) for f in roads if f["properties"]["class"] == "roundabout"]
    osm = {e["id"]: e for e in json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"] if e.get("tags", {}).get("highway")}
    offs = road_offsets()
    lines = {}
    for wid in main_ids:
        pts = [xy(q["lon"], q["lat"]) for q in osm[wid]["geometry"]]
        if str(wid) in offs:
            pts = shift_line(pts, offs[str(wid)])
        lines[wid] = LineString(pts)
    feats, report = [], []
    for wid, L in lines.items():
        if L.length < 80:
            continue
        others = [m for k, m in lines.items() if k != wid]
        D = np.arange(STEP / 2, L.length - STEP / 2, STEP)
        st, off, wid_m, side = [], [], [], []
        for d in D:
            p = np.array(L.interpolate(d).coords[0])
            q0, q1 = np.array(L.interpolate(max(0, d - 5)).coords[0]), np.array(L.interpolate(min(L.length, d + 5)).coords[0])
            u = (q1 - q0) / (np.hypot(*(q1 - q0)) or 1)
            nl = np.array([-u[1], u[0]])
            near = [(m.distance(Point(p)), m) for m in others]
            dm, m = min(near, key=lambda t: t[0])
            sgn = 0
            if dm < 40:
                q = np.array(m.interpolate(m.project(Point(p))).coords[0])
                sgn = -1 if np.dot(q - p, nl) > 0 else 1
            side.append(sgn)
        maj = 1 if sum(side) >= 0 else -1
        for d, sgn in zip(D, side):
            p = np.array(L.interpolate(d).coords[0])
            q0, q1 = np.array(L.interpolate(max(0, d - 5)).coords[0]), np.array(L.interpolate(min(L.length, d + 5)).coords[0])
            u = (q1 - q0) / (np.hypot(*(q1 - q0)) or 1)
            n = np.array([-u[1], u[0]]) * (sgn or maj)
            s, o, w, _ = station(p, u, n)
            st.append(s); off.append(o); wid_m.append(w)
        st = np.array(st); off = np.array(off, float); wid_m = np.array(wid_m, float)
        code = "".join(st)
        # existence: Google band (or merging), side streets bridged, short pieces dropped
        ex = np.isin(st, ["S", "m"])
        for i in np.where(st == "x")[0]:
            l = next((j for j in range(i - 1, -1, -1) if st[j] != "x"), None)
            r = next((j for j in range(i + 1, len(st)) if st[j] != "x"), None)
            ex[i] = l is not None and r is not None and ex[l] and ex[r]
        gap = int(30 / STEP)
        for a_, b_ in runs(~ex):
            if a_ > 0 and b_ < len(ex) - 1 and b_ - a_ + 1 <= gap:
                ex[a_:b_ + 1] = True
        # leave stretches that OpenStreetMap already maps to OpenStreetMap
        nsign = np.array([(s_ or maj) for s_ in side])
        sm = median_filter(np.where(ex, off, np.nan), 5)
        good = ~np.isnan(sm)
        if good.sum() < 5:
            report.append((wid, round(L.length), code, 0))
            continue
        sm = np.interp(D, D[good], sm[good])
        # a side street or a kink of Google's drawing pulls single stretches sideways: hold each station to within
        # 1.5 m of the 100 m running median (the service road runs parallel to its carriageway)
        lm = median_filter(sm, 12)
        sm = np.where(np.abs(sm - lm) > 1.5, lm, sm)
        sm = np.convolve(np.pad(sm, 3, mode="edge"), np.ones(7) / 7, mode="valid")
        pts = []
        for d, o, sg in zip(D, sm, nsign):
            p = np.array(L.interpolate(d).coords[0])
            q0, q1 = np.array(L.interpolate(max(0, d - 5)).coords[0]), np.array(L.interpolate(min(L.length, d + 5)).coords[0])
            u = (q1 - q0) / (np.hypot(*(q1 - q0)) or 1)
            pts.append(p + np.array([-u[1], u[0]]) * sg * o)
        covered = np.array([min((s_.distance(Point(*q)) for s_ in osm_svc), default=99) < 5.0 for q in pts])
        ex &= ~covered
        for a_, b_ in runs(ex):
            if (b_ - a_ + 1) * STEP < 40:
                continue
            seg = [tuple(pts[i]) for i in range(a_, b_ + 1)]
            slip = []
            for end, idx in ((0, a_), (1, b_)):
                dd = D[idx] if end == 0 else L.length - D[idx]
                pe = np.array(L.coords[0] if end == 0 else L.coords[-1])
                at_ring = any(r_.distance(Point(*pe)) < 3 for r_ in rings)
                if dd < 30 and at_ring:
                    # run on to the roundabout ring when the piece stops just short of the end of the carriageway
                    u = np.array(seg[1]) - np.array(seg[0]) if end == 0 else np.array(seg[-1]) - np.array(seg[-2])
                    u = u / (np.hypot(*u) or 1)
                    ext = np.array(seg[0] if end == 0 else seg[-1]) + (-u if end == 0 else u) * (dd + 4)
                    seg = ([tuple(ext)] + seg) if end == 0 else (seg + [tuple(ext)])
                elif dd < 90 and not at_ring:
                    # near the gate the service road runs into the main carriageway (Google draws the slip road):
                    # bring it in over 30 m, ending just across the carriageway centre line so that the two join
                    o0 = float(sm[idx])
                    taper = []
                    for k in range(1, 7):
                        dk = D[idx] + (k * 5.0 if end == 1 else -k * 5.0)
                        if not 0 <= dk <= L.length:
                            break
                        ok = o0 * (1 - k / 6) - 0.6 * (k / 6)
                        p = np.array(L.interpolate(dk).coords[0])
                        q0, q1 = np.array(L.interpolate(max(0, dk - 5)).coords[0]), np.array(L.interpolate(min(L.length, dk + 5)).coords[0])
                        u = (q1 - q0) / (np.hypot(*(q1 - q0)) or 1)
                        taper.append(tuple(p + np.array([-u[1], u[0]]) * nsign[idx] * ok))
                    seg = (taper[::-1] + seg) if end == 0 else (seg + taper)
                    slip.append("start" if end == 0 else "end")
            line = LineString(seg).simplify(0.25)
            ws = wid_m[a_:b_ + 1]
            ws = ws[~np.isnan(ws)]
            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [list(ll(*c)) for c in line.coords]},
                          "properties": {"beside_osm_way": int(wid), "length_m": round(line.length), "offset_m": round(float(np.median(sm[a_:b_ + 1])), 1),
                                         "width_measured_m": round(float(np.median(ws)), 1) if len(ws) else None,
                                         "slip_road_into_main": slip or None,
                                         "source": "Google Maps (a service road is drawn here); centre line measured on Google satellite imagery (zoom 19)"}})
        report.append((wid, round(L.length), code, int(ex.sum())))
    json.dump({"type": "FeatureCollection", "about": __doc__.strip().split("\n\n")[0], "features": feats},
              open(os.path.join(SRC, "service_roads.geojson"), "w", encoding="utf-8"), indent=0)
    for wid, Ln, code, n in report:
        print(f"  way {wid}: {Ln} m, {n * STEP:.0f} m of new service road")
        print("    " + code)
    print(f"service_roads: {len(feats)} lines, {sum(f['properties']['length_m'] for f in feats)} m; "
          f"S = Google draws a service road, m = it runs into the main road, x = side street, . = none")


if __name__ == "__main__":
    main()

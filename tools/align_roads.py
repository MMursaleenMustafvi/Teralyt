"""Measure where the main roads really run, on Google satellite imagery (zoom 19, about 0.25 m; Esri's photo here is too hazy to tell asphalt from paving), and store a sideways shift
for each OpenStreetMap way so that its carriageway sits on the real asphalt.

OpenStreetMap centre lines are good to a few metres; next to the boulevard that is enough to put a carriageway on the
brick footpath or a service road on the verge. For every way of a main class (boulevard, service roads, 110 / 85 / 60 ft
roads) the imagery is sampled across the road every 20 m; the offset at which a band of the carriageway's measured
width covers the most asphalt (grey, low saturation; not the pink brick paving, soil or grass) is the shift there. The
shifts are smoothed along the way and kept only where they are consistent.

Writes tools/source/road_offsets.json {osm_id: [[distance along the way m, shift to the left m], ...]};
tools/make_data.py applies it when it loads the OpenStreetMap ways. Run after make_data (it reads the road classes
from data/roads.geojson), then run make_data again.

usage: python -I tools/align_roads.py [--debug DIR]
"""
import argparse
import io
import json
import math
import os
import sys
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
CACHE = os.path.join(SRC, "cache", "gsat")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from make_data import xy, ll, WIDTH  # noqa: E402

Z = 19
URL = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
CLASSES = ("main", "service", "road110", "divider_half", "divider", "road85", "collector")
_tiles = {}


def tile(x, y):
    k = (x, y)
    if k in _tiles:
        return _tiles[k]
    p = os.path.join(CACHE, f"{Z}_{x}_{y}.jpg")
    if not os.path.exists(p):
        d = urllib.request.urlopen(urllib.request.Request(URL.format(z=Z, x=x, y=y), headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
        open(p, "wb").write(d)
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.int16)
    if len(_tiles) > 400:
        _tiles.clear()
    _tiles[k] = a
    return a


def gpx(lon, lat):
    n = 256 * 2 ** Z
    return (lon + 180) / 360 * n, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n


def sample(lon, lat):
    """RGB of the imagery at arrays of lon, lat (nearest pixel)"""
    gx, gy = gpx(np.asarray(lon), np.asarray(lat))
    tx, ty = (gx // 256).astype(int), (gy // 256).astype(int)
    out = np.zeros(gx.shape + (3,), np.int16)
    for key in set(zip(tx.ravel(), ty.ravel())):
        m = (tx == key[0]) & (ty == key[1])
        a = tile(*key)
        out[m] = a[(gy[m] % 256).astype(int), (gx[m] % 256).astype(int)]
    return out


def asphalt(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    v = rgb.mean(-1)
    return ((mx - mn) < 26) & (v > 95) & (v < 185) & ((rgb[..., 0] - rgb[..., 2]) < 15)     # (dark: trees, grass; pink: brick)


def paint(rgb):
    """white road paint (lane lines): bright and grey"""
    mx, mn = rgb.max(-1), rgb.min(-1)
    return ((mx - mn) < 32) & (rgb.mean(-1) > 188)


def shifts(line_xy, w, search=5.0, lanes=1):
    """best sideways shift (m, to the left) every 20 m along a local-metre polyline; NaN where unclear.
    lanes=2 (the boulevard's carriageways): once the asphalt band is found, the white dashed line between the two
    lanes, where it shows clearly within 2 m of the band's centre, gives the centre more precisely (the band alone can
    be pulled 1 to 2 m towards a service road or a paved strip beside it)."""
    P = np.array(line_xy, float)
    seg = np.diff(P, axis=0)
    L = np.hypot(*seg.T)
    cum = np.concatenate([[0], np.cumsum(L)])
    total = cum[-1]
    out = []
    ts = np.arange(-(search + w / 2 + 3), search + w / 2 + 3 + 1e-6, 0.25)
    ss = np.arange(-6, 6.01, 1.0)
    for d in np.arange(12, total - 12, 20.0):
        i = min(np.searchsorted(cum, d) - 1, len(L) - 1)
        i = max(i, 0)
        u = seg[i] / (L[i] or 1)
        n = np.array([-u[1], u[0]])
        c = P[i] + u * (d - cum[i])
        T, S = np.meshgrid(ts, ss)
        X = c[0] + n[0] * T + u[0] * S
        Y = c[1] + n[1] * T + u[1] * S
        lon, lat = ll_arr(X, Y)
        rgb = sample(lon, lat)
        a = asphalt(rgb).mean(0)                            # asphalt share across the road
        best, bo = -1, None
        for o in np.arange(-search, search + 1e-6, 0.25):
            inside = (ts >= o - w / 2) & (ts <= o + w / 2)
            flank = ((ts >= o - w / 2 - 2.5) & (ts < o - w / 2)) | ((ts > o + w / 2) & (ts <= o + w / 2 + 2.5))
            sc = a[inside].mean() - 0.7 * a[flank].mean()
            if sc > best:
                best, bo = sc, o
        cover = a[(ts >= bo - w / 2) & (ts <= bo + w / 2)].mean()
        if lanes == 2 and cover > 0.55:
            # paint: clearly brighter than this road's own asphalt, and grey (at 0.25 m a dash is a blurred line)
            v = rgb.mean(-1); asp = asphalt(rgb)
            med = np.median(v[asp]) if asp.any() else 130.0
            pt = ((v > med + 28) & ((rgb.max(-1) - rgb.min(-1)) < 36)).mean(0)   # the 13 m along the road catch a dash
            win = np.where(np.abs(ts - bo) <= 2.0)[0]
            k = win[np.argmax(pt[win])]
            base = np.median(pt[win])
            if pt[k] >= 0.12 and pt[k] > 3 * base + 0.02:
                bo = float(ts[k])
        out.append((d, bo if cover > 0.55 else np.nan, cover))
    return out


def ll_arr(X, Y):
    from make_data import LON0, LAT0, KX, KY
    return LON0 + X / KX, LAT0 + Y / KY


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", default=None)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    cls_of = {}
    for f in json.load(open(os.path.join(ROOT, "data", "roads.geojson"), encoding="utf-8"))["features"]:
        p = f["properties"]
        if p.get("osm_id") and p["class"] in CLASSES:
            cls_of[p["osm_id"]] = p["class"]
    osm = {e["id"]: e for e in json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"] if e.get("tags", {}).get("highway")}
    res = {}
    report = []
    for wid, cls in sorted(cls_of.items()):
        e = osm.get(wid)
        if not e:
            continue
        pts = [xy(q["lon"], q["lat"]) for q in e["geometry"]]
        L = sum(math.dist(p, q) for p, q in zip(pts[:-1], pts[1:]))
        if L < 60:
            continue
        w = WIDTH[cls] if cls != "divider" else 19.0
        st = shifts(pts, w, lanes=2 if cls == "main" else 1)
        d = np.array([s[0] for s in st])
        o = np.array([s[1] for s in st])
        ok = ~np.isnan(o)
        if ok.sum() < 4:
            report.append((wid, cls, round(L), int(ok.sum()), None))
            continue
        # smooth along the way: running median over 7 stations, then fill the gaps by interpolation
        oo = o.copy()
        for i in range(len(o)):
            win = o[max(0, i - 3):i + 4]
            win = win[~np.isnan(win)]
            oo[i] = np.median(win) if len(win) >= 3 else np.nan
        good = ~np.isnan(oo)
        if good.sum() < 4:
            report.append((wid, cls, round(L), int(ok.sum()), None))
            continue
        oo = np.interp(d, d[good], oo[good])
        spread = float(np.median(np.abs(o[ok] - np.interp(d[ok], d, oo))))
        if spread > 1.5:
            report.append((wid, cls, round(L), int(ok.sum()), f"inconsistent ({spread:.1f} m)"))
            continue
        if abs(float(np.median(oo))) >= 4.9:
            report.append((wid, cls, round(L), int(ok.sum()), "at the search limit: not trusted"))
            continue
        res[str(wid)] = [[round(float(x), 1), round(float(y), 2)] for x, y in zip(d, oo)]
        report.append((wid, cls, round(L), int(ok.sum()), round(float(np.median(oo)), 2)))
    json.dump(res, open(os.path.join(SRC, "road_offsets.json"), "w"))
    for r in report:
        print(f"  way {r[0]} {r[1]:13s} {r[2]:5d} m, {r[3]:3d} clear stations: shift {r[4]}")
    moved = [abs(np.median([q[1] for q in v])) for v in res.values()]
    print(f"align_roads: {len(res)} ways shifted (median {np.median(moved):.1f} m, max {max(moved):.1f} m) of {len(report)} measured")


if __name__ == "__main__":
    main()

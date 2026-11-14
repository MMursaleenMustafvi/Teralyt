"""Generate Terralyt map data for FDA City (Faisalabad), block by block.

Sources (all in tools/source/):
  * osm_fda_area.json     OpenStreetMap roads around the society (real, georeferenced centrelines).
  * nala_traced.geojson   the Barani Nala storm drain, traced on Esri World Imagery.
  * plan_features.json    features digitised from the official FDA City plan and block maps
                          (Advice Associates / fdacity.pk). Each map sheet has its own control
                          points; parks, schools, mosques, zones and named roads are given in
                          sheet pixels, with the official area in kanal where the map prints it.
  * sheet_layout.json     plot cells read off the official block maps by tools/trace_plots.py
                          (each sheet registered to the OpenStreetMap streets). Where the print is clear
                          the plots are these official outlines; elsewhere the street block is split
                          into plots of the official size.
  * buildings_fda.geojson building footprints detected on satellite imagery (Google Open Buildings,
                          Microsoft ML Buildings, via Overture Maps): which plots are built today.
  * the overall plan image is downloaded on first run into tools/source/cache/ (git-ignored);
    its colours give the plot size of every street block (blue 20, pink 10, green 5 Marla)
    and decide which land belongs to the society.

Road sizes: right of way from the official maps (202, 110, 85, 60, 40 ft); paved carriageway
widths measured on z19 satellite imagery (0.25 m/px), see WIDTH below.

Rules the output must satisfy (checked by tools/audit.py):
  * no plot overlaps a road, the nalla, a facility or another plot;
  * every plot fronts a road (existing or a planned 40 ft street);
  * no bare land: whatever is not road, plot or facility becomes green open space.

Everything derived from the plan is accuracy="approximate". Built / vacant and the development
class come from the building footprints; plot numbers, status and storeys are SAMPLE values.

usage (from the repo root):  python -I tools/make_data.py [--preview out.png]
needs: pip install shapely numpy pillow   (matplotlib for --preview)
"""
import argparse
import hashlib
import json
import math
import os
import urllib.request
from collections import Counter

import numpy as np
import shapely
from PIL import Image
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source")
OUT = os.path.join(ROOT, "data")

LAT_REF = 31.525
LON0, LAT0 = 73.0875, 31.525          # local metric frame used inside this script
KX = 111320.0 * math.cos(math.radians(LAT_REF))
KY = 111320.0
FT = 0.3048
KANAL = 505.857

SIZES = {"5 Marla": (28 * FT, 50 * FT), "10 Marla": (39 * FT, 70 * FT), "20 Marla": (54 * FT, 100 * FT), "Commercial": (30 * FT, 60 * FT)}

# Paved carriageway widths in metres, measured on Esri World Imagery (z19) in November 2026:
#   202 ft boulevard: service road 7.5 | paved strip 6.5 | carriageway 10.75 | median 5 | carriageway 10.75 | strip | service
#   110 ft road (Block A): two 7.5 m carriageways, centre lines 15 m apart, planted median
#   85 ft road between blocks: 19 to 20 m four-lane with a thin centre median (where OpenStreetMap maps it
#   as two one-way lines, each line is drawn 10 m wide);  85 ft road inside Block A: 10 m paved so far
#   60 ft road: 6.5 m;  40 ft street: 5 m
#   roundabouts: island 60 m across with a 17 m ring road (south-west one: island 46 m, ring 23.5 m)
WIDTH = {"main": 10.75, "service": 7.5, "road110": 7.5, "divider": 19.0, "divider_half": 10.0, "road85": 10.0, "arterial": 9.0, "collector": 6.5,
         "residential": 5.0, "roundabout": 17.0, "highway": 12.0, "planned": 5.0}
# Right of way used when cutting land (dual roads keep their carriageway width here so that the
# median between the two carriageways survives as its own piece; RESERVE adds the outer verge).
ROW = {"main": 10.75, "service": 9.5, "road110": 10.5, "divider": 85 * FT, "divider_half": 16.5, "road85": 85 * FT, "arterial": 14.0,
       "collector": 60 * FT, "residential": 40 * FT, "roundabout": 17.0, "highway": 30.0, "planned": 40 * FT}
RESERVE = {"service": 7.25, "road110": 9.25}      # half-width of the official corridor around these lines
OFFICIAL_FT = {"main": 202, "service": 202, "road110": 110, "divider": 85, "divider_half": 85, "road85": 85, "collector": 60, "residential": 40, "planned": 40}
ROAD_NAME = {"divider_half": "85 ft road", "main": "Main Boulevard (202 ft)", "service": "Main Boulevard service road", "road110": "110 ft road", "divider": "85 ft road",
             "road85": "85 ft road", "collector": "60 ft road", "residential": "40 ft street", "planned": "40 ft street (planned)"}
ROUNDABOUT_ISLAND = {"big": 30.0, "small": 23.0}
FOOTPATH = 0.6
NALA_CH, NALA_BANK = 3.25, 8.25   # channel about 6.5 m wide (measured), earth banks either side
STREET = 40 * FT                  # street reserve in front of plots read from the block maps
# main gate: measured on Esri World Imagery (z19), drawn on the official Block A map across the Main Entrance Road
GATE = {"lonlat": (73.06942, 31.50932), "span": 29.0}
BUILT_SOURCE = "Building footprints detected on satellite imagery (Google Open Buildings 2023, Microsoft ML Buildings)"


def ll(e, n):
    return (round(LON0 + e / KX, 7), round(LAT0 + n / KY, 7))


def xy(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def h01(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if hasattr(g, "geoms"):
        return [p for q in g.geoms for p in polys(q)]
    return []


def lines_of(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    if hasattr(g, "geoms"):
        return [p for q in g.geoms for p in lines_of(q)]
    return []


def largest(g):
    ps = polys(g)
    return max(ps, key=lambda p: p.area) if ps else None


def clean(g):
    return g if g.is_valid else g.buffer(0)


def geom_ll(g):
    t = g.geom_type
    if t == "Polygon":
        return {"type": "Polygon", "coordinates": [[ll(*c) for c in g.exterior.coords]] + [[ll(*c) for c in r.coords] for r in g.interiors]}
    if t == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [geom_ll(p)["coordinates"] for p in g.geoms]}
    if t == "LineString":
        return {"type": "LineString", "coordinates": [ll(*c) for c in g.coords]}
    if t == "Point":
        return {"type": "Point", "coordinates": ll(g.x, g.y)}
    raise ValueError(t)


def feature(g, props):
    return {"type": "Feature", "geometry": geom_ll(g), "properties": props}


def write(out, name, feats, extra=None):
    fc = {"type": "FeatureCollection", "name": name, "crs_note": "EPSG:4326 (WGS84 lon/lat)"}
    if extra:
        fc.update(extra)
    fc["features"] = feats
    path = os.path.join(out, name + ".geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, separators=(",", ":"))
    print(f"  {name}.geojson: {len(feats)} features, {os.path.getsize(path)//1024} KB")


def obb(poly):
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)
    e0, e1 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
    a, b = (cs[0], cs[1]) if e0 >= e1 else (cs[1], cs[2])
    ang = (math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + 90) % 180 - 90
    c = mrr.centroid
    lon, lat = ll(c.x, c.y)
    return {"lon": lon, "lat": lat, "angle": round(ang, 2), "length": round(max(e0, e1), 1), "width": round(min(e0, e1), 1)}


# ---------------------------------------------------------------------------------
# official plan sheets: georeference and colour classification
# ---------------------------------------------------------------------------------
class Plan:
    def __init__(self, feats):
        self.f = feats
        self.tf = {}
        for name, sh in feats["sheets"].items():
            X = np.array([complex(p["px"][0], -p["px"][1]) for p in sh["control_points"]])
            Z = np.array([complex(*xy(*p["lonlat"])) for p in sh["control_points"]])
            sol, *_ = np.linalg.lstsq(np.vstack([X, np.ones_like(X)]).T, Z, rcond=None)
            k, t = sol
            res = [abs(k * X[i] + t - Z[i]) for i in range(len(X))]
            self.tf[name] = (k, t)
            print(f"sheet {name}: {abs(k):.3f} m/px, rotation {math.degrees(np.angle(k)):.2f} deg, {len(X)} control points, residuals {[round(float(r), 1) for r in res]} m")
        self.k, self.t = self.tf["overall"]

    def to_m(self, x, y, sheet="overall"):
        k, t = self.tf[sheet]
        z = k * complex(x, -y) + t
        return (z.real, z.imag)

    def to_px(self, e, n):
        w = (complex(e, n) - self.t) / self.k
        return (w.real, -w.imag)

    def geom(self, item):
        """Polygon of a feature given as rect/px box [x0,y0,x1,y1] or px list of points."""
        sheet = item.get("sheet", "overall")
        v = item.get("rect") or item.get("px")
        if isinstance(v[0], (int, float)):
            x0, y0, x1, y1 = v
            v = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return Polygon([self.to_m(x, y, sheet) for x, y in v])

    def line(self, item):
        return LineString([self.to_m(x, y, item.get("sheet", "overall")) for x, y in item["px"]])

    def rect(self, r):
        x0, y0, x1, y1 = r
        return Polygon([self.to_m(*p) for p in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]])

    def load_image(self):
        cache = os.path.join(SRC, "cache")
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, "fda_plan.jpg")
        if not os.path.exists(path):
            url = self.f["plan_image"]["url"]
            print("downloading official plan:", url)
            req = urllib.request.Request(url, headers={"User-Agent": "Terralyt-FYP/0.1"})
            open(path, "wb").write(urllib.request.urlopen(req, timeout=60).read())
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
        assert a.shape[1] == self.f["plan_image"]["size"][0], "unexpected plan image size"
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mn, mx = a.min(axis=2), a.max(axis=2)
        code = np.full(r.shape, 4, np.uint8)                                   # 4 = other (lines, text, photos)
        code[(mn >= 236)] = 0                                                  # 0 = white background / road
        code[(r > 200) & (b > 170) & (r - g > 22) & (mn < 236)] = 1            # 1 = pink, 10 Marla
        code[(g > r + 6) & (g > b + 6) & (g > 150) & (mn < 236)] = 2           # 2 = green, 5 Marla
        code[(b >= r + 4) & (b >= g - 4) & (mn < 236) & (mn > 150) & (mx - mn < 70)] = 3   # 3 = light blue, 20 Marla
        self.code = code
        self.H, self.W = code.shape

    def sample(self, poly, step=4.0):
        minx, miny, maxx, maxy = poly.bounds
        xs, ys = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
        xs, ys = xs.ravel(), ys.ravel()
        if len(xs):
            inside = shapely.contains_xy(poly, xs, ys)
            xs, ys = xs[inside], ys[inside]
        if len(xs) < 4:
            c = poly.representative_point()
            xs, ys = np.array([c.x]), np.array([c.y])
        w = ((xs + 1j * ys) - self.t) / self.k
        px, py = np.round(w.real).astype(int), np.round(-w.imag).astype(int)
        ok = (px >= 0) & (px < self.W) & (py >= 0) & (py < self.H)
        if not ok.any():
            return {"n": 0, "bg": 1.0, "pink": 0, "green": 0, "blue": 0, "other": 0}
        c = self.code[py[ok], px[ok]]
        cnt = np.bincount(c, minlength=5) / len(c)
        return {"n": int(len(c)), "bg": float(cnt[0]), "pink": float(cnt[1]), "green": float(cnt[2]), "blue": float(cnt[3]), "other": float(cnt[4])}


def load_cells():
    """Plot cells read from the official block maps (tools/trace_plots.py), in local metres."""
    path = os.path.join(SRC, "sheet_layout.json")
    if not os.path.exists(path):
        print("no sheet_layout.json: run tools/trace_plots.py to read the plots off the official block maps")
        return []
    out = []
    for name, sh in json.load(open(path, encoding="utf-8"))["sheets"].items():
        for bi, b in enumerate(sh["blocks"]):
            if len(b["cells"]) < 4:
                continue                      # stray shapes (lettering, logos) never form a street block
            for c in b["cells"]:
                pg = Polygon([xy(*q) for q in c["ring"]])
                if not pg.is_valid:
                    pg = largest(pg.buffer(0))
                if pg is None or pg.area < 60 or pg.area > 1700:
                    continue
                if c.get("rect", 1) < 0.8 and pg.area < 200:
                    continue                  # small odd shapes are pieces of lettering, not plots
                out.append({"poly": pg, "sheet": name, "group": (name, bi), "colour": c.get("colour"), "rect": c.get("rect", 1)})
    return out


class SheetInk:
    """What the official block maps draw where: blank paper, or lines (plots, pictures)."""

    def __init__(self):
        self.sheets = []
        self.streets = []
        self.road = {}
        self.drawn = None
        drawn = []
        path = os.path.join(SRC, "sheet_layout.json")
        if not os.path.exists(path):
            return
        for name, sh in json.load(open(path, encoding="utf-8"))["sheets"].items():
            drawn += [clean(Polygon([xy(*q) for q in ring])) for ring in sh.get("drawn", [])]
            for st in sh.get("streets", []):
                if 8 <= st["width_m"] <= 22 and len(st["line"]) >= 2:
                    ln = LineString([xy(*q) for q in st["line"]])
                    if ln.length >= 8:
                        self.streets.append((ln, st["width_m"], name))
            ink = sh.get("ink")
            f = os.path.join(SRC, ink["file"]) if ink else None
            if not f or not os.path.exists(f):
                continue
            A = np.array(sh["affine"])
            inv = np.linalg.inv(np.vstack([A, [0, 0, 1]]))[:2]
            self.sheets.append((name, inv, np.asarray(Image.open(f)).astype(np.float32) / 255, ink["block"], sh["size"]))
            rf = os.path.join(SRC, sh["road"]) if sh.get("road") else None
            if rf and os.path.exists(rf):
                self.road[name] = (inv, np.asarray(Image.open(rf).convert("L")) > 127)
        self.tree = STRtree([ln for ln, _, _ in self.streets]) if self.streets else None
        if drawn:
            self.drawn = clean(unary_union(drawn).buffer(3.0))      # everything the block maps draw

    def sample(self, poly, step=5.0):
        """(share of the polygon shown on some block map, share of that which carries drawing)."""
        minx, miny, maxx, maxy = poly.bounds
        xs, ys = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
        xs, ys = xs.ravel(), ys.ravel()
        if len(xs):
            ins = shapely.contains_xy(poly, xs, ys)
            xs, ys = xs[ins], ys[ins]
        if len(xs) < 3:
            c = poly.representative_point()
            xs, ys = np.array([c.x]), np.array([c.y])
        seen = np.zeros(len(xs), bool)
        ink = np.zeros(len(xs), np.float32)
        for name, inv, img, blk, (W, H) in self.sheets:
            px = inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]
            py = inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]
            ok = (px >= 12) & (px < W - 12) & (py >= 12) & (py < H - 12)
            if not ok.any():
                continue
            i = np.clip((py[ok] / blk).astype(int), 0, img.shape[0] - 1)
            j = np.clip((px[ok] / blk).astype(int), 0, img.shape[1] - 1)
            # look a little around the point: registration is good to a few metres
            v = img[i, j]
            for di, dj in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                v = np.maximum(v, img[np.clip(i + di, 0, img.shape[0] - 1), np.clip(j + dj, 0, img.shape[1] - 1)])
            seen[ok] = True
            ink[ok] = np.maximum(ink[ok], v)
        return float(seen.mean()), (float((ink[seen] > 0.06).mean()) if seen.any() else 0.0)

    def streets_in(self, region):
        """Street centre lines the block maps show inside a region."""
        if self.tree is None:
            return []
        out = []
        for i in self.tree.query(region):
            ln, w, _ = self.streets[i]
            for part in lines_of(ln.intersection(region)):
                if part.length >= 18:
                    out.append((part, w))
        return out

    def road_share(self, poly, sheet, step=2.0):
        """Share of a polygon that the given block map shows as street space (None if the sheet does not cover it)."""
        if sheet not in self.road:
            return None
        inv, img = self.road[sheet]
        minx, miny, maxx, maxy = poly.bounds
        xs, ys = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
        xs, ys = xs.ravel(), ys.ravel()
        if len(xs):
            ins = shapely.contains_xy(poly, xs, ys)
            xs, ys = xs[ins], ys[ins]
        if len(xs) < 3:
            c = poly.representative_point()
            xs, ys = np.array([c.x]), np.array([c.y])
        px = np.round(inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]).astype(int)
        py = np.round(inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]).astype(int)
        ok = (px >= 0) & (px < img.shape[1]) & (py >= 0) & (py < img.shape[0])
        if ok.sum() < 3:
            return None
        return float(img[py[ok], px[ok]].mean())


class Parts:
    """A large area kept as an indexed list of its polygons, for quick cuts against small shapes."""

    def __init__(self, geoms):
        self.g = [q for g in geoms for q in polys(g)]
        self.tree = STRtree(self.g) if self.g else None

    def near(self, geom):
        if self.tree is None:
            return None
        hit = [self.g[i] for i in self.tree.query(geom)]
        return unary_union(hit) if hit else None

    def length_in(self, line):
        u = self.near(line)
        return line.intersection(u).length if u is not None else 0.0

    def minus(self, geom):
        u = self.near(geom)
        return geom.difference(u) if u is not None else geom


def corridor_lines(left, row, carriage, sheet_ink, block_of, res=1.0):
    """Centre lines of the street corridors between the placed plots.

    left: land that is neither plot, site nor mapped street. row / carriage: the mapped streets (so that a new street
    runs on to meet them). The land is rasterised at 1 m, thinned to its skeleton, and the skeleton is kept where the
    corridor is 6 to 26 m wide (wider land is plot land, not a street). Short dead-end spurs are dropped. A short link between two streets that nothing
    continues is a gap in a row of plots, not a street, unless the block map shows street space there.
    """
    try:
        import cv2
        from skimage.morphology import skeletonize
        import sys
        sys.path.insert(0, HERE)
        from trace_plots import trace_skeleton
    except ImportError as e:
        print("streets between plots not drawn (pip install opencv-python-headless scikit-image scipy):", e)
        return []
    minx, miny, maxx, maxy = left.bounds
    x0, y1 = minx - 20, maxy + 20
    W, H = int((maxx - minx + 40) / res), int((maxy - miny + 40) / res)

    def ras(geom):
        img = np.zeros((H, W), np.uint8)
        for q in sorted(polys(geom), key=lambda q: -q.area):          # big first: a polygon inside a hole is drawn after it
            cv2.fillPoly(img, [np.round((np.array(q.exterior.coords) - (x0, y1)) * (1 / res, -1 / res)).astype(np.int32)], 1)
            for r in q.interiors:
                cv2.fillPoly(img, [np.round((np.array(r.coords) - (x0, y1)) * (1 / res, -1 / res)).astype(np.int32)], 0)
        return img

    L, Rw, C = ras(left), ras(row), ras(carriage)
    M = L | Rw
    dt = cv2.distanceTransform(M, cv2.DIST_L2, 5) * res
    sk = skeletonize(M > 0) & (dt >= 3.0) & (dt <= 13.0) & (C == 0)
    Cd = cv2.dilate(C, np.ones((7, 7), np.uint8))
    edges = []
    for e in trace_skeleton(sk):
        pts = e["pts"]
        if len(pts) < 3:
            continue
        ix = np.clip(np.round(pts).astype(int), 0, [W - 1, H - 1])
        if L[ix[:, 1], ix[:, 0]].mean() < 0.6:
            continue                                        # runs along a mapped street, not through leftover land
        e["len"] = float(np.hypot(*np.diff(pts, axis=0).T).sum()) * res
        e["width"] = 2 * float(np.median(dt[ix[:, 1], ix[:, 0]]))
        e["road"] = [bool(Cd[ix[0, 1], ix[0, 0]]), bool(Cd[ix[-1, 1], ix[-1, 0]])]
        # the block map must show street space here: a strip it fills with plots (too fine to read) is not a street
        band = LineString([(x0 + px * res, y1 - py * res) for px, py in pts]).buffer(max(2.0, e["width"] / 2 - 1.0), cap_style=2)
        sheet = block_of(band.representative_point())
        e["share"] = sheet_ink.road_share(band, sheet) if sheet != "F" else None     # sheet F is too coarse to tell
        if e["share"] is not None and e["share"] < 0.4:
            continue
        edges.append(e)
    dirs = {}
    for i, e in enumerate(edges):
        pts = e["pts"]
        for node, a, b in ((e["a"], pts[0], pts[min(10, len(pts) - 1)]), (e["b"], pts[-1], pts[max(0, len(pts) - 11)])):
            if node:
                v = b - a
                dirs.setdefault(node, []).append((i, v / (np.hypot(*v) or 1)))
    keep = set(range(len(edges)))

    def degrees():
        d = Counter()
        for i in keep:
            for node in (edges[i]["a"], edges[i]["b"]):
                if node:
                    d[node] += 1
        return d

    def free_ends(e, d):
        return sum(1 for node, road in ((e["a"], e["road"][0]), (e["b"], e["road"][1])) if not road and (not node or d[node] <= 1))

    # a short link between two streets that nothing continues is a plot-deep gap in a row, unless the map shows a street
    d = degrees()
    for i in sorted(keep):
        e = edges[i]
        through = any(node and any(j != i and j in keep and float(v @ w) < -0.85 for j, w in dirs[node] for k, v in dirs[node] if k == i)
                      for node in (e["a"], e["b"]))
        if not free_ends(e, d) and not through and not any(e["road"]) and e["len"] <= 34:
            share = e["share"]
            if (share is not None and share < 0.6) or (share is None and e["width"] < 9.5):
                keep.discard(i)                             # (without the map to tell: a corridor under 9.5 m is a plot)
    key = lambda c: (round(c[0], 1), round(c[1], 1))
    lines, at_road = [], set()
    for i in sorted(keep):
        ln = LineString([(x0 + px * res, y1 - py * res) for px, py in edges[i]["pts"]])
        lines.append(ln)
        for c, road in ((ln.coords[0], edges[i]["road"][0]), (ln.coords[-1], edges[i]["road"][1])):
            if road:
                at_road.add(key(c))
    # dead ends shorter than 28 m go (spurs into corners), repeatedly; a street is measured from junction to junction
    for _ in range(6):
        if not lines:
            return []
        lines = lines_of(linemerge(MultiLineString(lines)) if len(lines) > 1 else lines[0])
        ends = Counter(key(c) for ln in lines for c in (ln.coords[0], ln.coords[-1]))
        free = lambda c: ends[key(c)] <= 1 and key(c) not in at_road
        kept = [ln for ln in lines if ln.length >= 28 or not (free(ln.coords[0]) or free(ln.coords[-1]))]
        if len(kept) == len(lines):
            break
        lines = kept
    # a street should lead to the mapped road network
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, ln in enumerate(lines):
        for c in (ln.coords[0], ln.coords[-1]):
            parent[find(("l", i))] = find(key(c))
    linked = {find(key(c)) for ln in lines for c in (ln.coords[0], ln.coords[-1]) if key(c) in at_road}
    total = Counter()
    for i, ln in enumerate(lines):
        total[find(("l", i))] += ln.length
    # (a network of 150 m or more stays even if its link to a mapped road was not found; lone stubs go)
    lines = [ln for i, ln in enumerate(lines) if find(("l", i)) in linked or total[find(("l", i))] >= 150]
    return [ln for ln in (q.simplify(3.0) for q in lines) if ln.length >= 9]     # straight between junctions


def load_buildings():
    path = os.path.join(SRC, "buildings_fda.geojson")
    if not os.path.exists(path):
        return []
    out = []
    for f in json.load(open(path, encoding="utf-8"))["features"]:
        pg = Polygon([xy(*q) for q in f["geometry"]["coordinates"][0]])
        if not pg.is_valid:
            pg = largest(pg.buffer(0))
        if pg is not None and pg.area >= 25:
            out.append((pg, f["properties"]))
    return out


def size_by_area(a):
    return "5 Marla" if a < 175 else "10 Marla" if a < 360 else "20 Marla"


def direction_at(ref, pt):
    s = ref.project(pt)
    a, b = ref.interpolate(max(0, s - 20)), ref.interpolate(min(ref.length, s + 20))
    lr = math.dist((a.x, a.y), (b.x, b.y)) or 1
    return ((b.x - a.x) / lr, (b.y - a.y) / lr)


def parallel_to(line, ref, tol=0.88):
    p0, p1 = line.coords[0], line.coords[-1]
    L = math.dist(p0, p1) or 1
    u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
    v = direction_at(ref, line.interpolate(0.5, normalized=True))
    return abs(u[0] * v[0] + u[1] * v[1]) > tol


# ---------------------------------------------------------------------------------
# plot subdivision: every plot fronts a road
# ---------------------------------------------------------------------------------
def subdivide(region, angle, size, commercial_side=None):
    """Split free land into rows of plots.

    Rows run along `angle` (the long axis of the street block). The block's two long edges
    front existing roads; where the block is deeper than two plots, planned 40 ft streets are
    inserted between pairs of back-to-back rows so that every plot has road frontage.
    commercial_side: None, 'lo' or 'hi' - the edge (low/high y in the rotated frame) that faces
    the main boulevard gets one row of commercial plots.
    Returns (plots [(polygon, size)], streets [polygon], street centre lines).
    """
    w, D = SIZES[size]
    c = region.centroid
    rot = affinity.rotate(region, -angle, origin=c)
    minx, miny, maxx, maxy = rot.bounds
    S = ROW["planned"]
    bands, streets = [], []
    lo, hi = miny, maxy
    Dc = SIZES["Commercial"][1]
    if commercial_side and hi - lo > Dc * 0.8:
        if commercial_side == "lo":
            bands.append((lo, min(hi, lo + Dc), "Commercial"))
            lo = min(hi, lo + Dc)
        else:
            bands.append((max(lo, hi - Dc), hi, "Commercial"))
            hi = max(lo, hi - Dc)
    H = hi - lo
    if H >= 0.55 * D:
        if H <= 1.45 * D:
            bands.append((lo, hi, size))
        else:
            k = max(1, round((H + S) / (2 * D + S)))
            d = (H - (k - 1) * S) / (2 * k)
            if d > 1.38 * D:
                k += 1
            elif d < 0.62 * D and k > 1:
                k -= 1
            d = (H - (k - 1) * S) / (2 * k)
            y = lo
            for i in range(k):
                bands += [(y, y + d, size), (y + d, y + 2 * d, size)]
                y += 2 * d
                if i < k - 1:
                    streets.append(box(minx - 1, y, maxx + 1, y + S))
                    y += S
    plots = []
    for y0, y1, sz in bands:
        bw = SIZES[sz][0]
        strip = rot.intersection(box(minx - 1, y0, maxx + 1, y1))
        for part in polys(strip):
            px0, _, px1, _ = part.bounds
            n = max(1, round((px1 - px0) / bw))
            wi = (px1 - px0) / n
            for i in range(n):
                cell = box(px0 + i * wi, y0, px0 + (i + 1) * wi, y1)
                pg = largest(cell.intersection(part))
                if pg is None or pg.area < 0.55 * bw * SIZES[sz][1] or pg.area < 0.6 * cell.area:
                    continue
                if pg.area / pg.minimum_rotated_rectangle.area < 0.78:
                    continue
                plots.append((affinity.rotate(pg, angle, origin=c), sz))
    st, cl = [], []
    for sb in streets:
        for q in polys(sb.intersection(rot)):
            if q.area > 30:
                st.append(affinity.rotate(q, angle, origin=c))
        y = (sb.bounds[1] + sb.bounds[3]) / 2
        for q in lines_of(LineString([(minx - 1, y), (maxx + 1, y)]).intersection(rot.buffer(FOOTPATH + 1))):
            if q.length > 8:
                cl.append(affinity.rotate(q, angle, origin=c))
    return plots, st, cl


# ---------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", default=None)
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)

    feats = json.load(open(os.path.join(SRC, "plan_features.json"), encoding="utf-8"))
    plan = Plan(feats)
    plan.load_image()
    env = Polygon([plan.to_m(*p) for p in feats["envelope"]]).buffer(0)
    bl = feats["blocks"]

    # ---- block rule (overall plan pixels) ---------------------------------------------
    def curve_y(x):
        best = None
        for (x0, y0), (x1, y1) in zip(bl["curve"][:-1], bl["curve"][1:]):
            lo, hi = min(x0, x1), max(x0, x1)
            if lo <= x <= hi and hi > lo:
                y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
                best = y if best is None else min(best, y)
        return best if best is not None else bl["boulevard_y"]

    def block_px(x, y):
        d1, d2 = bl["divider_x"]
        if x < d1:
            if bl["f_column"][0] <= x and y > curve_y(x) + 6:
                return "F"
            if y > bl["f_line_y"]:
                return "F"
            return "A"
        if x < d2:
            return "B" if y < bl["boulevard_y"] else "E"
        return "C" if y < bl["boulevard_y"] else "D"

    def block_m(pt):
        return block_px(*plan.to_px(pt.x, pt.y))

    def beyond_f_strip(pt):
        x, y = plan.to_px(pt.x, pt.y)
        return x < bl["f_column"][0] and y > bl.get("f_strip_max_y", 9999)

    # ---- roads ------------------------------------------------------------------------
    osm = json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"]
    work = env.buffer(900)
    near_env = env.buffer(60)
    dividers = [LineString([plan.to_m(x, 0), plan.to_m(x, 1150)]) for x in bl["divider_x"]]
    boulevard = [plan.line(r) for r in feats.get("road_lines", []) if r["class"] == "main"]
    roads = []
    for e in osm:
        t = e["tags"]
        hw = t.get("highway")
        if not hw:
            continue
        line = LineString([xy(p["lon"], p["lat"]) for p in e["geometry"]])
        if line.length < 1 or not line.intersects(work):
            continue
        if t.get("junction") in ("roundabout", "circular"):
            cls = "roundabout"
        elif hw in ("motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"):
            cls = "highway"
        elif hw in ("tertiary", "tertiary_link"):
            cls = "arterial"
        elif t.get("oneway") == "yes" and line.length > 150 and line.intersects(near_env):
            c = line.interpolate(0.5, normalized=True)
            if any(dv.distance(c) < 18 and parallel_to(line, dv, 0.95) for dv in dividers):
                cls = "divider_half"          # 85 ft road mapped as two one-way lines
            elif any(ln.distance(c) < 60 and parallel_to(line, ln, 0.8) for ln in boulevard):
                cls = "main"                  # dual carriageway of the boulevard / main entrance road
            else:
                cls = "residential"
        else:
            cls = "residential"
        roads.append({"id": e["id"], "name": t.get("name"), "oneway": t.get("oneway") == "yes", "line": line, "cls": cls})
    main_lines = [d["line"] for d in roads if d["cls"] == "main"]
    main_u = unary_union(main_lines)
    named = [(r["class"], plan.line(r), r) for r in feats.get("road_lines", []) if r["class"] != "main"]
    for d in roads:
        if d["cls"] != "residential":
            continue
        c = d["line"].interpolate(0.5, normalized=True)
        dm = main_u.distance(c)
        hit = next((cls for cls, ln, _ in named if ln.distance(c) < 24 and parallel_to(d["line"], ln)), None)
        if any(dv.distance(c) < 16 and parallel_to(d["line"], dv, 0.95) for dv in dividers):
            d["cls"] = "divider"
        elif hit:
            d["cls"] = hit
        elif 10 < dm < 32 and d["line"].length > 40 and parallel_to(d["line"], min(main_lines, key=lambda m: m.distance(c))):
            d["cls"] = "service"
    for cls, ln, item in named:            # roads on the official map that OpenStreetMap does not have yet
        if item.get("planned_if_missing"):
            have = sum(d["line"].length for d in roads if d["cls"] == cls and ln.distance(d["line"].interpolate(0.5, normalized=True)) < 24)
            if have < 0.5 * ln.length:
                roads.append({"id": None, "name": item.get("name"), "oneway": False, "line": ln, "cls": cls, "planned": True})
    merged = linemerge(MultiLineString([d["line"] for d in roads if d["cls"] == "residential"]))
    coll = [ch for ch in lines_of(merged) if ch.length > 650 and math.dist(ch.coords[0], ch.coords[-1]) / ch.length > 0.93]
    cz = unary_union([ch.buffer(1.0) for ch in coll]) if coll else None
    for d in roads:
        if d["cls"] == "residential" and cz is not None and d["line"].within(cz):
            d["cls"] = "collector"
    print("road classes:", dict(Counter(d["cls"] for d in roads)))

    # ---- nalla ------------------------------------------------------------------------
    g = json.load(open(os.path.join(SRC, "nala_traced.geojson"), encoding="utf-8"))["features"][0]
    nala_full = LineString([xy(*c) for c in g["geometry"]["coordinates"]]).simplify(0.8)
    nala = max(lines_of(nala_full.intersection(env.buffer(200))), key=lambda q: q.length)
    nala_zone = nala.buffer(NALA_BANK)
    print(f"nalla: {nala.length:.0f} m in the plan area")

    # ---- road surfaces ------------------------------------------------------------------
    ring_geo = {}
    for d in roads:
        if d["cls"] == "roundabout":
            pg = Polygon(d["line"].coords) if d["line"].is_ring else d["line"].convex_hull
            c = pg.centroid
            rc = sum(Point(q).distance(c) for q in d["line"].coords) / len(d["line"].coords)
            ri = ROUNDABOUT_ISLAND["big"] if rc > 34 else ROUNDABOUT_ISLAND["small"]
            ring_geo[id(d)] = (c, ri, ri + (17.0 if rc > 34 else 23.5))

    def surface(widths):
        parts = []
        by_cls = {}
        for d in roads:
            if d["cls"] == "roundabout":
                c, ri, ro = ring_geo[id(d)]
                parts.append(c.buffer(ro, 64).difference(c.buffer(ri, 64)))
            else:
                by_cls.setdefault(d["cls"], []).append(d["line"])
        for cls, ls in by_cls.items():
            m = linemerge(MultiLineString(ls)) if len(ls) > 1 else ls[0]
            for l in lines_of(m):      # flat ends: a dead-end street stops square, not with a round blob
                parts.append(l.buffer(widths[cls] / 2, cap_style=2, join_style=2, mitre_limit=2.5))
        u = unary_union(parts)
        return clean(u.buffer(1.0, join_style=2).buffer(-1.0, join_style=2))   # close notches at junctions

    surf = surface(ROW)
    carriage = surface(WIDTH)
    reserve = unary_union([d["line"].buffer(RESERVE[d["cls"]], cap_style=2, join_style=2) for d in roads if d["cls"] in RESERVE])

    # ---- faces of the road network ----------------------------------------------------------
    inner_lines = [d["line"].intersection(env.buffer(30)) for d in roads if d["cls"] != "highway"]
    noded = unary_union([l for l in inner_lines if not l.is_empty] + [LineString(env.exterior.coords), nala])
    faces = [f for f in polygonize(noded) if env.contains(f.representative_point())]
    print(f"faces: {len(faces)}")
    rbs = [{"c": c, "poly": c.buffer(ri + 1, 64), "ri": ri, "ro": ro} for d in roads if d["cls"] == "roundabout"
           for (c, ri, ro) in [ring_geo[id(d)]] if env.buffer(50).contains(c)]
    rb_zone = unary_union([r["poly"].buffer(2) for r in rbs]) if rbs else None
    services = [d["line"] for d in roads if d["cls"] == "service"]
    duals = [d["line"] for d in roads if d["cls"] == "road110"]

    zones = [dict(z, poly=plan.geom(z)) for z in feats["zones"]]
    inside_zones = unary_union([z["poly"] for z in zones if not z.get("outside")])

    cells = load_cells()
    sheet_ink = SheetInk()
    cell_pts = STRtree([c["poly"].representative_point() for c in cells]) if cells else None
    blank = 0
    P = []
    for f in faces:
        land = f.difference(surf).difference(nala_zone)
        for q in polys(land):
            if q.area < 40:
                continue
            mrr = q.minimum_rotated_rectangle
            cs = list(mrr.exterior.coords)
            short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
            touching = sum(1 for m in main_lines if m.distance(q) < WIDTH["main"] / 2 + 3)
            touching_srv = sum(1 for m in services if m.distance(q) < ROW["service"] / 2 + 3)
            touching_dual = sum(1 for m in duals if m.distance(q) < ROW["road110"] / 2 + 3)
            if rb_zone is not None and q.within(rb_zone):
                kind = "island"
            elif (touching >= 2 and short < 45) or (touching_dual >= 2 and short < 14):
                kind = "median"
            elif touching >= 1 and touching_srv >= 1 and short < 20:
                kind = "strip"
            else:
                kind = None
            subs = [q]
            if kind is None:
                subs = []
                for r in polys(q.difference(reserve)):          # official corridor beyond the paved road
                    if r.area < 40:
                        continue
                    ins = [s for s in polys(r.buffer(-FOOTPATH)) if s.area >= 25]
                    if len(ins) <= 1:
                        subs.append(r)
                    else:
                        subs += [s2 for s in ins for s2 in [largest(r.intersection(s.buffer(FOOTPATH + 0.3, join_style=2)))] if s2 is not None and s2.area >= 40]
            for r in subs:
                r = clean(r.simplify(0.2))
                if r.geom_type != "Polygon":
                    r = largest(r)
                    if r is None:
                        continue
                k2 = kind
                cen = r.representative_point()
                inner = largest(r.buffer(-FOOTPATH))
                size = None
                if k2 is None:
                    smp = plan.sample(r)
                    plotted = smp["pink"] + smp["green"] + smp["blue"] + smp["other"]
                    in_zone = (not inside_zones.is_empty) and r.intersection(inside_zones).area > 0.3 * r.area
                    n_cells = len(cell_pts.query(r, predicate="contains")) if cell_pts is not None else 0
                    seen, inked = sheet_ink.sample(r)
                    if n_cells >= 4 and n_cells * 120 > 0.12 * r.area and not beyond_f_strip(cen):
                        pass                                   # the block map fills this land with plots
                    elif (not in_zone and (plotted < 0.42 or smp["bg"] > 0.55)) or beyond_f_strip(cen):
                        k2 = "outside"
                    elif not in_zone and sheet_ink.sheets and seen * inked < 0.15:
                        k2 = "outside"                         # blank on, or beyond, every block map
                        blank += 1
                    if k2 == "outside":
                        pass
                    elif inner is None or inner.buffer(-5.0).is_empty:
                        k2 = "greenbelt"
                    else:
                        k2 = "parcel"
                        cols = {"10 Marla": smp["pink"], "5 Marla": smp["green"], "20 Marla": smp["blue"]}
                        size = max(cols, key=cols.get) if max(cols.values()) > 0.02 else "10 Marla"
                P.append({"land": r, "inner": inner if k2 in ("parcel", "greenbelt") else None, "kind": k2, "c": cen, "blk": block_m(cen),
                          "area": r.area, "size": size, "free": inner if k2 == "parcel" else None,
                          "angle": obb(inner)["angle"] if (k2 == "parcel" and inner is not None) else 0})
    print("land:", dict(Counter(p["kind"] for p in P)), f"| {blank} pieces left out because no block map draws anything there")
    parcels = [p for p in P if p["kind"] == "parcel"]

    # ---- plot cells from the official block maps ------------------------------------------------
    raw_sites = [z["poly"] for z in zones] + [plan.geom(f) for f in feats["facilities"]] + [plan.geom(pk) for pk in feats["parks"]]
    raw_u = unary_union([clean(q).buffer(-1.5) for q in raw_sites])
    with_free = [p for p in parcels if p["free"] is not None]
    ptree = STRtree([p["free"] for p in with_free])
    cand = []
    why = Counter()
    for c in cells:
        cen = c["poly"].representative_point()
        if not env.contains(cen):
            why["outside the plan area"] += 1
            continue
        if raw_u.contains(cen):
            why["inside a facility picture"] += 1
            continue
        best, ba = None, 0
        for i in ptree.query(c["poly"]):
            a = with_free[i]["free"].intersection(c["poly"]).area
            if a > ba:
                best, ba = with_free[i], a
        if best is None or ba < 0.55 * c["poly"].area:
            why["on a road or outside society land"] += 1
            continue
        c["p"] = best
        c["own"] = block_m(cen) == c["sheet"]
        cand.append(c)
    cand.sort(key=lambda c: (not c["own"], -c["rect"]))          # neighbouring sheets repeat the edge plots
    ctree = STRtree([c["poly"] for c in cand])
    taken = [False] * len(cand)
    for i, c in enumerate(cand):
        clash = any(taken[j] and cand[j]["poly"].intersection(c["poly"]).area > 0.2 * min(c["poly"].area, cand[j]["poly"].area)
                    for j in ctree.query(c["poly"]) if j != i)
        if clash:
            why["repeated on a neighbouring sheet"] += 1
            continue
        taken[i] = True
        c["p"].setdefault("cells", []).append(c)
    for p in parcels:
        if p.get("cells"):
            p["cells_u"] = unary_union([c["poly"] for c in p["cells"]])
    print(f"plot cells from the block maps: {len(cells)} read, {sum(taken)} placed; left out: {dict(why)}")

    def avail(p):
        """Land a facility may take: free land that the block maps do not show as plots."""
        return p["free"].difference(p["cells_u"]) if p.get("cells_u") is not None else p["free"]

    # ---- landmarks (carved out of parcels) -------------------------------------------------------
    landmarks = []

    def add_lm(poly, kind, name, blk, item=None, extra=None):
        if poly is None or poly.area < 60:
            return None
        item = item or {}
        props = {"id": len(landmarks) + 1, "kind": kind, "name": name, "block": ("Block " + blk) if blk else None,
                 "area_kanal": round(poly.area / KANAL, 1), "proposed": bool(item.get("proposed")), "obb": obb(poly),
                 "accuracy": "approximate", "source": "Official FDA City plan and block maps"}
        if item.get("kanal"):
            props["kanal_official"] = item["kanal"]
        if item.get("sign"):
            props["sign"] = item["sign"]
        if extra:
            props.update({k: v for k, v in extra.items() if v is not None})
        landmarks.append(feature(clean(poly.simplify(0.2)), props))
        return props

    def carve(poly, whole_frac=0.62, min_area=60, kanal=None):
        cand = None
        if kanal:                            # match the area printed on the official map
            target = kanal * KANAL
            cand = [p for p in parcels if p["free"] is not None and p["free"].intersects(poly) and avail(p).intersection(poly).area > 20]
            av = {id(p): avail(p) for p in cand}
            if cand and sum(av[id(p)].area for p in cand) <= target * 1.08:
                poly = unary_union([av[id(p)] for p in cand]).buffer(1)
            elif cand:
                lo_s, hi_s = 0.4, 3.0
                for _ in range(16):
                    mid = (lo_s + hi_s) / 2
                    sc = affinity.scale(poly, mid, mid, origin=poly.centroid)
                    if sum(av[id(p)].intersection(sc).area for p in cand) < target:
                        lo_s = mid
                    else:
                        hi_s = mid
                poly = affinity.scale(poly, hi_s, hi_s, origin=poly.centroid)
            whole_frac = 0.93
        got = []
        for p in (cand if cand is not None else parcels):
            if p["free"] is None or not p["free"].intersects(poly):
                continue
            pa = avail(p)
            part = pa.intersection(poly)
            if part.area < 20:
                continue
            whole = part.area > whole_frac * pa.area
            got.append((p, pa if whole else part, whole))
        if not got:
            return None
        site = largest(unary_union([g for _, g, _ in got]))
        if site is None or site.area < min_area:
            return None
        for p, g, whole in got:
            if g.intersection(site).area < 0.5 * g.area:
                continue                      # this piece is not part of the site: leave its parcel untouched
            if whole and not p.get("cells"):
                p["free"] = None
            else:
                rest = p["free"].difference(site.buffer(1.0, join_style=2))
                p["free"] = rest if rest.area > 30 else None
        return site

    for z in zones:
        if z.get("outside"):
            add_lm(largest(z["poly"].difference(surf.buffer(3))), z["kind"], z["name"], z.get("block"), z, {"outside": True})
        elif z["kind"] != "homes":
            add_lm(carve(z["poly"], 0.5, 60, z.get("kanal")), z["kind"], z["name"], z.get("block"), z)
    for c in feats["complexes"]:
        x0, y0, x1, y1 = c["px"]
        for part in feats["complex_parts"][c["parts"]]:
            rx0, ry0, rx1, ry1 = part["r"]
            r = (x0 + (x1 - x0) * rx0, y0 + (y1 - y0) * ry0, x0 + (x1 - x0) * rx1, y0 + (y1 - y0) * ry1)
            add_lm(carve(plan.rect(r).buffer(-2.0, join_style=2), 0.7), part["kind"], part["name"].format(b=c["block"]), c["block"])
    homes = next(z for z in zones if z["kind"] == "homes")
    homes_land = carve(homes["poly"], 0.35, 500)
    for f in feats["facilities"]:
        add_lm(carve(plan.geom(f).buffer(2, join_style=2), 0.75, 40), f["kind"], f["name"], f["block"], f)
    for pk in feats["parks"]:
        add_lm(carve(plan.geom(pk), 0.6, 60, pk.get("kanal")), "park", pk["name"], pk["block"], pk)
    if homes_land is not None:
        add_lm(homes_land, "homes", homes["name"], homes.get("block"), homes, {"note": "Reserved for the FDA City Homes housing scheme"})
    designs = ["rings", "tree", "fountain", "rings"]
    rbs.sort(key=lambda r: -r["c"].x)
    for n_, r in enumerate(rbs):
        add_lm(r["c"].buffer(r["ri"], 64), "roundabout", f"Roundabout {n_ + 1}", None, None,
               {"radius": round(r["ri"], 1), "ring_width": round(r["ro"] - r["ri"], 1), "monument": designs[n_ % len(designs)]})
    # main gate across the Main Entrance Road (a point feature: the 3D view builds the gate from heading and span)
    gp = Point(*xy(*GATE["lonlat"]))
    g2 = sorted(main_lines, key=lambda m: m.distance(gp))[:2]
    gl = g2[0]
    ent_pair = None
    if len(g2) == 2 and g2[1].distance(gp) < 30:          # centre the gate between the two carriageways
        ent_pair = (g2[0], g2[1])
        qa, qb = g2[0].interpolate(g2[0].project(gp)), g2[1].interpolate(g2[1].project(gp))
        gp = Point((qa.x + qb.x) / 2, (qa.y + qb.y) / 2)
        GATE["span"] = round(math.dist((qa.x, qa.y), (qb.x, qb.y)) + WIDTH["main"] + 2.5, 1)
    gv = direction_at(gl, gp)
    gate_feat = feature(gp, {"id": 0, "kind": "gate", "name": "FDA City Main Gate", "block": None, "area_kanal": None, "proposed": False,
                             "heading": round(math.degrees(math.atan2(gv[1], gv[0])), 1), "span": GATE["span"], "accuracy": "georeferenced",
                             "source": "Official Block A map (Main Entrance Road); position and span measured on satellite imagery"})
    # the official maps repeat some park names (E-3, E-5, C-4): tell them apart by position
    by_name = {}
    for f in landmarks:
        by_name.setdefault(f["properties"]["name"], []).append(f)
    for name, fs in by_name.items():
        if len(fs) > 1:
            la = [f["properties"]["obb"]["lat"] for f in fs]
            lo = [f["properties"]["obb"]["lon"] for f in fs]
            ns = (max(la) - min(la)) * KY >= (max(lo) - min(lo)) * KX
            order = sorted(fs, key=lambda f: -f["properties"]["obb"]["lat"] if ns else f["properties"]["obb"]["lon"])
            tags = (["north", "south"] if ns else ["west", "east"]) if len(fs) == 2 else [str(i + 1) for i in range(len(fs))]
            for f, tg in zip(order, tags):
                f["properties"]["name"] = f"{name} ({tg})"
    print("landmarks:", dict(Counter(f["properties"]["kind"] for f in landmarks)))

    # ---- society outline ------------------------------------------------------------------------
    society = [p["land"] for p in P if p["kind"] in ("parcel", "greenbelt", "median", "island", "strip")]
    # facility sites belong to the society too (the narrow south-west tip of Block F holds Mosque F-1 and Park F-1)
    society += [Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]]) for f in landmarks if not f["properties"].get("outside")]
    blob = unary_union([q.buffer(24, join_style=2) for q in society]).buffer(-21, join_style=2)
    main_part = largest(blob)
    near_parts = [q for q in polys(blob) if q is not main_part and q.area > 1500 and q.distance(main_part) < 160]
    if near_parts:                       # bridge detached tips along the shortest connection
        from shapely.ops import nearest_points
        links = [LineString(nearest_points(main_part, q)).buffer(14) for q in near_parts]
        main_part = largest(unary_union([main_part] + near_parts + links))
    outline = Polygon(main_part.exterior).simplify(1.5)
    cen = outline.centroid
    axis_a, axis_b = plan.to_m(945, 487), plan.to_m(1220, 487)
    axis_deg = math.degrees(math.atan2(axis_b[1] - axis_a[1], axis_b[0] - axis_a[0]))
    bprops = {"name": "FDA City", "city": "Faisalabad", "source": "Official FDA City plan, georeferenced; streets from OpenStreetMap",
              "accuracy": "approximate", "area_km2": round(outline.area / 1e6, 2), "centre_lon": ll(cen.x, cen.y)[0],
              "centre_lat": ll(cen.x, cen.y)[1], "lat_ref": LAT_REF, "axis_deg": round(axis_deg, 2), "sidewalk_m": FOOTPATH,
              "blocks": {b: list(ll(*plan.to_m(*p))) for b, p in bl["label_px"].items()}}
    print(f"society outline: {outline.area/1e6:.2f} km2")

    # ---- plots ---------------------------------------------------------------------------------
    # 1. official outlines: the plot cells read from the block maps, kept where they lie on free society land
    # 2. elsewhere: the street block is split into plots of the official size (planned 40 ft streets where needed)
    plot_geo, planned_streets, planned_lines, greens = [], [], [], []     # plot_geo: (polygon, size, layout)
    todo, unplotted = [], []
    cell_blocks = []
    lost = 0
    for p in sorted(parcels, key=lambda p: (p["blk"], -round(p["c"].y / 40), p["c"].x)):
        if p["free"] is None or not outline.buffer(3).contains(p["land"]):
            continue
        free = p["free"]
        acc = []
        for c in p.get("cells", []):
            g = largest(c["poly"].intersection(free))
            if g is None or g.area < 0.55 * c["poly"].area:
                lost += 1
                continue
            acc.append([clean(g), c])
        if acc:
            # neighbours must not overlap: a later cell gives way
            tr = STRtree([g for g, _ in acc])
            for i, (g, c) in enumerate(acc):
                for j in tr.query(g):
                    if j < i and acc[j][0] is not None and g is not None and g.intersection(acc[j][0]).area > 0.02:
                        g = largest(g.difference(acc[j][0].buffer(0.02)))
                if g is not None and len(g.exterior.coords) > 7:
                    g = largest(clean(g.simplify(0.6)))            # slivers cut by a neighbour leave a ragged edge
                acc[i][0] = g if (g is not None and g.area >= 0.5 * c["poly"].area) else None
            acc = [(g, c) for g, c in acc if g is not None]
        blocks_u = None
        if acc:
            blocks_u = clean(unary_union([g.buffer(1.0, join_style=2) for g, _ in acc]).buffer(-1.0, join_style=2))
            keep = [q for q in polys(blocks_u) if sum(1 for g, _ in acc if q.contains(g.representative_point())) >= 4]
            blocks_u = unary_union(keep) if keep else None
            acc = [(g, c) for g, c in acc if blocks_u is not None and blocks_u.contains(g.representative_point())]
        if acc:
            for g, c in acc:
                near_main = main_u.distance(g) < 45
                sz = "Commercial" if (c["colour"] == "Commercial" and near_main and g.area < 330) else size_by_area(g.area)
                plot_geo.append((g, sz, "official"))
            # plots the print did not let us read: holes and notches of a block that have the size of a plot
            closed = clean(blocks_u.buffer(5.0, join_style=2).buffer(-5.0, join_style=2)).intersection(free)
            for h in polys(closed.difference(blocks_u.buffer(0.05))):
                if 70 <= h.area <= 800 and h.area / h.minimum_rotated_rectangle.area > 0.8 and not h.buffer(-2.5).is_empty:
                    plot_geo.append((clean(h.buffer(-0.05)), size_by_area(h.area), "official"))
                    blocks_u = blocks_u.union(h)
            cell_blocks.append(blocks_u)
            rest = free.difference(blocks_u.buffer(STREET + 0.4, join_style=2))
        else:
            rest = free
        todo_regions = []
        for region in polys(rest):
            if region.area < 100:
                if not acc:
                    greens.append(region)
                continue
            if acc and (region.area < 500 or region.buffer(-6.5).is_empty):
                greens.append(region)                       # a strip too thin for plots
                continue
            if sheet_ink.drawn is not None:                 # no plots where every block map is blank
                part = clean(region.intersection(sheet_ink.drawn).buffer(-4.0, join_style=2).buffer(4.0, join_style=2)).intersection(region)
                blank_part = region.difference(part)
                if blank_part.area > 0.1 * region.area:
                    unplotted.extend(q for q in polys(blank_part) if q.area > 60)
                    for q in polys(part):
                        if q.area >= 500 and not q.buffer(-6.5).is_empty:
                            todo_regions.append(q)
                    continue
            todo_regions.append(region)
        for region in todo_regions:
            # streets the block map shows through this land split it into its street blocks
            sl = sheet_ink.streets_in(region.buffer(-1.0)) if region.area > 1500 else []
            if sl:
                cut = unary_union([ln.buffer(STREET / 2, cap_style=2, join_style=2) for ln, _ in sl])
                pieces = [q for q in polys(region.difference(cut)) if q.area >= 100 and not q.buffer(-3.0).is_empty]
                if len(pieces) >= 2:
                    todo += [(q, p, True) for q in pieces]
                    continue
            todo.append((region, p, bool(acc)))
    def split_region(region, p, own_axis, streets_ok=True):
        """Split a piece of land into plots of the official size (with planned streets where it is deep)."""
        nonlocal planned_streets, planned_lines, plot_geo, greens
        size = p["size"] or "10 Marla"
        angle = obb(region)["angle"] if own_axis else p["angle"]
        side = None
        if main_u.distance(region) < 30:                # one row of commercial plots faces the boulevard
            nearest = min(main_lines, key=lambda m: m.distance(region))
            v = direction_at(nearest, region.centroid)
            a = math.radians(angle)
            if abs(v[0] * math.cos(a) + v[1] * math.sin(a)) > 0.9:
                c = region.centroid
                rot = affinity.rotate(region, -angle, origin=c)
                _, miny, _, maxy = rot.bounds
                lo_pt = affinity.rotate(Point(rot.centroid.x, miny), angle, origin=c)
                hi_pt = affinity.rotate(Point(rot.centroid.x, maxy), angle, origin=c)
                side = "lo" if main_u.distance(lo_pt) < main_u.distance(hi_pt) else "hi"
        plots, streets, lines = subdivide(region, angle, size, side)

        def stubs(sts):                                 # planned streets too short to be a street
            n = 0
            for q in sts:
                cs = list(q.minimum_rotated_rectangle.exterior.coords)
                n += max(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])) < 30
            return n

        if stubs(streets):                              # rows the other way round may need no stub street
            alt = subdivide(region, angle + 90, size, None)
            if stubs(alt[1]) < stubs(streets) and len(alt[0]) >= 0.7 * len(plots):
                plots, streets, lines = alt
        if stubs(streets):                              # still a stub: one row of plots along each long side instead
            keep_s = [q for q in streets if not stubs([q])]
            gone = unary_union([q for q in streets if stubs([q])])
            streets = keep_s
            lines = [l for l in lines if l.distance(gone) > 1.0]
        if streets and not streets_ok:
            return 0                                    # too deep for plots without a new street: leave it open
        planned_streets += streets
        planned_lines += lines
        plot_geo += [(pg, sz, "generated") for pg, sz in plots]
        used = unary_union([pg.buffer(0.05) for pg, _ in plots] + [s.buffer(0.05) for s in streets]) if (plots or streets) else None
        rest2 = region.difference(used) if used is not None else region
        greens += [q for q in polys(rest2) if q.area > 25 and not q.buffer(-0.8).is_empty]
        return len(plots)

    for region, p, own_axis in todo:
        split_region(region, p, own_axis)

    # real plots stand in rows of plots of their own size. A shape read from a block map with no neighbour of similar
    # size is a stray (a piece of lettering, a symbol): dropped, and the land is filled like any other unread land
    if plot_geo:
        tr = STRtree([pg for pg, _, _ in plot_geo])
        stray = set()
        for i, (pg, _, lay) in enumerate(plot_geo):
            if lay != "official":
                continue
            like = [j for j in tr.query(pg.buffer(1.5), predicate="intersects") if j != i and 0.6 <= plot_geo[j][0].area / pg.area <= 1.67]
            if not like:
                stray.add(i)
        plot_geo = [t for i, t in enumerate(plot_geo) if i not in stray]
        print(f"stray shapes dropped: {len(stray)}")

    # ---- streets the block maps show, where OpenStreetMap has none yet ------------------------------
    # Their centre lines are read from the white street corridors of each sheet (tools/trace_plots.py). Each is drawn
    # as a 5 m carriageway in a 40 ft reserve, so the road keeps one width and runs straight whatever the plot edges do.
    site_u = unary_union([Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]]).buffer(0.5) for f in landmarks])
    plot_parts = [pg.buffer(0.15) for pg, _, _ in plot_geo]
    plots_u = clean(unary_union(plot_parts)) if plot_parts else Polygon()
    blocked_u = clean(unary_union([plots_u, site_u, nala_zone]))
    free_u = unary_union([p["free"] for p in parcels if p["free"] is not None and outline.buffer(3).contains(p["land"])])
    planned_car = [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets]
    left0 = clean(free_u.difference(unary_union([plots_u] + [q.buffer(0.05) for q in planned_streets] + [q.buffer(0.05) for q in greens]
                                                + [q.buffer(0.05) for q in unplotted])))
    row_now = clean(unary_union([surf.intersection(outline.buffer(5)), reserve.intersection(outline.buffer(5))] + planned_streets))
    car_now = clean(unary_union([carriage.intersection(outline.buffer(5))] + planned_car))
    # (open land counts too: the corridors between plot groups often lie on land the maps leave white)
    search = clean(unary_union([left0] + [q.buffer(0.1) for q in unplotted])) if unplotted else left0
    lines_new = corridor_lines(search, row_now, car_now, sheet_ink, block_m)
    new_reserve = new_carriage = None
    half = WIDTH["residential"] / 2
    if lines_new:
        lu = unary_union(lines_new)
        new_carriage = clean(lu.buffer(half, join_style=1, cap_style=1).difference(blocked_u.buffer(0.4)).intersection(outline))
        new_carriage = clean(unary_union([q for q in polys(new_carriage) if q.area > 40]))
        new_reserve = clean(lu.buffer(STREET / 2, join_style=1, cap_style=1).difference(blocked_u).intersection(outline))
        print(f"streets between the plots, not in OpenStreetMap yet: {sum(l.length for l in lines_new) / 1000:.1f} km in {len(lines_new)} pieces")
    sheet_lines = lines_new
    if new_reserve is not None and unplotted:                 # a street through open land is cut out of it
        rp = Parts([new_reserve])
        unplotted = [q for u in unplotted for q in polys(clean(rp.minus(u))) if q.area > 60]

    # ---- land left over between plots, sites and streets ---------------------------------------------
    # a plot-sized gap in a row is a plot whose print could not be read; wide leftovers the block map draws on are
    # split into plots, other wide leftovers become green space; everything else is street reserve (verge)
    left = clean(left0.difference(new_reserve)) if new_reserve is not None else left0
    verge_extra, n_gap, n_split = [], 0, 0
    late_bands, late_lines = [], []
    for q in polys(left):
        if q.area < 8:
            continue
        taken = []
        fat = clean(q.buffer(-3.0, join_style=2).buffer(3.0, join_style=2)).intersection(q)
        for f in polys(fat):
            if f.area < 60:
                continue
            f = clean(f.simplify(0.4))
            if f.geom_type != "Polygon":
                continue
            sheet_f = block_m(f.representative_point())
            share = sheet_ink.road_share(f, sheet_f) if sheet_f != "F" else 0.0     # sheet F is too coarse to tell
            mrr = f.minimum_rotated_rectangle
            cs = list(mrr.exterior.coords)
            short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
            if 70 <= f.area <= 900 and f.area / mrr.area > 0.62 and short >= 6.0 and share is not None and share < 0.45:
                plot_geo.append((clean(f.buffer(-0.05)), size_by_area(f.area), "generated"))
                taken.append(f.buffer(0.06))
                n_gap += 1
            elif f.area > 900 and (share is None or share < 0.75):
                # wide leftover: plots where the block map draws them but the print could not be read, else open space
                seen, inked = sheet_ink.sample(f)
                hit = [with_free[i] for i in ptree.query(f.representative_point())] if inked >= 0.3 else []
                hit = [w for w in hit if w["land"].contains(f.representative_point())]
                core = largest(f.buffer(-0.4, join_style=2)) if hit else None
                made = 0
                if core is not None and not core.buffer(-5.5).is_empty:
                    pieces = [core]
                    # the streets the block map shows through this land divide it into its street blocks
                    sl = sheet_ink.streets_in(core.buffer(-1.0)) if core.area > 1500 else []
                    if sl:
                        cut = unary_union([ln.buffer(STREET / 2, cap_style=2, join_style=2) for ln, _ in sl])
                        pc = [r for r in polys(core.difference(cut)) if r.area >= 100 and not r.buffer(-3.0).is_empty]
                        if len(pc) >= 2:
                            pieces = pc
                            band = clean(core.intersection(cut))
                            late_bands.append(band)
                            late_lines += [part for ln, _ in sl for part in lines_of(ln.intersection(band)) if part.length >= 9]
                    for r in pieces:
                        made += split_region(r, hit[0], True, streets_ok=len(pieces) > 1 or r.area > 4000)
                if made:
                    n_split += 1
                else:
                    (greens if f.area < 4000 else unplotted).append(f)
                taken.append(f.buffer(0.05))
        if taken:
            q = clean(q.difference(unary_union(taken)))
        verge_extra += [r for r in polys(q) if r.area > 4]
    if late_bands:                       # the streets that divided the unread land
        lb = clean(unary_union(late_bands))
        lc = clean(unary_union([ln.buffer(half, cap_style=2, join_style=1) for ln in late_lines]).intersection(lb)) if late_lines else None
        if lc is not None and not lc.is_empty:
            new_carriage = clean(unary_union(([new_carriage] if new_carriage is not None else []) + [lc]))
        verge_extra += [r for r in polys(lb) if r.area > 4]
        sheet_lines = sheet_lines + late_lines
    if verge_extra:
        new_reserve = clean(unary_union(([new_reserve] if new_reserve is not None else []) + verge_extra))
    print(f"leftover land: {n_gap} plot-sized gaps in rows filled with a plot, {n_split} wider pieces split into plots, {sum(r.area for r in verge_extra) / 1e4:.1f} ha became street reserve")
    # every plot must front a road
    access = unary_union([surf, reserve] + planned_streets + ([new_reserve] if new_reserve is not None else [])).buffer(FOOTPATH + 2.2)
    kept = [(pg, sz, lay) for pg, sz, lay in plot_geo if lay == "official" or pg.intersects(access)]
    greens += [pg for pg, sz, lay in plot_geo if lay != "official" and not pg.intersects(access)]
    tr = STRtree([pg for pg, _, _ in kept])
    fixed = []
    for i, (pg, sz, lay) in enumerate(kept):
        for j in tr.query(pg):
            if j < i and fixed[j] is not None and pg is not None and pg.intersection(fixed[j][0]).area > 0.3:
                pg = largest(clean(pg.difference(fixed[j][0].buffer(0.03))))
        fixed.append((pg, sz, lay) if (pg is not None and pg.area >= 55) else None)
    kept = [t for t in fixed if t is not None]
    n_off = sum(1 for _, _, lay in kept if lay == "official")
    print(f"plots: {len(kept)} ({n_off} official outlines from the block maps, {len(kept) - n_off} generated in street blocks the print does not resolve); "
          f"{len(plot_geo) - len(kept)} without road frontage turned into green space; {lost} cells cut by a road dropped; planned 40 ft street pieces: {len(planned_streets)}")

    # ---- buildings standing today (footprints detected on satellite imagery) -------------------------
    bld = [(g, pr) for g, pr in load_buildings() if outline.contains(g.representative_point())]
    kept.sort(key=lambda t: (block_m(t[0].centroid), -round(t[0].centroid.y / 40), t[0].centroid.x))
    ktree = STRtree([pg for pg, _, _ in kept])
    built_on = {}
    bfeats = []
    road_all = unary_union([carriage] + ([new_carriage] if new_carriage is not None else [])
                           + [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets])
    n_road = 0
    btaken = []
    for g, pr in sorted(bld, key=lambda t: -t[0].area):
        if any(g.intersection(o).area > 0.5 * g.area for o in btaken if o.intersects(g)):
            continue                                        # the same building in both datasets
        if g.intersection(road_all).area > 0.35 * g.area:
            n_road += 1                                     # on a mapped road: stale footprint, or the street is drawn a little off
            continue
        if site_u.contains(g.representative_point()):
            continue                                        # inside a facility site: drawn by that site's own model
        best, ba = None, 0
        for i in ktree.query(g):
            a = kept[i][0].intersection(g).area
            if a > ba:
                best, ba = i, a
        on = int(best) if (best is not None and ba >= max(20.0, 0.1 * kept[best][0].area)) else None
        btaken.append(g)
        mrr = obb(g)
        storeys = 1 if g.area < 70 else 2 if g.area < 420 else 3
        if on is not None:
            built_on.setdefault(on, []).append(len(bfeats))
        bfeats.append((g, {"id": len(bfeats) + 1, "plot_index": on, "area_m2": round(g.area), "storeys": storeys, "height": round(3.5 * storeys, 1), "height_source": "assumed",
                           "obb": mrr, "dataset": pr.get("dataset"), "source": BUILT_SOURCE, "accuracy": "georeferenced"}))
    print(f"buildings standing today: {len(bfeats)} footprints, on {len(built_on)} plots; {n_road} footprints left out because they lie on a mapped road")
    # development around each plot: share of built plots within 150 m
    cen = np.array([[pg.centroid.x, pg.centroid.y] for pg, _, _ in kept]) if kept else np.zeros((0, 2))
    is_built = np.array([i in built_on for i in range(len(kept))])
    share = np.zeros(len(kept))
    if len(kept):
        gx, gy = np.floor(cen[:, 0] / 150).astype(int), np.floor(cen[:, 1] / 150).astype(int)
        buckets = {}
        for i, key in enumerate(zip(gx, gy)):
            buckets.setdefault(key, []).append(i)
        for i in range(len(kept)):
            idx = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in buckets.get((gx[i] + dx, gy[i] + dy), [])]
            d = np.hypot(cen[idx, 0] - cen[i, 0], cen[idx, 1] - cen[i, 1]) < 150
            share[i] = is_built[np.array(idx)[d]].mean()

    plot_feats = []
    counters = Counter()
    for i, (pg, sz, lay) in enumerate(kept):
        pid = i + 1
        pg = clean(pg.simplify(0.05))
        blk = block_m(pg.centroid)
        counters[blk] += 1
        key = (blk, counters[blk])
        ptype = "Commercial" if sz == "Commercial" else "Residential"
        cx, cy = pg.centroid.x, pg.centroid.y
        built = bool(is_built[i])
        dev_class = "High" if share[i] >= 0.30 else "Medium" if share[i] >= 0.08 else "Low"
        r = h01("status", *key)
        status = "Sold" if (built or r < 0.42) else "Available" if r < 0.72 else "Reserved" if r < 0.85 else "Unknown"
        if built:
            storeys = max(bfeats[b][1]["storeys"] for b in built_on[i])
            height = 3.5 * storeys
        else:
            storeys, height = 0, 0.4
        lon, lat = ll(cx, cy)
        plot_feats.append(feature(pg, {
            "id": pid, "plot_no": f"{blk}-{counters[blk]}", "block": "Block " + blk,
            "size": sz, "type": ptype, "status": status, "dev_class": dev_class,
            "built": built, "storeys": storeys, "height": round(height, 1), "height_source": "assumed",
            "built_source": BUILT_SOURCE, "built_share_150m": round(float(share[i]), 2),
            "source": "Sample value (no society record yet)", "confidence": "Low", "lat": lat, "lon": lon,
            "area_m2": round(pg.area), "layout": "Official block map" if lay == "official" else "Generated in the street block",
            "accuracy": "georeferenced" if lay == "official" else "approximate"}))
    for g, pr in bfeats:
        if pr["plot_index"] is not None:
            pr["plot_id"] = pr["plot_index"] + 1
            pr["plot_no"] = plot_feats[pr["plot_index"]]["properties"]["plot_no"]
        del pr["plot_index"]
    print(f"plots per block: {dict(sorted(counters.items()))}")
    print("sizes:", dict(Counter(f["properties"]["size"] for f in plot_feats)))
    print("built plots per block:", dict(sorted(Counter(f["properties"]["block"][-1] for f in plot_feats if f["properties"]["built"]).items())),
          "| development class:", dict(Counter(f["properties"]["dev_class"] for f in plot_feats)))

    # ---- water ------------------------------------------------------------------------------
    water = []
    nprops = {"name": "Barani Nala (storm drain)", "source": "Traced from Esri World Imagery and the official plan", "accuracy": "approximate"}
    cut = carriage.buffer(0.6)
    channel = nala.buffer(NALA_CH, cap_style=2)
    wall = nala.buffer(NALA_CH + 0.45, cap_style=2).difference(nala.buffer(NALA_CH - 0.05, cap_style=2))
    bank = nala.buffer(NALA_BANK, cap_style=2).difference(nala.buffer(NALA_CH + 0.45, cap_style=2)).difference(carriage)
    for kind, geom, amin, tol in (("nala_water", channel.difference(cut), 5, 0.15), ("nala_wall", wall.difference(cut), 1, 0.1), ("nala_bank", bank, 5, 0.2)):
        for q in polys(clean(geom)):
            for r in polys(clean(q.simplify(tol))):
                if r.area > amin:
                    water.append(feature(r, dict(nprops, kind=kind)))
    water.append(feature(nala, dict(nprops, kind="nala_line", width_m=round(2 * NALA_CH, 1), length_m=round(nala.length))))
    sb = carriage.buffer(2.0)
    for side in (-1, 1):
        for q in lines_of(nala.offset_curve(side * (NALA_CH + 3.0))):
            dd = 6.0
            while dd < q.length:
                pt = q.interpolate(dd)
                if not sb.contains(pt):
                    water.append(feature(pt, {"kind": "nala_tree"}))
                dd += 13.0
    for d in roads:
        x = d["line"].intersection(nala)
        for pt in ([x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]):
            s = d["line"].project(pt)
            a, b = d["line"].interpolate(max(0, s - 3)), d["line"].interpolate(min(d["line"].length, s + 3))
            water.append(feature(pt, {"kind": "bridge", "heading": round(math.degrees(math.atan2(b.y - a.y, b.x - a.x)), 1),
                                      "road_width": round(WIDTH[d["cls"]], 1), "span": round(2 * NALA_CH + 2, 1)}))
    print("water:", dict(Counter(f["properties"]["kind"] for f in water)))

    # ---- write ------------------------------------------------------------------------------------
    print("writing to", out)
    write(out, "boundary", [feature(outline, bprops)])
    road_feats = []
    clip = outline.buffer(60)
    clip_main = outline.buffer(1500)             # the Main Entrance Road runs on to the gate, outside the outline
    for d in roads:
        for part in lines_of(d["line"].intersection(clip_main if d["cls"] == "main" else clip)):
            if part.length < 5:
                continue
            road_feats.append(feature(part, {"osm_id": d["id"], "name": d["name"] or ROAD_NAME.get(d["cls"]), "class": d["cls"],
                                             "width_m": round(WIDTH[d["cls"]], 1), "official_ft": OFFICIAL_FT.get(d["cls"]), "oneway": d["oneway"],
                                             "planned": bool(d.get("planned")), "source": "Official plan" if d.get("planned") else "OpenStreetMap",
                                             "accuracy": "approximate" if d.get("planned") else "georeferenced"}))
    for l in planned_lines:
        if l.length > 8:
            road_feats.append(feature(l, {"osm_id": None, "name": ROAD_NAME["planned"], "class": "residential", "width_m": WIDTH["planned"], "official_ft": 40,
                                          "oneway": False, "planned": True, "source": "Planned street (not in OpenStreetMap yet)", "accuracy": "approximate"}))
    for l in sheet_lines:
        road_feats.append(feature(l, {"osm_id": None, "name": ROAD_NAME["residential"], "class": "residential", "width_m": WIDTH["residential"], "official_ft": 40,
                                      "oneway": False, "planned": False, "source": "Official block map", "accuracy": "approximate"}))
    write(out, "roads", road_feats)
    planned_carriage = [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets]
    box_o = outline.buffer(1.0)
    extra_c = [new_carriage] if new_carriage is not None else []
    extra_r = [new_reserve] if new_reserve is not None else []
    inner_carriage = clean(unary_union([carriage.intersection(box_o)] + [q for q in planned_carriage if not q.is_empty] + extra_c))
    inner_row = clean(unary_union([surf.intersection(box_o), reserve.intersection(box_o)] + planned_streets + extra_r))
    medians = unary_union([p["land"] for p in P if p["kind"] in ("median", "strip", "island")])
    verge = clean(inner_row.difference(inner_carriage.buffer(0.05)).difference(medians.buffer(0.05)).difference(nala.buffer(NALA_CH + 0.5)))
    verge = clean(verge.difference(unary_union([pg.buffer(0.1) for pg, _, _ in kept])))      # a plot wins over the verge beside it
    write(out, "road_surface",
          [feature(clean(q.simplify(0.2)), {"kind": "carriageway", "accuracy": "approximate", "source": "widths measured on satellite imagery"}) for q in polys(inner_carriage) if q.area > 20]
          + [feature(clean(q.simplify(0.2)), {"kind": "verge", "accuracy": "approximate"}) for q in polys(verge) if q.area > 6])
    big = unary_union([d["line"].buffer(WIDTH[d["cls"]] / 2, cap_style=2, join_style=2) for d in roads
                       if d["cls"] in ("highway", "arterial", "main", "service", "divider", "road110", "road85", "collector")])
    near = carriage.intersection(outline.buffer(70))
    outer = clean(unary_union([big.intersection(outline.buffer(1500)), near]).difference(outline.buffer(-0.5)))
    write(out, "outer_roads", [feature(clean(q.simplify(0.3)), {"kind": "road", "accuracy": "approximate"}) for q in polys(outer) if q.area > 30])
    land_feats = []
    # (planned streets too: the plot ground must not cover any street)
    reserve_parts = Parts(([new_reserve] if new_reserve is not None else []) + planned_streets) if (new_reserve is not None or planned_streets) else None
    for p in P:
        if p["kind"] == "outside":
            continue
        use = "plots" if p["kind"] == "parcel" else p["kind"]
        lands, inners = [p["land"]], ([p["inner"]] if p["inner"] is not None else [])
        local = reserve_parts.near(p["land"]) if (reserve_parts is not None and p["kind"] == "parcel") else None
        if local is not None:
            # streets from the block maps run through this piece of land: cut their reserve out of it
            local = clean(local.intersection(p["land"].buffer(2.0)))
            lands = [q for q in polys(clean(p["land"].difference(local))) if q.area > 30]
            inners = [q for q in polys(clean(p["inner"].difference(local.buffer(FOOTPATH)))) if q.area > 25] if p["inner"] is not None else []
        for q in lands:
            land_feats.append(feature(clean(q.simplify(0.2)) if len(lands) > 1 else q, {"layer": "land", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "size": p["size"], "area_m2": round(q.area), "accuracy": "approximate"}))
        for q in inners:
            land_feats.append(feature(clean(q.simplify(0.2)), {"layer": "inner", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "accuracy": "approximate"}))
    for p in P:                      # land enclosed by the society that the plan leaves blank
        if p["kind"] == "outside" and outline.buffer(-2).contains(p["land"]):
            greens.append(p["land"])
    for q in greens:
        for r in polys(clean(q.simplify(0.15))):
            if r.area > 20:
                land_feats.append(feature(r, {"layer": "green", "kind": "green", "use": "open space", "area_m2": round(r.area), "accuracy": "approximate"}))
    # planted median of the Main Entrance Road between the society outline and the gate
    if ent_pair is not None:
        la, lb = ent_pair
        ca, cb = list(la.coords), list(lb.coords)
        if math.dist(ca[-1], cb[0]) > math.dist(ca[-1], cb[-1]):
            cb = cb[::-1]                       # the two one-way lines run in opposite directions
        between = clean(Polygon(ca + cb))
        half = WIDTH["main"] / 2
        med = between.difference(unary_union([l.buffer(half + 0.3, cap_style=2, join_style=2) for l in (la, lb)])).difference(outline.buffer(2))
        for q in polys(clean(med.buffer(-0.3))):
            if q.area > 150 and not q.buffer(-1.0).is_empty:
                land_feats.append(feature(clean(q.simplify(0.2)), {"layer": "land", "kind": "median", "use": "median", "block": None, "size": None, "area_m2": round(q.area), "accuracy": "approximate", "outside": True}))
    for q in unplotted:              # society land that no block map draws anything on
        for r in polys(clean(q.simplify(0.3))):
            if r.area > 60:
                land_feats.append(feature(r, {"layer": "open", "kind": "open", "use": "not plotted on the official block maps", "area_m2": round(r.area), "accuracy": "approximate"}))
    write(out, "blocks", land_feats)
    gate_feat["properties"]["id"] = len(landmarks) + 1
    write(out, "landmarks", landmarks + [gate_feat])
    write(out, "buildings", [feature(clean(g.simplify(0.15)), pr) for g, pr in bfeats],
          {"data_note": "Buildings standing today: footprints detected on satellite imagery (Google Open Buildings, Microsoft ML Buildings, via Overture Maps). Heights are assumed."})
    write(out, "water", water)
    write(out, "parks", [f for f in landmarks if f["geometry"]["type"] == "Polygon" and f["properties"]["kind"] != "roundabout"]
          + [dict(f, properties=dict(f["properties"], kind="nala", name="Barani Nala")) for f in water if f["properties"]["kind"] == "nala_water"])
    write(out, "context", [feature(Point(*plan.to_m(*c["px"])), {"name": c["name"], "kind": "context"}) for c in feats["context_labels"]])
    write(out, "plots", plot_feats, {"data_note": "layout = 'Official block map': outline read from the official FDA City block map and registered to the real streets. "
                                                  "layout = 'Generated in the street block': the print does not resolve single plots there, the street block is split into plots of the official size. "
                                                  "built and dev_class come from building footprints detected on satellite imagery; plot numbers, status and storeys are sample values."})

    if args.preview:
        preview(args.preview, outline, P, landmarks, plot_feats, road_feats, nala, plan, greens, planned_streets)


def preview(path, outline, P, landmarks, plot_feats, road_feats, nala, plan, greens, streets):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(18, 18), dpi=100)
    ax.set_aspect("equal")
    SZ = {"20 Marla": "#9fb8e8", "10 Marla": "#f0a8c8", "5 Marla": "#b8e098", "Commercial": "#f0b060"}
    for p in P:
        col = "#f4f4f4" if p["kind"] == "outside" else "#6fae5f" if p["kind"] in ("median", "island", "greenbelt") else "#c9c9c9" if p["kind"] == "strip" else "#e6e0d0"
        ax.fill(*p["land"].exterior.xy, color=col, ec="none")
    for q in greens:
        ax.fill(*q.exterior.xy, color="#86c878", ec="none")
    for q in streets:
        ax.fill(*q.exterior.xy, color="#999", ec="none")
    for f in plot_feats:
        pg = Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]])
        ax.fill(*pg.exterior.xy, color=SZ[f["properties"]["size"]], ec="#555", lw=0.1)
    KC = {"park": "#3f9f4f", "playground": "#8fd16a", "school": "#d98b5f", "highschool": "#c9703f", "mosque": "#ffffff", "commercial": "#4a86d0", "dispensary": "#ff9090",
          "hospital": "#e05c5c", "sports": "#c7a0e0", "civic": "#c9b48a", "stadium": "#60d0a0", "university": "#e0b0a0", "cinema": "#9050c0",
          "multipurpose": "#8080d0", "grid": "#888", "graveyard": "#8a8a6a", "cng": "#e0e070", "shrine": "#2e8a57", "homes": "#f0e0b0",
          "metro": "#f0e040", "sewerage": "#6a8a9a", "roundabout": "#2f7f2f", "hotel": "#70c0e0", "postoffice": "#d0a0a0", "community": "#e0c080",
          "firestation": "#f06060", "office": "#b0b0d0", "shops": "#80a0e0"}
    for f in landmarks:
        pr = f["properties"]
        pg = Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]])
        ax.fill(*pg.exterior.xy, color=KC.get(pr["kind"], "#f0f"), ec="k", lw=0.5, zorder=4)
        if pr["kind"] != "roundabout":
            ax.annotate(pr["name"].replace(" (", "\n("), (pg.centroid.x, pg.centroid.y), fontsize=5, ha="center", va="center", zorder=6)
    for f in road_feats:
        cs = [xy(*c) for c in f["geometry"]["coordinates"]]
        lw = {"main": 2.2, "service": 1.2, "divider": 2.0, "road110": 1.6, "road85": 1.6, "collector": 1.2, "arterial": 1.6, "highway": 2.6, "roundabout": 1.5}.get(f["properties"]["class"], 0.35)
        ax.plot([c[0] for c in cs], [c[1] for c in cs], color="#b03030" if f["properties"].get("planned") else "#333", lw=lw, zorder=5)
    ax.plot(*nala.xy, color="#1f78d0", lw=2.5, zorder=6)
    ax.plot(*outline.exterior.xy, color="red", lw=1.5, zorder=7)
    for b, p in plan.f["blocks"]["label_px"].items():
        x, y = plan.to_m(*p)
        ax.annotate("BLOCK " + b, (x, y), fontsize=20, weight="bold", ha="center", color="#102030", alpha=0.65, zorder=8)
    fig.savefig(path, bbox_inches="tight")
    print("preview:", path)


if __name__ == "__main__":
    main()

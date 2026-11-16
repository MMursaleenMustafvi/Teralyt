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


EMAP = os.path.join(SRC, "emap_layout.json")
PLOT_COLOURS = ("purple", "green", "yellow", "red", "pink")


class EmapPlan:
    """The whole FDA City plan read from emap.pk by tools/emap_plan.py, registered to the real streets.

    Same questions as SheetInk (what the plan draws where, where its street space is), answered from the plan's
    road and plot-colour masks; positions go through the registration field (real position -> plan pixel)."""

    coarse = set()                      # every part of this plan is sharp enough to tell streets from plots

    def __init__(self):
        L = json.load(open(EMAP, encoding="utf-8"))
        self.L = L
        self.sheets = [True]
        self.streets = []
        self.tree = None
        self.drawn = clean(unary_union([Polygon([xy(*q) for q in pg[0]], [[xy(*q) for q in h] for h in pg[1:]]) for pg in L["drawn"]]))
        self.road = np.asarray(Image.open(os.path.join(SRC, L["road_png"]["file"]))) > 127
        self.plotc = np.asarray(Image.open(os.path.join(SRC, L["plotcol_png"]["file"]))) > 127
        f = L["field"]
        self.gxs, self.gys = np.array(f["gxs"], float), np.array(f["gys"], float)
        self.FX, self.FY = np.array(f["FX"]), np.array(f["FY"])
        self.gx0, self.gy0 = L["mosaic_origin_px"]
        self.z = L["zoom"]

    def _idx(self, xs, ys):
        """local metres -> pixel of the half-resolution plan masks"""
        lon, lat = LON0 + xs / KX, LAT0 + ys / KY
        n = 256 * 2 ** self.z
        gx = (lon + 180) / 360 * n
        gy = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n
        fx = np.interp(gx, self.gxs, np.arange(len(self.gxs)))
        fy = np.interp(gy, self.gys, np.arange(len(self.gys)))
        from scipy import ndimage as ndi
        sx = ndi.map_coordinates(self.FX, [fy, fx], order=1, mode="nearest")
        sy = ndi.map_coordinates(self.FY, [fy, fx], order=1, mode="nearest")
        return np.round((gx + sx - self.gx0) / 2).astype(int), np.round((gy + sy - self.gy0) / 2).astype(int)

    def _pts(self, poly, step):
        minx, miny, maxx, maxy = poly.bounds
        xs, ys = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
        xs, ys = xs.ravel(), ys.ravel()
        if len(xs):
            ins = shapely.contains_xy(poly, xs, ys)
            xs, ys = xs[ins], ys[ins]
        if len(xs) < 3:
            c = poly.representative_point()
            xs, ys = np.array([c.x]), np.array([c.y])
        return xs, ys

    def _share(self, img, poly, step):
        xs, ys = self._pts(poly, step)
        px, py = self._idx(xs, ys)
        ok = (px >= 0) & (px < img.shape[1]) & (py >= 0) & (py < img.shape[0])
        if ok.sum() < 1:
            return None
        return float(img[py[ok], px[ok]].mean())

    def colour_share(self, poly, refs, tol=60, step=2.0):
        """share of the polygon the plan paints in one of the colours `refs` (read from the cached zoom-19 tiles,
        through the registration); None when the tiles are not cached"""
        xs, ys = self._pts(poly, step)
        px, py = self._idx(xs, ys)
        gx, gy = px * 2 + self.gx0, py * 2 + self.gy0
        tiles, hit, n = {}, 0, 0
        for x, y in zip(gx.tolist(), gy.tolist()):
            k = (x // 256, y // 256)
            if k not in tiles:
                p = os.path.join(SRC, "cache", "emap", "19", f"{k[0]}_{k[1]}.png")
                tiles[k] = np.asarray(Image.open(p).convert("RGBA")) if os.path.exists(p) and os.path.getsize(p) else None
            a = tiles[k]
            n += 1
            if a is None:
                continue
            c = a[y % 256, x % 256]
            if c[3] > 100 and any(sum(abs(int(c[i]) - r[i]) for i in range(3)) < tol for r in refs):
                hit += 1
        if not tiles or all(v is None for v in tiles.values()):
            return None
        return hit / max(n, 1)

    def sample(self, poly, step=5.0):
        """(share of the polygon on the drawn plan, share of that which is not street space)"""
        xs, ys = self._pts(poly, step)
        seen = shapely.contains_xy(self.drawn, xs, ys)
        if not seen.any():
            return 0.0, 0.0
        px, py = self._idx(xs[seen], ys[seen])
        ok = (px >= 0) & (px < self.road.shape[1]) & (py >= 0) & (py < self.road.shape[0])
        rd = self.road[py[ok], px[ok]] if ok.any() else np.zeros(1, bool)
        return float(seen.mean()), float(1 - rd.mean())

    def road_share(self, poly, sheet=None, step=2.0):
        return self._share(self.road, poly, step)

    def plot_share(self, poly, step=2.0):
        """share of a polygon that the plan colours as plots"""
        return self._share(self.plotc, poly, step) or 0.0

    def streets_in(self, region):
        return []

    def cells(self):
        """plot cells of the plan, in local metres: outlines cleaned of the bites the printed numbers and the red
        emap.pk watermark take out of them (the notch is filled up to the plot's hull, never over a neighbouring cell)"""
        raw = []
        for c in self.L["cells"]:
            if c["colour"] not in PLOT_COLOURS or not (45 <= c["area_m2"] <= 2000):
                continue
            pg = Polygon([xy(*q) for q in c["ring"]])
            if not pg.is_valid:
                pg = largest(pg.buffer(0))
            if pg is None or pg.area < 40:
                continue
            raw.append((c, pg))
        tree = STRtree([pg for _, pg in raw])
        out = []
        for i, (c, pg) in enumerate(raw):
            hull = pg.convex_hull
            g = pg
            if pg.area < 0.95 * hull.area:
                others = [raw[j][1] for j in tree.query(hull) if j != i]
                fill = hull.difference(unary_union(others).buffer(0.15)) if others else hull
                g = largest(clean(fill)) or pg
                if g.area > 2.2 * pg.area:            # a hull that spreads over open land: keep the outline
                    g = pg
            g = clean(g.simplify(0.3).buffer(0.3, join_style=2))     # out to the middle of the printed plot line
            mrr = g.minimum_rotated_rectangle
            out.append({"poly": g, "sheet": "emap", "group": None, "colour": "Commercial" if c["colour"] == "red" else c["colour"],
                        "rect": g.area / max(1.0, mrr.area), "number": c.get("number"), "checked": c.get("number_checked", False)})
        return out

    def sites(self):
        """coloured sites of the plan (schools, masjids, grid station ...), local metres, with their plan colour"""
        out = []
        for c in self.L["sites"] + [c for c in self.L["cells"] if c["colour"] == "other" and c["area_m2"] >= 150]:
            pg = Polygon([xy(*q) for q in c["ring"]])
            pg = pg if pg.is_valid else largest(pg.buffer(0))
            if pg is not None:
                out.append((pg, tuple(c["rgb"]), c["area_m2"]))
        return out


class Lay(str):
    """layout tag of a plot ('official' / 'generated') that also carries the plot number printed on the plan"""

    def __new__(cls, v, number=None, checked=False, gap=False, moved=None):
        o = str.__new__(cls, v)
        o.number, o.checked, o.gap, o.moved = number, checked, gap, moved
        return o


# sites the newer plan shows in Block X (where the fdacity.pk plan has Multi-Purpose Uses and the proposed university,
# stadium and IMAX theatre), recognised by their colour on the plan
GRAVE_COLOURS = [(180, 120, 84), (196, 162, 100)]      # graveyard browns of the emap.pk plan (Block F, Block X)
EMAP_SITE_COLOURS = [
    ((4, 146, 220), "school", "Primary School (Block X)", None),
    ((156, 178, 188), "grid", "Site for Grid Station (Block X)", 48),
    ((252, 246, 4), "mosque", "Masjid (Block X)", None),
    ((228, 122, 28), "site", "Site for Model Custom Collectorate Residential Accommodation", None),
    ((236, 154, 164), "site", "Site for Tax Office Residential Accommodation", None),
    ((196, 162, 100), "graveyard", "Graveyard (216 kanal)", None),
    ((76, 178, 52), "park", "Park (Block X)", None),
]


DIS_GREEN = (120, 174, 36)   # the newer plan paints dispensary sites this green and prints DIS on them
# DIS sites the plan reader merges into a neighbouring site (corners measured on the plan's zoom-19 tiles, lon, lat):
# Block C's, between the primary school and the commercial area of the block centre (about 21 x 27 m)
DIS_MEASURED = {"C": [(73.08635, 31.530252), (73.08614, 31.530416), (73.08629, 31.530558), (73.0865, 31.530394)]}


def emap_dispensaries(emap, others, named):
    """the newer plan's dispensary sites (green, printed DIS), placed where the plan has them. The older block maps put
    some dispensaries where the newer plan has plots or a street (Dispensary C was left as a sliver and dropped).
    others: polygons of the other sites (a DIS site mostly under one of them is skipped); named: (centroid, block) of
    the older maps' sites; a dispensary sits in its block's central complex, so most of its five nearest sites share its block."""
    out = []
    for pg, rgb, area in emap.sites():
        if area < 150 or sum(abs(a - b) for a, b in zip(rgb, DIS_GREEN)) >= 30:
            continue
        if others is not None and others.intersection(pg).area > 0.3 * pg.area:
            continue
        c = pg.representative_point()
        near = sorted(named, key=lambda t: t[0].distance(c))[:5]           # the block of most of the five nearest sites
        blk = Counter(b for _, b in near).most_common(1)[0][0] if near else None
        out.append({"kind": "dispensary", "name": f"Dispensary ({blk})" if blk else "Dispensary", "block": blk,
                    "poly": clean(pg.simplify(0.4)), "kanal": round(pg.area / 505.857, 2),
                    "source": "Newer FDA City plan (emap.pk): the site printed DIS"})
    return out


def emap_zones(emap, block_x, old_env):
    """Block X sites of the newer plan, as zone entries with their polygon (local metres)"""
    out = []
    where = clean(unary_union([block_x.buffer(40), emap.drawn.difference(old_env.buffer(-20))])) if block_x is not None else emap.drawn
    for pg, rgb, area in emap.sites():
        if area < 300 or not where.contains(pg.representative_point()):
            continue
        for ref, kind, name, kanal in EMAP_SITE_COLOURS:
            if sum(abs(a - b) for a, b in zip(rgb, ref)) < 40:
                z = {"kind": kind, "name": name, "block": "X", "poly": clean(pg.simplify(0.4)), "source": "Newer FDA City plan (emap.pk)"}
                if kanal:
                    z["kanal_label"] = kanal
                if kind == "site":
                    z["sign"] = name.replace("Site for ", "").upper()
                out.append(z)
                break
    # names must tell repeated sites apart
    seen = Counter(z["name"] for z in out)
    n = Counter()
    for z in out:
        if seen[z["name"]] > 1:
            n[z["name"]] += 1
            z["name"] = z["name"].replace("(Block X)", f"(Block X, {n[z['name']]})")
    print("Block X sites from the newer plan:", dict(Counter(z["kind"] for z in out)))
    return out


class Parts:
    """A large area kept as an indexed list of its polygons, for quick cuts against small shapes."""

    def __init__(self, geoms, cell=250.0):
        self.g = []
        for g in geoms:
            for q in polys(g):
                minx, miny, maxx, maxy = q.bounds
                if maxx - minx <= cell and maxy - miny <= cell:
                    self.g.append(q)
                    continue
                # a big shape (the joined road network) is kept in tiles, so that cuts against it stay small
                for x in np.arange(minx, maxx, cell):
                    for y in np.arange(miny, maxy, cell):
                        self.g += [r for r in polys(q.intersection(box(x, y, x + cell, y + cell))) if r.area > 0.01]
        self.tree = STRtree(self.g) if self.g else None

    def near(self, geom):
        if self.tree is None:
            return None
        hit = [self.g[i] for i in self.tree.query(geom, predicate="intersects")]
        return unary_union(hit) if hit else None

    def length_in(self, line):
        u = self.near(line)
        return line.intersection(u).length if u is not None else 0.0

    def minus(self, geom):
        u = self.near(geom)
        return geom.difference(u) if u is not None else geom


def numbering_areas(kept, blk, cxy, tree, landmarks):
    """The plan numbers plots per sub-block (addresses read "plot 108 D2"). Rebuild the numbering areas from the numbers:
    rows are neighbours numbered one after the other; nearby rows whose numbers continue and never repeat join into one
    area; small pieces join a neighbouring area they do not clash with. Each area takes the code of the nearest park
    named after a sub-block ("Park D-2" -> "D2"). Returns {plot index: sub-block code}."""
    import re
    n = len(kept)
    num = [getattr(lay, "number", None) for _, _, lay in kept]
    par = list(range(n))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for i, j in tree.query_pairs(25.0):
        if num[i] and num[j] and abs(num[i] - num[j]) == 1 and blk[i] == blk[j]:
            a, b = find(i), find(j)
            if a != b:
                par[a] = b
    nums = {}
    for i in range(n):
        if num[i]:
            nums.setdefault(find(i), set()).add(num[i])
    pairs = sorted(((float(np.hypot(*(cxy[i] - cxy[j]))), i, j) for i, j in tree.query_pairs(40.0)
                    if num[i] and num[j] and blk[i] == blk[j] and abs(num[i] - num[j]) <= 80))
    for _, i, j in pairs:
        a, b = find(i), find(j)
        if a != b and not (nums[a] & nums[b]):
            par[a] = b
            nums[b] |= nums.pop(a)
    # small pieces (under 40 plots) join the largest neighbouring area they do not clash with
    for _ in range(3):
        size = Counter(find(i) for i in range(n) if num[i])
        for r in sorted([r for r in size if size[r] < 40], key=lambda r: size[r]):
            r = find(r)
            members = [i for i in range(n) if num[i] and find(i) == r]
            best = None
            for i in members:
                for j in tree.query_ball_point(cxy[i], 30.0):
                    b = find(j)
                    if num[j] and b != r and blk[j] == blk[i] and not (nums[b] & nums[r]) and (best is None or size[b] > size[best]):
                        best = b
            if best is not None:
                par[r] = best
                nums[best] |= nums.pop(r)
                size[best] += size.pop(r, 0)
    parks = []
    for f in landmarks:
        m = re.match(r"Park ([A-FX])-(\d+)", f["properties"]["name"])
        if m and f["properties"]["kind"] == "park":
            o = f["properties"]["obb"]
            parks.append((m.group(1) + m.group(2), np.array(xy(o["lon"], o["lat"]))))
    out = {}
    area_pts = {}
    for i in range(n):
        if num[i]:
            area_pts.setdefault(find(i), []).append(i)
    for r, ms in area_pts.items():
        c = cxy[ms].mean(0)
        b = blk[ms[0]]
        cand = [(float(np.hypot(*(pc - c))), code) for code, pc in parks if code[0] == b]
        if not cand:
            continue
        d, code = min(cand)
        if d < 400:
            for i in ms:
                out[i] = code
    # plots without a number take the area of the nearest numbered plot (for the address only)
    for i in range(n):
        if not num[i]:
            for j in tree.query(cxy[i], k=6)[1]:
                if j in out and blk[j] == blk[i]:
                    out[i] = out[j]
                    break
    print(f"numbering areas: {len(area_pts)} ({sum(1 for r in area_pts if len(area_pts[r]) >= 40)} with 40 plots or more); "
          f"plots with an estimated sub-block: {len(out)}")
    return out


def plan_street_lines(emap, outline, row, blocked, res=1.0, shrink=0, corridor=None):
    """Centre lines of the streets the plan draws where no road is mapped yet (undeveloped parts of the society).

    The plan's street space is sampled on a 1 m grid through the registration field, kept inside the society and off
    plots and sites, thinned to its skeleton; a street is a skeleton run where the street space is 6 to 26 m wide.
    The skeleton also runs through the mapped roads (so the new streets meet them); those parts are cut away."""
    import cv2
    from skimage.morphology import skeletonize
    import sys
    sys.path.insert(0, HERE)
    from trace_plots import trace_skeleton
    minx, miny, maxx, maxy = outline.bounds
    x0, y1 = minx - 10, maxy + 10
    W, H = int((maxx - minx + 20) / res), int((maxy - miny + 20) / res)

    def ras(geom):
        img = np.zeros((H, W), np.uint8)
        gs = geom if isinstance(geom, list) else [geom]
        for q in sorted([q for g in gs for q in polys(g)], key=lambda q: -q.area):
            cv2.fillPoly(img, [np.round((np.array(q.exterior.coords) - (x0, y1)) * (1 / res, -1 / res)).astype(np.int32)], 1)
            for r in q.interiors:
                cv2.fillPoly(img, [np.round((np.array(r.coords) - (x0, y1)) * (1 / res, -1 / res)).astype(np.int32)], 0)
        return img > 0
    road = np.zeros((H, W), bool)
    xs = x0 + (np.arange(W) + 0.5) * res
    for j0 in range(0, H, 400):
        j1 = min(H, j0 + 400)
        ys = y1 - (np.arange(j0, j1) + 0.5) * res
        X, Y = np.meshgrid(xs, ys)
        px, py = emap._idx(X.ravel(), Y.ravel())
        ok = (px >= 0) & (px < emap.road.shape[1]) & (py >= 0) & (py < emap.road.shape[0])
        v = np.zeros(len(px), bool)
        v[ok] = emap.road[py[ok], px[ok]]
        road[j0:j1] = v.reshape(j1 - j0, W)
    inside, exist, block = ras(outline.buffer(-0.5)), ras(row), ras(blocked)
    # Street names ("ROAD 40'-0" WIDE"), the emap.pk watermark and plot numbers printed over a street punch small holes
    # in its street space; the centre line would bend round them (S-shaped jogs, loops). Holes under 150 m2 that are
    # not plots or sites are street.
    n_lab, lab, stats, _ = cv2.connectedComponentsWithStats((~(road & inside)).astype(np.uint8), connectivity=4)
    small = np.zeros(n_lab, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] * res * res < 150
    small[np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))] = False
    holes = small[lab] & ~block
    road = road | holes
    exist = cv2.dilate(exist.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0       # mapped roads, 1 m wider
    if shrink:
        block = cv2.erode(block.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=shrink) > 0
    M = road & inside & ~block
    M = cv2.morphologyEx(M.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    dt = cv2.distanceTransform(M.astype(np.uint8), cv2.DIST_L2, 5) * res
    sk = skeletonize(M) & (dt >= 3.0) & (dt <= 13.0) & ~exist
    lines = []
    for e in trace_skeleton(sk):
        pts = e["pts"]
        if len(pts) < 3:
            continue
        ln = LineString([(x0 + px * res, y1 - py * res) for px, py in pts])
        if ln.length >= 10:
            lines.append(ln)
    if not lines:
        return []
    merged = lines_of(linemerge(MultiLineString(lines)))
    # spurs of the skeleton into corners and road-name boxes: dead ends under 14 m that do not reach a mapped road
    near_row = cv2.dilate(exist.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=3) > 0

    def at_road(c):
        i, j = int((y1 - c[1]) / res), int((c[0] - x0) / res)
        return 0 <= i < H and 0 <= j < W and near_row[i, j]
    out = []
    for ln in merged:
        if ln.length < 14 and not (at_road(ln.coords[0]) or at_road(ln.coords[-1])):
            continue
        if corridor is not None and ln.intersection(corridor).length > 0.4 * ln.length:
            continue                      # runs along inside a main road's official corridor (service lanes, verges, median)
        if ln.length < 30 and not (at_road(ln.coords[0]) and at_road(ln.coords[-1])):
            continue                      # a short piece that does not link two roads is a stub, not a street
        out.append(dejog(ln.simplify(2.0)))
    return [ln for ln in out if ln.length >= 8]


def dejog(ln, max_lat=8.0, max_mid=20.0, min_leg=8.0, par=10.0):
    """Take S-shaped sideways steps out of a street centre line.

    Two parallel legs a few metres apart, joined by a short bend, are a break in the plan's drawing (big printed street
    names, the watermark, or the plan's nalla drawn with a kink where the real one runs straight), not a street that
    steps sideways. The street runs straight from the start of the first leg to the end of the second; its ends, and so
    its junctions, stay where they are."""
    pts = list(ln.coords)
    changed = True
    while changed and len(pts) >= 4:
        changed = False
        for i in range(len(pts) - 3):
            a0, a1 = pts[i], pts[i + 1]
            la = math.dist(a0, a1)
            if la < min_leg:
                continue
            ua = ((a1[0] - a0[0]) / la, (a1[1] - a0[1]) / la)
            mid = 0.0
            for k in range(i + 2, min(len(pts) - 1, i + 5)):
                mid += math.dist(pts[k - 1], pts[k])
                if mid > max_mid:
                    break
                b0, b1 = pts[k], pts[k + 1]
                lb = math.dist(b0, b1)
                if lb < min_leg:
                    continue
                ub = ((b1[0] - b0[0]) / lb, (b1[1] - b0[1]) / lb)
                if ua[0] * ub[0] + ua[1] * ub[1] < math.cos(math.radians(par)):
                    continue
                lat = ua[0] * (b0[1] - a1[1]) - ua[1] * (b0[0] - a1[0])
                if 1.0 <= abs(lat) <= max_lat:
                    pts = pts[:i + 1] + pts[k + 1:]
                    changed = True
                    break
            if changed:
                break
    return LineString(pts)


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
        e["share"] = sheet_ink.road_share(band, sheet) if sheet not in getattr(sheet_ink, "coarse", {"F"}) else None     # sheet F is too coarse to tell
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


def road_offsets():
    """sideways shifts of OpenStreetMap ways measured on satellite imagery (tools/align_roads.py)"""
    path = os.path.join(SRC, "road_offsets.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def service_roads():
    """service roads beside the main road that OpenStreetMap lacks, measured by tools/service_roads.py (local metres)"""
    path = os.path.join(SRC, "service_roads.geojson")
    if not os.path.exists(path):
        return []
    return [LineString([xy(*c) for c in f["geometry"]["coordinates"]]) for f in json.load(open(path, encoding="utf-8"))["features"]]


def shift_line(pts, prof):
    """move each vertex of a local-metre polyline to its left by the shift interpolated at its distance along"""
    P = np.array(pts, float)
    seg = np.diff(P, axis=0)
    L = np.hypot(*seg.T)
    L[L == 0] = 1e-9
    U = seg / L[:, None]
    N = np.stack([-U[:, 1], U[:, 0]], 1)
    cum = np.concatenate([[0], np.cumsum(L)])
    d = np.array([q[0] for q in prof])
    o = np.array([q[1] for q in prof])
    out = []
    for i, p in enumerate(P):
        n = N[min(i, len(N) - 1)] if i in (0, len(P) - 1) else (N[i - 1] + N[i])
        n = n / (np.hypot(*n) or 1)
        out.append(tuple(p + n * float(np.interp(cum[i], d, o))))
    return out


def align_to_plan(line, emap, band=12.2, search=8.0, step=15.0):
    """sideways shift (to the left, m) that centres a street on the plan's street space, every `step` m; None if unclear"""
    P = np.array(line.coords, float)
    seg = np.diff(P, axis=0)
    L = np.hypot(*seg.T)
    if L.sum() < 40:
        return None
    L[L == 0] = 1e-9
    cum = np.concatenate([[0], np.cumsum(L)])
    ts = np.arange(-(search + band / 2 + 3), search + band / 2 + 3 + 1e-6, 0.5)
    ss = np.arange(-4, 4.01, 2.0)
    prof = []
    for d in np.arange(8, cum[-1] - 8, step):
        i = int(min(max(np.searchsorted(cum, d) - 1, 0), len(L) - 1))
        u = seg[i] / L[i]
        n = np.array([-u[1], u[0]])
        c = P[i] + u * (d - cum[i])
        T, S = np.meshgrid(ts, ss)
        X, Y = c[0] + n[0] * T + u[0] * S, c[1] + n[1] * T + u[1] * S
        px, py = emap._idx(X.ravel(), Y.ravel())
        ok = (px >= 0) & (px < emap.road.shape[1]) & (py >= 0) & (py < emap.road.shape[0])
        v = np.zeros(px.shape, float)
        v[ok] = emap.road[py[ok], px[ok]]
        a = v.reshape(T.shape).mean(0)
        best, bo = -9, None
        for o in np.arange(-search, search + 1e-6, 0.5):
            ins = (ts >= o - band / 2) & (ts <= o + band / 2)
            fl = ((ts >= o - band / 2 - 3) & (ts < o - band / 2)) | ((ts > o + band / 2) & (ts <= o + band / 2 + 3))
            sc = a[ins].mean() - 0.8 * a[fl].mean() - 0.01 * abs(o)
            if sc > best:
                best, bo = sc, o
        cover = a[(ts >= bo - band / 2) & (ts <= bo + band / 2)].mean()
        prof.append((d, bo if cover > 0.6 else np.nan))
    d = np.array([q[0] for q in prof])
    o = np.array([q[1] for q in prof])
    good = ~np.isnan(o)
    if good.sum() < 3:
        return None
    oo = np.array([np.nanmedian(o[max(0, i - 2):i + 3]) if np.isfinite(o[max(0, i - 2):i + 3]).sum() >= 2 else np.nan for i in range(len(o))])
    g2 = ~np.isnan(oo)
    if g2.sum() < 3:
        return None
    oo = np.interp(d, d[g2], oo[g2])
    if np.nanmedian(np.abs(o[good] - np.interp(d[good], d, oo))) > 1.5 or np.max(np.abs(oo)) < 0.75:
        return None
    return [[float(a), float(b)] for a, b in zip(d, oo)]


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


def join_street_gaps(lines, blocked, max_gap=16.0, max_turn=25.0):
    """join pairs of street ends that face each other in line across a short gap free of plots; (lines, joins)"""
    lines = [ln for ln in lines]
    cos_t = math.cos(math.radians(max_turn))
    n = 0
    while True:
        ends = []
        for i, ln in enumerate(lines):
            cs = list(ln.coords)
            if len(cs) < 2:
                continue
            for k, (p, q) in enumerate(((cs[0], cs[1]), (cs[-1], cs[-2]))):
                L = math.dist(p, q) or 1
                ends.append((i, k, p, ((p[0] - q[0]) / L, (p[1] - q[1]) / L)))     # end point, outward direction
        best = None
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ia, ka, pa, da = ends[a]
                ib, kb, pb, db = ends[b]
                if ia == ib:
                    continue
                d = math.dist(pa, pb)
                if not 0.5 < d < max_gap:
                    continue
                v = ((pb[0] - pa[0]) / d, (pb[1] - pa[1]) / d)
                if da[0] * v[0] + da[1] * v[1] < cos_t or -(db[0] * v[0] + db[1] * v[1]) < cos_t:
                    continue
                if blocked is not None and blocked.intersection(LineString([pa, pb]).buffer(1.5)).area > 1.0:
                    continue
                if best is None or d < best[0]:
                    best = (d, ia, ka, ib, kb)
        if best is None:
            return lines, n
        _, ia, ka, ib, kb = best
        ca, cb = list(lines[ia].coords), list(lines[ib].coords)
        ca = ca if ka == 1 else ca[::-1]          # ca ends at the joined end
        cb = cb if kb == 0 else cb[::-1]          # cb starts at the joined end
        joined = dejog(LineString(ca + cb), max_lat=4.0)      # no sideways step where the two pieces meet
        lines = [ln for k, ln in enumerate(lines) if k not in (ia, ib)] + [joined]
        n += 1


def _runs(mask):
    """index pairs (first, last) of the runs of True in a 1-D boolean array"""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def inscribed_rect(poly, angle_deg, res=0.2, min_side=2.5):
    """Largest rectangle inside `poly` with its sides along `angle_deg` (the plot's long side), as an obb dict
    (centre lon/lat, angle of the long side, length >= width), or None when nothing min_side wide fits.
    The 3D house is drawn in this rectangle, so it stays inside its piece of plot."""
    import cv2
    a = math.radians(angle_deg)
    c = poly.centroid
    q = affinity.rotate(poly, -angle_deg, origin=c)
    minx, miny, maxx, maxy = q.bounds
    W, H = int(math.ceil((maxx - minx) / res)) + 2, int(math.ceil((maxy - miny) / res)) + 2
    img = np.zeros((H, W), np.uint8)
    for g in polys(q):
        cv2.fillPoly(img, [np.round((np.array(g.exterior.coords) - (minx, miny)) / res).astype(np.int32)], 1)
        for r in g.interiors:
            cv2.fillPoly(img, [np.round((np.array(r.coords) - (minx, miny)) / res).astype(np.int32)], 0)
    img = cv2.erode(img, np.ones((2, 2), np.uint8))          # stay just inside the edge
    best, h = (0, 0, 0, 0, 0), np.zeros(W, int)
    for y in range(H):
        h = np.where(img[y] > 0, h + 1, 0)
        stack = []
        for x in range(W + 1):
            cur = h[x] if x < W else 0
            start = x
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                area = hh * (x - s0)
                if area > best[0]:
                    best = (area, s0, x, y - hh + 1, y + 1)
                start = s0
            stack.append((start, cur))
    area, x0, x1, y0, y1 = best
    L, Wd = (x1 - x0) * res, (y1 - y0) * res
    if min(L, Wd) < min_side:
        return None
    cx, cy = minx + (x0 + x1) / 2 * res, miny + (y0 + y1) / 2 * res
    p = affinity.rotate(Point(cx, cy), angle_deg, origin=c)
    ang = angle_deg
    if Wd > L:
        L, Wd, ang = Wd, L, angle_deg + 90
    ang = (ang + 90) % 180 - 90
    lon, lat = ll(p.x, p.y)
    return {"lon": lon, "lat": lat, "angle": round(ang, 2), "length": round(L, 1), "width": round(Wd, 1)}


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
T0 = None


def tick(what):
    import time
    global T0
    T0 = T0 or time.time()
    print(f"  [{time.time() - T0:5.0f} s] {what}", flush=True)


def main():
    tick("start")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", default=None)
    ap.add_argument("--sheets", action="store_true", help="use the fdacity.pk block maps instead of the emap.pk plan")
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)

    feats = json.load(open(os.path.join(SRC, "plan_features.json"), encoding="utf-8"))
    plan = Plan(feats)
    plan.load_image()
    env = Polygon([plan.to_m(*p) for p in feats["envelope"]]).buffer(0)
    old_env = env
    bl = feats["blocks"]
    emap = EmapPlan() if (os.path.exists(EMAP) and not args.sheets) else None
    NE_OLD = ("multipurpose", "university", "stadium", "cinema")      # the newer plan lays out Block X here
    block_x = None
    if emap is not None:
        print("plan: emap.pk redraw of the FDA City plan (tools/emap_plan.py), registered to the streets")
        env = clean(unary_union([env, emap.drawn]))
        north = xy(73.08, 31.533)[1]
        new_land = [q for q in polys(clean(emap.drawn.difference(old_env.buffer(5)))) if q.representative_point().y > north and q.area > 2000]
        block_x = clean(unary_union(new_land + [plan.geom(z).buffer(2) for z in feats["zones"] if z["kind"] in NE_OLD]))

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
        if block_x is not None and block_x.contains(pt):
            return "X"
        return block_px(*plan.to_px(pt.x, pt.y))

    def beyond_f_strip(pt):
        if emap is not None:
            return False                     # the newer plan lays plots out along the whole strip
        x, y = plan.to_px(pt.x, pt.y)
        return x < bl["f_column"][0] and y > bl.get("f_strip_max_y", 9999)

    # ---- roads ------------------------------------------------------------------------
    osm = json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"]
    offs = road_offsets()
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
        pts_ = [xy(p["lon"], p["lat"]) for p in e["geometry"]]
        if str(e["id"]) in offs and len(pts_) >= 2:
            pts_ = shift_line(pts_, offs[str(e["id"])])          # onto the asphalt seen on satellite imagery
        line = LineString(pts_)
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
    if emap is not None:            # streets onto the plan's street space (registered to 0.65 m): one street, not two side by side
        n_al, moved = 0, []
        for d in roads:
            if d["cls"] in ("residential", "collector") and d.get("id") and str(d["id"]) not in offs and d["line"].intersects(env):
                pr = align_to_plan(d["line"], emap)
                if pr:
                    d["line"] = LineString(shift_line(list(d["line"].coords), pr))
                    n_al += 1
                    moved.append(float(np.median([q[1] for q in pr])))
        print(f"streets aligned to the plan's street space: {n_al} (median shift {np.median(np.abs(moved)) if moved else 0:.1f} m)")
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
    measured = service_roads()
    osm_svc = [d["line"] for d in roads if d["cls"] == "service"]
    if measured and osm_svc:
        # where a measured service road runs on into one OpenStreetMap already has, it joins it instead of running
        # alongside it a metre or two off (a kink, two roads side by side)
        su = unary_union(osm_svc)
        joined = []
        for m in measured:
            cs = list(m.coords)
            for _ in range(2):
                while len(cs) > 2 and su.distance(Point(cs[0])) < 4.5 and su.distance(Point(cs[1])) < 4.5:
                    cs.pop(0)
                if su.distance(Point(cs[0])) < 6.0:
                    cs[0] = su.interpolate(su.project(Point(cs[0]))).coords[0]
                cs.reverse()
            if LineString(cs).length > 20:
                joined.append(dejog(LineString(cs), max_lat=4.0))
        measured = joined
    if measured:
        # service roads beside the main road that OpenStreetMap does not map (tools/service_roads.py: Google Maps shows
        # them, the position is measured on Google satellite imagery). An OpenStreetMap street drawn along one of them
        # (tagged residential) is that service road: the measured line replaces the stretch it shares.
        zone = unary_union([m.buffer(6.0, cap_style=2) for m in measured])
        svc_u = unary_union(measured)
        kept_r, n_cut = [], 0
        for d in roads:
            if d["cls"] in ("residential", "collector") and d["line"].intersection(zone).length > 15:
                n_cut += 1
                for q in lines_of(d["line"].difference(zone)):
                    if q.length < 25:
                        continue
                    cs = list(q.coords)          # the cut end is joined back onto the service road
                    if svc_u.distance(Point(cs[0])) < 6.5:
                        cs = [svc_u.interpolate(svc_u.project(Point(cs[0]))).coords[0]] + cs
                    if svc_u.distance(Point(cs[-1])) < 6.5:
                        cs = cs + [svc_u.interpolate(svc_u.project(Point(cs[-1]))).coords[0]]
                    kept_r.append(dict(d, line=LineString(cs)))
                continue
            kept_r.append(d)
        roads = kept_r + [{"id": None, "name": ROAD_NAME["service"], "oneway": False, "line": m, "cls": "service",
                           "source": "Measured: Google Maps shows it, position from Google satellite imagery"} for m in measured]
        print(f"measured service roads: {len(measured)} lines, {sum(m.length for m in measured):.0f} m; {n_cut} OpenStreetMap streets along them cut back")
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

    # a service road carries traffic one way, the way of the main carriageway beside it (no car against the flow)
    mains_ = [d["line"] for d in roads if d["cls"] == "main"]
    for d in roads:
        if d["cls"] == "service" and mains_:
            mid = d["line"].interpolate(0.5, normalized=True)
            v = direction_at(min(mains_, key=lambda q: q.distance(mid)), mid)
            w_ = direction_at(d["line"], mid)
            if v[0] * w_[0] + v[1] * w_[1] < 0:
                d["line"] = LineString(list(d["line"].coords)[::-1])
            d["oneway"] = True
    surf = surface(ROW)
    carriage = surface(WIDTH)
    reserve = unary_union([d["line"].buffer(RESERVE[d["cls"]], cap_style=2, join_style=2) for d in roads if d["cls"] in RESERVE])
    # A kerbed divider between each main carriageway and the service road beside it. Where the two run close (by the
    # gate and along the Main Entrance Road their asphalt is 1 to 2 m apart) the faces of the road network leave no
    # strip and the asphalt of both ran together; there the divider is laid out from the two centre lines (at least
    # 0.9 m wide), open where a side street or a slip road joins.
    dividers = None
    if mains_:
        hm, hs = WIDTH["main"] / 2, WIDTH["service"] / 2
        rings_ = [(c_, ro_) for (c_, ri_, ro_) in ring_geo.values()]
        divs = []
        for d in roads:
            if d["cls"] != "service":
                continue
            s_ = d["line"]
            run = []

            def flush():
                if len(run) >= 4:
                    pts_ = [(x_, y_) for x_, y_, _ in run]
                    w_med = float(np.median([w for _, _, w in run]))
                    divs.append(LineString(pts_).buffer(w_med / 2, cap_style=2, join_style=2))
                run.clear()
            for t in list(np.arange(0.0, s_.length, 1.5)) + [s_.length]:
                p = s_.interpolate(t)
                m = min(mains_, key=lambda q: q.distance(p))
                q = m.interpolate(m.project(p))
                dist = p.distance(q)
                gap = dist - hm - hs
                du, dm = direction_at(s_, p), direction_at(m, q)
                ok = (-0.4 <= gap <= 3.0 and dist > 0.5 and abs(du[0] * dm[0] + du[1] * dm[1]) > 0.97
                      and all(p.distance(c_) > ro_ + 4 for c_, ro_ in rings_))
                if ok:
                    ux, uy = (p.x - q.x) / dist, (p.y - q.y) / dist
                    mv = hm + gap / 2
                    run.append((q.x + ux * mv, q.y + uy * mv, max(gap, 0.9)))
                else:
                    flush()
            flush()
        if divs:
            openings = unary_union([d["line"].buffer(WIDTH[d["cls"]] / 2 + 1.5, cap_style=2) for d in roads
                                    if d["cls"] not in ("main", "service", "highway")])
            dividers = clean(unary_union(divs).difference(openings))
            dividers = clean(unary_union([q for q in polys(dividers) if q.area > 4]))
            carriage = clean(carriage.difference(dividers))
            print(f"kerbed dividers between main carriageways and service roads: {len(polys(dividers))} pieces, "
                  f"{sum(q.length for q in polys(dividers)) / 2 / 1000:.1f} km")

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

    zones = [dict(z, poly=plan.geom(z)) for z in feats["zones"] if not (emap is not None and z["kind"] in NE_OLD)]
    if emap is not None:
        zones += emap_zones(emap, block_x, old_env)
        # dispensaries where the newer plan has them; they replace the older block maps' dispensary of that block
        named = [(plan.geom(f).centroid, f["block"]) for f in feats["facilities"] + feats["parks"]
                 if f.get("block") and f["block"] != "X" and f.get("kind") != "dispensary"]
        others = unary_union([z["poly"] for z in zones] + [plan.geom(f) for f in feats["facilities"] if f.get("kind") != "dispensary"])
        dis = [d for d in emap_dispensaries(emap, others, named) if d["block"] and d["block"] != "X"]
        for blk_, ring in DIS_MEASURED.items():
            if not any(d["block"] == blk_ for d in dis):
                pg_ = Polygon([xy(*q) for q in ring])
                dis.append({"kind": "dispensary", "name": f"Dispensary ({blk_})", "block": blk_, "poly": pg_, "kanal": round(pg_.area / 505.857, 2),
                            "source": "Newer FDA City plan (emap.pk): the site printed DIS, measured on the plan"})
        if dis:
            got = {d["block"] for d in dis}
            feats["facilities"] = [f for f in feats["facilities"] if not (f.get("kind") == "dispensary" and f.get("block") in got)]
            zones = dis + zones          # first, so an older outline drawn over the DIS site (Commercial Centre C) takes the rest
            print("dispensaries from the newer plan:", [(d["name"], d["kanal"]) for d in dis])
    inside_zones = unary_union([z["poly"] for z in zones if not z.get("outside")])

    cells = emap.cells() if emap is not None else load_cells()
    sheet_ink = emap if emap is not None else SheetInk()
    cell_pts = STRtree([c["poly"].representative_point() for c in cells]) if cells else None
    blank = 0
    P = []
    soc_fp = clean(unary_union([emap.drawn.buffer(3.0), inside_zones.buffer(2.0)])) if emap is not None else None
    for f in faces:
        land = f.difference(surf).difference(nala_zone)
        if soc_fp is not None:
            land = land.intersection(soc_fp)              # society land is what the plan draws
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
                for r in polys(q.difference(reserve) if emap is None else q):          # official corridor beyond the paved road (the full plan places its plots itself)
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
                    elif emap is not None:
                        if not in_zone and (seen < 0.5 or seen * inked < 0.15):
                            k2 = "outside"                     # off the plan, or street space only
                    elif (not in_zone and (plotted < 0.42 or smp["bg"] > 0.55)) or beyond_f_strip(cen):
                        k2 = "outside"
                    elif emap is None and not in_zone and sheet_ink.sheets and seen * inked < 0.15:
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
    # what a plot may never cover: carriageways, the nalla, medians, strips and roundabout islands
    Parts_hard = Parts([carriage.buffer(0.3), nala_zone] + [p["land"] for p in P if p["kind"] in ("median", "strip", "island")])
    cell_tree = STRtree([c["poly"] for c in cells])
    cand = []
    why = Counter()
    for c in cells:
        c["drop"] = None
        cen = c["poly"].representative_point()
        if not env.contains(cen):
            why["outside the plan area"] += 1
            c["drop"] = "outside the plan area"
            continue
        if emap is None and raw_u.contains(cen):
            why["inside a facility picture"] += 1
            continue
        best, ba = None, 0
        for i in ptree.query(c["poly"]):
            a = with_free[i]["free"].intersection(c["poly"]).area
            if a > ba:
                best, ba = with_free[i], a
        if (best is None or ba < 0.55 * c["poly"].area) and emap is not None:
            # the plan puts a plot where the road as built is wider or off: trim the plot to the road edge. Along the
            # main entrance road the plan draws the 202 ft road far narrower than built (no service roads): its
            # commercial rows lose up to 60% of their depth, but they stay the plan's numbered plots
            g = largest(clean(Parts_hard.minus(c["poly"])))
            if (g is not None and g.area >= 0.35 * c["poly"].area and g.area >= 50 and not g.buffer(-2.0).is_empty
                    and soc_fp.contains(g.representative_point())):
                near_p = [with_free[i] for i in ptree.query(g.buffer(15))]
                if near_p:
                    best = min(near_p, key=lambda q: q["free"].distance(g))
                    c["clip"] = g
                    ba = c["poly"].area
                    why["trimmed to the road as built"] += 1
        if (best is None or ba < 0.55 * c["poly"].area) and emap is not None:
            # still on the road: move the plot straight off it (at most 6 m), onto free land no other plan plot uses
            hard = Parts_hard.near(c["poly"])
            if hard is not None and not hard.is_empty and soc_fp.contains(cen):
                on = c["poly"].intersection(hard)
                if not on.is_empty:
                    v = np.array([cen.x - on.centroid.x, cen.y - on.centroid.y])
                    nv = float(np.hypot(*v))
                    for d in (np.arange(1.0, 6.01, 0.5) if nv > 0.2 else []):
                        g = affinity.translate(c["poly"], *(v / nv * d))
                        if g.intersection(Parts_hard.near(g) or Polygon()).area > 0.03 * g.area:
                            continue
                        if any(o is not c and o["poly"].intersection(g).area > 0.08 * g.area for o in (cells[j] for j in cell_tree.query(g))):
                            break                                  # it would sit on its neighbour: leave it out
                        hit = [with_free[i] for i in ptree.query(g)]
                        fa = max((q["free"].intersection(g).area for q in hit), default=0)
                        if fa >= 0.85 * g.area:
                            best = max(hit, key=lambda q: q["free"].intersection(g).area)
                            c["poly"], c["clip"], ba = g, g, g.area
                            c["moved"] = round(float(d), 1)
                            why["moved off the road as built"] += 1
                        break
        if best is None or ba < 0.55 * c["poly"].area:
            why["on a road or outside society land"] += 1
            c["drop"] = f"on a road or outside society land ({ba / c['poly'].area:.2f} on parcel land)"
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
            c["drop"] = "overlaps another cell"
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
                 "accuracy": "approximate", "source": item.get("source", "Official FDA City plan and block maps")}
        if item.get("kanal"):
            props["kanal_official"] = item["kanal"]
        if item.get("sign"):
            props["sign"] = item["sign"]
        if extra:
            props.update({k: v for k, v in extra.items() if v is not None})
        landmarks.append(feature(clean(poly.simplify(0.2)), props))
        return props

    def carve(poly, whole_frac=0.62, min_area=60, kanal=None):
        if emap is not None:
            whole_frac = max(whole_frac, 0.9)   # the plan draws its streets: a site never takes a whole street block's leftovers
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
            add_lm(carve(z["poly"], 0.9 if z.get("source") else 0.5, 60, z.get("kanal")), z["kind"], z["name"], z.get("block"), z)
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
    # where the newer plan (emap.pk) names a park on a different piece of land than the fdacity.pk block sheet
    EMAP_PARK_AT = {"Park C-3": (73.0813086, 31.532504)}
    EMAP_PARK_DROP = {"Park (Block C west)"}        # the same triangle, now named Park C-3
    for pk in feats["parks"]:
        if emap is not None and pk["name"] in EMAP_PARK_DROP:
            continue
        if emap is not None and pk["name"] in EMAP_PARK_AT:
            pt = Point(*xy(*EMAP_PARK_AT[pk["name"]]))
            face = next((q["land"] for q in parcels if q["land"].contains(pt)), None)
            if face is not None:
                add_lm(carve(face.buffer(-0.5), 0.6, 60), "park", pk["name"], pk["block"],
                       dict(pk, source="Newer FDA City plan (emap.pk), which names this triangle Park C-3"))
                continue
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
    # The asphalt across the gate (both main carriageways and the service roads beside them), in the 3D model's own
    # frame (z across the road, = minus the distance to the left of the road direction). The model puts its towers
    # beyond the outermost asphalt and its pier and guard room on the median: nothing of it stands on a road.
    nv = (-gv[1], gv[0])
    ts = np.arange(-45.0, 45.01, 0.1)
    on_road = shapely.contains_xy(carriage, gp.x + nv[0] * ts, gp.y + nv[1] * ts)
    bands = []
    for a_, b_ in [(ts[i], ts[j]) for i, j in _runs(on_road)]:
        mid = Point(gp.x + nv[0] * (a_ + b_) / 2, gp.y + nv[1] * (a_ + b_) / 2)
        near = min((d for d in roads if d["cls"] in ("main", "service")), key=lambda d: d["line"].distance(mid))
        bands.append([round(-b_ - 0.05, 2), round(-a_ + 0.05, 2), near["cls"]])
    bands.sort()
    gate_feat = feature(gp, {"id": 0, "kind": "gate", "name": "FDA City Main Gate", "block": None, "area_kanal": None, "proposed": False,
                             "heading": round(math.degrees(math.atan2(gv[1], gv[0])), 1), "span": GATE["span"], "asphalt": bands, "accuracy": "georeferenced",
                             "source": "Official Block A map (Main Entrance Road); position and span measured on satellite imagery"})
    print("gate: asphalt across it (local z from, to, road):", bands)
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
    outline = Polygon(main_part.exterior, [r for r in main_part.interiors if Polygon(r).area > 20000]).simplify(1.5)
    cen = outline.centroid
    axis_a, axis_b = plan.to_m(945, 487), plan.to_m(1220, 487)
    axis_deg = math.degrees(math.atan2(axis_b[1] - axis_a[1], axis_b[0] - axis_a[0]))
    bprops = {"name": "FDA City", "city": "Faisalabad", "source": "Official FDA City plan, georeferenced; streets from OpenStreetMap",
              "accuracy": "approximate", "area_km2": round(outline.area / 1e6, 2), "centre_lon": ll(cen.x, cen.y)[0],
              "centre_lat": ll(cen.x, cen.y)[1], "lat_ref": LAT_REF, "axis_deg": round(axis_deg, 2), "sidewalk_m": FOOTPATH,
              "blocks": {b: list(ll(*plan.to_m(*p))) for b, p in bl["label_px"].items()}}
    if block_x is not None:
        bprops["blocks"]["X"] = list(ll(*largest(block_x).representative_point().coords[0]))
        bprops["source"] = "FDA City plan (emap.pk redraw incl. Block X) registered to the streets; streets from OpenStreetMap"
    print(f"society outline: {outline.area/1e6:.2f} km2")

    tick("outline")
    # ---- plots ---------------------------------------------------------------------------------
    # 1. official outlines: the plot cells read from the block maps, kept where they lie on free society land
    # 2. elsewhere: the street block is split into plots of the official size (planned 40 ft streets where needed)
    plot_geo, planned_streets, planned_lines, greens = [], [], [], []     # plot_geo: (polygon, size, layout)
    todo, unplotted = [], []
    cell_blocks = []
    lost = 0
    for p in sorted(parcels, key=lambda p: (p["blk"], -round(p["c"].y / 40), p["c"].x)):
        if p["free"] is not None and not outline.buffer(3).contains(p["land"])                 and p["land"].difference(outline.buffer(3)).area <= 0.02 * p["land"].area:
            p["free"] = clean(p["free"].intersection(outline.buffer(3)))      # a sliver past the outline: clip it
            p["land"] = clean(p["land"].intersection(outline.buffer(3)))
        if p["free"] is None or p["free"].is_empty or not outline.buffer(3.5).contains(p["land"]):
            for c in p.get("cells", []):
                c["drop"] = "its land is not inside the society outline" if p["free"] is not None else "its land was given to a site"
            continue
        free = p["free"]
        acc = []
        for c in p.get("cells", []):
            g = c["clip"] if c.get("clip") is not None else largest(c["poly"].intersection(free))
            keep = 0.35 if c.get("clip") is not None else 0.5          # (trimmed to the road as built: see above)
            if g is None or g.area < keep * c["poly"].area:
                lost += 1
                c["drop"] = "cut by a road"
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
                acc[i][0] = g if (g is not None and g.area >= (0.35 if c.get("clip") is not None else 0.5) * c["poly"].area) else None
                if acc[i][0] is None:
                    c["drop"] = "squeezed out by a neighbouring cell"
            acc = [(g, c) for g, c in acc if g is not None]
        blocks_u = None
        if acc:
            blocks_u = clean(unary_union([clean(g).buffer(1.0, join_style=2) for g, _ in acc]).buffer(-1.0, join_style=2))
            need = 1 if emap is not None else 4             # a lone shape on a block map is lettering; on the full plan it is a plot
            keep = [q for q in polys(blocks_u) if sum(1 for g, _ in acc if q.contains(g.representative_point())) >= need]
            blocks_u = unary_union(keep) if keep else None
            for g, c in acc:
                if blocks_u is None or not blocks_u.contains(g.representative_point()):
                    c["drop"] = "in a group of fewer than 4 cells"
            acc = [(g, c) for g, c in acc if blocks_u is not None and blocks_u.contains(g.representative_point())]
        if acc:
            for g, c in acc:
                near_main = main_u.distance(g) < 45
                com = c["colour"] == "Commercial" and (emap is not None or (near_main and g.area < 330))
                sz = "Commercial" if com else size_by_area(g.area)
                plot_geo.append((g, sz, Lay("official", c.get("number"), c.get("checked", False), moved=c.get("moved"))))
            # plots the print did not let us read: holes and notches of a block that have the size of a plot
            closed = clean(blocks_u.buffer(5.0, join_style=2).buffer(-5.0, join_style=2)).intersection(free)
            for h in polys(closed.difference(blocks_u.buffer(0.05))):
                if 70 <= h.area <= 800 and h.area / h.minimum_rotated_rectangle.area > 0.8 and not h.buffer(-2.5).is_empty                         and (emap is None or emap.plot_share(h) > 0.6):
                    plot_geo.append((clean(h.buffer(-0.05)), size_by_area(h.area), Lay("official", None, False, gap=emap is not None)))
                    blocks_u = clean(blocks_u.union(h))
            cell_blocks.append(blocks_u)
            try:
                rest = free.difference(clean(blocks_u.buffer(STREET + 0.4, join_style=2)))
            except shapely.errors.GEOSException:
                rest = shapely.make_valid(free).difference(shapely.make_valid(blocks_u.buffer(STREET + 0.4, join_style=2)))
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
        if streets and (not streets_ok or emap is not None):
            return 0                                    # too deep for plots without a new street: leave it open
        planned_streets += streets
        planned_lines += lines
        plot_geo += [(pg, sz, "generated") for pg, sz in plots]
        used = unary_union([pg.buffer(0.05) for pg, _ in plots] + [s.buffer(0.05) for s in streets]) if (plots or streets) else None
        rest2 = region.difference(used) if used is not None else region
        greens += [q for q in polys(rest2) if q.area > 25 and not q.buffer(-0.8).is_empty]
        return len(plots)

    for region, p, own_axis in todo:
        if emap is not None and emap.plot_share(region) < 0.5:
            greens.append(region)                       # the plan shows a park, a site or open land here, not plots
            continue
        if not split_region(region, p, own_axis) and emap is not None:
            greens.append(region)

    # real plots stand in rows of plots of their own size. A shape read from a block map with no neighbour of similar
    # size is a stray (a piece of lettering, a symbol): dropped, and the land is filled like any other unread land
    if plot_geo and emap is None:
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
    free_u = unary_union([p["free"] for p in parcels if p["free"] is not None and not p["free"].is_empty and outline.buffer(3.5).contains(p["land"])])
    planned_car = [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets]
    left0 = clean(free_u.difference(unary_union([plots_u] + [q.buffer(0.05) for q in planned_streets] + [q.buffer(0.05) for q in greens]
                                                + [q.buffer(0.05) for q in unplotted])))
    row_now = clean(unary_union([surf.intersection(outline.buffer(5)), reserve.intersection(outline.buffer(5))] + planned_streets))
    car_now = clean(unary_union([carriage.intersection(outline.buffer(5))] + planned_car))
    # (open land counts too: the corridors between plot groups often lie on land the maps leave white)
    search = clean(unary_union([left0] + [q.buffer(0.1) for q in unplotted])) if unplotted else left0
    tick("streets")
    if emap is not None:          # the plan draws every street: take them from it where no road is mapped yet
        half_row = {"main": 21.0, "service": 5.0, "road110": 9.5, "divider_half": 8.0, "divider": 13.0, "road85": 13.0, "collector": 9.0,
                    "arterial": 15.0, "highway": 20.0, "roundabout": 12.0, "residential": 6.5}
        corridor = clean(unary_union([d["line"].buffer(half_row[d["cls"]], cap_style=2) for d in roads if d["cls"] in half_row]))
        # Site outlines come from the older fdacity.pk block maps and are sometimes drawn a few metres over the newer
        # plan's street beside them (Park A-2, a Block D park): only a site's interior stops a street; its outer 8 m may not.
        site_core = [q for f in landmarks if f["geometry"]["type"] == "Polygon"
                     for q in [Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]]).buffer(-8.0)] if not q.is_empty]
        lines_new = plan_street_lines(emap, outline, [surf.intersection(outline.buffer(5)), reserve.intersection(outline.buffer(5))],
                                      [pg for pg, _, _ in plot_geo] + site_core, shrink=1, corridor=corridor)
        # a short piece lying alongside a street (within 10 m, parallel) is a leftover of the tracing, not a street of its own
        known = [d["line"] for d in roads if d["cls"] != "highway"]
        ktree = STRtree(known)

        def sliver(ln):
            if ln.length >= 20:
                return False
            near = [known[j] for j in ktree.query(ln.buffer(10.0))] + [o for o in lines_new if o is not ln and o.distance(ln) < 10.0]
            return any(o.distance(ln) < 10.0 and parallel_to(ln, o, 0.87) for o in near)
        n_sl = sum(1 for ln in lines_new if sliver(ln))
        lines_new = [ln for ln in lines_new if not sliver(ln)]
        print(f"short street pieces alongside another street dropped: {n_sl}")
        # one street broken into two pieces (a plot number or the street name printed across it): join two ends that
        # face each other in line, under 16 m apart, across a gap no plot or site stands in
        plots_now = clean(unary_union([pg for pg, _, _ in plot_geo] + site_core))
        lines_new, n_join = join_street_gaps(lines_new, plots_now)
        print(f"streets joined across a gap: {n_join}")
        if lines_new:            # ... and the site is cut back to the street's 40 ft reserve
            band = unary_union(lines_new).buffer(STREET / 2, cap_style=2, join_style=1)
            n_trim = 0
            for f in landmarks:
                if f["geometry"]["type"] != "Polygon" or f["properties"]["kind"] == "roundabout":
                    continue
                rings = f["geometry"]["coordinates"]          # (keep the holes cut out of a site for plots)
                pg = clean(Polygon([xy(*c) for c in rings[0]], [[xy(*c) for c in r] for r in rings[1:]]))
                if pg.geom_type != "Polygon":
                    continue
                if pg.intersection(band).area > 10:
                    g2 = largest(clean(pg.difference(band)))
                    if g2 is not None and g2.area > 0.5 * pg.area:
                        g2 = clean(g2.simplify(0.2))
                        f["geometry"] = geom_ll(g2)
                        f["properties"]["area_kanal"] = round(g2.area / KANAL, 1)
                        f["properties"]["obb"] = obb(g2)
                        n_trim += 1
            site_u = unary_union([Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]]).buffer(0.5) for f in landmarks if f["geometry"]["type"] == "Polygon"])
            blocked_u = clean(unary_union([plots_u, site_u, nala_zone]))
            print(f"sites cut back off a street of the plan: {n_trim}")
    else:
        lines_new = corridor_lines(search, row_now, car_now, sheet_ink, block_m)
    tick(f"street lines: {len(lines_new)}")
    new_reserve = new_carriage = None
    half = WIDTH["residential"] / 2
    if lines_new:
        lu = unary_union(lines_new)
        new_carriage = clean(lu.buffer(half, join_style=1, cap_style=2).difference(blocked_u.buffer(0.4)).intersection(outline))
        # where plots press on a street, its asphalt narrows to a point: anything under 3 m wide is not a road
        new_carriage = clean(new_carriage.buffer(-1.5, join_style=2).buffer(1.5, join_style=2).intersection(new_carriage))
        new_carriage = clean(unary_union([q for q in polys(new_carriage) if q.area > 40]))
        new_reserve = clean(lu.buffer(STREET / 2, join_style=1, cap_style=2).difference(blocked_u).intersection(outline))
        print(f"streets between the plots, not in OpenStreetMap yet: {sum(l.length for l in lines_new) / 1000:.1f} km in {len(lines_new)} pieces")
    sheet_lines = lines_new
    if new_reserve is not None and unplotted:                 # a street through open land is cut out of it
        rp = Parts([new_reserve])
        unplotted = [q for u in unplotted for q in polys(clean(rp.minus(u))) if q.area > 60]

    tick("street surfaces")
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
            share = sheet_ink.road_share(f, sheet_f) if sheet_f not in getattr(sheet_ink, "coarse", {"F"}) else 0.0     # sheet F is too coarse to tell
            mrr = f.minimum_rotated_rectangle
            cs = list(mrr.exterior.coords)
            short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
            pshare = emap.plot_share(f) if emap is not None else 1.0
            if 70 <= f.area <= 900 and f.area / mrr.area > 0.62 and short >= 6.0 and share is not None and share < 0.45 and pshare > 0.6:
                plot_geo.append((clean(f.buffer(-0.05)), size_by_area(f.area), Lay("official", None, False, gap=True) if emap is not None else "generated"))
                taken.append(f.buffer(0.06))
                n_gap += 1
            elif f.area > 900 and (share is None or share < 0.75) and pshare > 0.5:
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
        for r in polys(q):
            if r.area <= 4:
                continue
            if emap is not None and r.area > 600 and not r.buffer(-7.0).is_empty and (emap.road_share(r) or 0) < 0.3:
                greens.append(r)                  # the plan draws a park or open ground here, not a street
            else:
                verge_extra.append(r)
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
    hard_final = Parts([carriage, nala_zone] + ([new_carriage] if new_carriage is not None else []))
    clipped = []
    for pg, sz, lay in kept:                     # no sliver of a plot on a carriageway, the nalla, or past the outline
        g = largest(clean(hard_final.minus(pg).intersection(outline)))
        if g is not None and g.area >= 0.5 * pg.area:
            clipped.append((g, sz, lay))
    kept = clipped
    if os.environ.get("TERRALYT_DEBUG"):
        placed_u = STRtree([pg for pg, _, _ in kept])
        dbg = [feature(c["poly"], {"drop": c.get("drop") or "placed, removed later (stray, frontage or overlap)", "number": c.get("number")})
               for c in cells if c.get("drop") or not len(placed_u.query(c["poly"].representative_point(), predicate="intersects"))]
        write(os.environ["TERRALYT_DEBUG"], "dropped_cells", dbg)
    n_off = sum(1 for _, _, lay in kept if lay == "official")
    print(f"plots: {len(kept)} ({n_off} official outlines from the block maps, {len(kept) - n_off} generated in street blocks the print does not resolve); "
          f"{len(plot_geo) - len(kept)} without road frontage turned into green space; {lost} cells cut by a road dropped; planned 40 ft street pieces: {len(planned_streets)}")

    tick("plots done")
    # ---- buildings standing today (footprints detected on satellite imagery) -------------------------
    bld = [(g, pr) for g, pr in load_buildings() if outline.contains(g.representative_point())]
    kept.sort(key=lambda t: (block_m(t[0].centroid), -round(t[0].centroid.y / 40), t[0].centroid.x))
    ktree = STRtree([pg for pg, _, _ in kept])
    built_on = {}
    bfeats = []
    road_all = unary_union([carriage] + ([new_carriage] if new_carriage is not None else [])
                           + [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets])
    n_road = n_split = n_trim = 0
    btaken = []
    for g, pr in sorted(bld, key=lambda t: -t[0].area):
        if any(g.intersection(o).area > 0.5 * g.area for o in btaken if o.intersects(g)):
            continue                                        # the same building in both datasets
        if g.intersection(road_all).area > 0.35 * g.area:
            n_road += 1                                     # on a mapped road: stale footprint, or the street is drawn a little off
            continue
        if site_u.contains(g.representative_point()):
            continue                                        # inside a facility site: drawn by that site's own model
        cover = sorted(((kept[i][0].intersection(g).area, int(i)) for i in ktree.query(g)), reverse=True)
        cover = [(a, i) for a, i in cover if a > 0.5]
        btaken.append(g)
        storeys = 1 if g.area < 70 else 2 if g.area < 420 else 3
        base = {"area_m2": round(g.area), "storeys": storeys, "height": round(3.5 * storeys, 1), "height_source": "assumed",
                "dataset": pr.get("dataset"), "source": BUILT_SOURCE, "accuracy": "georeferenced"}
        if not cover or cover[0][0] < max(20.0, 0.1 * kept[cover[0][1]][0].area):
            # on no plot (open land, a verge, village houses on land the plan has not laid out yet): drawn as it
            # stands, but kept off the plots it touches
            rest = g
            if cover:
                rest = largest(clean(g.difference(unary_union([kept[i][0].buffer(0.35, join_style=2) for _, i in cover]))))
            rect = inscribed_rect(rest, obb(rest)["angle"]) if rest is not None and rest.area >= 12 else None
            if rect is not None:
                bfeats.append((clean(rest.simplify(0.1)), dict(base, id=len(bfeats) + 1, plot_index=None, obb=rect)))
            continue
        # A footprint rarely matches the plot lines exactly. Where it covers a good part of a neighbouring plot too
        # (at least 30 m2 and a fifth of that plot), the house was built across both plots: both are built, and the
        # house is drawn on each, split at the plot line. Where it only pokes a metre or two over (registration of
        # the plan, or the footprint detection), it is trimmed to its own plot. No house is drawn over a plot line.
        own = cover[0][1]
        on_plots = [own] + [i for a, i in cover[1:] if a >= 30.0 and a >= 0.2 * kept[i][0].area]
        n_split += len(on_plots) > 1
        n_trim += any(a > 2.0 for a, i in cover if i not in on_plots)
        for i in on_plots:
            piece = largest(clean(g.intersection(kept[i][0].buffer(-0.35, join_style=2))))
            if piece is None or piece.area < 12:
                continue
            rect = inscribed_rect(piece, obb(kept[i][0])["angle"])
            if rect is None:
                continue
            built_on.setdefault(i, []).append(len(bfeats))
            bfeats.append((clean(piece.simplify(0.1)), dict(base, id=len(bfeats) + 1, plot_index=i, obb=rect, area_m2=round(piece.area),
                                                            footprint_m2=round(g.area), split=len(on_plots) > 1 or None)))
    print(f"buildings standing today: {len(bfeats)} houses (from footprints), on {len(built_on)} plots; {n_split} footprints span two or more plots "
          f"(split at the plot line, each plot built); {n_trim} poked over a plot line and were trimmed; {n_road} left out because they lie on a mapped road")
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

    # numbers far past a block's numbering are misreads of the small print (a 1 read as 4 or 7, an extra digit):
    # correct them when a neighbouring plot continues the sequence, otherwise leave the number out
    nb_blk = [block_m(pg.centroid) for pg, _, _ in kept]
    from collections import defaultdict
    hund = defaultdict(Counter)
    for (pg, _, lay), b in zip(kept, nb_blk):
        if getattr(lay, "number", None):
            hund[b][lay.number // 100] += 1
    top = {}
    for b, h in hund.items():
        k = 0
        while h.get(k + 1) or h.get(k + 2):             # stop at the first gap of two empty hundreds
            k += 1
        top[b] = (k + 1) * 100
    cxy = np.array([[pg.centroid.x, pg.centroid.y] for pg, _, _ in kept])
    from scipy.spatial import cKDTree
    ktr = cKDTree(cxy)
    fixed_n = dropped_n = 0
    for i, ((pg, sz, lay), b) in enumerate(zip(kept, nb_blk)):
        n = getattr(lay, "number", None)
        if not n or n <= top.get(b, 10 ** 6):
            continue
        st = str(n)
        cands = ([int("1" + st[1:])] if len(st) == 4 and st[0] in "47" else []) +                 [int(st[:j] + st[j + 1:]) for j in range(len(st)) if len(st) > 1 and st[:j] + st[j + 1:] and (st[:j] + st[j + 1:])[0] != "0"]
        cands = [c for c in cands if 0 < c <= top[b]]
        near_n = {getattr(kept[j][2], "number", None) for j in ktr.query_ball_point(cxy[i], 40.0) if j != i}
        pick = next((c for c in cands if near_n & {c - 2, c - 1, c + 1, c + 2}), None)
        if pick is None and cands and len(st) == 4 and st[0] in "47":
            # the whole row may be misread the same way: test against the corrected neighbours too
            near_c = {int("1" + str(m)[1:]) for m in near_n if m and len(str(m)) == 4 and str(m)[0] in "47"}
            pick = cands[0] if near_c & {cands[0] - 1, cands[0] + 1} else None
        lay.number = pick
        lay.checked = False
        fixed_n += pick is not None
        dropped_n += pick is None
    print(f"plot numbers past their block's range (misread): {fixed_n} corrected, {dropped_n} left out; block ranges {dict(sorted(top.items()))}")
    sub_of = numbering_areas(kept, nb_blk, cxy, ktr, landmarks) if emap is not None else {}
    plot_feats = []
    counters = Counter()
    in_block = Counter((nb_blk[i], getattr(lay, "number", None)) for i, (pg, _, lay) in enumerate(kept) if getattr(lay, "number", None))
    numbered = Counter((nb_blk[i], sub_of.get(i), getattr(lay, "number", None)) for i, (pg, _, lay) in enumerate(kept) if getattr(lay, "number", None))
    used_no = Counter()
    for i, (pg, sz, lay) in enumerate(kept):
        pid = i + 1
        pg = clean(pg.simplify(0.05))
        blk = block_m(pg.centroid)
        counters[blk] += 1
        key = (blk, counters[blk])
        number = getattr(lay, "number", None)
        sub = sub_of.get(i)
        if number:
            # the plan numbers plots per sub-block, so a number can repeat inside a block: then the estimated sub-block
            # (nearest park of that name) tells them apart, and a letter where even that repeats
            key2 = (blk, sub, number)
            used_no[key2] += 1
            plot_no = f"{blk}-{number}"
            if in_block[(blk, number)] > 1:
                plot_no += f" ({sub})" if sub else ""
                if numbered[key2] > 1 or not sub:
                    plot_no += "/" + "abcdefghij"[min(9, used_no[key2] - 1)]
        elif emap is not None:
            plot_no = f"{blk}-u{counters[blk]}"
        else:
            plot_no = f"{blk}-{counters[blk]}"
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
            "id": pid, "plot_no": plot_no, "plot_number": number, "sub_block": sub,
            "sub_block_source": "Estimated: the numbering area around the nearest park of that name" if sub else None,
            "number_source": ("Printed on the plan" + ("" if getattr(lay, "checked", False) else " (read by OCR, not confirmed by a neighbour)")) if number
            else ("Not readable on the plan" if emap is not None else "Running number"),
            "block": "Block " + blk,
            "size": sz, "type": ptype, "status": status, "dev_class": dev_class,
            "built": built, "storeys": storeys, "height": round(height, 1), "height_source": "assumed",
            "built_source": BUILT_SOURCE, "built_share_150m": round(float(share[i]), 2),
            "source": "Sample value (no society record yet)", "confidence": "Low", "lat": lat, "lon": lon,
            "area_m2": round(pg.area), "marla": round(pg.area / 25.29, 1),
            "layout": ("FDA City plan (emap.pk), registered to the streets" + (f"; moved {lay.moved} m off the road as built" if getattr(lay, "moved", None) else "")
                       if emap is not None and not getattr(lay, "gap", False) else
                       "Gap in a row of the plan (outline not readable)" if emap is not None else "Official block map") if lay == "official" else "Generated in the street block",
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
    # Bridges where roads cross the channel. Crossings close together are one structure: the two carriageways of a
    # dual road (Iqra Road, the boulevard, the 85 ft roads) share one bridge with railings on its outer edges only;
    # a side street that meets a road right at the channel gets no bridge of its own (its railings would run across
    # the road it joins).
    cand = []
    for d in roads:
        x = d["line"].intersection(nala)
        for pt in ([x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]):
            s = d["line"].project(pt)
            a, b = d["line"].interpolate(max(0, s - 3)), d["line"].interpolate(min(d["line"].length, s + 3))
            cand.append({"pt": pt, "h": math.atan2(b.y - a.y, b.x - a.x), "w": WIDTH[d["cls"]], "len": d["line"].length})
    order = sorted(range(len(cand)), key=lambda i: (-cand[i]["w"], -cand[i]["len"]))
    used = [False] * len(cand)
    n_merged = n_side = 0
    for i in order:
        if used[i]:
            continue
        used[i] = True
        c = cand[i]
        u, nv_ = (math.cos(c["h"]), math.sin(c["h"])), (-math.sin(c["h"]), math.cos(c["h"]))
        group = [c]
        for j in order:
            if used[j]:
                continue
            o = cand[j]
            dist = o["pt"].distance(c["pt"])
            dh = abs((o["h"] - c["h"] + math.pi / 2) % math.pi - math.pi / 2)
            if dh < math.radians(25) and dist - (o["w"] + c["w"]) / 2 < 8.0:
                group.append(o); used[j] = True; n_merged += 1          # the other carriageway of the same road
            elif dh >= math.radians(25) and dist < 10.0:
                used[j] = True; n_side += 1                              # a side street meeting the road at the channel
        across = [((g["pt"].x - c["pt"].x) * nv_[0] + (g["pt"].y - c["pt"].y) * nv_[1], g["w"] / 2) for g in group]
        along = [(g["pt"].x - c["pt"].x) * u[0] + (g["pt"].y - c["pt"].y) * u[1] for g in group]
        lo, hi = min(t - w for t, w in across), max(t + w for t, w in across)
        mid, al = (lo + hi) / 2, sum(along) / len(along)
        cp = Point(c["pt"].x + nv_[0] * mid + u[0] * al, c["pt"].y + nv_[1] * mid + u[1] * al)
        water.append(feature(cp, {"kind": "bridge", "heading": round(math.degrees(c["h"]), 1), "road_width": round(hi - lo, 1),
                                  "span": round(2 * NALA_CH + 2, 1), "carriageways": len(group)}))
    print(f"bridges: {len(cand)} crossings -> {len(cand) - n_merged - n_side} bridges ({n_merged} second carriageways share a bridge, "
          f"{n_side} side streets meeting a road at the channel)")
    print("water:", dict(Counter(f["properties"]["kind"] for f in water)))

    tick("water")
    # ---- write ------------------------------------------------------------------------------------
    print("writing to", out)
    write(out, "boundary", [feature(outline, bprops)])
    road_feats = []
    clip = outline.buffer(60)
    clip_main = outline.buffer(1500)             # the Main Entrance Road runs on to the gate, outside the outline
    for d in roads:
        for part in lines_of(d["line"].intersection(clip_main if (d["cls"] == "main" or d.get("source")) else clip)):
            if part.length < 5:
                continue
            road_feats.append(feature(part, {"osm_id": d["id"], "name": d["name"] or ROAD_NAME.get(d["cls"]), "class": d["cls"],
                                             "width_m": round(WIDTH[d["cls"]], 1), "official_ft": OFFICIAL_FT.get(d["cls"]), "oneway": d["oneway"],
                                             "planned": bool(d.get("planned")),
                                             "source": d.get("source") or ("Official plan" if d.get("planned") else "OpenStreetMap"),
                                             "accuracy": "approximate" if d.get("planned") else "measured" if d.get("source") else "georeferenced"}))
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
    div_new = None
    if dividers is not None:
        div_new = clean(dividers.difference(medians.buffer(0.05)))
        medians = unary_union([medians, dividers])
    verge = clean(inner_row.difference(inner_carriage.buffer(0.05)).difference(medians.buffer(0.05)).difference(nala.buffer(NALA_CH + 0.5)))
    verge = clean(verge.difference(unary_union([pg.buffer(0.1) for pg, _, _ in kept])))      # a plot wins over the verge beside it
    write(out, "road_surface",
          [feature(clean(q.simplify(0.2)), {"kind": "carriageway", "accuracy": "approximate", "source": "widths measured on satellite imagery"}) for q in polys(inner_carriage) if q.area > 20]
          + [feature(clean(q.simplify(0.2)), {"kind": "verge", "accuracy": "approximate"}) for q in polys(verge) if q.area > 6])
    big = unary_union([d["line"].buffer(WIDTH[d["cls"]] / 2, cap_style=2, join_style=2) for d in roads
                       if d["cls"] in ("highway", "arterial", "main", "service", "divider", "road110", "road85", "collector")])
    near = carriage.intersection(outline.buffer(70))
    outer = clean(unary_union([big.intersection(outline.buffer(1500)), near]).difference(outline.buffer(-0.5)))
    if dividers is not None:
        outer = clean(outer.difference(dividers))
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
    # open land the newer plan colours as a graveyard (brown; "EXISTING GRAVE YARD" by Block F) is a graveyard,
    # not a park
    if emap is not None:
        keep_g, n_gy = [], 0
        for q in greens:
            sh = emap.colour_share(q, GRAVE_COLOURS) if q.area >= 800 else None
            g_ = largest(clean(q.buffer(-0.3, join_style=2))) if sh is not None and sh >= 0.45 else None
            if g_ is not None:
                blk_ = block_m(g_.representative_point())
                add_lm(g_, "graveyard", f"Graveyard (Block {blk_})", blk_, {"source": "Newer FDA City plan (emap.pk): EXISTING GRAVE YARD"})
                n_gy += 1
            else:
                keep_g.append(q)
        greens = keep_g
        print(f"graveyards the newer plan draws on land left open: {n_gy}")
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
    # Outside the society outline (by the gate) the faces of the road network do not reach: the paved strip with its
    # painted kerb between a main carriageway and its measured service road is laid out here (about 1 m by the gate).
    n_sep = 0
    mains_now = [d["line"] for d in roads if d["cls"] == "main"]
    for m in measured:
        ml = min(mains_now, key=lambda q: q.distance(m.interpolate(0.5, normalized=True)))
        side_pts, main_pts = [], []
        for s in np.arange(0, m.length + 0.01, 2.0):
            p = m.interpolate(min(s, m.length))
            side_pts.append((p.x, p.y))
            q = ml.interpolate(ml.project(p))
            main_pts.append((q.x, q.y))
        if len(side_pts) < 3:
            continue
        between = clean(Polygon(side_pts + main_pts[::-1]))
        sep = clean(between.difference(carriage.buffer(0.05)).difference(outline.buffer(0.5)))
        if dividers is not None:
            sep = clean(sep.difference(dividers.buffer(0.05)))
        for q in polys(sep):
            if q.area > 4 and not q.buffer(-0.2).is_empty:
                land_feats.append(feature(clean(q.simplify(0.15)), {"layer": "land", "kind": "strip", "use": "strip", "block": None, "size": None, "area_m2": round(q.area), "accuracy": "approximate", "outside": True}))
                n_sep += 1
    if n_sep:
        print(f"paved strips between the main road and its service roads outside the outline: {n_sep}")
    for q in polys(div_new) if div_new is not None else []:
        if q.area > 3:
            land_feats.append(feature(clean(q.simplify(0.1)), {"layer": "land", "kind": "strip", "use": "divider", "block": None, "size": None,
                                                            "area_m2": round(q.area), "accuracy": "approximate", "outside": not outline.contains(q.representative_point())}))
    for q in unplotted:              # society land that no block map draws anything on
        for r in polys(clean(q.simplify(0.3))):
            if r.area > 60:
                land_feats.append(feature(r, {"layer": "open", "kind": "open", "use": "not plotted on the official block maps", "area_m2": round(r.area), "accuracy": "approximate"}))
    write(out, "blocks", land_feats)
    # Sites from the older fdacity.pk maps that the newer plan (emap.pk) covers with plots or a street keep only
    # slivers between those plots (Mosque F-1 lies on plots 281-295, Shops Block A on a street, Park C-3 on plots
    # 87-112). A site with under 30 m2 of usable land (2.5 m in from every edge) is not on the newer plan: dropped.
    gone = []
    for f in list(landmarks):
        g_ = f["geometry"]
        if g_["type"] != "Polygon" or f["properties"]["kind"] == "roundabout":
            continue
        rg = g_["coordinates"]
        net = clean(Polygon([xy(*c) for c in rg[0]], [[xy(*c) for c in r] for r in rg[1:]]))
        if net.buffer(-2.5).area < 30:
            gone.append(f["properties"]["name"])
            landmarks.remove(f)
    print(f"sites the newer plan covers with plots or a street (slivers left), dropped: {gone}")
    gate_feat["properties"]["id"] = max([f["properties"]["id"] for f in landmarks] + [0]) + 1
    write(out, "landmarks", landmarks + [gate_feat])
    write(out, "buildings", [feature(clean(g.simplify(0.15)), pr) for g, pr in bfeats],
          {"data_note": "Buildings standing today: footprints detected on satellite imagery (Google Open Buildings, Microsoft ML Buildings, via Overture Maps). Heights are assumed."})
    write(out, "water", water)
    write(out, "parks", [f for f in landmarks if f["geometry"]["type"] == "Polygon" and f["properties"]["kind"] != "roundabout"]
          + [dict(f, properties=dict(f["properties"], kind="nala", name="Barani Nala")) for f in water if f["properties"]["kind"] == "nala_water"])
    write(out, "context", [feature(Point(*plan.to_m(*c["px"])), {"name": c["name"], "kind": "context"}) for c in feats["context_labels"]])
    note_emap = ("layout = 'FDA City plan (emap.pk), registered to the streets': outline read from the FDA City plan published on emap.pk (zoom 19, about 0.25 m), "
                 "fitted piece by piece to the OpenStreetMap streets (tools/emap_plan.py). plot_number is the number printed in the plot on that plan "
                 "(read by OCR, checked against the neighbouring plots); plot_no adds the block, and a letter where the plan repeats a number within a block. ") if emap is not None else ""
    write(out, "plots", plot_feats, {"data_note": note_emap + "layout = 'Official block map': outline read from the official FDA City block map and registered to the real streets. "
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
    # the small plot files the React pages read (search, plot details, dashboards)
    import importlib.util
    _spec = importlib.util.spec_from_file_location("make_index", os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_index.py"))
    _mi = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mi); _mi.main()

"""Generate Terralyt map data for FDA City (Faisalabad), block by block.

Sources (all in tools/source/):
  * osm_fda_area.json     OpenStreetMap roads around the society (real, georeferenced centrelines).
  * nala_traced.geojson   the Barani Nala storm drain, traced on Esri World Imagery.
  * plan_features.json    features digitised from the official FDA City plan and block maps
                          (Advice Associates / fdacity.pk). Each map sheet has its own control
                          points; parks, schools, mosques, zones and named roads are given in
                          sheet pixels, with the official area in kanal where the map prints it.
  * the overall plan image is downloaded on first run into tools/source/cache/ (git-ignored);
    its colours give the plot size of every street block (blue 20, pink 10, green 5 Marla)
    and decide which land belongs to the society.

Road sizes: right of way from the official maps (202, 110, 85, 60, 40 ft); paved carriageway
widths measured on z19 satellite imagery (0.25 m/px), see WIDTH below.

Rules the output must satisfy (checked by tools/audit.py):
  * no plot overlaps a road, the nalla, a facility or another plot;
  * every plot fronts a road (existing or a planned 40 ft street);
  * no bare land: whatever is not road, plot or facility becomes green open space.

Everything derived from the plan is accuracy="approximate". Plot numbers, status,
development class and heights are SAMPLE values with a fixed seed.

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
                    if (not in_zone and (plotted < 0.42 or smp["bg"] > 0.55)) or beyond_f_strip(cen):
                        k2 = "outside"
                    elif inner is None or inner.buffer(-5.0).is_empty:
                        k2 = "greenbelt"
                    else:
                        k2 = "parcel"
                        cols = {"10 Marla": smp["pink"], "5 Marla": smp["green"], "20 Marla": smp["blue"]}
                        size = max(cols, key=cols.get) if max(cols.values()) > 0.02 else "10 Marla"
                P.append({"land": r, "inner": inner if k2 in ("parcel", "greenbelt") else None, "kind": k2, "c": cen, "blk": block_m(cen),
                          "area": r.area, "size": size, "free": inner if k2 == "parcel" else None,
                          "angle": obb(inner)["angle"] if (k2 == "parcel" and inner is not None) else 0})
    print("land:", dict(Counter(p["kind"] for p in P)))
    parcels = [p for p in P if p["kind"] == "parcel"]

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
            cand = [p for p in parcels if p["free"] is not None and p["free"].intersects(poly) and p["free"].intersection(poly).area > 20]
            if cand and sum(p["free"].area for p in cand) <= target * 1.08:
                poly = unary_union([p["free"] for p in cand]).buffer(1)
            elif cand:
                lo_s, hi_s = 0.4, 3.0
                for _ in range(16):
                    mid = (lo_s + hi_s) / 2
                    sc = affinity.scale(poly, mid, mid, origin=poly.centroid)
                    if sum(p["free"].intersection(sc).area for p in cand) < target:
                        lo_s = mid
                    else:
                        hi_s = mid
                poly = affinity.scale(poly, hi_s, hi_s, origin=poly.centroid)
            whole_frac = 0.93
        got = []
        for p in (cand if cand is not None else parcels):
            if p["free"] is None or not p["free"].intersects(poly):
                continue
            part = p["free"].intersection(poly)
            if part.area < 20:
                continue
            whole = part.area > whole_frac * p["free"].area
            got.append((p, p["free"] if whole else part, whole))
        if not got:
            return None
        site = largest(unary_union([g for _, g, _ in got]))
        if site is None or site.area < min_area:
            return None
        for p, g, whole in got:
            if g.intersection(site).area < 0.5 * g.area:
                continue                      # this piece is not part of the site: leave its parcel untouched
            if whole:
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
    plot_geo, planned_streets, planned_lines, greens = [], [], [], []
    for p in sorted(parcels, key=lambda p: (p["blk"], -round(p["c"].y / 40), p["c"].x)):
        if p["free"] is None or not outline.buffer(3).contains(p["land"]):
            continue
        for region in polys(p["free"]):
            if region.area < 100:
                greens.append(region)
                continue
            size = p["size"] or "10 Marla"
            side = None
            if main_u.distance(region) < 30:                # one row of commercial plots faces the boulevard
                nearest = min(main_lines, key=lambda m: m.distance(region))
                v = direction_at(nearest, region.centroid)
                a = math.radians(p["angle"])
                if abs(v[0] * math.cos(a) + v[1] * math.sin(a)) > 0.9:
                    c = region.centroid
                    rot = affinity.rotate(region, -p["angle"], origin=c)
                    _, miny, _, maxy = rot.bounds
                    lo_pt = affinity.rotate(Point(rot.centroid.x, miny), p["angle"], origin=c)
                    hi_pt = affinity.rotate(Point(rot.centroid.x, maxy), p["angle"], origin=c)
                    side = "lo" if main_u.distance(lo_pt) < main_u.distance(hi_pt) else "hi"
            plots, streets, lines = subdivide(region, p["angle"], size, side)
            planned_streets += streets
            planned_lines += lines
            plot_geo += [(pg, sz) for pg, sz in plots]
            used = unary_union([pg.buffer(0.05) for pg, _ in plots] + [s.buffer(0.05) for s in streets]) if (plots or streets) else None
            rest = region.difference(used) if used is not None else region
            greens += [q for q in polys(rest) if q.area > 25 and not q.buffer(-0.8).is_empty]
    # every plot must front a road
    access = unary_union([surf, reserve] + planned_streets).buffer(FOOTPATH + 2.2)
    kept = [(pg, sz) for pg, sz in plot_geo if pg.intersects(access)]
    greens += [pg for pg, sz in plot_geo if not pg.intersects(access)]
    print(f"plots: {len(kept)} kept, {len(plot_geo) - len(kept)} without road frontage turned into green space; planned 40 ft street pieces: {len(planned_streets)}")

    plot_feats = []
    counters = Counter()
    for pid, (pg, sz) in enumerate(kept, 1):
        pg = clean(pg.simplify(0.05))
        blk = block_m(pg.centroid)
        counters[blk] += 1
        key = (blk, counters[blk])
        ptype = "Commercial" if sz == "Commercial" else "Residential"
        cx, cy = pg.centroid.x, pg.centroid.y
        d_main = main_u.distance(pg.centroid)
        noise = 0.5 * math.sin(cx / 230 + 1.3) * math.cos(cy / 260 - 0.4) + 0.5 * math.sin((cx + cy) / 410)
        dev = 0.98 - min(d_main, 1400) / 1400 * 0.9 + 0.26 * noise + (h01("dev", *key) - 0.5) * 0.3
        dev_class = "High" if dev > 0.68 else "Medium" if dev > 0.36 else "Low"
        r = h01("status", *key)
        status = "Sold" if r < 0.42 else "Available" if r < 0.72 else "Reserved" if r < 0.85 else "Unknown"
        built_p = 0.92 if dev_class == "High" else 0.55 if dev_class == "Medium" else 0.18
        if status == "Available":
            built_p *= 0.3
        built = h01("built", *key) < built_p
        if built:
            s = h01("storeys", *key)
            storeys = 3 if (s < 0.18 or ptype == "Commercial") else 2 if s < 0.6 else 1
            height = 3.5 * storeys
        else:
            storeys, height = 0, 0.4
        src = "Not recorded" if status == "Unknown" else ["Society record", "Developer record", "Transaction record"][int(h01("src", *key) * 3)]
        conf = "Low" if status == "Unknown" else ["High", "High", "Medium"][int(h01("conf", *key) * 3)]
        lon, lat = ll(cx, cy)
        plot_feats.append(feature(pg, {
            "id": pid, "plot_no": f"{blk}-{counters[blk]}", "block": "Block " + blk,
            "size": sz, "type": ptype, "status": status, "dev_class": dev_class,
            "built": built, "storeys": storeys, "height": round(height, 1), "height_source": "assumed",
            "source": src, "confidence": conf, "lat": lat, "lon": lon,
            "area_m2": round(pg.area), "accuracy": "approximate"}))
    print(f"plots per block: {dict(sorted(counters.items()))}")
    print("sizes:", dict(Counter(f["properties"]["size"] for f in plot_feats)))

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
    for d in roads:
        for part in lines_of(d["line"].intersection(clip)):
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
    write(out, "roads", road_feats)
    planned_carriage = [clean(q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2)) for q in planned_streets]
    box_o = outline.buffer(1.0)
    inner_carriage = clean(unary_union([carriage.intersection(box_o)] + [q for q in planned_carriage if not q.is_empty]))
    inner_row = clean(unary_union([surf.intersection(box_o), reserve.intersection(box_o)] + planned_streets))
    medians = unary_union([p["land"] for p in P if p["kind"] in ("median", "strip", "island")])
    verge = clean(inner_row.difference(inner_carriage.buffer(0.05)).difference(medians.buffer(0.05)).difference(nala.buffer(NALA_CH + 0.5)))
    write(out, "road_surface",
          [feature(clean(q.simplify(0.2)), {"kind": "carriageway", "accuracy": "approximate", "source": "widths measured on satellite imagery"}) for q in polys(inner_carriage) if q.area > 20]
          + [feature(clean(q.simplify(0.2)), {"kind": "verge", "accuracy": "approximate"}) for q in polys(verge) if q.area > 6])
    big = unary_union([d["line"].buffer(WIDTH[d["cls"]] / 2, cap_style=2, join_style=2) for d in roads
                       if d["cls"] in ("highway", "arterial", "main", "service", "divider", "road110", "road85", "collector")])
    near = carriage.intersection(outline.buffer(70))
    outer = clean(unary_union([big.intersection(outline.buffer(1500)), near]).difference(outline.buffer(-0.5)))
    write(out, "outer_roads", [feature(clean(q.simplify(0.3)), {"kind": "road", "accuracy": "approximate"}) for q in polys(outer) if q.area > 30])
    land_feats = []
    for p in P:
        if p["kind"] == "outside":
            continue
        use = "plots" if p["kind"] == "parcel" else p["kind"]
        land_feats.append(feature(p["land"], {"layer": "land", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "size": p["size"], "area_m2": round(p["area"]), "accuracy": "approximate"}))
        if p["inner"] is not None:
            land_feats.append(feature(clean(p["inner"].simplify(0.2)), {"layer": "inner", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "accuracy": "approximate"}))
    for p in P:                      # land enclosed by the society that the plan leaves blank
        if p["kind"] == "outside" and outline.buffer(-2).contains(p["land"]):
            greens.append(p["land"])
    for q in greens:
        for r in polys(clean(q.simplify(0.15))):
            if r.area > 20:
                land_feats.append(feature(r, {"layer": "green", "kind": "green", "use": "open space", "area_m2": round(r.area), "accuracy": "approximate"}))
    write(out, "blocks", land_feats)
    write(out, "landmarks", landmarks)
    write(out, "water", water)
    write(out, "parks", [f for f in landmarks if f["geometry"]["type"] == "Polygon" and f["properties"]["kind"] != "roundabout"]
          + [dict(f, properties=dict(f["properties"], kind="nala", name="Barani Nala")) for f in water if f["properties"]["kind"] == "nala_water"])
    write(out, "context", [feature(Point(*plan.to_m(*c["px"])), {"name": c["name"], "kind": "context"}) for c in feats["context_labels"]])
    write(out, "plots", plot_feats, {"data_note": "Plot outlines follow the street blocks of the official plan and OpenStreetMap; plot attributes are generated samples (accuracy=approximate)."})

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

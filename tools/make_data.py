"""Generate Terralyt map data for FDA City (Faisalabad), block by block.

Sources (all in tools/source/):
  * osm_fda_area.json     OpenStreetMap roads, canals and motorways around the society
                          (real, georeferenced road centrelines).
  * nala_traced.geojson   the Barani Nala storm drain, traced on Esri World Imagery and,
                          for its south-west part, guided by the official plan.
  * plan_features.json    features digitised from the official FDA City plan and block
                          maps (Advice Associates / fdacity.pk): georeference control
                          points, block rules, parks, block complexes (Jamia Mosque,
                          school, playground, commercial), special zones and facilities.
  * the official plan image itself is downloaded on first run into tools/source/cache/
    (git-ignored) and used to read the plot size of every street block from its colour
    (blue = 20 Marla, pink = 10 Marla, green = 5 Marla) and to decide which land is part
    of the society.

Everything derived from the plan is accuracy="approximate". Plot numbers, status,
development class and heights are SAMPLE values with a fixed seed.

usage (from the repo root):  python -I tools/make_data.py [--preview out.png]
needs: pip install shapely numpy pillow   (matplotlib for --preview)
writes data/boundary, roads, road_surface, outer_roads, blocks, landmarks, water,
parks, plots and context .geojson
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
# Road sizes. ROW = right of way from the official FDA City maps (202, 85, 60 and 40 ft roads);
# WIDTH = paved carriageway measured on Esri World Imagery (z19, 0.25 m/px) in November 2026:
#   202 ft boulevard: service road 7.5 | paved strip 6.5 | carriageway 10.75 | planted median 5 | carriageway 10.75 | strip | service
#   85 ft road: 19 m four-lane carriageway;  60 ft road: 6.5 m;  40 ft street: 5 m
#   roundabouts: island 60 m across with a 17 m ring road (south-west one: island 46 m, ring 23.5 m)
WIDTH = {"main": 10.75, "service": 7.5, "arterial": 9.0, "divider": 19.0, "collector": 6.5, "residential": 5.0,
         "roundabout": 17.0, "highway": 12.0, "planned": 5.0}
ROW = {"main": 10.75, "service": 9.5, "arterial": 14.0, "divider": 85 * FT, "collector": 60 * FT, "residential": 40 * FT,
       "roundabout": 17.0, "highway": 30.0, "planned": 40 * FT}
ROUNDABOUT_ISLAND = {"big": 30.0, "small": 23.0}   # island radius in metres, measured
SIDEWALK = 0.6
LANE = 6.0
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


def largest_line(g):
    ls = lines_of(g)
    return max(ls, key=lambda q: q.length)


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
# official plan: georeference and colour classification
# ---------------------------------------------------------------------------------
class Plan:
    def __init__(self, feats):
        self.f = feats
        X = np.array([complex(p["px"][0], -p["px"][1]) for p in feats["control_points"]])
        Z = np.array([complex(*xy(*p["lonlat"])) for p in feats["control_points"]])
        sol, *_ = np.linalg.lstsq(np.vstack([X, np.ones_like(X)]).T, Z, rcond=None)
        self.k, self.t = sol
        res = [abs(self.k * X[i] + self.t - Z[i]) for i in range(len(X))]
        print(f"plan georeference: {abs(self.k):.3f} m/px, rotation {math.degrees(np.angle(self.k)):.2f} deg, residuals {[round(float(r), 1) for r in res]} m")

    def to_m(self, x, y):
        z = self.k * complex(x, -y) + self.t
        return (z.real, z.imag)

    def to_px(self, e, n):
        w = (complex(e, n) - self.t) / self.k
        return (w.real, -w.imag)

    def poly(self, pts):
        return Polygon([self.to_m(*p) for p in pts])

    def rect(self, r):
        x0, y0, x1, y1 = r
        return self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

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
        """Fractions of plan colour classes inside a polygon (metric)."""
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
    env = plan.poly(feats["envelope"]).buffer(0)
    bl = feats["blocks"]

    # ---- block rule (plan pixels) -----------------------------------------------------
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
    main_poly = LineString([plan.to_m(*p) for p in [(1585, 487), (1220, 487), (945, 487)] + [tuple(p) for p in bl["curve"][1:7]]])
    sw_poly = LineString([plan.to_m(*p) for p in [(560, 635), (400, 643), (200, 656)]])
    dividers = [LineString([plan.to_m(x, 0), plan.to_m(x, 1150)]) for x in bl["divider_x"]]
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
        else:
            cls = "residential"
        roads.append({"e": e, "line": line, "cls": cls})

    def parallel_to(line, ref, tol=0.88):
        p0, p1 = line.coords[0], line.coords[-1]
        L = math.dist(p0, p1) or 1
        u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
        s = ref.project(line.interpolate(0.5, normalized=True))
        a, b = ref.interpolate(max(0, s - 20)), ref.interpolate(min(ref.length, s + 20))
        lr = math.dist((a.x, a.y), (b.x, b.y)) or 1
        v = ((b.x - a.x) / lr, (b.y - a.y) / lr)
        return abs(u[0] * v[0] + u[1] * v[1]) > tol

    for d in roads:
        if d["cls"] not in ("residential", "arterial"):
            continue
        c = d["line"].interpolate(0.5, normalized=True)
        if main_poly.distance(c) < 32 and parallel_to(d["line"], main_poly):
            d["cls"] = "main" if d["e"]["tags"].get("oneway") == "yes" else "service"
        elif sw_poly.distance(c) < 32 and parallel_to(d["line"], sw_poly):
            d["cls"] = "arterial"
        elif any(dv.distance(c) < 16 and parallel_to(d["line"], dv, 0.95) for dv in dividers):
            d["cls"] = "divider"
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
    nala = largest_line(nala_full.intersection(env.buffer(200)))
    nala_zone = nala.buffer(NALA_BANK)
    print(f"nalla: {nala.length:.0f} m in the plan area")

    # ---- surfaces and faces ---------------------------------------------------------------
    ring_geo = {}
    for d in roads:
        if d["cls"] == "roundabout":
            pg = Polygon(d["line"].coords) if d["line"].is_ring else d["line"].convex_hull
            c = pg.centroid
            rc = sum(Point(q).distance(c) for q in d["line"].coords) / len(d["line"].coords)
            ri = ROUNDABOUT_ISLAND["big"] if rc > 34 else ROUNDABOUT_ISLAND["small"]
            ro = ri + (17.0 if rc > 34 else 23.5)
            ring_geo[id(d)] = (c, ri, ro)
    def road_poly(d, widths):
        if d["cls"] == "roundabout":
            c, ri, ro = ring_geo[id(d)]
            return c.buffer(ro, 64).difference(c.buffer(ri, 64))
        return d["line"].buffer(widths[d["cls"]] / 2, join_style=2, mitre_limit=3)
    surf = unary_union([road_poly(d, ROW) for d in roads]).buffer(0.3).buffer(-0.3)          # right of way
    carriage = unary_union([road_poly(d, WIDTH) for d in roads]).buffer(0.2).buffer(-0.2)     # paved carriageway
    inner_lines = [d["line"].intersection(env.buffer(30)) for d in roads if d["cls"] != "highway"]
    noded = unary_union([l for l in inner_lines if not l.is_empty] + [LineString(env.exterior.coords), nala])
    faces = [f for f in polygonize(noded) if env.contains(f.representative_point())]
    print(f"faces: {len(faces)}")

    rbs = []
    for d in roads:
        if d["cls"] == "roundabout" and env.buffer(50).contains(d["line"].centroid):
            c, ri, ro = ring_geo[id(d)]
            rbs.append({"c": c, "poly": c.buffer(ri + 1, 64), "ri": ri, "ro": ro})
    rb_zone = unary_union([r["poly"].buffer(2) for r in rbs]) if rbs else None
    mains = [d["line"] for d in roads if d["cls"] == "main"]
    services = [d["line"] for d in roads if d["cls"] == "service"]

    zones = [dict(z, poly=plan.poly(z["px"])) for z in feats["zones"]]
    inside_zones = unary_union([z["poly"] for z in zones if not z.get("outside")])

    pieces = []
    for f in faces:
        land = f.difference(surf).difference(nala_zone)
        for q in sorted(polys(land), key=lambda q: -q.area):
            if q.area < 40:
                continue
            ins = [r for r in polys(q.buffer(-SIDEWALK)) if r.area >= 25]
            if len(ins) <= 1:
                pieces.append(q)
            else:
                for r in ins:
                    sub = largest(q.intersection(r.buffer(SIDEWALK + 0.4, join_style=2)))
                    if sub is not None and sub.area >= 40:
                        pieces.append(sub)

    P = []
    for q in pieces:
        q = q.simplify(0.2)
        cen = q.representative_point()
        inner = largest(q.buffer(-SIDEWALK))
        mrr = q.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        touching = sum(1 for m in mains if m.distance(q) < WIDTH["main"] / 2 + 3)
        touching_srv = sum(1 for m in services if m.distance(q) < ROW["service"] / 2 + 3)
        smp = plan.sample(q)
        plotted = smp["pink"] + smp["green"] + smp["blue"] + smp["other"]
        in_zone = (not inside_zones.is_empty) and q.intersection(inside_zones).area > 0.3 * q.area
        if rb_zone is not None and q.within(rb_zone):
            kind = "island"
        elif touching >= 2 and short < 45:
            kind = "median"
        elif touching >= 1 and touching_srv >= 1 and short < 20:
            kind = "strip"          # paved strip between a boulevard carriageway and its service road
        elif not in_zone and (plotted < 0.42 or smp["bg"] > 0.55):
            kind = "outside"
        elif beyond_f_strip(cen):
            kind = "outside"
        elif inner is None or inner.buffer(-6.5).is_empty:
            kind = "greenbelt"
        else:
            kind = "parcel"
        size = None
        if kind == "parcel":
            cols = {"10 Marla": smp["pink"], "5 Marla": smp["green"], "20 Marla": smp["blue"]}
            size = max(cols, key=cols.get) if max(cols.values()) > 0.02 else "10 Marla"
        P.append({"land": q, "inner": inner if kind in ("parcel", "greenbelt") else None, "kind": kind, "c": cen,
                  "blk": block_m(cen), "area": q.area, "size": size, "free": inner if kind == "parcel" else None})
    print("land:", dict(Counter(p["kind"] for p in P)))
    parcels = [p for p in P if p["kind"] == "parcel"]

    # ---- landmarks (carved out of parcels) -------------------------------------------------------
    landmarks = []

    def add_lm(poly, kind, name, blk, proposed=False, extra=None):
        if poly is None or poly.area < 60:
            return None
        props = {"id": len(landmarks) + 1, "kind": kind, "name": name, "block": ("Block " + blk) if blk else None,
                 "area_kanal": round(poly.area / KANAL, 1), "proposed": proposed, "obb": obb(poly),
                 "accuracy": "approximate", "source": "Official FDA City plan and block maps"}
        if extra:
            props.update({k: v for k, v in extra.items() if v is not None})
        landmarks.append(feature(poly.simplify(0.2), props))
        return props

    def carve(poly, whole_frac=0.62, min_area=60):
        got = []
        for p in parcels:
            if p["free"] is None or not p["free"].intersects(poly):
                continue
            part = p["free"].intersection(poly)
            if part.area < 20:
                continue
            if part.area > whole_frac * p["free"].area:
                got.append(p["free"])
                p["free"] = None
            else:
                got.append(part)
                rest = p["free"].difference(poly.buffer(3.0, join_style=2))
                p["free"] = rest if rest.area > 30 else None
        u = unary_union(got) if got else None
        return largest(u) if u is not None and u.area >= min_area else None

    for z in zones:
        if z.get("outside"):
            add_lm(z["poly"], z["kind"], z["name"], z.get("block"), z.get("proposed", False), {"outside": True})
        elif z["kind"] != "homes":
            add_lm(carve(z["poly"], 0.4), z["kind"], z["name"], z.get("block"), z.get("proposed", False))
    for c in feats["complexes"]:
        x0, y0, x1, y1 = c["px"]
        for part in feats["complex_parts"][c["parts"]]:
            rx0, ry0, rx1, ry1 = part["r"]
            r = (x0 + (x1 - x0) * rx0, y0 + (y1 - y0) * ry0, x0 + (x1 - x0) * rx1, y0 + (y1 - y0) * ry1)
            add_lm(carve(plan.rect(r).buffer(-2.0, join_style=2), 0.7), part["kind"], part["name"].format(b=c["block"]), c["block"])
    homes = next(z for z in zones if z["kind"] == "homes")
    homes_land = carve(homes["poly"], 0.35, 500)
    for f in feats["facilities"]:
        add_lm(carve(plan.rect(f["px"]).buffer(2, join_style=2), 0.75, 40), f["kind"], f["name"], f["block"])
    seq = Counter()
    for pk in feats["parks"]:
        poly = carve(plan.rect(pk["px"]), 0.6)
        if poly is None:
            continue
        seq[pk["block"]] += 1
        add_lm(poly, "park", pk.get("name") or f"Park {pk['block']}-{seq[pk['block']]}", pk["block"], extra={"kanal_official": pk.get("kanal")})
    if homes_land is not None:
        add_lm(homes_land, "homes", homes["name"], homes.get("block"), extra={"note": "Reserved for the FDA City Homes housing scheme"})
    designs = ["rings", "tree", "fountain", "rings"]
    rbs.sort(key=lambda r: -r["c"].x)
    for n_, r in enumerate(rbs):
        isl = r["c"].buffer(r["ri"], 64)
        if isl.is_empty or isl.area < 20:
            continue
        add_lm(isl, "roundabout", f"Roundabout {n_ + 1}", None, extra={"radius": round(math.sqrt(isl.area / math.pi), 1), "monument": designs[n_ % len(designs)]})
    print("landmarks:", dict(Counter(f["properties"]["kind"] for f in landmarks)))

    # ---- planned streets inside very large parcels the OSM network does not cover ---------------
    def subdivide_large(p):
        region = p["free"]
        o = obb(region)
        c = region.centroid
        rot = affinity.rotate(region, -o["angle"], origin=c)
        minx, miny, maxx, maxy = rot.bounds
        dep = SIZES[p["size"] or "10 Marla"][1]
        band = 2 * dep + WIDTH["planned"]
        cuts = []
        y = miny + 2 * dep
        while y < maxy - dep:
            cuts.append(box(minx - 5, y, maxx + 5, y + WIDTH["planned"]))
            y += band
        x = minx + 180
        while x < maxx - 60:
            cuts.append(box(x, miny - 5, x + WIDTH["planned"], maxy + 5))
            x += 180
        if not cuts:
            return [region], []
        cutu = affinity.rotate(unary_union(cuts), o["angle"], origin=c)
        return [q for q in polys(region.difference(cutu)) if q.area > 60], polys(cutu.intersection(region))

    planned_streets, extra_free = [], []
    for p in parcels:
        if p["free"] is not None and p["free"].area > 30000:
            parts, streets = subdivide_large(p)
            planned_streets += streets
            p["free"] = None
            for q in parts:
                inner = largest(q.buffer(-SIDEWALK))
                if inner is not None:
                    extra_free.append(dict(p, free=inner, c=q.representative_point()))
    if planned_streets:
        print(f"planned streets: {len(planned_streets)} pieces in large parcels without OSM streets")

    # ---- plots ---------------------------------------------------------------------------------
    plot_feats = []
    counters = Counter()
    pid = 0
    corridor = 31 + 40     # half of the 202 ft corridor plus one row of commercial plots
    main_u = unary_union(mains) if mains else None
    regions = [p for p in parcels if p["free"] is not None] + extra_free
    regions.sort(key=lambda p: (p["blk"], -p["c"].y, p["c"].x))
    for p in regions:
        for region in polys(p["free"]):
            if region.area < 120:
                continue
            blk, size = p["blk"], p["size"] or "10 Marla"
            near_main = main_u is not None and main_u.distance(region) < corridor
            w, dep = SIZES["Commercial" if near_main else size]
            o = obb(region)
            c = region.centroid
            rot = affinity.rotate(region, -o["angle"], origin=c)
            minx, miny, maxx, maxy = rot.bounds
            width_b = maxy - miny
            if width_b < dep * 0.6:
                dep = width_b
            bands, y = [], miny
            while y + dep <= maxy + 0.01:
                bands.append((y, y + dep))
                if y + 2 * dep <= maxy + 0.01:
                    bands.append((y + dep, y + 2 * dep))
                else:
                    break
                y += 2 * dep + LANE
            if len(bands) == 1 and width_b > dep * 1.4:
                bands = [(miny, miny + dep), (maxy - dep, maxy)]
            for (y0, y1) in bands:
                n = max(1, int((maxx - minx) / w))
                for k in range(n):
                    x0 = minx + k * w
                    x1 = maxx if k == n - 1 else x0 + w
                    pg = largest(box(x0, y0, x1, y1).intersection(rot))
                    if pg is None or pg.area < w * dep * 0.45:
                        continue
                    pg = affinity.rotate(pg, o["angle"], origin=c).simplify(0.15)
                    blk = block_m(pg.centroid)          # block from the plot's own position on the plan
                    pid += 1
                    counters[blk] += 1
                    key = (blk, counters[blk])
                    commercial = near_main and main_u.distance(pg.centroid) < corridor
                    ptype = "Commercial" if commercial else "Residential"
                    psize = "Commercial" if commercial else size
                    cx, cy = pg.centroid.x, pg.centroid.y
                    d_main = main_u.distance(pg.centroid) if main_u is not None else 500
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
                        "size": psize, "type": ptype, "status": status, "dev_class": dev_class,
                        "built": built, "storeys": storeys, "height": round(height, 1), "height_source": "assumed",
                        "source": src, "confidence": conf, "lat": lat, "lon": lon,
                        "area_m2": round(pg.area), "accuracy": "approximate"}))
    print(f"plots: {len(plot_feats)}  per block: {dict(sorted(counters.items()))}")
    print("sizes:", dict(Counter(f["properties"]["size"] for f in plot_feats)))

    # ---- society outline ------------------------------------------------------------------------
    society = [p["land"] for p in P if p["kind"] in ("parcel", "greenbelt", "median", "island", "strip")]
    outline = largest(unary_union([q.buffer(16, join_style=2) for q in society]).buffer(-13, join_style=2))
    outline = Polygon(outline.exterior).simplify(1.5)
    cen = outline.centroid
    axis_a, axis_b = plan.to_m(945, 487), plan.to_m(1220, 487)
    axis_deg = math.degrees(math.atan2(axis_b[1] - axis_a[1], axis_b[0] - axis_a[0]))
    bprops = {"name": "FDA City", "city": "Faisalabad", "source": "Official FDA City plan, georeferenced; streets from OpenStreetMap",
              "accuracy": "approximate", "area_km2": round(outline.area / 1e6, 2), "centre_lon": ll(cen.x, cen.y)[0],
              "centre_lat": ll(cen.x, cen.y)[1], "lat_ref": LAT_REF, "axis_deg": round(axis_deg, 2), "sidewalk_m": SIDEWALK,
              "blocks": {b: list(ll(*plan.to_m(*p))) for b, p in bl["label_px"].items()}}
    print(f"society outline: {outline.area/1e6:.2f} km2")

    # ---- water ------------------------------------------------------------------------------
    water = []
    nprops = {"name": "Barani Nala (storm drain)", "source": "Traced from Esri World Imagery and the official plan", "accuracy": "approximate"}
    cut = surf.buffer(0.6)
    channel = nala.buffer(NALA_CH, cap_style=2)
    wall = nala.buffer(NALA_CH + 0.45, cap_style=2).difference(nala.buffer(NALA_CH - 0.05, cap_style=2))
    bank = nala.buffer(NALA_BANK, cap_style=2).difference(nala.buffer(NALA_CH + 0.45, cap_style=2)).difference(surf)
    for q in polys(channel.difference(cut)):
        if q.area > 5:
            water.append(feature(q.simplify(0.15), dict(nprops, kind="nala_water")))
    for q in polys(wall.difference(cut)):
        if q.area > 1:
            water.append(feature(q.simplify(0.1), dict(nprops, kind="nala_wall")))
    for q in polys(bank):
        if q.area > 5:
            water.append(feature(q.simplify(0.2), dict(nprops, kind="nala_bank")))
    water.append(feature(nala, dict(nprops, kind="nala_line", width_m=round(2 * NALA_CH, 1), length_m=round(nala.length))))
    sb = surf.buffer(1.5)   # no trees on roads
    for side in (-1, 1):
        for q in lines_of(nala.offset_curve(side * (NALA_CH + 3.2))):
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
            t = d["e"]["tags"]
            name = t.get("name") or {"main": "Main Boulevard (202 ft)", "service": "Main Boulevard service road", "divider": "85 ft road",
                                     "collector": "60 ft road", "residential": "40 ft street"}.get(d["cls"])
            road_feats.append(feature(part, {"osm_id": d["e"]["id"], "name": name, "class": d["cls"], "width_m": round(WIDTH[d["cls"]], 1),
                                             "row_m": round(ROW[d["cls"]], 1),
                                             "oneway": t.get("oneway") == "yes", "source": "OpenStreetMap", "accuracy": "georeferenced"}))
    write(out, "roads", road_feats)
    planned_carriage = [q.buffer(-(ROW["planned"] - WIDTH["planned"]) / 2, join_style=2) for q in planned_streets]
    inner_carriage = unary_union([carriage.intersection(outline.buffer(1.0))] + planned_carriage)
    inner_row = unary_union([surf.intersection(outline.buffer(1.0))] + planned_streets)
    verge = inner_row.difference(inner_carriage.buffer(0.05))
    write(out, "road_surface",
          [feature(q.simplify(0.25), {"kind": "carriageway", "accuracy": "approximate", "source": "widths measured on satellite imagery"}) for q in polys(inner_carriage) if q.area > 20]
          + [feature(q.simplify(0.25), {"kind": "verge", "accuracy": "approximate"}) for q in polys(verge) if q.area > 8])
    outer = carriage.intersection(outline.buffer(700)).difference(outline.buffer(-0.5))
    write(out, "outer_roads", [feature(q.simplify(0.3), {"kind": "road", "accuracy": "approximate"}) for q in polys(outer) if q.area > 20])
    land_feats = []
    for p in P:
        if p["kind"] == "outside":
            continue
        use = "plots" if p["kind"] == "parcel" else p["kind"]
        land_feats.append(feature(p["land"], {"layer": "land", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "size": p["size"], "area_m2": round(p["area"]), "accuracy": "approximate"}))
        if p["inner"] is not None:
            land_feats.append(feature(p["inner"].simplify(0.2), {"layer": "inner", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "accuracy": "approximate"}))
    write(out, "blocks", land_feats)
    write(out, "landmarks", landmarks)
    write(out, "water", water)
    write(out, "parks", [f for f in landmarks if f["geometry"]["type"] == "Polygon" and f["properties"]["kind"] != "roundabout"]
          + [dict(f, properties=dict(f["properties"], kind="nala", name="Barani Nala")) for f in water if f["properties"]["kind"] == "nala_water"])
    write(out, "context", [feature(Point(*plan.to_m(*c["px"])), {"name": c["name"], "kind": "context"}) for c in feats["context_labels"]])
    write(out, "plots", plot_feats, {"data_note": "Plot outlines follow the street blocks of the official plan and OpenStreetMap; plot attributes are generated samples (accuracy=approximate)."})

    if args.preview:
        preview(args.preview, outline, P, landmarks, plot_feats, road_feats, nala, plan)


def preview(path, outline, P, landmarks, plot_feats, road_feats, nala, plan):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(18, 18), dpi=100)
    ax.set_aspect("equal")
    BC = {"A": "#cfe0f0", "B": "#e8d6f0", "C": "#d6f0dc", "D": "#f0e6d0", "E": "#f0d6d6", "F": "#e0e0c8"}
    SZ = {"20 Marla": "#9fb8e8", "10 Marla": "#f0a8c8", "5 Marla": "#b8e098", "Commercial": "#f0b060"}
    for p in P:
        col = "#f4f4f4" if p["kind"] == "outside" else "#6fae5f" if p["kind"] in ("median", "island", "greenbelt") else BC[p["blk"]]
        ax.fill(*p["land"].exterior.xy, color=col, ec="none")
    for f in plot_feats:
        pg = Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]])
        ax.fill(*pg.exterior.xy, color=SZ[f["properties"]["size"]], ec="#555", lw=0.1)
    KC = {"park": "#3f9f4f", "playground": "#8fd16a", "school": "#d98b5f", "mosque": "#ffffff", "commercial": "#4a86d0", "dispensary": "#ff9090",
          "hospital": "#e05c5c", "sports": "#c7a0e0", "civic": "#c9b48a", "stadium": "#60d0a0", "university": "#e0b0a0", "cinema": "#9050c0",
          "multipurpose": "#8080d0", "grid": "#888", "graveyard": "#8a8a6a", "cng": "#e0e070", "shrine": "#2e8a57", "homes": "#f0e0b0",
          "metro": "#f0e040", "sewerage": "#6a8a9a", "roundabout": "#2f7f2f"}
    for f in landmarks:
        pr = f["properties"]
        pg = Polygon([xy(*c) for c in f["geometry"]["coordinates"][0]])
        ax.fill(*pg.exterior.xy, color=KC.get(pr["kind"], "#f0f"), ec="k", lw=0.5, zorder=4)
        if pr["kind"] != "roundabout":
            ax.annotate(pr["name"].replace(" (", "\n("), (pg.centroid.x, pg.centroid.y), fontsize=5, ha="center", va="center", zorder=6)
    for f in road_feats:
        cs = [xy(*c) for c in f["geometry"]["coordinates"]]
        lw = {"main": 2.4, "service": 1.4, "divider": 2.0, "collector": 1.4, "arterial": 1.6, "highway": 2.6, "roundabout": 1.5}.get(f["properties"]["class"], 0.4)
        ax.plot([c[0] for c in cs], [c[1] for c in cs], color="#333", lw=lw, zorder=5)
    ax.plot(*nala.xy, color="#1f78d0", lw=2.5, zorder=6)
    ax.plot(*outline.exterior.xy, color="red", lw=1.5, zorder=7)
    for b, p in plan.f["blocks"]["label_px"].items():
        x, y = plan.to_m(*p)
        ax.annotate("BLOCK " + b, (x, y), fontsize=20, weight="bold", ha="center", color="#102030", alpha=0.65, zorder=8)
    fig.savefig(path, bbox_inches="tight")
    print("preview:", path)


if __name__ == "__main__":
    main()

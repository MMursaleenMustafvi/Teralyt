"""Generate Terralyt map data for FDA City (Faisalabad).

Real geometry (accuracy="georeferenced"):
  * society boundary and every road centreline come from OpenStreetMap
    (tools/source/osm_fda_city.json, Overpass export of OSM way 287541676 and the
    highways inside it). Roundabouts are the OSM junction=roundabout rings.

Traced from satellite imagery (accuracy="approximate"):
  * the Barani Nala storm drain (tools/source/nala_traced.geojson, traced on
    Esri World Imagery and snapped to the channel); no plots are placed on it
    or on its banks, and bridges are added where roads cross it.

Derived geometry (accuracy="approximate"):
  * road surfaces use the official FDA City road widths (202 ft boulevard,
    60/85 ft collectors, 40 ft streets) buffered around the OSM centrelines;
  * land parcels are the faces of the road network minus the road surfaces;
  * landmarks follow the official FDA City block maps: every block gets its
    Jamia Mosque, Primary School, Playground, Commercial Centre and numbered
    parks; the hospital / sports complex / public building ("Area for FDA City
    Homes"), the proposed university, cricket stadium and IMAX theatre, the
    multi-purpose zone, grid station, graveyard, CNG station, shrine and the
    main gate are placed where the brochure shows them. Positions are
    approximate until a surveyed layout replaces them;
  * plots fill the remaining parcels at the official sizes
    (5 Marla 28x50 ft, 10 Marla 39x70 ft, 20 Marla 54x100 ft, commercial 30x60 ft).
    Plot numbers, status, class and heights are SAMPLE values (fixed seed).

usage (from the repo root):  python -I tools/make_data.py [--preview out.png]
writes data/boundary, roads, road_surface, outer_roads, blocks (land parcels), landmarks, water (nalla),
parks (landmark footprints for the CesiumJS view) and plots, all .geojson
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os

from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source", "osm_fda_city.json")
OUT = os.path.join(ROOT, "data")
BOUNDARY_ID = 287541676

# local metric frame (equirectangular; fine for a 3 km site). JS uses the same constants.
LAT_REF = 31.525
LAT0, LON0 = 31.5136158, 73.0742353
MLAT = 111320.0
MLON = 111320.0 * math.cos(math.radians(LAT_REF))
FT = 0.3048
KANAL = 505.857  # m2

SIZES = {  # name: (frontage m, depth m)
    "5 Marla": (28 * FT, 50 * FT),
    "10 Marla": (39 * FT, 70 * FT),
    "20 Marla": (54 * FT, 100 * FT),
    "Commercial": (30 * FT, 60 * FT),
}
WIDTH = {  # carriageway width in metres
    "main": 11.0,          # each one-way carriageway of the 202 ft boulevard
    "collector": 60 * FT,  # 60 / 85 ft collector roads
    "residential": 40 * FT,
    "roundabout": 12.0,
    "arterial": 14.0,      # Samaana Road
}
SIDEWALK = 2.5
LANE = 6.0  # service lane between back-to-back plot rows

# Official layout facts used to place landmarks (from the FDA City block maps)
PARKS_PER_BLOCK = {"A": 4, "B": 4, "C": 6, "D": 7, "E": 6, "F": 3}
COMPLEX_SPLIT = [("playground", 0.46), ("school", 0.26), ("mosque", 0.14), ("commercial", 0.14)]
COMPLEX_NAMES = {"playground": "Playground {b}", "school": "Govt. Primary School ({b})",
                 "mosque": "Jamia Mosque ({b})", "commercial": "Commercial Centre ({b})"}


def ll(x, y):
    return (round(LON0 + x / MLON, 7), round(LAT0 + y / MLAT, 7))


def xy(p):
    return ((p["lon"] - LON0) * MLON, (p["lat"] - LAT0) * MLAT)


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


def largest_polygon(g):
    ps = polys(g)
    return max(ps, key=lambda p: p.area) if ps else None


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
    """Oriented box: centre (lon,lat), long-axis angle in degrees (east = 0, CCW), length, width."""
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)
    e0 = math.dist(cs[0], cs[1])
    e1 = math.dist(cs[1], cs[2])
    a, b = (cs[0], cs[1]) if e0 >= e1 else (cs[1], cs[2])
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    ang = (ang + 90) % 180 - 90  # keep in [-90, 90)
    c = mrr.centroid
    return {"lon": ll(c.x, c.y)[0], "lat": ll(c.x, c.y)[1], "angle": round(ang, 2), "length": round(max(e0, e1), 1), "width": round(min(e0, e1), 1)}


def split_along(poly, fracs, gap=4.0):
    """Cut a polygon into strips across its long axis, sized by fracs."""
    o = obb(poly)
    c = poly.centroid
    rot = affinity.rotate(poly, -o["angle"], origin=c)
    minx, miny, maxx, maxy = rot.bounds
    L = maxx - minx
    parts, x = [], minx
    for i, f in enumerate(fracs):
        x1 = maxx if i == len(fracs) - 1 else x + L * f
        cell = box(x + (gap / 2 if i else 0), miny - 1, x1 - (gap / 2 if i < len(fracs) - 1 else 0), maxy + 1)
        pg = largest_polygon(cell.intersection(rot))
        parts.append(affinity.rotate(pg, o["angle"], origin=c) if pg is not None else None)
        x = x1
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", default=None)
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)

    data = json.load(open(args.src, encoding="utf-8-sig"))
    els = data["elements"]
    bnd = next(e for e in els if e["id"] == BOUNDARY_ID)
    roads = [e for e in els if e.get("tags", {}).get("highway")]
    B = Polygon([xy(p) for p in bnd["geometry"]])
    print(f"boundary: {B.area/1e6:.2f} km2, {len(roads)} OSM roads")

    # ---- roundabouts and main axis -------------------------------------------------
    rings = [e for e in roads if e["tags"].get("junction") == "roundabout"]
    rbs = []
    for e in rings:
        pts = [xy(p) for p in e["geometry"]]
        pg = Polygon(pts)
        c = pg.centroid
        r = sum(math.dist((c.x, c.y), p) for p in pts) / len(pts)
        rbs.append({"c": c, "r": r, "poly": pg, "id": e["id"]})
    rbs.sort(key=lambda d: d["c"].x)
    r1, r2 = rbs[0]["c"], rbs[-1]["c"]
    dx, dy = r2.x - r1.x, r2.y - r1.y
    Lr = math.hypot(dx, dy)
    ax, ay = dx / Lr, dy / Lr
    nx, ny = -ay, ax
    axis_line = LineString([(r1.x - 4000 * ax, r1.y - 4000 * ay), (r2.x + 4000 * ax, r2.y + 4000 * ay)])
    axis_deg = math.degrees(math.atan2(ay, ax))

    def uv(p):
        px, py = p.x - r1.x, p.y - r1.y
        return (px * ax + py * ay, px * nx + py * ny)

    U_AB, U_BC = 480.0, 980.0

    def block_of(p):
        u, v = uv(p)
        side = "NW" if v > 0 else "SE"
        if u < U_AB:
            return "A" if side == "NW" else "F"
        if u < U_BC:
            return "B" if side == "NW" else "E"
        return "C" if side == "NW" else "D"

    # ---- classify roads ------------------------------------------------------------
    lines = []
    for e in roads:
        line = LineString([xy(p) for p in e["geometry"]])
        t = e["tags"]
        if t.get("junction") == "roundabout":
            cls = "roundabout"
        elif t.get("highway") == "tertiary":
            cls = "arterial"
        else:
            c = line.interpolate(0.5, normalized=True)
            p0, p1 = line.coords[0], line.coords[-1]
            ln = math.dist(p0, p1) or 1
            par = abs(((p1[0] - p0[0]) * ax + (p1[1] - p0[1]) * ay) / ln)
            cls = "main" if (axis_line.distance(c) < 30 and par > 0.9) else "residential"
        lines.append({"e": e, "line": line, "cls": cls})

    # collectors: long straight residential chains (the 60/85 ft roads between blocks)
    res = [d["line"] for d in lines if d["cls"] == "residential"]
    merged = linemerge(MultiLineString(res))
    chains = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    coll = [ch for ch in chains if ch.length > 700 and math.dist(ch.coords[0], ch.coords[-1]) / ch.length > 0.93]
    coll_zone = unary_union([ch.buffer(1.0) for ch in coll]) if coll else None
    for d in lines:
        if d["cls"] == "residential" and coll_zone is not None and d["line"].within(coll_zone):
            d["cls"] = "collector"
    print("road classes:", dict(Counter(d["cls"] for d in lines)))

    # main carriageway spacing
    mains = [d["line"] for d in lines if d["cls"] == "main"]
    if len(mains) >= 2:
        mid = mains[0].interpolate(0.5, normalized=True)
        spacing = min(m.distance(mid) for m in mains[1:] if m.distance(mid) > 3) if any(m.distance(mid) > 3 for m in mains[1:]) else 20
    else:
        spacing = 20
    print(f"main carriageway spacing: {spacing:.1f} m")

    # ---- road surfaces -------------------------------------------------------------
    surf = unary_union([d["line"].buffer(WIDTH[d["cls"]] / 2, join_style=2 if d["cls"] != "roundabout" else 1, mitre_limit=3) for d in lines])
    surf = surf.buffer(0.3).buffer(-0.3)  # heal slivers at junctions

    # ---- nalla (storm drain) traced from satellite imagery ----------------------------
    nala = None
    nala_src = os.path.join(HERE, "source", "nala_traced.geojson")
    if os.path.exists(nala_src):
        g = json.load(open(nala_src, encoding="utf-8"))["features"][0]
        raw = LineString([xy({"lon": a, "lat": b}) for a, b in g["geometry"]["coordinates"]]).simplify(0.8)
        clipped = raw.intersection(B.buffer(150))
        parts = [clipped] if clipped.geom_type == "LineString" else [q for q in getattr(clipped, "geoms", []) if q.geom_type == "LineString"]
        if parts:
            nala = max(parts, key=lambda q: q.length)
            print(f"nalla: {nala.length:.0f} m inside the society")
    NALA_CH, NALA_BANK = 3.4, 8.5   # half-widths: lined channel, channel + banks
    nala_zone = nala.buffer(NALA_BANK) if nala is not None else None

    # ---- faces of the road network (with the boundary and the nalla as closing edges) --
    noded = unary_union([d["line"] for d in lines] + [LineString(B.exterior.coords)] + ([nala] if nala is not None else []))
    faces = [f for f in polygonize(noded) if f.representative_point().within(B)]
    print(f"faces: {len(faces)}")

    rb_zone = unary_union([d["poly"].buffer(2) for d in rbs])
    F = []  # parcels
    pieces = []
    for i, f in enumerate(faces):
        land = f.difference(surf)
        if nala_zone is not None:
            land = land.difference(nala_zone)
        # a dead-end road can cut a face into several pieces: keep every piece
        for j, q in enumerate(sorted(polys(land), key=lambda q: -q.area)):
            if q.area < 40:
                continue
            # a piece whose footpath inset falls apart becomes several parcels
            ins = [r for r in polys(q.buffer(-SIDEWALK)) if r.area >= 25]
            if len(ins) <= 1:
                pieces.append((i * 100 + j, q))
            else:
                for k2, r in enumerate(ins):
                    sub = largest_polygon(q.intersection(r.buffer(SIDEWALK + 0.4, join_style=2)))
                    if sub is not None and sub.area >= 40:
                        pieces.append((i * 100 + j * 10 + k2 + 5000000, sub))
    for i, lp in pieces:
        lp = lp.simplify(0.2)
        cen = lp.representative_point()
        mrr = lp.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        touching_mains = sum(1 for m in mains if m.distance(lp) < WIDTH["main"] / 2 + 3)
        inner = largest_polygon(lp.buffer(-SIDEWALK))
        if lp.within(rb_zone):
            kind = "island"
        elif (touching_mains >= 2 and short < 45) or (axis_line.distance(cen) < spacing / 2 + 4 and short < spacing + 4):
            kind = "median"          # strip between the two carriageways of the boulevard
        elif inner is None or inner.buffer(-6.5).is_empty:
            kind = "greenbelt"       # too narrow for a row of plots: planted strip between roads
        else:
            kind = "parcel"
        u, v = uv(cen)
        F.append({"i": i, "land": lp, "kind": kind, "blk": block_of(cen), "u": u, "v": v, "c": cen,
                  "area": lp.area, "inner": inner if kind in ("parcel", "greenbelt") else None, "use": None})
    parcels = [p for p in F if p["kind"] == "parcel"]
    print("land:", dict(Counter(p["kind"] for p in F)))

    # ---- landmarks -----------------------------------------------------------------
    landmarks = []

    def add_lm(poly, kind, name, blk, proposed=False, extra=None):
        if poly is None or poly.area < 200:
            return
        props = {"id": len(landmarks) + 1, "kind": kind, "name": name, "block": "Block " + blk if blk else None,
                 "area_kanal": round(poly.area / KANAL, 1), "proposed": proposed, "obb": obb(poly),
                 "accuracy": "approximate", "source": "Placed per official FDA City block map"}
        if extra:
            props.update(extra)
        landmarks.append(feature(poly.simplify(0.2), props))

    def free(p, min_area=0):
        return p["use"] is None and p["inner"] is not None and p["inner"].area >= min_area

    def aspect(p):
        o = obb(p["inner"])
        r = o["length"] / max(o["width"], 1)
        solid = p["inner"].area / max(p["inner"].convex_hull.area, 1)
        return r if solid > 0.86 else 99   # L-shapes and other awkward sites are never "compact"

    blocks_c = {}
    for b in "ABCDEF":
        ps = [p for p in parcels if p["blk"] == b]
        blocks_c[b] = Point(sum(p["c"].x for p in ps) / len(ps), sum(p["c"].y for p in ps) / len(ps))

    # special zones first (they need particular locations)
    # Area for FDA City Homes: hospital, sports complex, public building (far south-east, middle)
    se = [p for p in parcels if free(p, 6500) and p["v"] < 0 and U_AB - 100 < p["u"] < U_BC + 500 and aspect(p) < 2.8]
    if se:
        se.sort(key=lambda p: p["v"])                    # farthest from the boulevard first
        pick = sorted(se[:8], key=lambda p: -p["inner"].area)[:3]
        pick.sort(key=lambda p: p["u"])
        for (k, nm), z in zip([("hospital", "FDA City Hospital"), ("sports", "Sports Complex"), ("civic", "Public Building")], pick):
            z["use"] = k
            add_lm(z["inner"], k, nm, z["blk"])

    # proposed university, cricket stadium, IMAX theatre: north-east end, Block C side
    ne = sorted([p for p in parcels if free(p, 8000) and p["v"] > 0 and p["blk"] == "C" and aspect(p) < 2.6], key=lambda p: -p["u"])[:5]
    ne.sort(key=lambda p: -p["inner"].area)
    for (k, nm), p in zip([("stadium", "Proposed Cricket Stadium"), ("university", "Proposed University"), ("cinema", "Proposed IMAX Theatre")], ne[:3]):
        p["use"] = k
        add_lm(p["inner"], k, nm, "C", proposed=True)

    # multi-purpose zone: northern corner of Block C
    mp = [p for p in parcels if free(p, 5000) and p["blk"] == "C" and aspect(p) < 4]
    if mp:
        p = max(mp, key=lambda p: p["v"] + 0.3 * p["u"])
        p["use"] = "multipurpose"
        add_lm(p["inner"], "multipurpose", "Multi-Purpose Zone", "C")

    # grid station and existing graveyard: west end of Block F
    wf = sorted([p for p in parcels if free(p, 2500) and p["blk"] in "F" and aspect(p) < 4], key=lambda p: p["u"])
    for (k, nm), p in zip([("grid", "Grid Station"), ("graveyard", "Existing Graveyard")], wf[:2]):
        p["use"] = k
        add_lm(p["inner"], k, nm, p["blk"])

    # CNG station: small parcel in Block D next to the boulevard
    dd = sorted([p for p in parcels if free(p, 900) and p["blk"] == "D" and p["area"] < 9000], key=lambda p: abs(p["v"]))
    if dd:
        dd[0]["use"] = "cng"
        add_lm(dd[0]["inner"], "cng", "CNG Station", "D")
    # Darbar (shrine): small parcel in Block E
    ee = sorted([p for p in parcels if free(p, 700) and p["blk"] == "E" and p["area"] < 7000], key=lambda p: p["c"].distance(blocks_c["E"]))
    if ee:
        ee[0]["use"] = "shrine"
        add_lm(ee[0]["inner"], "shrine", "Darbar (Shrine)", "E")

    # block community complex: playground + school + mosque + commercial in one central parcel
    for b in "ABCDEF":
        cand = [p for p in parcels if free(p, 9000) and p["blk"] == b and aspect(p) < 3.5] or [p for p in parcels if free(p, 9000) and p["blk"] == b]
        if not cand:
            continue
        p = max(cand, key=lambda p: p["inner"].area / 1000 - p["c"].distance(blocks_c[b]) / 45)
        p["use"] = "complex"
        for (k, _), pg in zip(COMPLEX_SPLIT, split_along(p["inner"], [f for _, f in COMPLEX_SPLIT])):
            add_lm(pg, k, COMPLEX_NAMES[k].format(b=b), b)

    # numbered parks, spread over each block (farthest-point sampling)
    for b in "ABCDEF":
        def compact(p):
            o = obb(p["inner"])
            return o["length"] / max(o["width"], 1) < 3.2
        cand = [p for p in parcels if free(p, 2200) and p["blk"] == b and p["area"] < 16000 and compact(p)]
        if len(cand) < PARKS_PER_BLOCK[b]:
            cand += [p for p in parcels if free(p, 2200) and p["blk"] == b and p["area"] < 26000 and p not in cand]
        chosen = []
        while cand and len(chosen) < PARKS_PER_BLOCK[b]:
            if not chosen:
                p = min(cand, key=lambda p: p["c"].distance(blocks_c[b]) - p["area"] / 400)
            else:
                p = max(cand, key=lambda p: min(p["c"].distance(q["c"]) for q in chosen) * (0.6 + min(p["area"], 20000) / 50000))
            chosen.append(p)
            cand.remove(p)
        chosen.sort(key=lambda p: (p["u"], -p["v"]))
        for n, p in enumerate(chosen, 1):
            p["use"] = "park"
            add_lm(p["inner"], "park", f"Park {b}-{n}", b)

    # main gate across the boulevard at the south-west entrance
    if rbs:
        off = rbs[0]["r"] + WIDTH["roundabout"] / 2 + 38
        gp = Point(r1.x - ax * off, r1.y - ay * off)
        landmarks.append(feature(gp, {"id": len(landmarks) + 1, "kind": "gate", "name": "FDA City Main Gate", "block": None,
                                      "heading": round(axis_deg, 2), "span": round(spacing + WIDTH["main"] + 6, 1),
                                      "accuracy": "approximate", "source": "Placed at the boulevard entrance"}))

    # roundabout islands with monuments (first one carries a Clock Tower replica)
    for n, d in enumerate(rbs):
        isl = d["poly"].buffer(-(WIDTH["roundabout"] / 2 + 0.5))
        if isl.is_empty:
            continue
        add_lm(isl, "roundabout", ["Clock Tower Roundabout", "Fountain Roundabout"][n % 2], None,
               extra={"radius": round(math.sqrt(isl.area / math.pi), 1), "monument": ["clocktower", "fountain"][n % 2]})

    kinds = Counter(f["properties"]["kind"] for f in landmarks)
    print("landmarks:", dict(kinds))

    # ---- plots ---------------------------------------------------------------------
    plot_feats = []
    counters = {k: 0 for k in "ABCDEF"}
    pid = 0
    corridor_half = spacing / 2 + WIDTH["main"] / 2
    for p in sorted(parcels, key=lambda p: (p["blk"], p["u"], -p["v"])):
        if p["use"] is not None or p["inner"] is None or p["inner"].area < 250:
            continue
        p["use"] = "plots"
        blk, region = p["blk"], p["inner"]
        d_main = axis_line.distance(p["c"])
        size = "20 Marla" if d_main < 280 else "10 Marla" if d_main < 620 else "5 Marla"
        if blk in "BC" and d_main > 900:
            size = "5 Marla"
        if blk == "A" and d_main > 620 and h01("asz", p["i"]) < 0.5:
            size = "10 Marla"
        commercial_face = axis_line.distance(region) < corridor_half + SIDEWALK + 30
        w, dep = SIZES["Commercial" if commercial_face else size]
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
                pg = largest_polygon(box(x0, y0, x1, y1).intersection(rot))
                if pg is None or pg.area < w * dep * 0.45:
                    continue
                pg = affinity.rotate(pg, o["angle"], origin=c).simplify(0.15)
                pid += 1
                counters[blk] += 1
                key = (blk, counters[blk])
                ptype = "Commercial" if (commercial_face and axis_line.distance(pg.centroid) < corridor_half + SIDEWALK + 30) else "Residential"
                psize = "Commercial" if ptype == "Commercial" else size
                cx, cy = pg.centroid.x, pg.centroid.y
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
    print(f"plots: {len(plot_feats)}  per block: {counters}")

    # ---- write -----------------------------------------------------------------------
    cen = B.centroid
    bprops = {"name": "FDA City", "city": "Faisalabad", "osm_id": BOUNDARY_ID, "source": "OpenStreetMap", "accuracy": "georeferenced",
              "area_km2": round(B.area / 1e6, 2), "centre_lon": ll(cen.x, cen.y)[0], "centre_lat": ll(cen.x, cen.y)[1],
              "lat_ref": LAT_REF, "axis_deg": round(axis_deg, 2), "sidewalk_m": SIDEWALK}
    road_feats = []
    clip = B.buffer(60)
    for d in lines:
        g = d["line"].intersection(clip)
        for part in ([g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]):
            if part.length < 5:
                continue
            t = d["e"]["tags"]
            road_feats.append(feature(part, {"osm_id": d["e"]["id"], "name": t.get("name") or ("Main Boulevard (202 ft)" if d["cls"] == "main" else None),
                                             "class": d["cls"], "width_m": round(WIDTH[d["cls"]], 1), "oneway": t.get("oneway") == "yes",
                                             "source": "OpenStreetMap", "accuracy": "georeferenced"}))
    outer = surf.intersection(B.buffer(450)).difference(B.buffer(-0.5))
    land_feats = []
    for p in F:
        use = p["use"] or ("open" if p["kind"] == "parcel" else p["kind"])
        land_feats.append(feature(p["land"], {"layer": "land", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "area_m2": round(p["area"]), "accuracy": "approximate"}))
        if p["inner"] is not None and p["kind"] in ("parcel", "greenbelt"):
            land_feats.append(feature(p["inner"].simplify(0.2), {"layer": "inner", "kind": p["kind"], "use": use, "block": "Block " + p["blk"], "accuracy": "approximate"}))
    print("writing to", out)
    write(out, "boundary", [feature(B, bprops)])
    write(out, "roads", road_feats)
    water_feats = []
    if nala is not None:
        cut = surf.buffer(0.6)
        channel = nala.buffer(NALA_CH, cap_style=2)
        wall = nala.buffer(NALA_CH + 0.45, cap_style=2).difference(nala.buffer(NALA_CH - 0.05, cap_style=2))
        bank = nala.buffer(NALA_BANK, cap_style=2).difference(nala.buffer(NALA_CH + 0.45, cap_style=2)).difference(surf)
        nprops = {"name": "Barani Nala (storm drain)", "source": "Traced from Esri World Imagery", "accuracy": "approximate"}
        for q in polys(channel.difference(cut)):
            if q.area > 5:
                water_feats.append(feature(q.simplify(0.15), dict(nprops, kind="nala_water")))
        for q in polys(wall.difference(cut)):
            if q.area > 1:
                water_feats.append(feature(q.simplify(0.1), dict(nprops, kind="nala_wall")))
        for q in polys(bank):
            if q.area > 5:
                water_feats.append(feature(q.simplify(0.2), dict(nprops, kind="nala_bank")))
        water_feats.append(feature(nala, dict(nprops, kind="nala_line", width_m=round(2 * NALA_CH, 1), length_m=round(nala.length))))
        trees = []
        for side in (-1, 1):
            off = nala.offset_curve(side * (NALA_CH + 3.2))
            for q in ([off] if off.geom_type == "LineString" else list(getattr(off, "geoms", []))):
                dist = 6.0
                while dist < q.length:
                    pt = q.interpolate(dist)
                    if not surf.buffer(1.5).contains(pt):
                        trees.append(pt)
                    dist += 13.0
        for pt in trees:
            water_feats.append(feature(pt, {"kind": "nala_tree"}))
        for d in lines:  # bridges where a road crosses the channel
            x = d["line"].intersection(nala)
            for pt in ([x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]):
                c = d["line"].project(pt)
                a, b = d["line"].interpolate(max(0, c - 3)), d["line"].interpolate(min(d["line"].length, c + 3))
                water_feats.append(feature(pt, {"kind": "bridge", "heading": round(math.degrees(math.atan2(b.y - a.y, b.x - a.x)), 1),
                                                "road_width": round(WIDTH[d["cls"]], 1), "span": round(2 * NALA_CH + 2, 1)}))
        print("water:", dict(Counter(f["properties"]["kind"] for f in water_feats)))
    inner_surf = surf.intersection(B.buffer(1.0))
    write(out, "road_surface", [feature(q.simplify(0.25), {"kind": "carriageway", "accuracy": "approximate", "source": "OSM centrelines buffered to official widths"}) for q in polys(inner_surf) if q.area > 20])
    write(out, "outer_roads", [feature(q.simplify(0.3), {"kind": "road", "accuracy": "approximate"}) for q in polys(outer) if q.area > 20])
    write(out, "blocks", land_feats)
    write(out, "landmarks", landmarks)
    write(out, "water", water_feats)
    write(out, "parks", [f for f in landmarks if f["geometry"]["type"] == "Polygon" and f["properties"]["kind"] != "roundabout"]
          + [dict(f, properties=dict(f["properties"], kind="nala", name="Barani Nala")) for f in water_feats if f["properties"]["kind"] == "nala_water"])
    write(out, "plots", plot_feats, {"data_note": "Plot geometry and attributes are generated samples (accuracy=approximate). Replace with surveyed or georeferenced data using the same property names."})

    if args.preview:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axp = plt.subplots(figsize=(16, 16), dpi=100)
        axp.set_aspect("equal")
        for q in polys(surf.intersection(B.buffer(200))):
            axp.fill(*q.exterior.xy, color="#555", ec="none")
            for r in q.interiors:
                axp.fill(*r.xy, color="white", ec="none")
        LC = {"parcel": "#d9cfb6", "median": "#5a9a55", "island": "#5a9a55", "greenbelt": "#7fbf6a"}
        if nala is not None:
            for q in polys(nala.buffer(NALA_CH)):
                axp.fill(*q.exterior.xy, color="#2b7fc4", ec="none", zorder=5)
        for p in F:
            axp.fill(*p["land"].exterior.xy, color=LC[p["kind"]], ec="none")
        KC = {"park": "#62b06a", "playground": "#9bd17a", "school": "#d98b5f", "mosque": "#f2f2f2", "commercial": "#7aa6d9",
              "hospital": "#e05c5c", "sports": "#c7a0e0", "civic": "#c9b48a", "stadium": "#a0e0c7", "university": "#e0b0a0",
              "cinema": "#b07ad9", "multipurpose": "#a0a0e0", "grid": "#999", "graveyard": "#8a8a6a", "cng": "#e0e070", "shrine": "#40a060", "roundabout": "#3f8f3f"}
        for f in landmarks:
            pr = f["properties"]
            if f["geometry"]["type"] != "Polygon":
                continue
            pg = Polygon([xy({"lon": a, "lat": b}) for a, b in f["geometry"]["coordinates"][0]])
            axp.fill(*pg.exterior.xy, color=KC.get(pr["kind"], "#f0f"), ec="k", lw=0.4)
            if pr["kind"] not in ("roundabout",):
                axp.annotate(pr["name"].replace(" (", "\n("), (pg.centroid.x, pg.centroid.y), fontsize=5.5, ha="center", va="center")
        for f in plot_feats:
            pg = Polygon([xy({"lon": a, "lat": b}) for a, b in f["geometry"]["coordinates"][0]])
            axp.fill(*pg.exterior.xy, color="#e8a04a" if f["properties"]["type"] == "Commercial" else "#f4e3c0", ec="#9a8a6a", lw=0.15)
        axp.plot(*B.exterior.xy, color="red", lw=1)
        for b, c in blocks_c.items():
            axp.annotate("BLOCK " + b, (c.x, c.y), fontsize=18, weight="bold", ha="center", color="#123", alpha=0.6)
        fig.savefig(args.preview, bbox_inches="tight")
        print("preview:", args.preview)


if __name__ == "__main__":
    main()

"""Generate Terralyt map data for FDA City (Faisalabad) from OpenStreetMap.

Real geometry: the society boundary and every road come from OpenStreetMap
(tools/source/osm_fda_city.json, Overpass export of OSM way 287541676 and the
highways inside it).  City blocks are computed by polygonising the road network.

Approximate geometry: plots are generated inside each block at the official
FDA City plot sizes (5 Marla 28x50 ft, 10 Marla 39x70 ft, 20 Marla 54x100 ft).
Plot numbers, block letters, parks, status, class and heights are SAMPLE values
with a fixed seed.  Every feature carries accuracy="approximate" until surveyed
or georeferenced data replaces it.  The map code must not depend on sample-ness.

usage (from repo root):  python -I tools/make_data.py [--preview out.png]
writes data/boundary.geojson, roads.geojson, blocks.geojson, parks.geojson, plots.geojson
"""
import argparse
import hashlib
import json
import math
import os
import sys

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source", "osm_fda_city.json")
OUT = os.path.join(ROOT, "data")
BOUNDARY_ID = 287541676

# local metric frame (equirectangular, fine for a 4 km site)
LAT0, LON0 = 31.5136158, 73.0742353
MLAT = 111320.0
MLON = 111320.0 * math.cos(math.radians(31.525))
FT = 0.3048

SIZES = {  # name: (frontage m, depth m)
    "5 Marla": (28 * FT, 50 * FT),
    "10 Marla": (39 * FT, 70 * FT),
    "20 Marla": (54 * FT, 100 * FT),
    "Commercial": (30 * FT, 60 * FT),
}
ROAD_WIDTH = {"main": 22.0, "arterial": 16.0, "residential": 10.0}
LANE = 8.0          # internal service lane between back-to-back plot rows
INSET = 6.0         # plot setback from road centreline beyond half the road width


def ll(x, y):
    return (round(LON0 + x / MLON, 6), round(LAT0 + y / MLAT, 6))


def xy(p):
    return ((p["lon"] - LON0) * MLON, (p["lat"] - LAT0) * MLAT)


def h01(*parts):
    """Deterministic pseudo-random in [0,1) from a key."""
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def geom_ll(g):
    """Shapely geometry in local metres -> GeoJSON geometry in lon/lat."""
    if g.geom_type == "Polygon":
        rings = [[ll(*c) for c in g.exterior.coords]] + [[ll(*c) for c in r.coords] for r in g.interiors]
        return {"type": "Polygon", "coordinates": rings}
    if g.geom_type == "LineString":
        return {"type": "LineString", "coordinates": [ll(*c) for c in g.coords]}
    if g.geom_type == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [geom_ll(p)["coordinates"] for p in g.geoms]}
    raise ValueError(g.geom_type)


def feature(g, props):
    return {"type": "Feature", "geometry": geom_ll(g), "properties": props}


def write(name, feats, extra=None):
    fc = {"type": "FeatureCollection", "name": name, "crs_note": "EPSG:4326 (WGS84 lon/lat)"}
    if extra:
        fc.update(extra)
    fc["features"] = feats
    path = os.path.join(OUT, name + ".geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, separators=(",", ":"))
    print(f"  {name}.geojson: {len(feats)} features, {os.path.getsize(path)//1024} KB")


def largest_polygon(g):
    if g.is_empty:
        return None
    if g.geom_type == "Polygon":
        return g
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        polys = [p for p in g.geoms if p.geom_type == "Polygon" and not p.is_empty]
        return max(polys, key=lambda p: p.area) if polys else None
    return None


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", default=None, help="write a PNG preview of the generated data")
    args = ap.parse_args()
    OUT = args.out
    os.makedirs(OUT, exist_ok=True)

    data = json.load(open(args.src, encoding="utf-8-sig"))
    els = data["elements"]
    bnd = next(e for e in els if e["id"] == BOUNDARY_ID)
    roads = [e for e in els if e.get("tags", {}).get("highway")]
    B = Polygon([xy(p) for p in bnd["geometry"]])
    print(f"boundary: {B.area/1e6:.2f} km2, {len(roads)} OSM roads")

    # --- main axis from the two roundabouts (SW -> NE) -----------------------
    rbs = [LineString([xy(p) for p in e["geometry"]]).centroid for e in roads if e["tags"].get("junction") == "roundabout"]
    rbs.sort(key=lambda p: p.x)
    r1, r2 = rbs[0], rbs[-1]
    dx, dy = r2.x - r1.x, r2.y - r1.y
    L = math.hypot(dx, dy)
    ax, ay = dx / L, dy / L          # along the main road, SW -> NE
    nx, ny = -ay, ax                 # normal, pointing NW
    u2 = L                           # u of the second roundabout
    main_line = LineString([(r1.x - 3000 * ax, r1.y - 3000 * ay), (r2.x + 3000 * ax, r2.y + 3000 * ay)]).intersection(B.buffer(60))

    def uv(p):
        px, py = p.x - r1.x, p.y - r1.y
        return (px * ax + py * ay, px * nx + py * ny)

    # Block letters follow the official layout: A, B, C on the north-west side of the
    # main boulevard (south-west to north-east), F, E, D on the south-east side.
    # The along-road split points are approximate (no surveyed block limits exist).
    U_AB, U_BC = 480.0, 980.0

    def block_of(p):
        u, v = uv(p)
        side = "NW" if v > 0 else "SE"
        if u < U_AB:
            return "A" if side == "NW" else "F"
        if u < U_BC:
            return "B" if side == "NW" else "E"
        return "C" if side == "NW" else "D"

    # --- roads -----------------------------------------------------------------
    road_feats, road_lines = [], []
    clip = B.buffer(45)
    for e in roads:
        line = LineString([xy(p) for p in e["geometry"]])
        t = e["tags"]
        if t.get("junction") == "roundabout":
            cls = "main"
        elif t.get("highway") == "tertiary":
            cls = "arterial"
        else:
            # parallel to and within ~30 m of the main axis -> main road carriageway
            c = line.interpolate(0.5, normalized=True)
            d = main_line.distance(c)
            p0, p1 = line.coords[0], line.coords[-1]
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1
            par = abs(((p1[0] - p0[0]) * ax + (p1[1] - p0[1]) * ay) / ln)
            cls = "main" if (d < 30 and par > 0.9) else "residential"
        road_lines.append(line)
        g = line.intersection(clip)
        parts = [g] if g.geom_type == "LineString" else [p for p in getattr(g, "geoms", []) if p.geom_type == "LineString"]
        for part in parts:
            if part.length < 5:
                continue
            road_feats.append(feature(part, {
                "osm_id": e["id"], "name": t.get("name") or ("Main Boulevard" if cls == "main" else None),
                "class": cls, "width_m": ROAD_WIDTH[cls], "source": "OpenStreetMap", "accuracy": "georeferenced"}))
    main_corridor = unary_union([l for l, f in zip(road_lines, [None] * 0)] or [main_line]).buffer(ROAD_WIDTH["main"] / 2)

    # --- blocks (faces of the road graph) --------------------------------------
    faces = [f for f in polygonize(unary_union(road_lines)) if f.representative_point().within(B)]
    faces.sort(key=lambda f: (block_of(f.centroid), uv(f.centroid)[0], uv(f.centroid)[1]))
    print(f"blocks: {len(faces)} faces inside boundary")

    block_feats, park_feats, plot_feats = [], [], []
    counters = {k: 0 for k in "ABCDEF"}
    park_n = {k: 0 for k in "ABCDEF"}
    amen_n = 0
    AMEN = ["Primary School", "Jamia Mosque", "Commercial Centre", "Community Centre", "Dispensary", "Grid Station"]
    pid = 0
    for fi, f in enumerate(faces):
        blk = block_of(f.centroid)
        d_main = main_line.distance(f.centroid)
        area = f.area
        inset = largest_polygon(f.buffer(-(ROAD_WIDTH["residential"] / 2 + INSET)))
        # face kind
        if area < 1500 or inset is None or inset.area < 600 or any(f.contains(r) for r in rbs):
            kind = "open"
        elif area > 15000 and h01("park", fi) < 0.14:
            kind = "park"
        elif area > 10000 and h01("amenity", fi) < 0.08:
            kind = "amenity"
        else:
            kind = "residential"
        # plot size band: bigger plots near the main road, 5 Marla in the far NW/SE
        size = "20 Marla" if d_main < 280 else "10 Marla" if d_main < 620 else "5 Marla"
        if blk in "BC" and d_main > 900:
            size = "5 Marla"
        if blk == "A" and d_main > 620 and h01("asz", fi) < 0.5:
            size = "10 Marla"
        bprops = {"block": "Block " + blk, "kind": kind, "area_m2": round(area), "plot_size": size if kind == "residential" else None,
                  "accuracy": "approximate", "source": "Derived from OpenStreetMap road network"}
        block_feats.append(feature(f.simplify(0.2), bprops))
        if kind == "park":
            park_n[blk] += 1
            park_feats.append(feature(inset.simplify(0.3), {"name": f"Park {blk}-{park_n[blk]}", "kind": "park", "block": "Block " + blk,
                                                             "area_kanal": round(inset.area / 505.857, 1), "accuracy": "approximate"}))
            continue
        if kind == "amenity":
            nm = AMEN[amen_n % len(AMEN)]
            amen_n += 1
            park_feats.append(feature(inset.simplify(0.3), {"name": f"{nm} ({blk})", "kind": "amenity", "block": "Block " + blk,
                                                             "area_kanal": round(inset.area / 505.857, 1), "accuracy": "approximate"}))
            continue
        if kind != "residential":
            continue

        # --- subdivide the inset face into plots ---------------------------------
        commercial_face = d_main < 60
        w, dep = SIZES[size]
        mrr = inset.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        e0 = math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        a, b = (cs[0], cs[1]) if e0 >= e1 else (cs[1], cs[2])
        theta = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        c = inset.centroid
        rot = affinity.rotate(inset, -theta, origin=c)
        minx, miny, maxx, maxy = rot.bounds
        width_b = maxy - miny
        if width_b < dep * 0.7:
            continue
        # row bands across the short axis: pairs of back-to-back rows separated by a lane
        bands = []
        y = miny
        while True:
            if y + dep <= maxy + 0.01:
                bands.append((y, min(y + dep, maxy)))
            else:
                break
            if y + 2 * dep <= maxy + 0.01:
                bands.append((y + dep, y + 2 * dep))
            else:
                break
            y += 2 * dep + LANE
        if not bands:
            bands = [(miny, maxy)]
        if len(bands) == 1 and width_b > dep * 1.4:
            bands = [(miny, miny + dep), (maxy - dep, maxy)]
        for bi, (y0, y1) in enumerate(bands):
            n = max(1, int((maxx - minx) / w))
            for k in range(n):
                x0 = minx + k * w
                x1 = maxx if k == n - 1 else x0 + w
                cell = box(x0, y0, x1, y1)
                if cell.area > w * dep * 1.8:          # oversize remainder: split again
                    continue
                pg = largest_polygon(cell.intersection(rot))
                if pg is None or pg.area < w * dep * 0.5:
                    continue
                pg = affinity.rotate(pg, theta, origin=c).simplify(0.15)
                pid += 1
                counters[blk] += 1
                key = (blk, counters[blk])
                # commercial frontage on the main boulevard
                ptype = "Commercial" if (commercial_face and main_line.distance(pg.centroid) < 50) else "Residential"
                psize = "Commercial" if ptype == "Commercial" else size
                # development: higher near the main road and the centre, with smooth variation
                cx, cy = pg.centroid.x, pg.centroid.y
                noise = 0.5 * math.sin(cx / 230 + 1.3) * math.cos(cy / 260 - 0.4) + 0.5 * math.sin((cx + cy) / 410)
                dev = 0.98 - min(d_main, 1400) / 1400 * 0.9 + 0.26 * noise + (h01("dev", *key) - 0.5) * 0.3
                dev_class = "High" if dev > 0.68 else "Medium" if dev > 0.36 else "Low"
                r = h01("status", *key)
                status = "Sold" if r < 0.42 else "Available" if r < 0.72 else "Reserved" if r < 0.85 else "Unknown"
                built_p = (0.92 if dev_class == "High" else 0.55 if dev_class == "Medium" else 0.18)
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
    byc = {}
    for p in plot_feats:
        for k in ("status", "dev_class", "size", "type"):
            byc.setdefault(k, {}).setdefault(p["properties"][k], 0)
            byc[k][p["properties"][k]] += 1
    for k, v in byc.items():
        print(f"  {k}: {v}")

    # --- write -------------------------------------------------------------------
    cen = B.centroid
    bprops = {"name": "FDA City", "city": "Faisalabad", "osm_id": BOUNDARY_ID, "source": "OpenStreetMap", "accuracy": "georeferenced",
              "area_km2": round(B.area / 1e6, 2), "centre_lon": ll(cen.x, cen.y)[0], "centre_lat": ll(cen.x, cen.y)[1]}
    print("writing to", OUT)
    write("boundary", [feature(B, bprops)])
    write("roads", road_feats)
    write("blocks", block_feats)
    write("parks", park_feats)
    write("plots", plot_feats, {"data_note": "Plot geometry and attributes are generated samples (accuracy=approximate). Replace with surveyed/georeferenced data using the same property names."})

    if args.preview:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        COL = {"High": "#3fae5f", "Medium": "#e0a93a", "Low": "#c9573f"}
        fig, axs = plt.subplots(1, 2, figsize=(22, 11), dpi=100)
        for axx in axs:
            axx.set_aspect("equal")
            bx, by = B.exterior.xy
            axx.plot(bx, by, color="red", lw=1)
        BC = {"A": "#9bc", "B": "#bcb", "C": "#cba", "D": "#cab", "E": "#abc", "F": "#bbb"}
        for bf in block_feats:
            pg = Polygon([((lon - LON0) * MLON, (lat - LAT0) * MLAT) for lon, lat in bf["geometry"]["coordinates"][0]])
            k = bf["properties"]["kind"]
            col = "#7fbf7f" if k == "park" else "#d8b0e0" if k == "amenity" else "#eee" if k == "open" else BC[bf["properties"]["block"][-1]]
            axs[0].fill(*pg.exterior.xy, color=col, ec="#555", lw=0.3)
        for blk in "ABCDEF":
            pts = [Polygon([((lon - LON0) * MLON, (lat - LAT0) * MLAT) for lon, lat in bf["geometry"]["coordinates"][0]]).centroid
                   for bf in block_feats if bf["properties"]["block"][-1] == blk and bf["properties"]["kind"] == "residential"]
            if pts:
                axs[0].annotate("BLOCK " + blk, (sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts)),
                                fontsize=16, weight="bold", ha="center", color="#123")
        for pf in plot_feats:
            pg = Polygon([((lon - LON0) * MLON, (lat - LAT0) * MLAT) for lon, lat in pf["geometry"]["coordinates"][0]])
            axs[1].fill(*pg.exterior.xy, color=COL[pf["properties"]["dev_class"]], ec="none", alpha=0.9 if pf["properties"]["built"] else 0.35)
        for rf in road_feats:
            xs = [(lon - LON0) * MLON for lon, lat in rf["geometry"]["coordinates"]]
            ys = [(lat - LAT0) * MLAT for lon, lat in rf["geometry"]["coordinates"]]
            lw = {"main": 2.5, "arterial": 1.8, "residential": 0.5}[rf["properties"]["class"]]
            for axx in axs:
                axx.plot(xs, ys, color="#222", lw=lw)
        axs[0].set_title("blocks: letter zones, parks (green), amenities (purple), open (grey)")
        axs[1].set_title("plots coloured by dev_class (faded = vacant)")
        fig.savefig(args.preview, bbox_inches="tight")
        print("preview:", args.preview)


if __name__ == "__main__":
    main()

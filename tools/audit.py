"""Audit the generated map data (data/*.geojson) for geometric inconsistencies.

Checks the rules listed in tools/make_data.py: no overlaps, every plot fronts a road,
no bare land, landmark areas against the official kanal figures.
usage (from the repo root): python -I tools/audit.py"""
import json, math, sys, os
from collections import Counter, defaultdict
from shapely.geometry import shape, Polygon, LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely import affinity

repo = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KX, KY = 111320 * math.cos(math.radians(31.525)), 111320.0
INVALID = Counter()
def tom(g):
    g = affinity.affine_transform(g, [KX, 0, 0, KY, -73.0875 * KX, -31.525 * KY])
    if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_valid:
        INVALID[g.geom_type] += 1; g = g.buffer(0)
    return g
D = lambda n: json.load(open(os.path.join(repo, "data", n + ".geojson"), encoding="utf-8"))["features"]
plots = D("plots"); lms = D("landmarks"); surf = D("road_surface"); water = D("water"); blocks = D("blocks"); bnd = D("boundary"); roads = D("roads")
PG = [tom(shape(f["geometry"])) for f in plots]
PP = [f["properties"] for f in plots]
LG = [(f["properties"], tom(shape(f["geometry"]))) for f in lms if f["geometry"]["type"] == "Polygon"]
carr_parts = [tom(shape(f["geometry"])) for f in surf if f["properties"]["kind"] == "carriageway"]
row_parts = [tom(shape(f["geometry"])) for f in surf]
nala_parts = [tom(shape(f["geometry"])) for f in water if f["properties"]["kind"] in ("nala_water", "nala_wall", "nala_bank")]
carr, row, nala = unary_union(carr_parts), unary_union(row_parts), unary_union(nala_parts)
row_tree = STRtree(row_parts)
B = tom(shape(bnd[0]["geometry"]))
tree = STRtree(PG)
print("- invalid polygons repaired for the audit:", dict(INVALID))
print(f"plots {len(PG)}, landmarks {len(LG)}, boundary {B.area/1e6:.2f} km2, carriageway {carr.area/1e4:.1f} ha, right-of-way {row.area/1e4:.1f} ha")

def over(name, parts, thresh=1.0):
    tot = {}
    for g in parts:                       # piece by piece: one huge union makes every intersection slow
        for i in tree.query(g, predicate="intersects"):
            a = PG[i].intersection(g).area
            if a > 0: tot[i] = tot.get(i, 0) + a
    bad = [(i, a) for i, a in tot.items() if a > thresh]
    print(f"- plots overlapping {name}: {len(bad)} (total {sum(a for _, a in bad):.0f} m2)", [PP[i]['plot_no'] for i, _ in sorted(bad, key=lambda t: -t[1])[:6]])
over("carriageway", carr_parts); over("road right-of-way", row_parts); over("nalla", nala_parts)
n = 0; ex = []
for pr, g in LG:
    if pr.get("outside"): continue
    for i in tree.query(g):
        a = PG[i].intersection(g).area
        if a > 1: n += 1; ex.append((pr["name"], PP[i]["plot_no"], round(a)))
print(f"- plots overlapping landmarks: {n}", ex[:6])
out = [PP[i]["plot_no"] for i in range(len(PG)) if not B.buffer(2).contains(PG[i])]
print(f"- plots outside boundary: {len(out)}", out[:6])
# plot-plot overlaps
pp = 0
for i, g in enumerate(PG):
    for j in tree.query(g):
        if j > i and g.intersection(PG[j]).area > 2.0: pp += 1
print(f"- plot-plot overlaps: {pp}")
# shape quality
areas = [g.area for g in PG]
size_ref = {"5 Marla": 130, "10 Marla": 254, "20 Marla": 502, "Commercial": 167}
dev = Counter()
odd = []
for g, p in zip(PG, PP):
    r = g.area / size_ref[p["size"]]
    dev["<0.6x" if r < .6 else "0.6-0.85x" if r < .85 else "0.85-1.2x" if r <= 1.2 else "1.2-1.6x" if r <= 1.6 else ">1.6x"] += 1
    mrr = g.minimum_rotated_rectangle
    if g.area / mrr.area < 0.8: odd.append(p["plot_no"])
print("- plot area vs official size:", dict(dev))
print(f"- non-rectangular plots (fill < 80% of bounding box): {len(odd)}", odd[:8])
# plots not fronting any road (distance to right-of-way > 3 m)
# (plots read from a block map can sit a few metres off an OpenStreetMap street: the sheets register to about 2.5 m)
gap = [min((row_parts[j].distance(g) for j in row_tree.query(g.buffer(30.0))), default=99.0) for g in PG]
far = [PP[i]["plot_no"] for i, d in enumerate(gap) if d > 6.0]
print(f"- plots more than 3 m from any road reserve: {sum(1 for d in gap if d > 3.0)}, of which 3 to 6 m (registration gap): {sum(1 for d in gap if 3.0 < d <= 6.0)}; "
      f"more than 6 m (no street found): {len(far)} ({100*len(far)/len(PG):.1f}%)", far[:6])
# landmarks
names = Counter(pr["name"] for pr, _ in LG)
print("- duplicate landmark names:", {k: v for k, v in names.items() if v > 1})
for (p1, g1) in LG:
    if p1["kind"] != "roundabout" and sum(g1.intersection(row_parts[i]).area for i in row_tree.query(g1, predicate="intersects") if surf[i]["properties"]["kind"] == "carriageway") > 5: print(f"- landmark on carriageway: {p1['name']}")
lo = []
for i, (p1, g1) in enumerate(LG):
    for p2, g2 in LG[i + 1:]:
        a = g1.intersection(g2).area
        if a > 5: lo.append((p1["name"], p2["name"], round(a)))
print(f"- landmark-landmark overlaps: {len(lo)}", lo[:8])
small = [(pr["name"], round(g.area)) for pr, g in LG if g.area < 400 and pr["kind"] not in ("roundabout",)]
print("- very small landmark sites (< 400 m2):", small)
# official kanal vs carved area
offs = [(pr["name"], pr["kanal_official"], g.area / 505.857) for pr, g in LG if pr.get("kanal_official")]
bad = [(n, k, round(m, 1)) for n, k, m in offs if abs(m - k) / k > 0.25]
print(f"- facilities with an official area: {len(offs)}; more than 25% off: {len(bad)}", bad)
# main gate
gates = [f for f in lms if f["properties"]["kind"] == "gate"]
mains = [tom(shape(f["geometry"])) for f in roads if f["properties"]["class"] == "main"]
for f in gates:
    gp = tom(shape(f["geometry"])); ds = sorted(m.distance(gp) for m in mains)[:2]
    print(f"- main gate: {f['properties']['name']} at {f['geometry']['coordinates'][1]:.5f}, {f['geometry']['coordinates'][0]:.5f}; carriageway centre lines {ds[0]:.1f} m and {ds[1]:.1f} m either side, span {f['properties']['span']} m")
if not gates: print("- main gate: MISSING")
# plot outlines and buildings
print("- plot outlines:", dict(Counter(p.get("layout") for p in PP)))
try:
    BL = D("buildings")
except FileNotFoundError:
    BL = []
BG = [tom(shape(f["geometry"])) for f in BL]
on_road = sum(1 for g in BG if sum(g.intersection(carr_parts[i]).area for i in STRtree(carr_parts).query(g)) > 0.35 * g.area) if BG else 0
no_plot = sum(1 for f in BL if f["properties"].get("plot_id") is None)
built = [p for p in PP if p["built"]]
ids = {f["properties"].get("plot_id") for f in BL}
print(f"- buildings standing today: {len(BL)} footprints; on a carriageway: {on_road}; not on any plot: {no_plot}; built plots: {len(built)}; built plots without a footprint: {sum(1 for p in built if p['id'] not in ids)}")
print("  built plots per block:", dict(sorted(Counter(p["block"] for p in built).items())), "| development class:", dict(Counter(p["dev_class"] for p in PP)))
# per block
per = defaultdict(Counter)
for p in PP: per[p["block"]][p["size"]] += 1
for b in sorted(per): print("  ", b, dict(per[b]), "total", sum(per[b].values()))
# uncovered land inside boundary
other = [tom(shape(f["geometry"])) for f in blocks if f["properties"]["layer"] in ("green", "open") or f["properties"]["kind"] in ("median", "strip", "island", "greenbelt")]
cover = unary_union([row.buffer(0.1), nala.buffer(0.1)] + [g.buffer(0.7) for g in PG] + [g.buffer(0.7) for _, g in LG] + [g.buffer(0.7) for g in other])
gaps = [q for q in (B.difference(cover).geoms if hasattr(B.difference(cover), "geoms") else [B.difference(cover)]) if q.area > 600 and q.buffer(-4).area > 200]
print(f"- empty land patches > 600 m2 inside boundary (no plot, road or facility): {len(gaps)}, total {sum(q.area for q in gaps)/1e4:.1f} ha; largest {[round(q.area) for q in sorted(gaps, key=lambda q: -q.area)[:8]]}")
for q in sorted(gaps, key=lambda q: -q.area)[:5]:
    c = q.representative_point(); print(f"     gap {q.area:.0f} m2 at {31.525 + c.y / KY:.5f}, {73.0875 + c.x / KX:.5f}")

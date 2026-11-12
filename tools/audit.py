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
carr = unary_union([tom(shape(f["geometry"])) for f in surf if f["properties"]["kind"] == "carriageway"])
row = unary_union([tom(shape(f["geometry"])) for f in surf])
nala = unary_union([tom(shape(f["geometry"])) for f in water if f["properties"]["kind"] in ("nala_water", "nala_wall", "nala_bank")])
B = tom(shape(bnd[0]["geometry"]))
tree = STRtree(PG)
print("- invalid polygons repaired for the audit:", dict(INVALID))
print(f"plots {len(PG)}, landmarks {len(LG)}, boundary {B.area/1e6:.2f} km2, carriageway {carr.area/1e4:.1f} ha, right-of-way {row.area/1e4:.1f} ha")

def over(name, geom, thresh=1.0):
    idx = tree.query(geom)
    bad = [(i, PG[i].intersection(geom).area) for i in idx]
    bad = [(i, a) for i, a in bad if a > thresh]
    print(f"- plots overlapping {name}: {len(bad)} (total {sum(a for _, a in bad):.0f} m2)", [PP[i]['plot_no'] for i, _ in sorted(bad, key=lambda t: -t[1])[:6]])
over("carriageway", carr); over("road right-of-way", row); over("nalla", nala)
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
far = [PP[i]["plot_no"] for i, g in enumerate(PG) if g.distance(row) > 3.0]
print(f"- plots with no road frontage (> 3 m from any road): {len(far)} ({100*len(far)/len(PG):.1f}%)", far[:6])
# landmarks
names = Counter(pr["name"] for pr, _ in LG)
print("- duplicate landmark names:", {k: v for k, v in names.items() if v > 1})
for (p1, g1) in LG:
    if g1.intersection(carr).area > 5 and p1["kind"] != "roundabout": print(f"- landmark on carriageway: {p1['name']} {g1.intersection(carr).area:.0f} m2")
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
# per block
per = defaultdict(Counter)
for p in PP: per[p["block"]][p["size"]] += 1
for b in sorted(per): print("  ", b, dict(per[b]), "total", sum(per[b].values()))
# uncovered land inside boundary
other = [tom(shape(f["geometry"])) for f in blocks if f["properties"]["layer"] == "green" or f["properties"]["kind"] in ("median", "strip", "island", "greenbelt")]
cover = unary_union([row.buffer(0.1), nala.buffer(0.1)] + [g.buffer(0.7) for g in PG] + [g.buffer(0.7) for _, g in LG] + [g.buffer(0.7) for g in other])
gaps = [q for q in (B.difference(cover).geoms if hasattr(B.difference(cover), "geoms") else [B.difference(cover)]) if q.area > 600 and q.buffer(-4).area > 200]
print(f"- empty land patches > 600 m2 inside boundary (no plot, road or facility): {len(gaps)}, total {sum(q.area for q in gaps)/1e4:.1f} ha; largest {[round(q.area) for q in sorted(gaps, key=lambda q: -q.area)[:8]]}")
for q in sorted(gaps, key=lambda q: -q.area)[:5]:
    c = q.representative_point(); print(f"     gap {q.area:.0f} m2 at {31.525 + c.y / KY:.5f}, {73.0875 + c.x / KX:.5f}")

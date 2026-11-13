"""Read the plot layout off the official FDA City block maps.

The block maps on fdacity.pk draw every plot as a small outlined cell, every street as a white
corridor and every street block as a closed outline. This tool reads three things from each sheet:

  * street blocks   closed groups of plots, bounded by the white street corridors;
  * plot cells      the individual plots inside a street block, where the print is clear enough;
  * streets         the centre lines of the white corridors, with their width.

Each sheet is then registered to the ground: the similarity transform of plan_features.json is
refined by fitting the sheet's street centre lines to the OpenStreetMap streets (which were
traced on satellite imagery), so that sheet features land on the real streets.

Output: tools/source/sheet_layout.json (lon/lat) and sheet_ink_A..F.png (how much is drawn where,
8 px blocks). tools/make_data.py builds the plots from them.
Sheets are downloaded once into tools/source/cache/.

usage (from the repo root):  python -I tools/trace_plots.py [--debug DIR]
needs: pip install numpy pillow shapely opencv-python-headless scikit-image scipy
"""
import argparse
import io
import json
import math
import os
import urllib.request

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Polygon
from skimage.morphology import skeletonize

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
CACHE = os.path.join(SRC, "cache")

LAT_REF = 31.525
LON0, LAT0 = 73.0875, 31.525
KX = 111320.0 * math.cos(math.radians(LAT_REF))
KY = 111320.0
SHEETS = "ABCDEF"


def ll(e, n):
    return (round(LON0 + e / KX, 7), round(LAT0 + n / KY, 7))


def xy(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


# ---------------------------------------------------------------------------------
def load_sheet(name, sh):
    """Pages of a block map stacked top to bottom, cached as PNG."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"sheet_{name}.png")
    if not os.path.exists(path):
        pages = []
        for url in sh["urls"]:
            print("  downloading", url)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Terralyt-FYP"})
            pages.append(Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("RGB"))
        w = max(p.width for p in pages)
        im = Image.new("RGB", (w, sum(p.height for p in pages)), "white")
        y = 0
        for p in pages:
            im.paste(p, (0, y))
            y += p.height
        im.save(path)
    return cv2.imread(path)


def similarity(sh):
    X = np.array([complex(p["px"][0], -p["px"][1]) for p in sh["control_points"]])
    Z = np.array([complex(*xy(*p["lonlat"])) for p in sh["control_points"]])
    sol, *_ = np.linalg.lstsq(np.vstack([X, np.ones_like(X)]).T, Z, rcond=None)
    k, t = sol
    # as a 2x3 affine acting on (px, py): e = a*px + b*py + c
    return np.array([[k.real, k.imag, t.real], [k.imag, -k.real, t.imag]])


def apply(A, pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    return pts @ A[:, :2].T + A[:, 2]


# ---------------------------------------------------------------------------------
def masks(img, mpp):
    """ink (lines, lettering, pictures) and the street space of a sheet."""
    im = img.astype(np.int16)
    mn = img.min(axis=2)
    ch = im.max(axis=2) - im.min(axis=2)
    kb = 9 if mpp < 1.5 else 7
    bh = cv2.morphologyEx(mn, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (kb, kb)))
    thin = (bh > 24).astype(np.uint8)
    solid = cv2.morphologyEx((mn < 120).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    coloured = cv2.morphologyEx(((mn < 170) & (ch > 60)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    ink = thin | solid | coloured
    # street space: lettering inside the corridors ("ROAD 40'-0" WIDE") has no long straight strokes, plot outlines do
    # (plot outlines are coloured, lettering is grey; grey lines are kept only where they run long and straight)
    Lr = int(round(max(7, 12.0 / mpp)))
    Lr += 1 - Lr % 2
    ink_nt = (((thin > 0) & (ch >= 38)).astype(np.uint8) | line_open(thin, Lr, [math.pi * i / 36 for i in range(36)]) | solid | coloured)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink_nt, 8)
    small = (st[:, 4] <= 100 / mpp ** 2) & (np.maximum(st[:, 2], st[:, 3]) <= 31 / mpp)
    small[0] = False
    ink_nt[small[lab]] = 0
    ink_nt = cv2.morphologyEx(ink_nt, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8) if mpp < 1.0 else np.ones((3, 3), np.uint8))
    paper = (1 - ink_nt).astype(np.uint8)
    # street space = the large connected white areas; plot cells are small enclosed white areas
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(paper, 4)
    big = st2[:, 4] > 2500 / mpp ** 2
    big[0] = False
    road = big[lab2].astype(np.uint8)
    return thin, ink, road, mn, ch


def line_open(ink, L, angles):
    out = np.zeros_like(ink)
    for a in angles:
        k = np.zeros((L, L), np.uint8)
        c = (L - 1) / 2
        dx, dy = math.cos(a) * c, math.sin(a) * c
        cv2.line(k, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1, 1)
        out |= cv2.morphologyEx(ink, cv2.MORPH_OPEN, k)
    return out


def colour_class(img, mask):
    """Plot size from the colour of the outlines: green 5 Marla, pink 10 Marla, blue 20 Marla, red commercial."""
    px = img[mask > 0].astype(np.int16)
    if len(px) < 12:
        return None, {}
    b, g, r = px[:, 0], px[:, 1], px[:, 2]
    cnt = {
        "5 Marla": int(((g >= r + 12) & (g >= b + 12)).sum()),
        "10 Marla": int(((r >= g + 25) & (b >= g + 5) & (r - b < 90)).sum()),
        "Commercial": int(((r >= g + 45) & (r >= b + 45)).sum()),
        "20 Marla": int(((b >= r + 25) & (b >= g - 5)).sum()),
    }
    best = max(cnt, key=cnt.get)
    return (best if cnt[best] >= 0.3 * sum(cnt.values()) and cnt[best] >= 10 else None), cnt


def dominant_angle(contour):
    (_, _), (rw, rh), ang = cv2.minAreaRect(contour)
    return math.radians(ang if rw >= rh else ang + 90)


def cells_of(img, thin, mn, ch, mpp):
    """Plot cells: small white areas closed in by long straight outlines. Returns cells grouped into street blocks."""
    H, W = mn.shape
    L = int(round(max(7, 11.6 / mpp)))
    L += 1 - L % 2
    lines = line_open(thin, L, [math.pi * i / 36 for i in range(36)])       # plot numbers have no long strokes
    solid = cv2.morphologyEx((mn < 120).astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    paper = (1 - (lines | solid)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(paper, 4)
    amin, amax = 70 / mpp ** 2, 1600 / mpp ** 2
    line_px = (thin > 0) & (ch > 38)
    cells = []
    cellmap = np.zeros((H, W), np.uint8)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        pad = 3
        if a > amax or x <= pad or y <= pad or x + w >= W - pad or y + h >= H - pad or w < 3 or h < 3:
            continue
        m = (lab[y - pad:y + h + pad, x - pad:x + w + pad] == i).astype(np.uint8)
        m = cv2.dilate(m, np.ones((3, 3), np.uint8))                          # out towards the line centres
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cs, key=cv2.contourArea)
        ca = cv2.contourArea(c)
        if ca < amin or ca > amax:
            continue
        (rx, ry), (rw, rh), ang = cv2.minAreaRect(c)
        if rw * rh <= 0 or min(rw, rh) * mpp < 5.5 or max(rw, rh) / min(rw, rh) > 6:
            continue
        rect = ca / (rw * rh)
        sol = ca / (cv2.contourArea(cv2.convexHull(c)) + 1e-6)
        if not (rect > 0.8 or (sol > 0.93 and rect > 0.5)):
            continue
        off = np.array([x - pad + 0.5, y - pad + 0.5])
        ring = cv2.dilate(m, np.ones((5, 5), np.uint8)) - cv2.erode(m, np.ones((3, 3), np.uint8))
        size, _ = colour_class(img[y - pad:y + h + pad, x - pad:x + w + pad], ring & line_px[y - pad:y + h + pad, x - pad:x + w + pad])
        cells.append({"px": cv2.approxPolyDP(c, 1.2, True)[:, 0, :].astype(float) + off, "pts": c[:, 0, :].astype(float) + off,
                      "area": ca, "rect": rect, "colour": size, "ang": math.radians(ang) % (math.pi / 2), "c": (rx + off[0], ry + off[1])})
        cv2.fillPoly(cellmap, [np.round(cells[-1]["px"]).astype(np.int32)], 1)
    # street blocks: cells that touch across an outline
    g = 5 if mpp < 1.5 else 3
    nb, blab = cv2.connectedComponents(cv2.dilate(cellmap, np.ones((g, g), np.uint8)), connectivity=4)
    blocks = {}
    for c in cells:
        k = int(blab[int(np.clip(c["c"][1], 0, H - 1)), int(np.clip(c["c"][0], 0, W - 1))])
        blocks.setdefault(k, []).append(c)
    out = []
    for k, cl in blocks.items():
        if k == 0:
            continue
        # block axis: circular median of the cell angles (period 90 degrees)
        v = np.array([c["ang"] for c in cl if c["rect"] > 0.86] or [c["ang"] for c in cl])
        z = np.exp(4j * v).mean()
        out.append({"cells": cl, "angle": float(np.angle(z) / 4)})
    return out

def regular_cells(block):
    """Square up the rectangular cells of a block to its axis and make neighbours share edges."""
    a = block["angle"]
    R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])        # sheet px -> block frame
    boxes = []
    for c in block["cells"]:
        if c["rect"] > 0.84:
            q = c["pts"] @ R.T
            boxes.append([q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()])
        else:
            boxes.append(None)
    for k in (0, 1):                                    # snap x edges, then y edges
        vals = sorted((b[k + d], i, k + d) for i, b in enumerate(boxes) if b is not None for d in (0, 2))
        grp = []
        for v in vals + [(1e18, -1, 0)]:
            if grp and v[0] - grp[-1][0] > 2.2:
                mean = sum(g[0] for g in grp) / len(grp)
                for _, i, j in grp:
                    boxes[i][j] = mean
                grp = []
            grp.append(v)
    out = []
    for c, b in zip(block["cells"], boxes):
        if b is None or b[2] - b[0] < 3 or b[3] - b[1] < 3:
            out.append(c["px"])
        else:
            q = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
            out.append(q @ R)
    return out


# ---------------------------------------------------------------------------------
def trace_skeleton(sk):
    """Polylines (pixel paths) of a 1 px skeleton, split at junctions and ends."""
    sk = sk.astype(np.uint8)
    H, W = sk.shape
    nb = cv2.filter2D(sk, cv2.CV_16S, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - sk
    node = (sk > 0) & (nb != 2)
    nn, nlab = cv2.connectedComponents(node.astype(np.uint8), connectivity=8)
    ys, xs = np.nonzero(node)
    cen = np.zeros((nn, 2))
    cnt = np.zeros(nn)
    np.add.at(cen, nlab[ys, xs], np.stack([xs, ys], 1))
    np.add.at(cnt, nlab[ys, xs], 1)
    cen[1:] /= cnt[1:, None]
    visited = np.zeros_like(sk, bool)
    edges = []
    N8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    for y, x in zip(ys, xs):
        a = nlab[y, x]
        for dx, dy in N8:
            px, py = x + dx, y + dy
            if not (0 <= px < W and 0 <= py < H) or not sk[py, px] or node[py, px] or visited[py, px]:
                continue
            path = [(x, y), (px, py)]
            visited[py, px] = True
            b = 0
            while True:
                cx, cy = path[-1]
                nxt = None
                for ex, ey in N8:
                    qx, qy = cx + ex, cy + ey
                    if not (0 <= qx < W and 0 <= qy < H) or not sk[qy, qx]:
                        continue
                    if node[qy, qx]:
                        if nlab[qy, qx] != a or len(path) > 3:
                            nxt = (qx, qy, True)
                            break
                        continue
                    if not visited[qy, qx]:
                        nxt = (qx, qy, False)
                if nxt is None:
                    break
                if nxt[2]:
                    b = nlab[nxt[1], nxt[0]]
                    path.append((nxt[0], nxt[1]))
                    break
                visited[nxt[1], nxt[0]] = True
                path.append((nxt[0], nxt[1]))
            pts = np.array(path, float)
            pts[0] = cen[a]
            if b:
                pts[-1] = cen[b]
            edges.append({"a": int(a), "b": int(b), "pts": pts, "free": int(cnt[a] == 1 and nb[y, x] <= 1) + int(b == 0 or (cnt[b] == 1 and nb[int(path[-1][1]), int(path[-1][0])] <= 1))})
    return edges


def streets_of(road, mpp):
    dt = cv2.distanceTransform(road, cv2.DIST_L2, 5)
    sk = skeletonize(road > 0)
    sk &= (dt * mpp > 3.6) & (dt * mpp < 20)             # corridors 7 to 40 m wide
    out = []
    for e in trace_skeleton(sk):
        p = e["pts"]
        if len(p) < 3:
            continue
        ix = np.clip(np.round(p[1:-1]).astype(int), 0, [road.shape[1] - 1, road.shape[0] - 1])
        width = float(np.median(dt[ix[:, 1], ix[:, 0]])) * 2 * mpp if len(ix) else 0
        ln = LineString(p)
        if ln.length * mpp < (26 if e["free"] else 9):
            continue                                     # spurs into corners and dead ends
        ln = ln.simplify(2.2 / mpp)
        out.append({"px": np.array(ln.coords), "width": width})
    return out


# ---------------------------------------------------------------------------------
def osm_points(step=2.0):
    osm = json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"]
    pts = []
    for e in osm:
        t = e.get("tags", {})
        if t.get("highway") not in ("residential", "unclassified", "service", "living_street", "tertiary", "road"):
            continue
        ln = LineString([xy(p["lon"], p["lat"]) for p in e["geometry"]])
        if ln.length < 5:
            continue
        for d in np.arange(0, ln.length, step):
            q = ln.interpolate(d)
            pts.append((q.x, q.y))
    return np.array(pts)


def register(A, streets, tree, osm, name):
    """Refine the sheet transform so its street centre lines fall on the OpenStreetMap streets."""
    S = []
    for s in streets:
        if not 8 <= s["width"] <= 24:
            continue
        ln = LineString(s["px"])
        step = max(1.0, 3.0 / math.hypot(A[0, 0], A[1, 0]))
        for d in np.arange(0, ln.length, step):
            q = ln.interpolate(d)
            S.append((q.x, q.y))
    S = np.array(S)
    stats = None
    for thr in (30, 22, 16, 12, 9, 7, 6, 6, 6):
        M = apply(A, S)
        d, j = tree.query(M)
        ok = d < thr
        if ok.sum() < 30:
            break
        X = np.hstack([S[ok], np.ones((ok.sum(), 1))])
        sol, *_ = np.linalg.lstsq(X, osm[j[ok]], rcond=None)
        A = sol.T
        stats = (int(ok.sum()), len(S), float(np.sqrt((d[ok] ** 2).mean())))
    M = apply(A, S)
    d, j = tree.query(M)
    ok = d < 6
    print(f"  sheet {name}: {ok.sum()} of {len(S)} street points matched to OpenStreetMap, rms {np.sqrt((d[ok]**2).mean()):.2f} m, "
          f"scale {math.hypot(A[0,0],A[1,0]):.3f}/{math.hypot(A[0,1],A[1,1]):.3f} m/px")
    return A, S[ok], osm[j[ok]] - M[ok]


# ---------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", default=None, help="folder for check images")
    args = ap.parse_args()
    feats = json.load(open(os.path.join(SRC, "plan_features.json"), encoding="utf-8"))
    osm = osm_points()
    tree = cKDTree(osm)
    out = {"about": "Street blocks, plot cells and street centre lines read from the official FDA City block maps by tools/trace_plots.py. "
                    "Coordinates are lon/lat (WGS84). Each sheet was registered to the OpenStreetMap streets.", "sheets": {}}
    for name in SHEETS:
        sh = feats["sheets"][name]
        img = load_sheet(name, sh)
        A0 = similarity(sh)
        mpp = math.hypot(A0[0, 0], A0[1, 0])
        print(f"sheet {name}: {img.shape[1]}x{img.shape[0]} px, {mpp:.3f} m/px")
        thin, ink, road, mn, ch = masks(img, mpp)
        streets = streets_of(road, mpp)
        A, _, _ = register(A0, streets, tree, osm, name)
        blocks = cells_of(img, thin, mn, ch, mpp)
        det = abs(np.linalg.det(A[:, :2]))
        nb = nc = 0
        ob = []
        for bi, b in enumerate(blocks):
            cl = []
            for c, px in zip(b["cells"], regular_cells(b)):
                q = Polygon(apply(A, px))
                if not q.is_valid:
                    q = q.buffer(0)
                if q.geom_type == "Polygon" and q.area > 50:
                    cl.append({"ring": [list(ll(*p)) for p in q.exterior.coords[:-1]], "colour": c["colour"], "rect": round(c["rect"], 2)})
            if cl:
                d = apply(A, [[math.cos(b["angle"]), math.sin(b["angle"])], [0, 0]])
                ob.append({"angle": round(math.degrees(math.atan2(d[0][1] - d[1][1], d[0][0] - d[1][0])), 1), "cells": cl})
                nb += 1
                nc += len(cl)
        os_ = [{"line": [list(ll(*p)) for p in apply(A, s["px"])], "width_m": round(s["width"], 1)} for s in streets]
        # how much is drawn where: lets the generator tell blank paper from plotted land
        blk = 8
        dens = cv2.resize(thin.astype(np.float32), (img.shape[1] // blk, img.shape[0] // blk), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(SRC, f"sheet_ink_{name}.png"), np.clip(dens * 255, 0, 255).astype(np.uint8))
        # outline of everything the sheet draws (plots, pictures and the streets between them): beyond it the paper is blank
        m = (dens > 0.06).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        drawn = []
        for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            if cv2.contourArea(c) * (blk * mpp) ** 2 < 2500:
                continue
            q = Polygon(apply(A, (cv2.approxPolyDP(c, 0.8, True)[:, 0, :].astype(float) + 0.5) * blk))
            if not q.is_valid:
                q = q.buffer(0)
            for g in (q.geoms if hasattr(q, "geoms") else [q]):
                if g.geom_type == "Polygon" and g.area > 2500:
                    drawn.append([list(ll(*pt)) for pt in g.exterior.coords[:-1]])
        out["sheets"][name] = {"affine": [[round(float(v), 6) for v in row] for row in A], "size": [img.shape[1], img.shape[0]],
                               "ink": {"file": f"sheet_ink_{name}.png", "block": blk}, "drawn": drawn, "blocks": ob, "streets": os_}
        print(f"  {nb} street blocks, {nc} plot cells, {len(os_)} street pieces")
        if args.debug:
            os.makedirs(args.debug, exist_ok=True)
            vis = (img * 0.45 + 135).astype(np.uint8)
            vis[road > 0] = (vis[road > 0] * 0.6 + np.array([210, 150, 90]) * 0.4).astype(np.uint8)
            COL = {"5 Marla": (60, 170, 60), "10 Marla": (170, 60, 200), "20 Marla": (200, 120, 0), "Commercial": (0, 0, 220), None: (90, 90, 90)}
            for b in blocks:
                for c, px in zip(b["cells"], regular_cells(b)):
                    cv2.polylines(vis, [np.round(px).astype(np.int32)], True, COL[c["colour"]], 1)
            for s in streets:
                cv2.polylines(vis, [np.round(s["px"]).astype(np.int32)], False, (0, 0, 0), 1)
            cv2.imwrite(os.path.join(args.debug, f"trace_{name}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 88])
    path = os.path.join(SRC, "sheet_layout.json")
    json.dump(out, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print("wrote", path, os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    main()

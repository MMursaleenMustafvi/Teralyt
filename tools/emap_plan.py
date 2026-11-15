"""Read the FDA City plan from emap.pk and register it to the real streets.

emap.pk shows the whole FDA City plan (a redraw of the official FDA plan, newer revision with Block X)
as map tiles over Google satellite: https://emap.pk/fda-city-faisalabad-map . At zoom 19 a tile pixel
is about 0.25 m and every plot outline and plot number is printed sharply. emap's own placement on
the satellite photo is only good to about 4 m (up to 13 m in Block D), so its positions are not
used as they are: the plan is registered piece by piece to the OpenStreetMap streets (which lie on
the real roads, checked on Google and Esri imagery).

Stages (each caches its result in tools/source/cache/emap/, delete a file to redo that stage):
  1. fetch     download the zoom-19 tiles of the plan (about 4,000 tiles, 50 MB)
  2. cells     segment every closed plot outline (and every larger coloured site) in plan pixels
  3. roads     the plan's road space at half resolution (0.5 m)
  4. register  displacement field: local shift of the plan against the OpenStreetMap streets,
               measured in overlapping 260 m windows, outliers removed, smoothed
  5. ocr       read the plot number printed in each cell (Tesseract)
  5b. rapid    read them again with RapidOCR (tools/rapid_ocr.py, run in a Python with rapidocr_onnxruntime)
  6. digits    read them again with a digit recogniser trained on the map's own print (from Tesseract's sure
               readings) and correct them with their neighbours (plots in a row are numbered one after the other)
  7. write     tools/source/emap_layout.json (cells in lon/lat, registered) and emap_road.png

usage:  python -I tools/emap_plan.py [--stages fetch,cells,roads,register,ocr,write] [--check out_dir]
needs:  numpy scipy pillow opencv-python-headless shapely; Tesseract (winget install UB-Mannheim.TesseractOCR)
"""
import argparse
from collections import Counter
import concurrent.futures as cf
import json
import math
import os
import subprocess
import tempfile
import urllib.request

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
CACHE = os.path.join(SRC, "cache", "emap")
TILE_URL = "https://emap.pk/storage/tiles/faisalabad/fda_city/{z}/{x}/{y}.png?v=1"
PAGE = "https://emap.pk/fda-city-faisalabad-map"
S, W, N, E = 31.50136, 73.06612, 31.54504, 73.10260      # plan bounds published by emap.pk (map 117)
Z = 19
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
LAT_REF = 31.525
MPP = 156543.03392 * math.cos(math.radians(31.523)) / 2 ** Z    # metres per zoom-19 pixel here (0.255)
KX = 111320.0 * math.cos(math.radians(LAT_REF))
KY = 111320.0


def tile_xy(lon, lat, z=Z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def gpx_ll(gx, gy, z=Z):
    """global pixel (zoom z) -> lon, lat (arrays ok)"""
    n = 256 * 2 ** z
    lon = np.asarray(gx) / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi - 2 * np.pi * np.asarray(gy) / n)))
    return lon, lat


def ll_gpx(lon, lat, z=Z):
    n = 256 * 2 ** z
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return (lon + 180) / 360 * n, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n


TX0, TY0 = (int(v) for v in tile_xy(W, N))
TX1, TY1 = (int(v) for v in tile_xy(E, S))
NTX, NTY = TX1 - TX0 + 1, TY1 - TY0 + 1
GX0, GY0 = TX0 * 256, TY0 * 256                     # global pixel of the mosaic origin


def tpath(x, y):
    return os.path.join(CACHE, "19", f"{x}_{y}.png")


# ------------------------------------------------------------------------------------------------
def fetch():
    os.makedirs(os.path.join(CACHE, "19"), exist_ok=True)
    jobs = [(x, y) for x in range(TX0, TX1 + 1) for y in range(TY0, TY1 + 1) if not os.path.exists(tpath(x, y))]

    def get(xy):
        x, y = xy
        req = urllib.request.Request(TILE_URL.format(z=Z, x=x, y=y), headers={"User-Agent": "Mozilla/5.0 (Terralyt FYP)", "Referer": PAGE})
        for _ in range(3):
            try:
                data = urllib.request.urlopen(req, timeout=40).read()
                open(tpath(x, y), "wb").write(data)
                return True
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    open(tpath(x, y), "wb").write(b"")          # no tile here (outside the plan)
                    return False
            except Exception:
                pass
        return False

    with cf.ThreadPoolExecutor(10) as ex:
        ok = sum(ex.map(get, jobs))
    print(f"fetch: {NTX}x{NTY} tiles, {len(jobs)} downloaded now ({ok} with content)")


def window(tx, ty, nx, ny):
    """RGBA array of tiles [tx, tx+nx) x [ty, ty+ny)"""
    a = np.zeros((ny * 256, nx * 256, 4), np.uint8)
    for i in range(nx):
        for j in range(ny):
            p = tpath(tx + i, ty + j)
            if os.path.exists(p) and os.path.getsize(p) > 0:
                a[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = np.asarray(Image.open(p).convert("RGBA"))
    return a


def _line_kernels(L=25, step=6):
    ks = []
    c = (L - 1) / 2
    for ang in np.arange(0, 180, step):
        k = np.zeros((L, L), np.float32)
        dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        for t in np.linspace(-c, c, 2 * L):
            k[int(round(c + t * dy)), int(round(c + t * dx))] = 1
        ks.append(k / k.sum())
    return ks


KERNELS = _line_kernels()


def masks(a):
    """line / road / fill masks of an RGBA window.

    Plot lines are thin, straight and long; the printed numbers are thick, short black strokes; the emap.pk watermark
    is light and short. So: (1) find the digit glyphs (thick dark strokes, small), (2) measure how dark each pixel
    is against its surroundings with the glyphs taken out, (3) keep as lines the pixels that lie on a dark straight run
    of 25 px (6 m) in any direction. A line that runs through a digit stays a line."""
    al = a[..., 3] > 200
    rgb = a[..., :3].astype(np.int16)
    mx, mn = rgb.max(2), rgb.min(2)
    s = rgb.sum(2).astype(np.float32)
    dark = (mx < 110) & al
    core = ndi.binary_opening(dark, structure=np.ones((3, 3)))
    lab, n = ndi.label(core)
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(lab)):
        keep[i + 1] = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) <= 60
    glyph = ndi.binary_dilation(keep[lab], iterations=2) & ndi.binary_dilation(dark)
    gcore = ndi.binary_dilation(keep[lab], iterations=1)        # the strokes themselves
    # white numbers on the red commercial plots: small bright shapes surrounded by red (not the grey road)
    red = (np.abs(rgb - np.array([220, 38, 28])).sum(2) < 90) & al
    white = (mn > 238) & al
    wl, wn = ndi.label(white)
    if wn:
        ring = ndi.binary_dilation(white, iterations=3) & ~ndi.binary_dilation(white, iterations=1)   # past the anti-aliased edge
        idx = np.arange(1, wn + 1)
        near_lab = ndi.grey_dilation(wl, size=7)
        tot = ndi.sum(ring, near_lab, idx)
        on_red = ndi.sum(ring & red, near_lab, idx)
        okw = np.zeros(wn + 1, bool)
        for i, sl in enumerate(ndi.find_objects(wl)):
            if sl is not None and max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) <= 70 and tot[i] > 0 and on_red[i] / tot[i] > 0.5:
                okw[i + 1] = True
        lglyph = ndi.binary_dilation(okw[wl], iterations=1) & (white | ndi.binary_dilation(white))
        glyph |= lglyph
        gcore |= lglyph
        # white digits must not make the red around them look dark: clamp only pixels brighter than the red fill,
        # so a dark divider line beside a digit stays dark
        s = np.where(ndi.binary_dilation(lglyph, iterations=2) & (s > 286.0), 286.0, s)
    loc = ndi.maximum_filter(s, size=7)
    D = np.clip(1 - s / np.maximum(loc, 1), 0, 1)
    D2 = np.where(gcore, 0, D)
    R = np.max([cv2.filter2D(D2, -1, k) for k in KERNELS], 0)
    line = ((R > 0.10) & ((D2 > 0.04) | glyph)) | (dark & ~glyph)
    road = al & (mx - mn < 16) & (mx > 185) & ~glyph      # grey road space and white label boxes
    fill = ndi.binary_opening(al & ~line & ~road, iterations=1)
    return al, line, road, fill, rgb


# ------------------------------------------------------------------------------------------------
def cells():
    """Every closed outline of the plan, in global zoom-19 pixels."""
    step, pad = 12, 1
    out_cells, out_sites = [], []
    pa = MPP * MPP
    for ty in range(TY0, TY1 + 1, step):
        for tx in range(TX0, TX1 + 1, step):
            wx, wy = tx - pad, ty - pad
            nx = ny = step + 2 * pad
            a = window(wx, wy, nx, ny)
            if a[..., 3].max() == 0:
                continue
            al, line, road, fill, rgb = masks(a)
            lab, n = ndi.label(fill)
            if n == 0:
                continue
            idx = np.arange(1, n + 1)
            area = ndi.sum(np.ones(lab.shape, np.uint8), lab, idx) * pa
            objs = ndi.find_objects(lab)
            H, Wd = lab.shape
            core = (pad * 256, pad * 256, (pad + step) * 256, (pad + step) * 256)
            for i in range(n):
                if area[i] < 35:
                    continue
                sl = objs[i]
                if sl[0].start == 0 or sl[1].start == 0 or sl[0].stop == H or sl[1].stop == Wd:
                    continue                                   # cut by the window edge: taken by the next window
                m = lab[sl] == i + 1
                cy, cx = ndi.center_of_mass(m)
                cx += sl[1].start
                cy += sl[0].start
                if not (core[0] <= cx < core[2] and core[1] <= cy < core[3]):
                    continue
                mm = np.pad(m, 2).astype(np.uint8)
                cs, _ = cv2.findContours(mm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                c = max(cs, key=cv2.contourArea)
                ap = cv2.approxPolyDP(c, 1.2, True)[:, 0, :].astype(float)
                if len(ap) < 3:
                    continue
                ox, oy = wx * 256 + sl[1].start - 2 + 0.5, wy * 256 + sl[0].start - 2 + 0.5
                ring = [[round(float(x + ox), 2), round(float(y + oy), 2)] for x, y in ap]
                (rw, rh) = cv2.minAreaRect(c)[1]
                rect = float(cv2.contourArea(c) / max(1.0, rw * rh))
                col = [int(np.median(rgb[sl][..., k][m])) for k in range(3)]
                rec = {"ring": ring, "area": round(float(area[i]), 1), "rgb": col, "rect": round(rect, 3),
                       "bbox": [int(wx * 256 + sl[1].start), int(wy * 256 + sl[0].start), int(wx * 256 + sl[1].stop), int(wy * 256 + sl[0].stop)]}
                (out_cells if area[i] <= 2600 else out_sites).append(rec)
            print(f"  cells: window {tx},{ty}: {len(out_cells)} cells, {len(out_sites)} large shapes so far", flush=True)
    json.dump({"cells": out_cells, "sites": out_sites}, open(os.path.join(CACHE, "cells.json"), "w"))
    print(f"cells: {len(out_cells)} plot-sized outlines, {len(out_sites)} larger shapes")


def number_groups(a, ring_local, fill_rgb):
    """centres (local px) of the separate numbers printed inside a cell"""
    h, w = a.shape[:2]
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [cv2.convexHull(np.round(np.array(ring_local)).astype(np.int32))], 1)
    m = m.astype(bool)
    rgb = a[..., :3].astype(np.int16)
    if sum(fill_rgb) < 330:
        ink = rgb.min(2) > 200
    else:
        ink = (rgb.sum(2) < 0.62 * float(sum(fill_rgb))) | (rgb.max(2) < 120)
    ink = ndi.binary_opening(ink & (a[..., 3] > 200), structure=np.ones((2, 2)))
    lab, n = ndi.label(ink)
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    sizes = ndi.sum(ink, lab, idx)
    cyx = ndi.center_of_mass(ink, lab, idx)
    objs = ndi.find_objects(lab)
    ids = [i for i in range(n) if sizes[i] >= 8 and max(objs[i][0].stop - objs[i][0].start, objs[i][1].stop - objs[i][1].start) <= 70
           and m[int(round(cyx[i][0])), int(round(cyx[i][1]))]]
    if not ids:
        return []
    big = max(sizes[i] for i in ids)
    ids = [i for i in ids if sizes[i] >= 0.25 * big]
    hmed = float(np.median([max(objs[i][0].stop - objs[i][0].start, objs[i][1].stop - objs[i][1].start) for i in ids]))
    groups, left = [], set(ids)
    while left:
        g, todo = {left.pop()}, None
        todo = list(g)
        while todo:
            j = todo.pop()
            for i in list(left):
                if math.hypot(cyx[i][0] - cyx[j][0], cyx[i][1] - cyx[j][1]) <= 0.95 * hmed:
                    left.discard(i)
                    g.add(i)
                    todo.append(i)
        groups.append(g)
    return [(float(np.mean([cyx[i][1] for i in g])), float(np.mean([cyx[i][0] for i in g])), sum(sizes[i] for i in g)) for g in groups]


def split():
    """The plan sometimes prints two plots in one outline (no line between them, two numbers inside). Such a cell is
    about twice the size of its neighbours: cut it halfway between its two numbers."""
    from shapely.geometry import Polygon, LineString
    from shapely.ops import split as cut
    from shapely.strtree import STRtree
    data = json.load(open(os.path.join(CACHE, "cells.json")))
    cells_ = data["cells"]
    polys = [Polygon(c["ring"]).convex_hull for c in cells_]
    tree = STRtree(polys)
    out, n_split = [], 0
    for k, c in enumerate(cells_):
        pg = polys[k]
        nb = [polys[j].area for j in tree.query(pg.buffer(16)) if j != k and polys[j].distance(pg) < 16 and 0.3 < polys[j].area / pg.area < 1.2]
        ratio = pg.area / float(np.median(nb)) if len(nb) >= 2 else 1.0
        if not (1.6 <= ratio <= 4.5) or colour_class(c["rgb"]) not in ("purple", "green", "yellow", "red", "pink"):
            out.append(c)
            continue
        x0, y0, x1, y1 = c["bbox"]
        tx0, ty0, tx1, ty1 = (x0 - 8) // 256, (y0 - 8) // 256, (x1 + 8) // 256, (y1 + 8) // 256
        a = window(tx0, ty0, tx1 - tx0 + 1, ty1 - ty0 + 1)
        ox, oy = tx0 * 256, ty0 * 256
        gs = number_groups(a, [[x - ox - 0.5, y - oy - 0.5] for x, y in c["ring"]], c["rgb"])
        gs = [g for g in gs if g[2] >= 0.35 * max(q[2] for q in gs)] if gs else []
        k_ = len(gs)
        if k_ < 2 or not (0.7 * k_ <= ratio <= 1.6 * k_):
            out.append(c)
            continue
        # order the numbers along the line through them; cut halfway between each pair of neighbours
        P_ = np.array([[g[0], g[1]] for g in gs])
        ctr = P_.mean(0)
        u = np.linalg.svd(P_ - ctr)[2][0]
        order = np.argsort((P_ - ctr) @ u)
        P_ = P_[order] + [ox, oy]
        whole = Polygon(c["ring"]).buffer(0)
        L = 10 * (abs(x1 - x0) + abs(y1 - y0))
        nvec = np.array([-u[1], u[0]])
        parts, rest, ok = [], whole, True
        for i in range(k_ - 1):
            m_ = (P_[i] + P_[i + 1]) / 2
            line = LineString([tuple(m_ - nvec * L), tuple(m_ + nvec * L)])
            pieces = list(cut(rest, line).geoms) if not rest.is_empty else []
            if len(pieces) != 2:
                ok = False
                break
            first = min(pieces, key=lambda q: np.hypot(*(np.array(q.centroid.coords[0]) - P_[i])))
            parts.append(first)
            rest = [q for q in pieces if q is not first][0]
        parts.append(rest)
        if not ok or any(q.area < 0.5 * whole.area / k_ for q in parts):
            out.append(c)
            continue
        for p in parts:
            p = p.simplify(0.8)
            r = [[round(float(x), 2), round(float(y), 2)] for x, y in list(p.exterior.coords)[:-1]]
            bx0, by0, bx1, by1 = p.bounds
            out.append(dict(c, ring=r, area=round(float(c["area"] * p.area / whole.area), 1), split=True,
                            bbox=[int(bx0), int(by0), int(math.ceil(bx1)), int(math.ceil(by1))]))
        n_split += 1
    data["cells"] = out
    json.dump(data, open(os.path.join(CACHE, "cells.json"), "w"))
    print(f"split: {n_split} outlines with two plots (two numbers, no line between them) cut in two; {len(out)} cells now")


# ------------------------------------------------------------------------------------------------
def roads():
    """Road space of the plan and the drawn area, at half resolution (2 zoom-19 pixels per cell)."""
    H, Wd = NTY * 128, NTX * 128
    road = np.zeros((H, Wd), bool)
    drawn = np.zeros((H, Wd), bool)
    plotc = np.zeros((H, Wd), bool)
    step = 12
    for ty in range(TY0, TY1 + 1, step):
        for tx in range(TX0, TX1 + 1, step):
            nx, ny = min(step, TX1 + 1 - tx), min(step, TY1 + 1 - ty)
            a = window(tx, ty, nx, ny)
            al, line, rd, fill, rgb = masks(a)
            r2 = rd.reshape(ny * 128, 2, nx * 128, 2).mean((1, 3)) > 0.5
            d2 = al.reshape(ny * 128, 2, nx * 128, 2).mean((1, 3)) > 0.5
            y0, x0 = (ty - TY0) * 128, (tx - TX0) * 128
            road[y0:y0 + ny * 128, x0:x0 + nx * 128] = r2
            drawn[y0:y0 + ny * 128, x0:x0 + nx * 128] = d2
            pc = np.zeros(al.shape, bool)               # plot colours (purple, green, yellow, red), with their lines and numbers
            for ref in ((184, 176, 216), (184, 216, 168), (248, 248, 144), (220, 38, 28)):
                pc |= (np.abs(rgb - np.array(ref)).sum(2) < 40) & al
            pc = ndi.binary_closing(pc, iterations=3)
            plotc[y0:y0 + ny * 128, x0:x0 + nx * 128] = pc.reshape(ny * 128, 2, nx * 128, 2).mean((1, 3)) > 0.5
    road = ndi.binary_closing(road, iterations=4) & drawn          # road names printed on the road
    Image.fromarray((road * 255).astype(np.uint8)).save(os.path.join(CACHE, "road_half.png"))
    Image.fromarray((drawn * 255).astype(np.uint8)).save(os.path.join(CACHE, "drawn_half.png"))
    Image.fromarray((plotc * 255).astype(np.uint8)).save(os.path.join(CACHE, "plotcol_half.png"))
    print(f"roads: {road.mean() * 100:.1f}% of the mosaic is road space, {drawn.mean() * 100:.1f}% drawn")


# ------------------------------------------------------------------------------------------------
def osm_raster(shape):
    """OpenStreetMap streets on the half-resolution plan grid, 7 m wide."""
    osm = json.load(open(os.path.join(SRC, "osm_fda_area.json"), encoding="utf-8"))["elements"]
    img = np.zeros(shape, np.uint8)
    w = max(1, int(round(7.0 / (2 * MPP))))
    for e in osm:
        hw = e.get("tags", {}).get("highway")
        if not hw or hw in ("motorway", "motorway_link", "trunk", "trunk_link", "footway", "path", "track"):
            continue
        gx, gy = ll_gpx([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]])
        pts = np.stack([(gx - GX0) / 2, (gy - GY0) / 2], 1)
        cv2.polylines(img, [np.round(pts * 4).astype(np.int32)], False, 1, w, cv2.LINE_8, shift=2)
    return img > 0


def correlate(a, b, S_):
    """shift s (dx, dy) with a(x) ~ b(x - s), subpixel; and a quality score."""
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt((a * a).sum() * (b * b).sum()) + 1e-9
    F = np.fft.fftshift(np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b))).real) / den
    c = a.shape[0] // 2
    sub = F[c - S_:c + S_ + 1, c - S_:c + S_ + 1]
    iy, ix = np.unravel_index(sub.argmax(), sub.shape)
    pk = sub[iy, ix]

    def par(m1, m0, p1):
        d = m1 - 2 * m0 + p1
        return 0.0 if d == 0 else 0.5 * (m1 - p1) / d
    dx = ix - S_ + (par(sub[iy, ix - 1], pk, sub[iy, ix + 1]) if 0 < ix < 2 * S_ else 0)
    dy = iy - S_ + (par(sub[iy - 1, ix], pk, sub[iy + 1, ix]) if 0 < iy < 2 * S_ else 0)
    # second best peak at least 12 m away: ambiguity of repeated street grids
    yy, xx = np.mgrid[-S_:S_ + 1, -S_:S_ + 1]
    far = np.hypot(yy - (iy - S_), xx - (ix - S_)) > 12 / (2 * MPP)
    second = sub[far].max() if far.any() else 0
    edge = abs(ix - S_) == S_ or abs(iy - S_) == S_
    return dx, dy, float(pk), float(second), edge


def register():
    road = np.asarray(Image.open(os.path.join(CACHE, "road_half.png"))) > 127
    osm = osm_raster(road.shape)
    np.save(os.path.join(CACHE, "osm_half.npy"), osm)
    m2 = 2 * MPP                                        # metres per half-res pixel
    WIN = int(260 / m2) // 2 * 2
    STEP = int(65 / m2)
    S_ = int(22 / m2)
    win = []
    H, Wd = road.shape
    for y in range(0, H - WIN, STEP):
        for x in range(0, Wd - WIN, STEP):
            a = road[y:y + WIN, x:x + WIN].astype(np.float32)
            b = osm[y:y + WIN, x:x + WIN].astype(np.float32)
            if b.mean() < 0.012 or a.mean() < 0.05:
                continue
            a = ndi.gaussian_filter(a, 1.0)
            b = ndi.gaussian_filter(b, 1.0)
            dx, dy, pk, second, edge = correlate(a, b, S_)
            if edge or pk < 0.2 or second > 0.93 * pk:
                continue
            gx, gy = GX0 + 2 * (x + WIN / 2), GY0 + 2 * (y + WIN / 2)
            lon, lat = gpx_ll(gx, gy)
            win.append({"gx": gx, "gy": gy, "lon": float(lon), "lat": float(lat), "dx": float(dx) * 2, "dy": float(dy) * 2, "pk": pk})
    # outliers: a window that disagrees with its neighbours by more than 3 m
    P = np.array([[w["gx"], w["gy"]] for w in win])
    D = np.array([[w["dx"], w["dy"]] for w in win])
    good = np.ones(len(win), bool)
    for _ in range(3):
        for i in range(len(win)):
            d = np.hypot(*(P - P[i]).T) * MPP
            nb = (d < 300) & good
            nb[i] = False
            if nb.sum() >= 3:
                med = np.median(D[nb], 0)
                good[i] = np.hypot(*(D[i] - med)) * MPP <= 3.0
    print(f"register: {len(win)} windows matched, {good.sum()} kept, {len(win) - good.sum()} outliers")
    for w, g in zip(win, good):
        w["good"] = bool(g)
    json.dump(win, open(os.path.join(CACHE, "windows.json"), "w"))
    # field on a 25 m grid in plan pixels (Gaussian weights, sigma 90 m; far from any window: nearest windows)
    G = int(25 / MPP)
    gxs = np.arange(GX0, GX0 + NTX * 256 + G, G)
    gys = np.arange(GY0, GY0 + NTY * 256 + G, G)
    Pg, Dg, Wg = P[good], D[good], np.array([w["pk"] for w in win])[good]
    sig = 90 / MPP
    FX = np.zeros((len(gys), len(gxs)))
    FY = np.zeros_like(FX)
    for j, gy in enumerate(gys):
        for i, gx in enumerate(gxs):
            d2 = ((Pg[:, 0] - gx) ** 2 + (Pg[:, 1] - gy) ** 2)
            dmin = d2.min()
            w = Wg * np.exp(-(d2 - dmin) / (2 * sig * sig))   # relative weights: far nodes fall back to the nearest windows
            w /= w.sum()
            FX[j, i] = (w * Dg[:, 0]).sum()
            FY[j, i] = (w * Dg[:, 1]).sum()
    np.savez(os.path.join(CACHE, "field.npz"), gxs=gxs, gys=gys, FX=FX, FY=FY)
    res = [np.hypot(w["dx"] - sample_field(w["gx"], w["gy"])[0], w["dy"] - sample_field(w["gx"], w["gy"])[1]) * MPP for w in win if w["good"]]
    print(f"register: field {FX.shape}; shift before {np.median(np.hypot(Dg[:, 0], Dg[:, 1])) * MPP:.1f} m median, "
          f"{np.percentile(np.hypot(Dg[:, 0], Dg[:, 1]), 95) * MPP:.1f} m p95; window residual after {np.median(res):.2f} m median, {np.percentile(res, 95):.2f} m p95")


_F = None


def sample_field(gx, gy):
    """shift (plan pixels) of the plan at a plan pixel: real position = plan position - shift"""
    global _F
    if _F is None:
        z = np.load(os.path.join(CACHE, "field.npz"))
        _F = (z["gxs"], z["gys"], z["FX"], z["FY"])
    gxs, gys, FX, FY = _F
    fx = np.interp(gx, gxs, np.arange(len(gxs)))
    fy = np.interp(gy, gys, np.arange(len(gys)))
    co = np.array([np.atleast_1d(fy), np.atleast_1d(fx)])
    sx = ndi.map_coordinates(FX, co, order=1, mode="nearest")
    sy = ndi.map_coordinates(FY, co, order=1, mode="nearest")
    if np.ndim(gx) == 0:
        return float(sx[0]), float(sy[0])
    return sx, sy


def to_ll(gx, gy):
    """plan pixel -> registered lon, lat"""
    sx, sy = sample_field(np.asarray(gx, float), np.asarray(gy, float))
    return gpx_ll(np.asarray(gx) - sx, np.asarray(gy) - sy)


# ------------------------------------------------------------------------------------------------
def glyphs(a, light=False):
    """digit strokes: thick, compact dark shapes (white ones on dark red commercial plots when light=True)"""
    rgb = a[..., :3].astype(np.int16)
    al = a[..., 3] > 200
    ink = ((rgb.min(2) > 205) if light else (rgb.max(2) < 120)) & al
    core = ndi.binary_opening(ink, structure=np.ones((3, 3)))
    lab, n = ndi.label(core)
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(lab)):
        keep[i + 1] = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) <= 70
    return ndi.binary_dilation(keep[lab], iterations=1) & ink


def cell_text(a, ring_local, fill_rgb):
    """the number printed in a cell, turned so that its text line is horizontal; returns (image, n_glyphs) or None.
    The text may still be upside down or turned by 90 degrees: the caller tries all four turns."""
    h, w = a.shape[:2]
    m = np.zeros((h, w), np.uint8)
    hull = cv2.convexHull(np.round(np.array(ring_local)).astype(np.int32))     # the outline bends round the digits
    cv2.fillPoly(m, [hull], 1)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1).astype(bool)
    light = sum(fill_rgb) < 330                  # dark (red) plots carry white numbers
    rgb = a[..., :3].astype(np.int16)
    if light:
        ink = rgb.min(2) > 200
    else:                                         # dark against the plot colour (the light watermark is not)
        ink = (rgb.sum(2) < 0.62 * float(sum(fill_rgb))) | (rgb.max(2) < 120)
    ink &= a[..., 3] > 200
    ink = ndi.binary_opening(ink, structure=np.ones((2, 2)))      # thin plot lines go, digit strokes stay
    # whole digit shapes whose centre lies in the cell: in small plots the number spills over the plot lines
    lab, n = ndi.label(ink)
    if n == 0:
        return None
    idx = np.arange(1, n + 1)
    sizes = ndi.sum(ink, lab, idx)
    cyx = ndi.center_of_mass(ink, lab, idx)
    objs = ndi.find_objects(lab)
    ok = np.zeros(n + 1, bool)
    for i in range(n):
        sl = objs[i]
        big = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
        cy_, cx_ = cyx[i]
        ok[i + 1] = sizes[i] >= 8 and big <= 70 and m[int(round(cy_)), int(round(cx_))]
    if not ok.any():
        return None
    sizes = np.where(ok[1:], sizes, 0)
    ok[1:] &= sizes >= 0.15 * sizes.max()
    # one number only: the digits that chain together (gap under ~1.2 glyph heights) around the one nearest the cell centre
    ids = [i for i in range(n) if ok[i + 1]]
    hts = {i: max(objs[i][0].stop - objs[i][0].start, objs[i][1].stop - objs[i][1].start) for i in ids}
    hmed = float(np.median([hts[i] for i in ids]))
    ys_m, xs_m = np.nonzero(m)
    mc = (ys_m.mean(), xs_m.mean())
    seed = min(ids, key=lambda i: math.hypot(cyx[i][0] - mc[0], cyx[i][1] - mc[1]))
    group, todo = {seed}, [seed]
    while todo:
        j = todo.pop()
        for i in ids:
            if i not in group and math.hypot(cyx[i][0] - cyx[j][0], cyx[i][1] - cyx[j][1]) <= 1.2 * hmed:
                group.add(i)
                todo.append(i)
    ok[:] = False
    ok[[i + 1 for i in group]] = True
    keep = ok[lab]
    sizes = np.array([sizes[i] for i in sorted(group)])
    if keep.sum() < 15:
        return None
    ng = int((sizes >= 0.25 * sizes.max()).sum())
    ys, xs = np.nonzero(keep)
    cx, cy = xs.mean(), ys.mean()
    cov = np.cov(np.stack([xs - cx, ys - cy]))
    ev, evec = np.linalg.eigh(cov)
    vx, vy = evec[:, 1]                              # main axis of the ink
    ang = math.degrees(math.atan2(vy, vx))
    M = cv2.getRotationMatrix2D((float(cx), float(cy)), ang, 1.0)
    big = max(h, w) * 2
    M[0, 2] += big / 2 - cx
    M[1, 2] += big / 2 - cy
    img = np.where(keep, 0, 255).astype(np.uint8)
    rot = cv2.warpAffine(img, M, (big, big), flags=cv2.INTER_NEAREST, borderValue=255)
    yy, xx = np.nonzero(rot < 128)
    if len(xx) == 0:
        return None
    crop = rot[max(0, yy.min() - 4):yy.max() + 5, max(0, xx.min() - 4):xx.max() + 5]
    return crop, ng


def ocr():
    data = json.load(open(os.path.join(CACHE, "cells.json")))
    cells_ = data["cells"]
    crops = []
    tile_cache = {}
    for k, c in enumerate(cells_):
        x0, y0, x1, y1 = c["bbox"]
        tx0, ty0, tx1, ty1 = (x0 - 8) // 256, (y0 - 8) // 256, (x1 + 8) // 256, (y1 + 8) // 256
        key = (tx0, ty0, tx1, ty1)
        if key not in tile_cache:
            if len(tile_cache) > 64:
                tile_cache.clear()
            tile_cache[key] = window(tx0, ty0, tx1 - tx0 + 1, ty1 - ty0 + 1)
        a = tile_cache[key]
        ring = [[x - tx0 * 256 - 0.5, y - ty0 * 256 - 0.5] for x, y in c["ring"]]
        r = cell_text(a, ring, c["rgb"])
        if r is None:
            continue
        img, ng = r
        h, w = img.shape
        sc = 44.0 / max(8, min(h, w) if ng == 1 else h)    # glyphs about 44 px high for Tesseract
        img = cv2.resize(img, (max(8, int(w * sc)), max(8, int(h * sc))), interpolation=cv2.INTER_CUBIC)
        img = np.where(img > 127, 255, 0).astype(np.uint8)
        crops.append((k, img, ng))
        if k % 2000 == 0:
            print(f"  ocr: cropped {k}/{len(cells_)}", flush=True)
    print(f"ocr: {len(crops)} cells with printed text")
    import pickle
    pickle.dump([(k, img, ng) for k, img, ng in crops], open(os.path.join(CACHE, "crops.pkl"), "wb"))
    results = {}
    for turn in (0, 1, 2, 3):
        res = run_tesseract([(k, np.ascontiguousarray(np.rot90(img, turn))) for k, img, _ in crops])
        for k, (txt, conf) in res.items():
            results.setdefault(k, {})[turn] = (txt, conf)
    out = {}
    for k, img, ng in crops:
        r = results.get(k, {})
        cand = sorted([(conf, txt, t) for t, (txt, conf) in r.items() if txt.isdigit() and 1 <= len(txt) <= 4 and txt[0] != "0"], reverse=True)
        if not cand:
            continue
        conf, txt, t = cand[0]
        out[k] = {"no": int(txt), "conf": round(conf, 1), "turn": t, "ng": ng, "alt": [[int(c[1]), round(c[0], 1)] for c in cand[1:]]}
    json.dump(out, open(os.path.join(CACHE, "ocr.json"), "w"))
    print(f"ocr: {len(out)} numbers read")


def run_tesseract(items):
    """OCR many small images at once: they are laid out on sheets with wide gaps, read with psm 11."""
    res = {}
    CW, CH, COLS, ROWS = 360, 110, 10, 40
    per = COLS * ROWS
    tmp = tempfile.mkdtemp()
    for s0 in range(0, len(items), per):
        batch = items[s0:s0 + per]
        sheet = np.full((ROWS * CH, COLS * CW), 255, np.uint8)
        slots = {}
        for i, (k, img) in enumerate(batch):
            r, c = divmod(i, COLS)
            h, w = img.shape
            if w > CW - 40 or h > CH - 30:
                sc = min((CW - 40) / w, (CH - 30) / h)
                img = cv2.resize(img, (max(4, int(w * sc)), max(4, int(h * sc))), interpolation=cv2.INTER_AREA)
                h, w = img.shape
            x0, y0 = c * CW + 20, r * CH + 15
            sheet[y0:y0 + h, x0:x0 + w] = img
            slots[i] = (k, c * CW, r * CH)
        p = os.path.join(tmp, "s.png")
        cv2.imwrite(p, sheet)
        out = subprocess.run([TESSERACT, p, "stdout", "--psm", "11", "-c", "tessedit_char_whitelist=0123456789", "tsv"],
                             capture_output=True, text=True).stdout
        words = {}
        for line in out.splitlines()[1:]:
            f = line.split("\t")
            if len(f) < 12 or f[11].strip() == "" or f[10] == "-1":
                continue
            x, y, w, h, conf, txt = int(f[6]), int(f[7]), int(f[8]), int(f[9]), float(f[10]), f[11].strip()
            i = (y + h // 2) // CH * COLS + (x + w // 2) // CW
            words.setdefault(i, []).append((x, txt, conf))
        for i, ws in words.items():
            if i not in slots:
                continue
            ws.sort()
            txt = "".join(t for _, t, _ in ws)
            conf = min(c for _, _, c in ws)
            res[slots[i][0]] = (txt, conf)
        print(f"  tesseract: {min(s0 + per, len(items))}/{len(items)}", flush=True)
    return res


def rapid():
    """Read the number crops with RapidOCR, in a Python that has rapidocr_onnxruntime (TERRALYT_RAPID_PY, else
    `py -3.12`). Skipped with a message when none is installed; the other readers still work."""
    exe = os.environ.get("TERRALYT_RAPID_PY")
    cmd = [exe] if exe else ["py", "-3.12"]
    try:
        r = subprocess.run(cmd + ["-I", os.path.join(HERE, "rapid_ocr.py"), os.path.join(CACHE, "crops.pkl"), os.path.join(CACHE, "rapid.json")],
                           capture_output=True, text=True)
        print("\n".join(l for l in r.stdout.splitlines() if not l.startswith("  ")) or r.stderr[-500:])
    except FileNotFoundError:
        print("rapid: no Python with rapidocr_onnxruntime found (pip install rapidocr_onnxruntime); skipped")


def split_glyphs(img):
    """digit shapes of a crop (black on white), left to right: list of (x0, x1, normalised 16x24 image)"""
    ink = img < 128
    lab, n = ndi.label(ink)
    if n == 0:
        return []
    objs = ndi.find_objects(lab)
    sizes = ndi.sum(ink, lab, np.arange(1, n + 1))
    out = []

    def norm(g):
        h, w = g.shape
        side_w = max(w, int(h * 0.75))
        box = np.zeros((h, side_w), np.float32)
        x0 = (side_w - w) // 2
        box[:, x0:x0 + w] = g
        return cv2.resize(box, (16, 24), interpolation=cv2.INTER_AREA)
    hs = [sl[0].stop - sl[0].start for i, sl in enumerate(objs) if sizes[i] >= 0.12 * sizes.max()]
    hmax = max(hs) if hs else 1
    for i, sl in enumerate(objs):
        if sizes[i] < 0.12 * sizes.max():
            continue
        g = (lab[sl] == i + 1)
        h, w = g.shape
        k = int(round(w / (0.62 * max(h, 0.8 * hmax)))) if h >= 0.6 * hmax else 1
        if k >= 2:
            # digits that touch: cut at the thinnest columns near the even split points
            col = g.sum(0).astype(float)
            cuts = []
            for j in range(1, k):
                c0 = int(w * j / k)
                lo, hi = max(1, c0 - w // (3 * k)), min(w - 1, c0 + w // (3 * k) + 1)
                cuts.append(lo + int(np.argmin(col[lo:hi])) if hi > lo else c0)
            edges = [0] + cuts + [w]
            for a, b in zip(edges[:-1], edges[1:]):
                part = g[:, a:b]
                rows = np.nonzero(part.any(1))[0]
                if b - a >= 2 and len(rows):
                    out.append((sl[1].start + a, sl[1].start + b, norm(part[rows[0]:rows[-1] + 1])))
            continue
        out.append((sl[1].start, sl[1].stop, norm(g)))
    out.sort(key=lambda t: t[0])
    # a digit can come apart into two pieces stacked one over the other: merge pieces that overlap in x
    merged = []
    for g in out:
        if merged and g[0] < merged[-1][1] - 0.5 * (g[1] - g[0]):
            continue
        merged.append(g)
    return merged


def glyph_ratios(img):
    """width / height of each digit shape of a crop, left to right"""
    ink = img < 128
    lab, n = ndi.label(ink)
    if n == 0:
        return []
    objs = ndi.find_objects(lab)
    sizes = ndi.sum(ink, lab, np.arange(1, n + 1))
    out = sorted((sl[1].start, (sl[1].stop - sl[1].start) / max(1, sl[0].stop - sl[0].start)) for i, sl in enumerate(objs) if sizes[i] >= 0.12 * sizes.max())
    return [r for _, r in out]


def narrow_ones(st, img):
    """In this font a 1 is a narrow stroke (0.40 to 0.55 as wide as tall), a 4 or a 7 is wide (0.6 to 0.8):
    a 4 or 7 narrower than 0.56 is a misread 1."""
    r = glyph_ratios(img)
    if len(r) != len(st):
        return st
    out = []
    for i, (ch, q) in enumerate(zip(st, r)):
        others = [r[j] for j in range(len(st)) if j != i and st[j] != "1"]
        if ch in "47" and (q < 0.56 and q < 0.78 * float(np.median(others)) if others else q < 0.5):
            out.append("1")                    # clearly narrower than the other digits of the same number
        else:
            out.append(ch)
    return "".join(out)


def digits():
    """Read every number again with a digit recogniser trained on this map's own print, then correct the numbers
    with their neighbours: plots in a row are numbered one after the other."""
    import pickle
    crops = pickle.load(open(os.path.join(CACHE, "crops.pkl"), "rb"))
    oc = {int(k): v for k, v in json.load(open(os.path.join(CACHE, "ocr.json"))).items()}
    # 1. training glyphs: confident Tesseract readings whose digit count matches the shapes found
    X, Y = [], []
    for k, img, ng in crops:
        o = oc.get(k)
        if not o or o["conf"] < 88:
            continue
        up = np.ascontiguousarray(np.rot90(img, o["turn"]))
        gl = split_glyphs(up)
        s = narrow_ones(str(o["no"]), up)
        if len(gl) != len(s):
            continue
        for (_, _, g), d in zip(gl, s):
            X.append(g.ravel())
            Y.append(int(d))
    X, Y = np.array(X), np.array(Y)
    rng = np.random.default_rng(0)
    keep = np.concatenate([rng.permutation(np.nonzero(Y == d)[0])[:900] for d in range(10)])
    X, Y = X[keep], Y[keep]
    print(f"digits: {len(X)} training glyphs, per digit {np.bincount(Y, minlength=10).tolist()}")
    mu = X.mean(0)
    U, Sv, Vt = np.linalg.svd(X - mu, full_matrices=False)
    P = Vt[:40].T
    Xp = (X - mu) @ P
    Xn = (Xp ** 2).sum(1)

    def classify(gs):
        A = (np.array(gs) - mu) @ P
        D = (A ** 2).sum(1)[:, None] + Xn[None, :] - 2 * A @ Xp.T
        idx = np.argsort(D, 1)[:, :5]
        out = []
        for i in range(len(gs)):
            votes = np.bincount(Y[idx[i]], minlength=10)
            d = int(votes.argmax())
            out.append((d, float(np.sqrt(max(0, D[i, idx[i, 0]]))), int(votes.max())))
        return out
    # self-check on a held-out half
    half = len(X) // 2
    perm = rng.permutation(len(X))
    # 2. read every crop in four turns
    knn = {}
    for b0 in range(0, len(crops), 2000):
        batch = crops[b0:b0 + 2000]
        jobs = []
        for k, img, ng in batch:
            for t in range(4):
                gl = split_glyphs(np.ascontiguousarray(np.rot90(img, t)))
                if 1 <= len(gl) <= 4:
                    jobs.append((k, t, [g.ravel() for _, _, g in gl]))
        flat = [g for _, _, gs in jobs for g in gs]
        if not flat:
            continue
        res = classify(flat)
        i = 0
        for k, t, gs in jobs:
            r = res[i:i + len(gs)]
            i += len(gs)
            if r[0][0] == 0:
                continue                                  # plot numbers never start with 0
            txt = "".join(str(d) for d, _, _ in r)
            score = float(np.mean([dist for _, dist, _ in r]))
            v = min(vv for _, _, vv in r)
            if k not in knn or score < knn[k][1]:
                knn[k] = (int(txt), score, v, t)
        print(f"  digits: {min(b0 + 2000, len(crops))}/{len(crops)}", flush=True)
    # 3. one reading per cell: Tesseract when confident, else the recogniser when it is sure
    raw = {}
    turn_of = {}
    # RapidOCR (tools/rapid_ocr.py, run in the Python that has rapidocr_onnxruntime) when its readings exist
    rp = {}
    rf = os.path.join(CACHE, "rapid.json")
    if os.path.exists(rf):
        for k, v in json.load(open(rf)).items():
            best = None
            for t, (txt, sc) in v.items():
                txt = txt.strip()
                if txt and all(ch in "0123456789" for ch in txt) and len(txt) <= 4 and txt[0] != "0" and (best is None or sc > best[1]):
                    best = (int(txt), sc, int(t))
            if best and best[1] >= 0.6:
                rp[int(k)] = best
        print(f"digits: {len(rp)} RapidOCR readings")
    cand_of = {}
    for k, img, ng in crops:
        o, q, r = oc.get(k), knn.get(k), rp.get(k)
        votes = {}

        def vote(v, w, how, t):
            e = votes.setdefault(v, [0.0, how, t])
            e[0] += w + (0.3 if len(str(v)) == ng else 0.0) * (e[0] == 0)
        if o and o["conf"] >= 50:
            vote(o["no"], o["conf"] / 100, "ocr" if o["conf"] >= 80 else "ocr-low", o["turn"])
        if q and q[2] >= 4 and q[1] < 3.2:
            vote(q[0], 0.75, "glyphs", q[3])
        if r:
            vote(r[0], r[1] * 1.1, "rapidocr", r[2])
        if not votes:
            continue
        cand_of[k] = votes
        v, (w, how, t) = max(votes.items(), key=lambda kv: kv[1][0])
        raw[k] = (v, how)
        turn_of[k] = t
    imgs = {k: img for k, img, _ in crops}
    n_one = 0
    for k in list(raw):
        if k in turn_of and raw[k][1] != "rapidocr":
            st = str(raw[k][0])
            fixed = narrow_ones(st, np.ascontiguousarray(np.rot90(imgs[k], turn_of[k])))
            if fixed != st:
                raw[k] = (int(fixed), raw[k][1])
                n_one += 1
    print(f"digits: {n_one} readings with a narrow 1 read as 4 or 7, corrected")
    alts = {k: {oc[k]["no"]} | {a[0] for a in oc[k].get("alt", [])} if k in oc else set() for k, _, _ in crops}
    for k, q in knn.items():
        alts.setdefault(k, set()).add(q[0])
    for k, r in rp.items():
        alts.setdefault(k, set()).add(r[0])
    print(f"digits: {len(raw)} cells with a reading ({sum(1 for v in raw.values() if v[1] == 'glyphs')} from the recogniser)")
    # 4. neighbours: cells touching each other
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree
    cells_ = json.load(open(os.path.join(CACHE, "cells.json")))["cells"]
    polys = [Polygon(c["ring"]).convex_hull for c in cells_]
    tree = STRtree(polys)
    nb = {}
    for k, p in enumerate(polys):
        nb[k] = [int(j) for j in tree.query(p.buffer(4.0)) if j != k and polys[j].distance(p) < 4.0]
    num = dict((k, v[0]) for k, v in raw.items())
    src = dict((k, v[1]) for k, v in raw.items())

    def consistent(k):
        return k in num and any(j in num and abs(num[j] - num[k]) == 1 for j in nb[k])

    def similar(a, b):
        a, b = str(a), str(b)
        if a == b:
            return True
        if len(a) == len(b):
            return sum(x != y for x, y in zip(a, b)) <= 1
        s, l = (a, b) if len(a) < len(b) else (b, a)
        return len(l) - len(s) == 1 and any(l[:i] + l[i + 1:] == s for i in range(len(l)))
    good = {k for k in num if consistent(k)}
    print(f"digits: {len(good)} of {len(num)} readings have a neighbour numbered one up or down")
    text_cells = {k for k, _, _ in crops}
    for it in range(6):
        changed = 0
        for k in text_cells:
            if k in good:
                continue
            votes = {}
            for j in nb[k]:
                if j in good:
                    for c in (num[j] - 1, num[j] + 1):
                        if c > 0 and not any(num.get(i) == c and i in good for i in nb[j] if i != k):
                            votes[c] = votes.get(c, 0) + 1
            if not votes:
                continue
            best = max(votes.values())
            cands = [c for c, v in votes.items() if v == best]
            pick = None
            sim = [c for c in cands if any(similar(c, a) for a in alts.get(k, ()))]
            if len(sim) == 1:
                pick = sim[0]
            elif best >= 2 and len(cands) == 1:
                pick = cands[0]
            if pick is not None:
                if num.get(k) != pick:
                    src[k] = "neighbours" if k in num else "neighbours (unread)"
                num[k] = pick
                good.add(k)
                changed += 1
        print(f"  digits: pass {it + 1}: {changed} numbers set from their neighbours")
        if not changed:
            break
    # row neighbours: plots side by side in a row share a long side; the numbering runs along the row
    row_nb = {}
    for k in text_cells:
        pg = polys[k]
        mrr = pg.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        long_side = max(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        out_ = []
        for j in nb[k]:
            shared = pg.buffer(6).intersection(polys[j].buffer(6)).area / 12.0
            if shared >= 0.55 * long_side:
                out_.append(j)
        row_nb[k] = out_

    def support(k, n):
        return sum(1 for j in row_nb[k] if j in num and abs(num[j] - n) == 1)
    n_pick = 0
    for _ in range(3):                                   # the readers disagree: take the reading its row agrees with
        for k, votes in cand_of.items():
            if len(votes) < 2:
                continue
            cur = num.get(k)
            here = support(k, cur) if cur else 0
            best = max(votes, key=lambda v: (support(k, v), votes[v][0]))
            if best != cur and support(k, best) > here:
                num[k] = best
                src[k] = votes[best][1]
                turn_of[k] = votes[best][2]
                good.add(k)
                n_pick += 1
    print(f"digits: {n_pick} cells where the readers disagreed took the reading their row agrees with")
    conf = {"1": "47", "4": "1", "7": "1", "3": "8", "8": "3069", "5": "6", "6": "589", "0": "8", "9": "86", "2": "7"}
    rot = {"0": "0", "1": "1", "8": "8", "6": "9", "9": "6"}
    n_sw = n_fill = n_rot = 0
    # a number made only of 0 1 6 8 9 reads as a different number upside down: the numbers around it are printed the
    # same way up, so take their turn
    for k in list(num):
        st = str(num[k])
        if k not in turn_of or not all(ch in rot for ch in st):
            continue
        other = "".join(rot[ch] for ch in reversed(st))
        if other == st or other[0] == "0":
            continue
        ts = [turn_of[j] for j in nb[k] if j in turn_of and not all(ch in rot for ch in str(num.get(j, "")))]
        if len(ts) >= 2:
            maj = Counter(ts).most_common(1)[0][0]
            if (turn_of[k] - maj) % 4 == 2 and Counter(ts)[maj] >= 0.6 * len(ts):
                num[k] = int(other)
                src[k] = "read the same way up as its neighbours"
                n_rot += 1
    for _ in range(3):
        for k in text_cells:
            cur = num.get(k)
            here = support(k, cur) if cur else 0
            if here >= 2 or (cur is not None and any(j in num and abs(num[j] - cur) == 2 for j in row_nb[k])):
                continue                                  # (rows numbered in steps of two: 63, 65, 67)
            cands = set()
            if cur:
                st = str(cur)
                for i, ch in enumerate(st):
                    for alt_ch in conf.get(ch, ""):
                        cands.add(st[:i] + alt_ch + st[i + 1:])
                if all(ch in rot for ch in st):
                    cands.add("".join(rot[ch] for ch in reversed(st)))       # read upside down
            ns = sorted(num[j] for j in row_nb[k] if j in num)
            for a_ in ns:
                for b_ in ns:
                    if b_ - a_ == 2:
                        cands.add(str(a_ + 1))                             # between n-1 and n+1 in its row
            best = None
            for c_ in cands:
                if not c_ or c_[0] == "0":
                    continue
                sup = support(k, int(c_))
                if sup >= 2 and sup > here and (best is None or sup > best[1]):
                    best = (int(c_), sup)
            if best:
                if cur is None:
                    n_fill += 1
                else:
                    n_sw += 1
                num[k] = best[0]
                src[k] = "corrected by its neighbours" if cur else "between its neighbours in the row"
                good.add(k)
    print(f"digits: {n_rot} numbers turned the same way up as their neighbours, {n_sw} corrected and {n_fill} unread numbers filled from the plots on both sides in the row")
    final = {}
    for k in text_cells:
        if k in num:
            final[k] = {"no": int(num[k]), "how": src.get(k, "ocr"), "checked": k in good}
    json.dump(final, open(os.path.join(CACHE, "numbers.json"), "w"))
    print(f"digits: {len(final)} numbered cells, {sum(v['checked'] for v in final.values())} confirmed by a neighbour, "
          f"{len(text_cells) - len(final)} cells with print left unnumbered")


# ------------------------------------------------------------------------------------------------
CLASSES = {"purple": (184, 176, 216), "green": (184, 216, 168), "yellow": (248, 248, 144), "red": (220, 38, 28), "pink": (232, 152, 160)}


def colour_class(rgb):
    best = min(CLASSES, key=lambda k: sum((a - b) ** 2 for a, b in zip(rgb, CLASSES[k])))
    return best if sum((a - b) ** 2 for a, b in zip(rgb, CLASSES[best])) < 45 ** 2 else "other"


def write():
    data = json.load(open(os.path.join(CACHE, "cells.json")))
    nf = os.path.join(CACHE, "numbers.json")
    oc = json.load(open(nf)) if os.path.exists(nf) else {}
    out = []
    for k, c in enumerate(data["cells"]):
        ring = np.array(c["ring"])
        lon, lat = to_ll(ring[:, 0], ring[:, 1])
        rec = {"ring": [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat)], "area_m2": c["area"], "colour": colour_class(c["rgb"]),
               "rgb": c["rgb"], "rect": c["rect"], "px": [round(float(ring[:, 0].mean()), 1), round(float(ring[:, 1].mean()), 1)]}
        o = oc.get(str(k))
        if o:
            rec["number"] = o["no"]
            rec["number_read"] = o["how"]
            rec["number_checked"] = o["checked"]
        out.append(rec)
    sites = []
    for c in data["sites"]:
        ring = np.array(c["ring"])
        lon, lat = to_ll(ring[:, 0], ring[:, 1])
        sites.append({"ring": [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat)], "area_m2": c["area"], "rgb": c["rgb"],
                      "colour": colour_class(c["rgb"]), "px": [round(float(ring[:, 0].mean()), 1), round(float(ring[:, 1].mean()), 1)]})
    # drawn area of the plan (society land on the plan), registered
    drawn = np.asarray(Image.open(os.path.join(CACHE, "drawn_half.png"))) > 127
    drawn = ndi.binary_closing(drawn, iterations=6)
    holes, nh = ndi.label(ndi.binary_fill_holes(drawn) & ~drawn)
    if nh:
        hs = ndi.sum(np.ones_like(holes), holes, np.arange(1, nh + 1)) * (2 * MPP) ** 2
        small = np.zeros(nh + 1, bool)
        small[1:] = hs < 20000                         # specks; a large hole (Motorway City) is not society land
        drawn |= small[holes]
    cs, hier = cv2.findContours(drawn.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    def ring_ll(c):
        ap = cv2.approxPolyDP(c, 2.0, True)[:, 0, :].astype(float)
        gx, gy = GX0 + 2 * ap[:, 0] + 1, GY0 + 2 * ap[:, 1] + 1
        lon, lat = to_ll(gx, gy)
        return [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat)]
    rings = []                                          # polygons: [outer ring, hole rings ...]
    for i, c in enumerate(cs):
        if hier[0][i][3] != -1 or cv2.contourArea(c) * (2 * MPP) ** 2 < 5000:
            continue
        poly = [ring_ll(c)]
        j = hier[0][i][2]
        while j != -1:
            if cv2.contourArea(cs[j]) * (2 * MPP) ** 2 >= 20000:
                poly.append(ring_ll(cs[j]))
            j = hier[0][j][0]
        rings.append(poly)
    win = json.load(open(os.path.join(CACHE, "windows.json")))
    z = np.load(os.path.join(CACHE, "field.npz"))
    # road mask in plan pixels + the registration field: make_data samples it through the field
    Image.open(os.path.join(CACHE, "road_half.png")).save(os.path.join(SRC, "emap_road.png"), optimize=True)
    Image.open(os.path.join(CACHE, "plotcol_half.png")).save(os.path.join(SRC, "emap_plotcol.png"), optimize=True)
    lay = {"about": "FDA City plan read from emap.pk (zoom-19 tiles, a redraw of the official FDA plan incl. Block X), "
                    "registered piece by piece to the OpenStreetMap streets by tools/emap_plan.py",
           "page": PAGE, "tile_url": TILE_URL, "zoom": Z, "m_per_px": round(MPP, 4),
           "mosaic_origin_px": [GX0, GY0], "road_png": {"file": "emap_road.png", "px_per_cell": 2},
           "plotcol_png": {"file": "emap_plotcol.png", "px_per_cell": 2},
           "field": {"gxs": z["gxs"].tolist(), "gys": z["gys"].tolist(), "FX": np.round(z["FX"], 2).tolist(), "FY": np.round(z["FY"], 2).tolist(),
                     "note": "shift of the plan in zoom-19 pixels: real position = plan pixel - shift"},
           "registration": {"windows": len(win), "kept": sum(w["good"] for w in win)},
           "drawn": rings, "cells": out, "sites": sites}
    json.dump(lay, open(os.path.join(SRC, "emap_layout.json"), "w"), separators=(",", ":"))
    print(f"write: emap_layout.json with {len(out)} cells ({sum('number' in c for c in out)} numbered), {len(sites)} sites, {len(rings)} drawn areas, "
          f"{os.path.getsize(os.path.join(SRC, 'emap_layout.json')) // 1024} KB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="fetch,cells,split,roads,register,ocr,rapid,digits,write")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    for st in a.stages.split(","):
        globals()[st.strip()]()


if __name__ == "__main__":
    main()

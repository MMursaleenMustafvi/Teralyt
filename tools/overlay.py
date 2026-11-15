"""Draw the generated map data over Google satellite imagery or the Google Maps road map, for checking.

usage: python -I tools/overlay.py LAT LON [--size 300] [--z 19] [--base sat|map|none] [--out out.png]
                                  [--layers roads,surface,plots,water,land,landmarks,buildings]

  --size   width of the square in metres
  --base   sat: Google satellite; map: Google Maps road map (shows where Google draws service roads);
           none: plain background
Road centre lines are coloured by class (main red, service orange, road110 magenta, 85 ft blue,
60 ft cyan, 40 ft yellow); paved carriageways are outlined white, verges green, medians and strips
light green, plots thin black, the nalla blue. Tiles are cached in tools/source/cache/gsat and gmap.
"""
import argparse
import io
import json
import math
import os
import urllib.request

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(HERE, "source", "cache")
URL = {"sat": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "map": "https://mt1.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}",
       "mapnl": "https://mt1.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&apistyle=s.e%3Al%7Cp.v%3Aoff"}   # mapnl: road map without labels
COL = {"main": (255, 40, 40), "service": (255, 150, 0), "road110": (230, 0, 230), "divider": (40, 120, 255), "divider_half": (40, 120, 255),
       "road85": (40, 120, 255), "collector": (0, 230, 230), "residential": (255, 230, 0), "roundabout": (255, 255, 255), "arterial": (160, 255, 160),
       "highway": (140, 140, 140)}


def tile(base, z, x, y):
    d = os.path.join(CACHE, {"sat": "gsat", "map": "gmap", "mapnl": "gmapnl"}[base])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{z}_{x}_{y}.{'jpg' if base == 'sat' else 'png'}")
    if not os.path.exists(p):
        b = urllib.request.urlopen(urllib.request.Request(URL[base].format(z=z, x=x, y=y), headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
        open(p, "wb").write(b)
    return Image.open(p).convert("RGB")


def gpx(lon, lat, z):
    n = 256 * 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lat", type=float); ap.add_argument("lon", type=float)
    ap.add_argument("--size", type=float, default=300)
    ap.add_argument("--z", type=int, default=19)
    ap.add_argument("--base", default="sat", choices=["sat", "map", "mapnl", "mix", "plan", "none"])
    ap.add_argument("--layers", default="roads,surface,plots,water,land")
    ap.add_argument("--out", default="overlay.png")
    ap.add_argument("--scale", type=float, default=1.0, help="resize the output by this factor")
    a = ap.parse_args()
    z = a.z
    mpp = 156543.03392 * math.cos(math.radians(a.lat)) / 2 ** z
    half = a.size / 2 / mpp
    cx, cy = gpx(a.lon, a.lat, z)
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    W = int(x1 - x0); H = int(y1 - y0)
    def mosaic(base):
        im = Image.new("RGB", (W, H), (235, 235, 225))
        for tx in range(int(x0 // 256), int(x1 // 256) + 1):
            for ty in range(int(y0 // 256), int(y1 // 256) + 1):
                for attempt in range(3):
                    try:
                        im.paste(tile(base, z, tx, ty), (int(tx * 256 - x0), int(ty * 256 - y0)))
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 2:
                            print("tile failed", tx, ty, e)
        return im

    if a.base == "mix":     # satellite with Google's road drawing laid over it at half strength
        img = Image.blend(mosaic("sat"), mosaic("map"), 0.45)
    elif a.base == "plan":  # the emap.pk plan tiles (zoom 19, cached by emap_plan.py; as published, not registered)
        img = Image.new("RGBA", (W, H), (235, 235, 225, 255))
        f = 2 ** (19 - z)
        for tx in range(int(x0 * f // 256), int(x1 * f // 256) + 1):
            for ty in range(int(y0 * f // 256), int(y1 * f // 256) + 1):
                p = os.path.join(CACHE, "emap", "19", f"{tx}_{ty}.png")
                if os.path.exists(p) and os.path.getsize(p):
                    t = Image.open(p).convert("RGBA")
                    if f != 1:
                        t = t.resize((round(256 / f), round(256 / f)), Image.LANCZOS)
                    img.alpha_composite(t, (int(tx * 256 / f - x0), int(ty * 256 / f - y0)))
        img = img.convert("RGB")
    elif a.base != "none":
        img = mosaic(a.base)
    else:
        img = Image.new("RGB", (W, H), (235, 235, 225))
    dr = ImageDraw.Draw(img, "RGBA")
    P = lambda c: (gpx(c[0], c[1], z)[0] - x0, gpx(c[0], c[1], z)[1] - y0)
    lay = set(a.layers.split(","))

    def rings(g):
        if g["type"] == "Polygon":
            return g["coordinates"]
        if g["type"] == "MultiPolygon":
            return [r for p in g["coordinates"] for r in p]
        return []

    def load(n):
        p = os.path.join(DATA, n + ".geojson")
        return json.load(open(p, encoding="utf-8"))["features"] if os.path.exists(p) else []

    def inview(ring):
        xs = [P(c)[0] for c in ring[:: max(1, len(ring) // 8)]]
        ys = [P(c)[1] for c in ring[:: max(1, len(ring) // 8)]]
        return max(xs) > -200 and min(xs) < W + 200 and max(ys) > -200 and min(ys) < H + 200

    if "land" in lay:
        for f in load("blocks"):
            k = f["properties"].get("kind")
            if k in ("median", "strip", "island"):
                for r in rings(f["geometry"]):
                    if inview(r):
                        dr.line([P(c) for c in r], fill=(120, 255, 120, 220), width=2)
    if "surface" in lay:
        for f in load("road_surface") + load("outer_roads"):
            verge = f["properties"].get("kind") == "verge"
            for r in rings(f["geometry"]):
                if inview(r):
                    dr.line([P(c) for c in r], fill=(60, 220, 60, 200) if verge else (255, 255, 255, 230), width=1 if verge else 2)
    if "plots" in lay:
        for f in load("plots"):
            for r in rings(f["geometry"]):
                if inview(r):
                    dr.line([P(c) for c in r], fill=(0, 0, 0, 200), width=1)
    if "landmarks" in lay:
        for f in load("landmarks"):
            for r in rings(f["geometry"]):
                if inview(r):
                    dr.line([P(c) for c in r], fill=(200, 0, 255, 230), width=2)
    if "buildings" in lay:
        for f in load("buildings"):
            for r in rings(f["geometry"]):
                if inview(r):
                    dr.line([P(c) for c in r], fill=(255, 0, 120, 230), width=1)
    if "water" in lay:
        for f in load("water"):
            if f["properties"].get("kind") in ("nala_water", "nala_wall"):
                for r in rings(f["geometry"]):
                    if inview(r):
                        dr.line([P(c) for c in r], fill=(0, 160, 255, 230), width=2)
    if "svc" in lay:          # measured service roads (tools/service_roads.py), before make_data adds them
        sp = os.path.join(HERE, "source", "service_roads.geojson")
        for f in (json.load(open(sp, encoding="utf-8"))["features"] if os.path.exists(sp) else []):
            pts = [P(c) for c in f["geometry"]["coordinates"]]
            dr.line(pts, fill=(255, 0, 255, 255), width=3)
    if "roads" in lay:
        for f in load("roads"):
            g = f["geometry"]
            if g["type"] != "LineString":
                continue
            pts = [P(c) for c in g["coordinates"]]
            if not inview(g["coordinates"]):
                continue
            c = COL.get(f["properties"].get("class"), (255, 255, 0))
            dr.line(pts, fill=c + (255,), width=3)
            dr.ellipse([pts[0][0] - 4, pts[0][1] - 4, pts[0][0] + 4, pts[0][1] + 4], outline=c + (255,), width=2)
            dr.ellipse([pts[-1][0] - 4, pts[-1][1] - 4, pts[-1][0] + 4, pts[-1][1] + 4], outline=c + (255,), width=2)
    # scale bar 20 m
    L = 20 / mpp
    dr.rectangle([10, H - 22, 10 + L, H - 14], fill=(255, 255, 255, 230), outline=(0, 0, 0, 255))
    dr.text((14 + L, H - 26), "20 m", fill=(255, 255, 255, 255))
    if a.scale != 1:
        img = img.resize((int(W * a.scale), int(H * a.scale)), Image.LANCZOS)
    img.save(a.out)
    print(a.out, img.size, f"{mpp:.3f} m/px")


if __name__ == "__main__":
    main()

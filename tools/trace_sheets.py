"""Digitise Blocks B-F from their own official block maps into tools/source/plan_features.json.

Each sheet = the block's map pages from fdacity.pk stacked top to bottom. Features are given as
rectangles (s = coordinates read on the reduced preview, f = full-resolution sheet pixels) and
snapped to the detected picture boxes where one matches. Control points: roundabout centres
(exact lon/lat) plus parks that also appear on the georeferenced overall plan.
usage: python -I trace_sheets.py <repo> <fda_maps dir>
"""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

repo, mdir = sys.argv[1], sys.argv[2]
pf_path = os.path.join(repo, "tools/source/plan_features.json")
pf = json.load(open(pf_path, encoding="utf-8"))
KX, KY = 111320 * math.cos(math.radians(31.525)), 111320.0
ov = pf["sheets"]["overall"]["control_points"]
X = np.array([complex(p["px"][0], -p["px"][1]) for p in ov]); Z = np.array([complex((p["lonlat"][0] - 73.0875) * KX, (p["lonlat"][1] - 31.525) * KY) for p in ov])
(k0, t0), *_ = np.linalg.lstsq(np.vstack([X, np.ones_like(X)]).T, Z, rcond=None)
def overall_ll(x, y):
    w = k0 * complex(x, -y) + t0
    return [round(73.0875 + w.real / KX, 7), round(31.525 + w.imag / KY, 7)]
RB1, RB2, RBSW = [73.082462, 31.520554], [73.087766, 31.52568], [73.078424, 31.511277]
BASE = "https://fdacity.pk/images/fdacity/"

S = {
 "B": dict(scale=.820, urls=[BASE + "fda_b/Fdacity%20Block_B_0" + str(i) + ".jpg" for i in (1, 2, 3)], size=[1200, 1829],
   rb=[((64, 1751), RB1), ((1150, 1751), RB2)],
   corr={"Park B-1": (1022, 416), "Park B-4": (1177.5, 326), "Park B-3 (west)": (1067.5, 196.5), "Park B-2": (1005.5, 181.5), "Park (4.51 kanal)": (1159, 86.5)},
   feats=[
    ("park", "Park (4.51 kanal)", "s", (715, 108, 770, 192), 4.51), ("park", "Park B-2 (north)", "s", (282, 248, 306, 292), 1.76),
    ("park", "Park (2 kanal)", "s", (443, 243, 548, 268), 2.0), ("mosque", "Mosque (B north)", "s", (551, 236, 589, 270), 1.85),
    ("park", "Park B-3 (north)", "s", (592, 238, 702, 270), 3.75), ("park", "Park B-2", "s", (228, 422, 258, 502), 2.95),
    ("park", "Park B-3 (west)", "s", (400, 478, 478, 532), None), ("park", "Park B-3 (east)", "s", (688, 545, 738, 597), 3.6),
    ("mosque", "Jamia Mosque (B)", "f", (440, 828, 516, 903), 5.0), ("school", "Govt. Primary School (B)", "f", (403, 907, 516, 1065), 13.9),
    ("playground", "Playground B-1", "f", (517, 828, 675, 1004), 25.5), ("dispensary", "Dispensary (B)", "f", (517, 1007, 543, 1065), 1.5),
    ("commercial", "Commercial Centre (B)", "f", (546, 1007, 675, 1065), 6.54),
    ("park", "Park B-4", "s", (745, 858, 857, 977), 16.18), ("park", "Park B-1", "s", (210, 1160, 382, 1242), 16.55),
    ("park", "Park (Block B, nalla side)", "s", (62, 1160, 100, 1262), None)]),
 "C": dict(scale=.965, urls=[BASE + "fda_c/Fdacity%20Block_C_01.jpg", BASE + "fda_c/Fdacity%20Block_C_02.jpg", BASE + "fda_c/Fdacity%20Block_C_03.jpg", BASE + "fda_c/FdacityBlock_C_04.jpg", BASE + "fda_c/Fdacity%20Block_C_05.jpg"], size=[1200, 1554],
   rb=[((58, 1483), RB2)], rb_axis=(1142, 1482),
   corr={"Park C-3": (1279, 76), "Park C-4 (north)": (1376, 114), "Park C-5": (1343, 197.5), "Park C-2": (1281.5, 200), "Park C-4 (south)": (1434, 248.5), "Park C-6": (1404, 335.5), "Park C-1": (1332.5, 410.5)},
   feats=[
    ("multipurpose", "Multi-Purpose Uses", "s", (790, 95, 1090, 775), None), ("university", "Proposed University", "s", (790, 810, 1090, 945), None),
    ("stadium", "Proposed Cricket Stadium", "s", (790, 960, 1090, 1170), None), ("cinema", "Proposed IMAX Theatre", "s", (790, 1200, 1090, 1410), None),
    ("mosque", "Jamia Mosque (C)", "f", (333, 824, 378, 872), None), ("school", "Govt. Primary School (C)", "f", (333, 874, 378, 975), 7.5),
    ("playground", "Playground C-5", "f", (383, 824, 484, 938), 18.3), ("dispensary", "Dispensary (C)", "f", (383, 944, 405, 975), None),
    ("commercial", "Commercial Centre (C)", "f", (407, 944, 484, 975), 3.9),
    ("mosque", "Mosque (Park C-4)", "f", (455, 322, 490, 351), None), ("shops", "Shops (Park C-4)", "f", (455, 353, 490, 384), None),
    ("park", "Park C-4 (north)", "f", (491, 317, 553, 385), None),
    ("mosque", "Mosque (Park C-1)", "f", (314, 1163, 365, 1209), None), ("shops", "Shops (Park C-1)", "f", (371, 1163, 413, 1209), None),
    ("shrine", "Mazar (Park C-1)", "f", (415, 1163, 459, 1209), None), ("park", "Park C-1", "f", (314, 1213, 461, 1295), None),
    ("park", "Park C-3", "s", (172, 210, 262, 248), None), ("park", "Park (Block C west)", "s", (190, 393, 250, 414), None),
    ("park", "Park C-5", "s", (380, 560, 440, 602), None), ("park", "Park C-2", "s", (200, 560, 250, 642), None),
    ("park", "Park C-4 (south)", "s", (650, 690, 712, 773), None), ("park", "Park C-6", "s", (540, 965, 622, 1006), None)]),
 "D": dict(scale=.649, urls=[BASE + "fda_d/Fdacity%20Block_D_01.jpg", BASE + "fda_d/Fdacity%20Block_D_02.jpg", BASE + "fda_d/Fda%20cityBlock_D_03.jpg", BASE + "fda_d/Fdacity%20Block_D_04.jpg", BASE + "fda_d/Fdacity%20Block_D_05.jpg"], size=[1400, 2310],
   rb=[((64, 147), RB2)], rb_axis=(1338, 148),
   corr={"Park D-2": (1377.5, 573), "Park D-1": (1269, 622), "Park D-3": (1417, 733), "Park D-4": (1300.5, 771.5), "Park D-5 (west)": (1272.5, 844), "Park D-6": (1352, 924), "Park D-7": (1267.5, 999.5)},
   feats=[
    ("cng", "CNG Pump", "s", (808, 143, 836, 166), None),
    ("mosque", "Jamia Mosque (D)", "f", (384, 659, 455, 731), 5.3), ("school", "Govt. Primary School (D)", "f", (384, 734, 455, 883), 10.3),
    ("playground", "Playground D", "f", (459, 659, 608, 828), 24.9), ("dispensary", "Dispensary (D)", "f", (459, 835, 480, 883), None),
    ("commercial", "Commercial Centre (D)", "f", (483, 835, 608, 883), 6.5),
    ("mosque", "Mosque (Park D-5)", "f", (192, 1361, 236, 1401), None), ("shops", "Shops (Park D-5)", "f", (239, 1361, 282, 1401), None),
    ("park", "Park D-5 (west)", "f", (192, 1405, 282, 1463), None),
    ("park", "Park D-6", "f", (441, 1648, 538, 1746), None), ("mosque", "Mosque (Park D-6)", "f", (542, 1648, 601, 1696), None),
    ("shops", "Shops (Park D-6)", "f", (542, 1699, 601, 1746), None),
    ("park", "Park D-2", "s", (365, 238, 430, 347), None), ("park", "Park D-1", "s", (118, 365, 166, 437), None),
    ("park", "Park D-3", "s", (445, 618, 516, 682), None), ("park", "Park D-4", "s", (192, 728, 246, 777), None),
    ("park", "Park D-5 (east)", "s", (470, 920, 528, 952), None), ("park", "Park D-7", "s", (115, 1225, 171, 1312), None)]),
 "E": dict(scale=.594, urls=[BASE + "fda_e/Fda%20Block_E_01.jpg", BASE + "fda_e/FDA%20Block_E_02.jpg", BASE + "fda_e/Fda%20Block_E_03.jpg", BASE + "fda_e/Fda%20Block_E_04.jpg"], size=[1200, 2526],
   rb=[((61, 71), RB1), ((1139, 71), RB2)],
   corr={"Park E-2": (1125.5, 561.5), "Park E-1": (1012, 616), "Park E-3 (north)": (1172, 684), "Park E-4": (1036, 772), "Park E-3 (south)": (1155, 772), "Park E-5 (west)": (994.5, 843.5), "Park E-5 (east)": (1104.5, 851.5)},
   feats=[
    ("mosque", "Jamia Mosque (E)", "f", (489, 632, 560, 708), 5.3), ("school", "Govt. Primary School (E)", "f", (489, 711, 560, 864), 10.9),
    ("playground", "Playground E-2", "f", (565, 632, 718, 806), 24.9), ("dispensary", "Dispensary (E)", "f", (565, 811, 592, 864), None),
    ("commercial", "Commercial Centre (E)", "f", (597, 811, 718, 864), 6.5),
    ("commercial", "Commercial Centre (FDA City Homes)", "f", (472, 1772, 549, 1907), None), ("school", "Primary School (FDA City Homes)", "f", (472, 1911, 549, 2036), None),
    ("playground", "Playground E-6", "f", (553, 1772, 705, 1960), None), ("civic", "Public Building", "f", (553, 1964, 705, 2036), None),
    ("sports", "Sports Complex", "f", (730, 1772, 843, 1932), None), ("hospital", "FDA City Hospital", "f", (730, 1936, 843, 2036), None),
    ("mosque", "Mosque (Park E-5)", "f", (218, 1394, 253, 1428), None), ("shops", "Shops (Park E-5)", "f", (256, 1394, 290, 1428), None),
    ("park", "Park E-5 (west)", "f", (218, 1432, 290, 1503), None),
    ("park", "Park E-6", "f", (547, 1705, 619, 1748), None), ("shops", "Shops (Park E-6)", "f", (621, 1705, 656, 1748), None),
    ("shrine", "Darbar (E)", "s", (633, 411, 668, 429), None),
    ("park", "Park E-2", "s", (412, 182, 490, 238), None), ("park", "Park E-1", "s", (170, 310, 214, 392), None),
    ("park", "Park E-3 (north)", "s", (530, 470, 580, 523), None), ("park", "Park E-4", "s", (200, 668, 295, 723), None),
    ("park", "Park E-3 (south)", "s", (532, 670, 578, 722), None), ("park", "Park E-5 (east)", "s", (360, 862, 425, 896), None)],
   homes=[(78, 1050), (270, 1050), (270, 1212), (500, 1212), (500, 1050), (650, 1050), (650, 1420), (78, 1425)]),
 "F": dict(scale=1.0, urls=[BASE + "fda_f/Block_F.jpg"], size=[1200, 854],
   rb=[((695, 213), RBSW), ((1185, 22), RB1)],
   corr={"Park F-4": (875, 749.5), "Park F-5": (890.5, 858.5), "Park F-6": (889.5, 924.5), "Park F-6 (south)": (890, 1062.5)},
   feats=[("park", "Park F-3", "f", (1113, 209, 1144, 236), 1.82), ("park", "Park F-4", "f", (1077, 354, 1111, 390), None),
          ("park", "Park F-5", "f", (1100, 498, 1128, 520), None), ("park", "Park F-6", "f", (1098, 578, 1128, 612), None),
          ("park", "Park F-6 (south)", "f", (1099, 764, 1128, 787), None)]),
}

def iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0: return 0
    i = (x1 - x0) * (y1 - y0); return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)

new_zones, new_parks = [], []
for name, sh in S.items():
    det = json.load(open(os.path.join(mdir, f"ph_{name}.json")))
    sc = sh["scale"]; rects = {}
    for kind, nm, mode, r, kan in sh["feats"]:
        r = [v / sc for v in r] if mode == "s" else list(r)
        best = max(det, key=lambda b: iou(r, b)) if det else None
        snapped = mode == 's' and best is not None and iou(r, best) >= 0.45   # hand-traced parts of a complex are never snapped
        if snapped: r = [best[0], best[1], best[2] + 1, best[3] + 1]
        r = [round(v, 1) for v in r]; rects[nm] = r
        item = {"kind": kind, "name": nm, "block": name, "sheet": name, "rect": r}
        if kan: item["kanal"] = kan
        if nm.startswith("Proposed"): item["proposed"] = True
        (new_parks if kind == "park" else new_zones).append({k: v for k, v in item.items() if not (k == "kind" and kind == "park")})
        sh.setdefault("log", []).append((nm, "snapped" if snapped else "traced", r))
    if "homes" in sh:
        new_zones.append({"kind": "homes", "name": "Area for FDA City Homes", "block": name, "sheet": name, "px": [[round(x / sc, 1), round(y / sc, 1)] for x, y in sh["homes"]]})
    cps = [{"px": list(p), "lonlat": ll, "what": "roundabout centre"} for p, ll in sh["rb"]]
    for nm, opx in sh["corr"].items():
        r = rects[nm]; cps.append({"px": [round((r[0] + r[2]) / 2, 1), round((r[1] + r[3]) / 2, 1)], "lonlat": overall_ll(*opx), "what": nm + " (also on the overall plan)"})
    # fit + report; roundabouts weigh 4x
    w = np.array([4.0 if c["what"].startswith("roundabout") else 1.0 for c in cps])
    Xs = np.array([complex(c["px"][0], -c["px"][1]) for c in cps]); Zs = np.array([complex((c["lonlat"][0] - 73.0875) * KX, (c["lonlat"][1] - 31.525) * KY) for c in cps])
    (k, t), *_ = np.linalg.lstsq(np.vstack([Xs, np.ones_like(Xs)]).T * w[:, None], Zs * w, rcond=None)
    res = np.abs(k * Xs + t - Zs)
    keep = [i for i, c in enumerate(cps) if c["what"].startswith("roundabout") or res[i] <= 25]
    if len(keep) < len(cps):            # drop park pairs that disagree by more than 25 m and refit
        print("   dropped:", [cps[i]["what"].split(" (also")[0] for i in range(len(cps)) if i not in keep])
        cps = [cps[i] for i in keep]; w = w[keep]; Xs = Xs[keep]; Zs = Zs[keep]
        (k, t), *_ = np.linalg.lstsq(np.vstack([Xs, np.ones_like(Xs)]).T * w[:, None], Zs * w, rcond=None)
        res = np.abs(k * Xs + t - Zs)
    print(f"sheet {name}: {abs(k):.3f} m/px, rot {math.degrees(np.angle(k)):.2f} deg, residuals m: " + ", ".join(f"{c['what'].split(' (')[0][:16]} {r:.0f}" for c, r in zip(cps, res)))
    if "rb_axis" in sh:
        # the sheet's second roundabout is not built yet, but it lies on the straight boulevard axis
        # (RB1 -> RB2 extended): place it there at the fitted scale so the sheet's rotation is tied to the axis
        a1 = complex((RB1[0] - 73.0875) * KX, (RB1[1] - 31.525) * KY); a2 = complex((RB2[0] - 73.0875) * KX, (RB2[1] - 31.525) * KY); u = (a2 - a1) / abs(a2 - a1)
        p0 = complex(sh["rb"][0][0][0], -sh["rb"][0][0][1]); p1 = complex(sh["rb_axis"][0], -sh["rb_axis"][1])
        for _ in range(4):
            zz = a2 + u * abs(k) * abs(p1 - p0)
            X2 = np.append(Xs, p1); Z2 = np.append(Zs, zz); w2 = np.append(w, 4.0)
            (k, t), *_ = np.linalg.lstsq(np.vstack([X2, np.ones_like(X2)]).T * w2[:, None], Z2 * w2, rcond=None)
        cps.append({"px": list(sh["rb_axis"]), "lonlat": [round(73.0875 + zz.real / KX, 7), round(31.525 + zz.imag / KY, 7)], "what": "roundabout centre (planned, on the boulevard axis)"})
        print(f"   {name}: axis-tied fit {abs(k):.3f} m/px, rot {math.degrees(np.angle(k)):.2f} deg; planned roundabout {abs(k) * abs(p1 - p0):.0f} m beyond RB2; park residuals {[round(float(r)) for r in np.abs(k * Xs + t - Zs)]}")
    for c in cps:                       # replicate roundabouts so the generator's plain least squares weighs them the same way
        if c["what"].startswith("roundabout"): cps = cps + [c] * 3
    pf["sheets"][name] = {"about": f"Block {name} map from fdacity.pk, pages stacked top to bottom ({sh['size'][0]}x{sh['size'][1]})", "urls": sh["urls"], "control_points": cps}
    # overlay for checking
    im = Image.open(os.path.join(mdir, f"sheet_{name}.jpg")).convert("RGB"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("arialbd.ttf", 15)
    except Exception: f = ImageFont.load_default()
    for nm, how, r in sh["log"]:
        d.rectangle(r, outline=(255, 0, 0) if how == "snapped" else (0, 0, 255), width=3)
        d.text((r[0] + 3, r[1] + 3), nm.replace("Park ", "P ").replace("Govt. Primary ", "")[:18], fill=(255, 255, 0), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
    s2 = min(1, 1500 / max(im.size)); im.resize((int(im.width * s2), int(im.height * s2)), Image.LANCZOS).save(os.path.join(mdir, f"chk_{name}.jpg"), quality=88)

# replace the entries that came from the small overall plan
keep_zone_kinds = {"metro", "grid", "graveyard", "sewerage"}
pf["zones"] = [z for z in pf["zones"] if z.get("sheet") == "A" or z["kind"] in keep_zone_kinds] + new_zones
pf["parks"] = [p for p in pf["parks"] if p.get("sheet") == "A" or p.get("name") == "Park F-1"] + new_parks
pf["facilities"] = [f for f in pf["facilities"] if f["name"] in ("Mosque (F-1)", "Mosque (F)", "Shrine (F, 1.40 kanal)")]
pf["complexes"] = []
json.dump(pf, open(pf_path, "w", encoding="utf-8"), indent=1)
print(len(pf["zones"]), "zones;", len(pf["parks"]), "parks;", len(pf["facilities"]), "facilities")

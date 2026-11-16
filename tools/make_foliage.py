"""Builds public/tex/foliage.webp, the texture of the trees in the 3D society model, from photographed leaves.

    python -I tools/make_foliage.py

Source (all CC0): the compound leaves of Poly Haven's `jacaranda_tree` (pinnate, like neem and sheesham), the single
leaves of Poly Haven's `island_tree_02` (long and narrow, like the Ashoka trees planted along Pakistani streets) and the
ambientCG bark `Bark014`. Downloads the 1k maps once into tools/source/cache/ (git-ignored).

Output, a 1024 x 1024 RGBA atlas of four 512 px cells:
    top left      leaf cluster of compound leaves (round crowns: neem, sheesham)
    top right     leaf cluster of long single leaves (columnar crowns: Ashoka)
    bottom left   one palm frond (date palms on the boulevard)
    bottom right  bark (opaque)
Leaves are stamped at random angles, sizes and shades, lower layers darker (self-shading). Transparent pixels carry
the average leaf colour, so mipmaps do not darken the edges. Needs pillow, numpy, opencv.
"""
import os, sys, urllib.request
import numpy as np, cv2
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tools', 'source', 'cache', 'polyhaven')
OUT = os.path.join(ROOT, 'public', 'tex', 'foliage.webp')
BASE = 'https://dl.polyhaven.org/file/ph-assets/Models/jpg/1k/'
FILES = ['jacaranda_tree/jacaranda_tree_leaves_diff_1k', 'jacaranda_tree/jacaranda_tree_leaves_alpha_1k',
         'island_tree_02/island_tree_02_leaves_diff_1k', 'island_tree_02/island_tree_02_leaves_alpha_1k']
BARK = 'Bark014'
C = 512
rng = np.random.default_rng(7)


def get(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(name) + '.jpg')
    if not os.path.exists(path):
        req = urllib.request.Request(BASE + name + '.jpg', headers={'User-Agent': 'terralyt-texture-builder'})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
            f.write(r.read())
    return np.asarray(Image.open(path).convert('RGB')).astype(np.float32) / 255.


def bark_map():
    import io, zipfile
    path = os.path.join(ROOT, 'tools', 'source', 'cache', 'ambientcg', BARK + '_1K-JPG.zip')
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(f'https://ambientcg.com/get?file={BARK}_1K-JPG.zip', headers={'User-Agent': 'terralyt-texture-builder'})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
            f.write(r.read())
    z = zipfile.ZipFile(path)
    name = [n for n in z.namelist() if n.endswith('_Color.jpg')][0]
    return np.asarray(Image.open(io.BytesIO(z.read(name))).convert('RGB').resize((C, C), Image.LANCZOS)).astype(np.float32) / 255.


def axis_angle(sp):
    """angle (degrees, for cv2) that turns the long axis of a sprite horizontal"""
    ys, xs = np.nonzero(sp[..., 3] > .5)
    xy = np.stack([xs - xs.mean(), ys - ys.mean()])
    w, v = np.linalg.eigh(xy @ xy.T)
    d = v[:, np.argmax(w)]
    return np.degrees(np.arctan2(d[1], d[0]))


def sprites(diff, alpha, min_area=4000):
    """cut every leaf (connected piece of the alpha map) out of an atlas: list of RGBA float arrays"""
    a = alpha[..., 0]
    mask = (cv2.dilate((a > .35).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area: continue
        m = (lab[y:y + h, x:x + w] == i)
        rgba = np.dstack([diff[y:y + h, x:x + w], a[y:y + h, x:x + w] * m])
        out.append(rgba)
    return out


def stamp(canvas, sp, cx, cy, scale, angle, shade):
    """draw sprite sp onto canvas (RGBA float) centred at cx, cy, rotated and scaled, colour times shade"""
    h, w = sp.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    M[0, 2] += cx - w / 2; M[1, 2] += cy - h / 2
    H, W = canvas.shape[:2]
    warped = cv2.warpAffine(sp, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    al = warped[..., 3:4]
    col = np.clip(warped[..., :3] * shade, 0, 1)
    canvas[..., :3] = canvas[..., :3] * (1 - al) + col * al
    canvas[..., 3:4] = canvas[..., 3:4] + al * (1 - canvas[..., 3:4])


def cluster(leaves, n, radius, scale, tint, droop=0.0):
    """a rounded clump of leaves: back layers first and darker, front layers lighter"""
    cv_ = np.zeros((C, C, 4), np.float32)
    for k in range(n):
        t = k / max(1, n - 1)                                    # 0 = back / inside, 1 = front / outside
        r = radius * np.sqrt(rng.uniform(0, 1)) * (.55 + .45 * t)
        a = rng.uniform(0, 2 * np.pi)
        cx, cy = C / 2 + r * np.cos(a), C / 2 + r * np.sin(a) * .9 + droop * r
        sp = leaves[rng.integers(len(leaves))]
        sc = scale * rng.uniform(.75, 1.15) * C / max(sp.shape[:2])
        shade = np.array(tint) * (.62 + .5 * t) * rng.uniform(.9, 1.1, 3) ** .3
        stamp(cv_, sp, cx, cy, sc, rng.uniform(0, 360), shade)
    return cv_


def fill_background(cell):
    """transparent pixels get the mean leaf colour (no dark fringes in mipmaps)"""
    a = cell[..., 3]
    if (a > .5).any():
        mean = cell[..., :3][a > .5].mean(0)
        cell[..., :3] = cell[..., :3] * a[..., None] + mean * (1 - a[..., None])
    return cell


def main():
    jd, ja, idf, ia = (get(f) for f in FILES)
    bark = bark_map()
    pinnate = sprites(jd, ja)
    broad = sprites(idf, ia, min_area=1500)
    print(f'{len(pinnate)} compound leaves, {len(broad)} single leaves')
    atlas = np.zeros((2 * C, 2 * C, 4), np.float32)
    # top left: compound leaves, fresh green (neem / sheesham)
    atlas[:C, :C] = fill_background(cluster(pinnate, 46, C * .3, .55, (1.0, 1.08, .86)))
    # top right: long single leaves, darker glossy green (Ashoka)
    atlas[:C, C:] = fill_background(cluster(broad, 150, C * .32, .2, (.82, 1.0, .82)))
    # bottom left: a palm frond: the longest compound leaf laid along the cell, twice, darker
    fr = np.zeros((C, C, 4), np.float32)
    big = max(pinnate, key=lambda s: max(s.shape[:2]))
    ys, xs = np.nonzero(big[..., 3] > .5)
    ang = axis_angle(big)
    a = np.radians(ang); L = np.ptp((xs - xs.mean()) * np.cos(a) + (ys - ys.mean()) * np.sin(a))   # length along the axis
    for dy, sh in ((-16, .7), (14, .85), (0, 1.0)):
        stamp(fr, big, C / 2, C / 2 + dy, .94 * C / L, ang + rng.uniform(-3, 3), np.array((.78, .95, .7)) * sh)
    atlas[C:, :C] = fill_background(fr)
    # bottom right: bark, opaque
    atlas[C:, C:, :3] = bark; atlas[C:, C:, 3] = 1
    img = Image.fromarray((np.clip(atlas, 0, 1) * 255).astype(np.uint8), 'RGBA')
    img.save(OUT, 'WEBP', quality=88, method=6)
    a = atlas[..., 3]
    for name, cell in (('compound', atlas[:C, :C]), ('single', atlas[:C, C:]), ('frond', atlas[C:, :C])):
        m = cell[..., 3] > .5
        print(f'{name}: coverage {m.mean():.2f}, mean colour {np.round(cell[..., :3][m].mean(0) * 255).astype(int)}')
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')


if __name__ == '__main__':
    sys.exit(main())

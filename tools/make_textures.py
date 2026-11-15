"""Builds the photo textures in assets/tex/ from ambientCG (CC0) material packs.

    python -I tools/make_textures.py

Downloads each 1K-JPG pack once into tools/source/cache/ambientcg/ (git-ignored), takes its colour map, scales it to
512 px, removes large stains with a high-pass filter on the tiled image (so the result still tiles; otherwise the stains
repeat as a visible pattern over a road or lawn) and sets the contrast of the fine grain. Needs pillow, numpy, opencv.
"""
import io, os, sys, urllib.request, zipfile
import numpy as np, cv2
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tools', 'source', 'cache', 'ambientcg')
OUT = os.path.join(ROOT, 'assets', 'tex')
SIZE = 512
SPEC = {  # file: (ambientCG asset, high-pass sigma in px (0 = keep), grain gain)
    'asphalt': ('Asphalt025C', 14, 2.4), 'grass': ('Grass004', 28, 1.1), 'soil': ('Ground103', 28, 1.0),
    'plaster': ('Plaster001', 24, 1.7), 'brick': ('Bricks101', 0, 1.0), 'paving': ('PavingStones070', 0, 1.0),
    'concrete': ('Concrete036', 22, 1.0), 'gravel': ('Gravel023', 24, 1.0)}


def pack(asset):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, asset + '_1K-JPG.zip')
    if not os.path.exists(path):
        req = urllib.request.Request(f'https://ambientcg.com/get?file={asset}_1K-JPG.zip', headers={'User-Agent': 'terralyt-texture-builder'})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
            f.write(r.read())
    return zipfile.ZipFile(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (asset, sigma, gain) in SPEC.items():
        z = pack(asset)
        colour = [n for n in z.namelist() if n.endswith('_Color.jpg')][0]
        a = np.asarray(Image.open(io.BytesIO(z.read(colour))).convert('RGB').resize((SIZE, SIZE), Image.LANCZOS)).astype(np.float32)
        mean = a.reshape(-1, 3).mean(0)
        if sigma:
            low = cv2.GaussianBlur(np.tile(a, (3, 3, 1)), (0, 0), sigma)[SIZE:2 * SIZE, SIZE:2 * SIZE]
            a = a - low + mean
        a = np.clip(mean + (a - mean) * gain, 0, 255).astype(np.uint8)
        Image.fromarray(a).save(os.path.join(OUT, name + '.jpg'), quality=84, optimize=True, progressive=True)
        print(f'{name}.jpg from {asset}: grain {np.round((a / 255.).reshape(-1, 3).std(0), 3)}')


if __name__ == '__main__':
    sys.exit(main())

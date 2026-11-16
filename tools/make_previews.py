"""Pictures of the real 3D map for the home and dashboard pages: public/img/hero-3d.jpg and layer-{real,cls,stat}.jpg.

    npm run build && (cd dist && python -m http.server 8080)      # in one terminal
    python -I tools/make_previews.py                                # in another

Opens the 3D map in headless Chrome (software rendering is slow: about 2 minutes), hides the map controls, flies to a
view over Block A and the main boulevard and saves each view as a JPEG. Needs `pip install playwright pillow`.
"""
import io, os, sys, time
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'public', 'img')
URL = os.environ.get('TERRALYT_URL', 'http://127.0.0.1:8080/')
CAM = """(a) => { const [lon, lat, dist, polar, az] = a; const K = 111320 * Math.cos(31.525 * Math.PI / 180);
  const e = (lon - 73.0860075) * K, n = (lat - 31.523318) * 111320; window.__map.flyTo(e, n, dist, polar, az, 0.05); return 1; }"""
HIDE = """.s3d-mini,.s3d-pad,.s3d-compass,.leg,.fsb,.hint,#tip,.msw,#side,.s3d-labels,.cap{display:none!important}"""
VIEWS = [  # file, layer, lon, lat, distance, polar, azimuth, size
    ('hero-3d', 'real', 73.0745, 31.5135, 520, 0.95, 0.75, (1200, 900)),
    ('layer-real', 'real', 73.0728, 31.5158, 300, 0.9, 2.1, (1200, 760)),
    ('layer-cls', 'cls', 73.0740, 31.5140, 650, 0.85, 0.6, (1200, 760)),
    ('layer-stat', 'stat', 73.0740, 31.5140, 650, 0.85, 0.6, (1200, 760)),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        pg = b.new_page(viewport={'width': 1200, 'height': 900})
        pg.goto(URL + '#/map?quality=fast', wait_until='domcontentloaded')
        t0 = time.time()
        while time.time() - t0 < 300 and not pg.evaluate('!!(window.__map && window.__map.rendered && window.__map.rendered())'):
            time.sleep(1)
        pg.mouse.move(600, 400); pg.keyboard.press('f'); time.sleep(3)
        pg.add_style_tag(content=HIDE)
        for name, layer, lon, lat, dist, polar, az, size in VIEWS:
            pg.evaluate(f"window.__map.setLayer('{layer}')")
            pg.set_viewport_size({'width': size[0], 'height': size[1]}); time.sleep(1.5)
            pg.evaluate(CAM, [lon, lat, dist, polar, az]); time.sleep(6)
            im = Image.open(io.BytesIO(pg.screenshot())).convert('RGB')
            path = os.path.join(OUT, name + '.jpg'); im.save(path, quality=82, optimize=True, progressive=True)
            print(name, im.size, os.path.getsize(path) // 1024, 'KB', flush=True)
        b.close()


if __name__ == '__main__':
    sys.exit(main())

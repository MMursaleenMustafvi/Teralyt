"""Screenshot the 3D map with headless Chromium (Playwright) for visual checks.

usage: python -I tools/shoot.py <url> <out.png> [--click X,Y] [--js "expr"] [--wait S] [--size WxH]
Waits for window.__map.ready and window.__map.rendered() before capturing.
Prints console messages and page errors, which is how we catch runtime bugs.
"""
import argparse, sys, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("url"); ap.add_argument("out")
ap.add_argument("--click", default=None, help="x,y to click before the shot")
ap.add_argument("--js", action="append", default=[], help="JS to run after ready (repeatable)")
ap.add_argument("--wait", type=float, default=2.0, help="extra seconds after rendered()")
ap.add_argument("--size", default="1500x1050")
ap.add_argument("--timeout", type=float, default=120)
a = ap.parse_args()
w, h = (int(v) for v in a.size.split("x"))

with sync_playwright() as p:
    flags = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"]
    try:
        b = p.chromium.launch(channel="chrome", args=flags)   # installed Google Chrome
    except Exception:
        b = p.chromium.launch(args=flags)                     # Playwright's own Chromium
    pg = b.new_page(viewport={"width": w, "height": h})
    msgs = []
    pg.on("console", lambda m: msgs.append(f"[{m.type}] {m.text[:300]}"))
    pg.on("pageerror", lambda e: msgs.append(f"[pageerror] {str(e)[:300]}"))
    pg.on("requestfailed", lambda r: msgs.append(f"[reqfail] {r.url[:120]} {r.failure}"))
    pg.goto(a.url, wait_until="domcontentloaded", timeout=120000)   # Cesium (4.8 MB) may load slowly from the CDN
    t0 = time.time()
    state = "timeout"
    while time.time() - t0 < a.timeout:
        s = pg.evaluate("(() => { const m = window.__map; if (!m) return 'nomap'; if (m.__failed) return 'failed'; return m.rendered() ? 'ready' : 'waiting'; })()")
        if s in ("ready", "failed"):
            state = s; break
        if s == "nomap" and time.time() - t0 > 15:
            st = pg.evaluate("document.getElementById('st') ? document.getElementById('st').innerText : ''")
            if "unavailable" in st: state = "error:" + st; break
        time.sleep(0.5)
    print(f"state={state} after {time.time()-t0:.1f}s")
    for js in a.js:
        print("js:", js, "->", pg.evaluate(js))
        time.sleep(1.5)
    if a.click:
        x, y = (int(v) for v in a.click.split(","))
        pg.mouse.click(x, y); time.sleep(1.5)
    time.sleep(a.wait)
    pg.evaluate("window.__map && window.__map.requestRender()")
    time.sleep(0.5)
    pg.screenshot(path=a.out)
    print("log:", pg.evaluate("window.__log || []"))
    print("side panel:", pg.evaluate("(document.getElementById('side')||{}).innerText || ''")[:400].replace("\n", " | "))
    for m in msgs:
        if "drawImage" in m: continue  # bg.js background animation, not the map
        print(m)
    b.close()

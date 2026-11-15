"""Read the plot-number crops of tools/emap_plan.py with RapidOCR (PaddleOCR text recogniser on ONNX).

Runs in the Python that has rapidocr_onnxruntime installed (on Taha's PC: Python 3.12), called by emap_plan.py:
    py -3.12 -I tools/rapid_ocr.py <crops.pkl> <out.json> [--limit N]
Each crop is read in four turns; the result per cell is {turn: [text, score]}.
"""
import json
import pickle
import sys
import time

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


def main():
    src, out = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    crops = pickle.load(open(src, "rb"))
    if limit:
        crops = crops[:limit]
    eng = RapidOCR()
    rec = eng.text_rec
    res = {}
    t0 = time.time()
    B = 64
    jobs = []
    for k, img, ng in crops:
        for t in range(4):
            a = np.ascontiguousarray(np.rot90(img, t))
            h, w = a.shape
            if t in (1, 3) and ng >= 2:
                continue                              # a number of several digits reads along its line, not across
            a = cv2.copyMakeBorder(a, 8, 8, 12, 12, cv2.BORDER_CONSTANT, value=255)
            sc = 48.0 / a.shape[0]
            a = cv2.resize(a, (max(16, int(a.shape[1] * sc)), 48), interpolation=cv2.INTER_AREA)
            jobs.append((int(k), t, cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)))
    for i in range(0, len(jobs), B):
        batch = jobs[i:i + B]
        out_b = rec([j[2] for j in batch])
        items = out_b[0] if isinstance(out_b, tuple) else out_b
        for (k, t, _), r in zip(batch, items):
            txt, score = (r[0], float(r[1])) if r else ("", 0.0)
            res.setdefault(str(k), {})[str(t)] = [txt, round(score, 4)]
        if (i // B) % 50 == 0:
            print(f"  rapidocr: {min(i + B, len(jobs))}/{len(jobs)} ({time.time() - t0:.0f} s)", flush=True)
    json.dump(res, open(out, "w"))
    print(f"rapidocr: {len(res)} crops read in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OCR scanned exercise PDFs to per-page text (JSONL).

Usage: python3 scripts/ocr_pdfs.py
Writes tmp/pdfs/ocr.jsonl with {pdf, page, text}.
"""
import fitz, io, json, sys, time
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

PDFS = {
    "pdf1": "/Users/td_xu/Desktop/SKill/图片转pdf_20260615_220818.pdf",
    "pdf2": "/Users/td_xu/Desktop/SKill/图片转pdf_20260615_220957.pdf",
}
OUT = "/Users/td_xu/Desktop/SKill/study-loop/tmp/pdfs/ocr.jsonl"
DPI = 150
MAX_LONG_EDGE = 2200  # downscale huge scans before inference for speed


def resize_long_edge(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    edge = max(w, h)
    if edge <= max_edge:
        return img
    sc = max_edge / edge
    return img.resize((int(w * sc), int(h * sc)))

def main():
    engine = RapidOCR()
    started = time.time()
    n_done = 0
    n_total = sum(fitz.open(p).page_count for p in PDFS.values())
    with open(OUT, "w") as f:
        for key, path in PDFS.items():
            d = fitz.open(path)
            for i in range(d.page_count):
                t0 = time.time()
                pix = d[i].get_pixmap(dpi=DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                img = resize_long_edge(img, MAX_LONG_EDGE)
                arr = np.array(img)
                result, _elapse = engine(arr)
                lines = [r[1] for r in result] if result else []
                rec = {"pdf": key, "page": i, "text": "\n".join(lines)}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                n_done += 1
                print(f"[{key} p{i}] {len(lines)} lines, {time.time()-t0:.1f}s | "
                      f"{n_done}/{n_total} done, {time.time()-started:.0f}s elapsed",
                      flush=True)
    print(f"DONE -> {OUT}")

if __name__ == "__main__":
    main()

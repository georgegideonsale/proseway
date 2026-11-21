"""Optional OCR for scanned pages, using RapidOCR (Apache-2.0, ONNX, CPU-only).

Install with:  pip install "proseway[ocr]"   (adds ~60 MB of models and onnxruntime)

If RapidOCR isn't installed, scanned pages are kept as page images so nothing is lost,
and the reader shows a note explaining how to enable OCR.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

OCR_SCALE = 200 / 72  # render at ~200 dpi


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


class RapidOcrEngine:
    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def page_lines(self, pdfium_doc, index: int, page_w: float, page_h: float) -> list[dict]:
        import numpy as np

        page = pdfium_doc[index]
        try:
            img = page.render(scale=OCR_SCALE, may_draw_forms=False).to_pil().convert("RGB")
        finally:
            page.close()
        result, _elapse = self._engine(np.asarray(img))
        lines: list[dict] = []
        for box, text, score in result or []:
            if not text or not text.strip() or float(score) < 0.5:
                continue
            xs = [p[0] / OCR_SCALE for p in box]
            ys = [p[1] / OCR_SCALE for p in box]
            top, bot = min(ys), max(ys)
            height = bot - top
            lines.append({
                "t": text.strip(), "x0": round(min(xs), 2), "x1": round(max(xs), 2),
                "top": round(top, 2), "bot": round(bot, 2),
                # Glyph height is roughly 70% of the detected box height.
                "sz": round(height * 0.72 * 2) / 2 or 10.0,
                "font": "OCR", "b": False, "i": False, "m": False, "mt": 0.0, "sp": [],
                "conf": round(float(score), 3),
            })
        lines.sort(key=lambda d: (d["top"], d["x0"]))
        return lines


def get_engine():
    if not available():
        return None
    try:
        return RapidOcrEngine()
    except Exception as exc:
        log.warning("OCR engine failed to start: %s", exc)
        return None

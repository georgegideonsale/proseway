"""Benchmark conversion accuracy, speed and memory on the test corpus.

    uv run python scripts/benchmark.py                       # all books, pdfium engine
    uv run python scripts/benchmark.py --engines pdfium plumber --only pride arxiv

Metrics (all on lower-cased alphanumeric word tokens):

* layer_recall: share of the PDF's own text-layer words that appear in our output
  (multiset). Running headers and page numbers are removed on purpose, so 0.97-0.99 is
  the expected ceiling for a book with a header on every page.
* layer_order: Indel similarity between the word sequences (catches reading-order errors).
* ref_similarity / ref_recall: the same against an independent reference text (Gutenberg
  plain text or arXiv LaTeX source, with markup stripped). Edition differences lower these.

Results go to bench-results/benchmark.json and bench-results/benchmark.md.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import tarfile
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

import psutil
import pypdfium2 as pdfium
from rapidfuzz.distance import Indel

from proseway import library
from proseway.db import Database
from proseway.paths import DataPaths
from proseway.pipeline.convert import run_conversion

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "test-books"
OUT = ROOT / "bench-results"
TOKEN = re.compile(r"[a-z0-9]+")
QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.translate(QUOTES).casefold().replace("'", ""))


def layer_text(pdf: Path) -> str:
    doc = pdfium.PdfDocument(str(pdf))
    parts = []
    for page in doc:
        tp = page.get_textpage()
        parts.append(tp.get_text_range())
        tp.close()
        page.close()
    doc.close()
    # PDFium returns line-end hyphens as U+0002 and keeps the line break: join them like a reader would.
    text = "\n".join(parts).replace("\u0002\r\n", "").replace("\u0002\n", "").replace("\u0002", "")
    # Rejoin ordinary hyphens at line ends when the next line starts in lower case.
    return re.sub(r"(\w)-\r?\n(?=[a-z])", r"\1", text)


def gutenberg_body(txt: str) -> str:
    start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n", txt)
    end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG", txt)
    return txt[start.end() if start else 0: end.start() if end else len(txt)]


def latex_text(archive: Path) -> str:
    data = archive.read_bytes()
    texts = []
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".tex"):
                    f = tf.extractfile(m)
                    if f:
                        texts.append(f.read().decode("utf-8", "replace"))
    except tarfile.TarError:
        texts.append(gzip.decompress(data).decode("utf-8", "replace"))
    tex = "\n".join(texts)
    tex = re.sub(r"(?<!\\)%.*", "", tex)  # comments
    tex = re.sub(r"\\begin\{(equation|align|eqnarray|figure|table|tabular)\*?\}.*?\\end\{\1\*?\}", " ", tex, flags=re.S)
    tex = re.sub(r"\$[^$]*\$", " ", tex)
    tex = re.sub(r"\\(cite|ref|label|eqref|url|href|includegraphics)\*?(\[[^\]]*\])?\{[^}]*\}", " ", tex)
    tex = re.sub(r"\\[a-zA-Z]+\*?", " ", tex)
    return re.sub(r"[{}\[\]]", " ", tex)


def multiset_recall(ours: list[str], ref: list[str]) -> float:
    a, b = Counter(ours), Counter(ref)
    total = sum(b.values()) or 1
    return sum(min(a[w], n) for w, n in b.items()) / total


def run_one(pdf: Path, engine: str) -> dict:
    os.environ["PROSEWAY_ENGINE"] = engine
    root = Path(tempfile.mkdtemp(prefix="pw-bench-"))
    paths = DataPaths(root).ensure()
    db = Database(paths.db).init()
    with open(pdf, "rb") as fh:
        tmp, sha, size = library.save_upload(paths, fh)
    book_id, _ = library.create_book(db, paths, tmp, sha, size, pdf.name)
    proc = psutil.Process()
    base = proc.memory_info().rss
    peak = [base]
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            stop.wait(0.1)

    t = threading.Thread(target=sample, daemon=True)
    t.start()
    started = time.perf_counter()
    run_conversion(str(paths.db), str(root), book_id)
    seconds = time.perf_counter() - started
    stop.set()
    with db.connect() as c:
        book = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        rows = c.execute("SELECT type, text FROM blocks WHERE book_id=? ORDER BY seq", (book_id,)).fetchall()
    text = "\n".join(r["text"] for r in rows if r["type"] not in ("figure", "page_image"))
    stats = json.loads(book["stats_json"] or "{}")
    return {
        "status": book["status"],
        "error": book["error"],
        "pages": book["page_count"],
        "seconds": round(seconds, 1),
        "sec_per_page": round(seconds / max(1, book["page_count"]), 3),
        "peak_rss_mb": round(peak[0] / 2**20),
        "blocks": stats.get("blocks"),
        "removed": stats.get("removed", {}),
        "ocr_pages": stats.get("ocr_pages", 0),
        "scanned_pages": stats.get("scanned_pages", 0),
        "text": text,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", default=["pdfium"])
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()
    meta = json.loads((ROOT / "scripts" / "test_books.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    results_file = OUT / "benchmark.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}

    for b in meta:
        if args.only and not any(o in b["id"] for o in args.only):
            continue
        pdf = BOOKS / f"{b['id']}.pdf"
        if not pdf.exists():
            print(f"skip {b['id']}: not downloaded")
            continue
        layer = tokens(layer_text(pdf))
        ref_tokens = None
        ref_txt = BOOKS / f"{b['id']}.reference.txt"
        ref_src = BOOKS / f"{b['id']}.source.tar.gz"
        if ref_txt.exists():
            ref_tokens = tokens(gutenberg_body(ref_txt.read_text(encoding="utf-8", errors="replace")))
        elif ref_src.exists():
            ref_tokens = tokens(latex_text(ref_src))
        for engine in args.engines:
            print(f"{b['id']} [{engine}] …", flush=True)
            r = run_one(pdf, engine)
            ours = tokens(r.pop("text"))
            r["words"] = len(ours)
            r["layer_words"] = len(layer)
            r["layer_recall"] = round(multiset_recall(ours, layer), 4)
            r["layer_precision"] = round(multiset_recall(layer, ours), 4)
            r["layer_order"] = round(Indel.normalized_similarity(ours, layer), 4) if layer else None
            if ref_tokens:
                r["ref_recall"] = round(multiset_recall(ours, ref_tokens), 4)
                # Share of our words that exist in the reference: OCR quality when the
                # reference covers more than the PDF does.
                r["ref_precision"] = round(multiset_recall(ref_tokens, ours), 4)
                r["ref_similarity"] = round(Indel.normalized_similarity(ours, ref_tokens), 4)
            r["category"] = b["category"]
            results[f"{b['id']}|{engine}"] = r
            print(json.dumps(r), flush=True)
            results_file.write_text(json.dumps(results, indent=1), encoding="utf-8")

    lines = [
        "| Book | Engine | Pages | Time (s) | s/page | Peak RSS (MB) | Layer recall | Layer order | Ref similarity | Ref recall | Status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in sorted(results.items()):
        book, engine = key.split("|")
        lines.append(
            f"| {book} | {engine} | {r['pages']} | {r['seconds']} | {r['sec_per_page']} | {r['peak_rss_mb']} | "
            f"{r.get('layer_recall', '')} | {r.get('layer_order', '')} | {r.get('ref_similarity', '–')} | "
            f"{r.get('ref_recall', '–')} | {r['status']} |"
        )
    (OUT / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

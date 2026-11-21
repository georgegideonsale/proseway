"""Convert one PDF into a throwaway library and dump the blocks for inspection.

    uv run python scripts/inspect_book.py data/test-books/sleepy-hollow-smoke.pdf [--engine pdfium]

Writes <out>/<name>.blocks.txt (one block per line, with type and page) and prints timing,
peak memory and the pipeline stats.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

from proseway import library
from proseway.db import Database
from proseway.paths import DataPaths
from proseway.pipeline.convert import run_conversion


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=Path("bench-results"))
    ap.add_argument("--engine", default=None)
    args = ap.parse_args()
    if args.engine:
        os.environ["PROSEWAY_ENGINE"] = args.engine

    root = Path(tempfile.mkdtemp(prefix="proseway-inspect-"))
    paths = DataPaths(root).ensure()
    db = Database(paths.db).init()
    with open(args.pdf, "rb") as fh:
        tmp, sha, size = library.save_upload(paths, fh)
    book_id, _ = library.create_book(db, paths, tmp, sha, size, args.pdf.name)

    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            stop.wait(0.2)

    t = threading.Thread(target=sample, daemon=True)
    t.start()
    started = time.perf_counter()
    run_conversion(str(paths.db), str(root), book_id)
    elapsed = time.perf_counter() - started
    stop.set()

    with db.connect() as c:
        book = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        rows = c.execute("SELECT * FROM blocks WHERE book_id=? ORDER BY seq", (book_id,)).fetchall()
    args.out.mkdir(parents=True, exist_ok=True)
    dump = args.out / f"{args.pdf.stem}.blocks.txt"
    with open(dump, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(f"[{r['type']} p{r['page']} L{r['level']} ch{r['chapter']}] {r['text']}\n")
    result = {
        "file": args.pdf.name,
        "status": book["status"],
        "error": book["error"],
        "pages": book["page_count"],
        "seconds": round(elapsed, 2),
        "sec_per_page": round(elapsed / max(book["page_count"], 1), 4),
        "peak_rss_mb": round(peak[0] / 2**20),
        "stats": json.loads(book["stats_json"]),
        "toc_entries": len(json.loads(book["toc_json"])),
        "dump": str(dump),
        "data_dir": str(root),
    }
    print(json.dumps(result, indent=1))
    return 0 if book["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())

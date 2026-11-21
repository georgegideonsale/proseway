"""Download the public-domain / openly licensed test corpus into data/test-books/.

Usage:
    uv run python scripts/fetch_test_books.py            # everything
    uv run python scripts/fetch_test_books.py smoke      # only ids containing "smoke"

Books are never committed to the repository. Checksums of what we downloaded are written to
data/test-books/SHA256SUMS so results can be compared between machines.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "scripts" / "test_books.json"
OUT = ROOT / "data" / "test-books"
UA = "proseway-test-corpus/0.1 (+https://github.com/; test fixtures)"


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310 - fixed https URLs
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 2**20:6.1f} / {total / 2**20:.1f} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def main(argv: list[str]) -> int:
    books = json.loads(LIST.read_text(encoding="utf-8"))
    flt = argv[0] if argv else ""
    OUT.mkdir(parents=True, exist_ok=True)
    sums = []
    for b in books:
        if flt and flt not in b["id"]:
            continue
        pdf = OUT / f"{b['id']}.pdf"
        if not pdf.exists():
            print(f"{b['id']}: {b['pdf_url']}")
            try:
                download(b["pdf_url"], pdf)
            except Exception as exc:
                print(f"  failed: {exc}")
                continue
        head = pdf.read_bytes()[:1024]
        if b"%PDF-" not in head:
            print(f"  {pdf.name} is not a PDF; removing")
            pdf.unlink()
            continue
        sums.append(f"{hashlib.sha256(pdf.read_bytes()).hexdigest()}  {pdf.name}")
        ref = b.get("reference") or {}
        if ref.get("kind") == "gutenberg_txt":
            txt = OUT / f"{b['id']}.reference.txt"
            if not txt.exists():
                for url in (ref.get("url"), ref.get("mirror_url")):
                    if not url:
                        continue
                    try:
                        print(f"  reference: {url}")
                        download(url, txt)
                        break
                    except Exception as exc:
                        print(f"  reference failed: {exc}")
        elif ref.get("kind") == "arxiv_source":
            src = OUT / f"{b['id']}.source.tar.gz"
            if not src.exists() and ref.get("url"):
                try:
                    print(f"  source: {ref['url']}")
                    download(ref["url"], src)
                except Exception as exc:
                    print(f"  source failed: {exc}")
    (OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"done: {len(sums)} PDFs in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

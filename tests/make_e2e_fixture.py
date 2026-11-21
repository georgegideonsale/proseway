"""Write the small generated PDFs the browser tests import (keeps real books out of the repo).

Usage: make_e2e_fixture.py OUT.pdf [novel|long|short]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pdfgen  # noqa: E402

out = Path(sys.argv[1])
kind = sys.argv[2] if len(sys.argv) > 2 else "novel"
out.parent.mkdir(parents=True, exist_ok=True)
if kind == "long":
    pdfgen.make_long_book(out, chapters=6, pages_per_chapter=2)
elif kind == "short":
    pdfgen.make_short_start_book(out, short=4, chapters=4, pages_per_chapter=2)
else:
    pdfgen.make_novel(out, pages=3)
print(out)

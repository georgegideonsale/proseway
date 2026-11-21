"""Write the small generated PDF the browser tests import (keeps real books out of the repo)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pdfgen  # noqa: E402

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
pdfgen.make_novel(out, pages=3)
print(out)

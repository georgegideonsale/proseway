"""GET /api/books/{id}/blocks/{block_id}: one block and its chapter, for notes in unloaded chapters."""

from __future__ import annotations

from fastapi.testclient import TestClient

import pdfgen
from proseway.pipeline.convert import run_conversion
from proseway.server import AppConfig, create_app

H = {"X-Proseway": "1"}


def test_block_lookup_returns_the_block_and_its_chapter(tmp_path):
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=False)
    pdf = tmp_path / "long.pdf"
    pdfgen.make_long_book(pdf, chapters=3, pages_per_chapter=1)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        with open(pdf, "rb") as fh:
            r = client.post("/api/books", files={"files": (pdf.name, fh, "application/pdf")}, headers=H)
        book = r.json()["results"][0]["bookId"]
        run_conversion(str(app.state.paths.db), str(app.state.paths.root), book)

        target = client.get(f"/api/books/{book}/chapters/2").json()["blocks"][1]
        got = client.get(f"/api/books/{book}/blocks/{target['id']}")
        assert got.status_code == 200
        assert got.json() == {"chapter": 2, "block": target}

        missing = client.get(f"/api/books/{book}/blocks/0123456789")
        assert missing.status_code == 404
        assert client.get(f"/api/books/nope/blocks/{target['id']}").status_code == 404

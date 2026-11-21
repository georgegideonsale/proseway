"""API flows: import, read, annotate, export, backup/restore, and the security guards."""

from __future__ import annotations

import io
import json
import zipfile
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

import pdfgen
from proseway.pipeline.convert import run_conversion
from proseway.server import AppConfig, create_app

H = {"X-Proseway": "1"}
BASE = "http://127.0.0.1:8765"


@pytest.fixture
def app(tmp_path):
    return create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE) as c:
        yield c


def import_and_convert(client, app, pdf) -> str:
    with open(pdf, "rb") as fh:
        r = client.post("/api/books", files={"files": (pdf.name, fh, "application/pdf")}, headers=H)
    assert r.status_code == 200, r.text
    book_id = r.json()["results"][0]["bookId"]
    run_conversion(str(app.state.paths.db), str(app.state.paths.root), book_id)
    return book_id


@pytest.fixture
def book(client, app, tmp_path):
    pdf = tmp_path / "novel.pdf"
    pdfgen.make_novel(pdf, pages=2)
    return import_and_convert(client, app, pdf)


def first_paragraph(client, book_id):
    blocks = client.get(f"/api/books/{book_id}/chapters/0").json()["blocks"]
    return next(b for b in blocks if b["type"] == "paragraph")


def test_library_and_reading(client, book):
    books = client.get("/api/books").json()["books"]
    assert books[0]["id"] == book and books[0]["status"] == "ready"
    m = client.get(f"/api/books/{book}/manifest").json()
    assert m["totalBlocks"] > 3 and m["chapters"][0]["firstSeq"] == 0
    assert client.get(f"/api/books/{book}/cover").status_code == 200


def test_duplicate_import_is_detected(client, app, tmp_path, book):
    pdf = tmp_path / "novel.pdf"
    with open(pdf, "rb") as fh:
        r = client.post("/api/books", files={"files": ("again.pdf", fh, "application/pdf")}, headers=H)
    assert r.json()["results"][0] == {"fileName": "again.pdf", "bookId": book, "duplicate": True}


def test_highlight_note_bookmark_position_and_export(client, book):
    p = first_paragraph(client, book)
    r = client.post(f"/api/books/{book}/annotations", headers=H,
                    json={"kind": "highlight", "blockId": p["id"], "start": 0, "end": 20, "color": "blue"})
    assert r.status_code == 200
    ann = r.json()["annotation"]
    assert ann["exact"] == p["text"][:20] and ann["page"] == p["page"]
    r = client.patch(f"/api/annotations/{ann['id']}", headers=H, json={"note": "Remember this"})
    assert r.json()["annotation"]["note"] == "Remember this"
    client.post(f"/api/books/{book}/annotations", headers=H, json={"kind": "bookmark", "blockId": p["id"]})
    assert client.put(f"/api/books/{book}/position", headers=H, json={"blockId": p["id"], "progress": 0.25}).status_code == 200
    assert client.get(f"/api/books/{book}/position").json()["position"]["blockId"] == p["id"]

    md = client.get(f"/api/books/{book}/export.md").text
    assert f"> {p['text'][:20]}" in md and "Remember this" in md and f"p. {p['page']}" in md
    assert "## Bookmarks" in md


def test_bad_annotation_ranges_are_rejected(client, book):
    p = first_paragraph(client, book)
    for body in ({"blockId": p["id"], "start": 5, "end": 5}, {"blockId": p["id"], "start": 0, "end": 10**6},
                 {"blockId": "nope", "start": 0, "end": 3}, {"blockId": p["id"], "start": 0, "end": 3, "color": "red;"}):
        r = client.post(f"/api/books/{book}/annotations", headers=H, json={"kind": "highlight", **body})
        assert r.status_code == 400, body


def test_search(client, book):
    r = client.get(f"/api/books/{book}/search", params={"q": "miller"}).json()
    assert r["total"] >= 1 and "\x02" in r["results"][0]["snippet"]
    assert client.get(f"/api/books/{book}/search", params={"q": '"); DROP TABLE books; --'}).status_code == 200


def test_backup_and_restore_into_a_fresh_library(client, app, book, tmp_path):
    p = first_paragraph(client, book)
    client.post(f"/api/books/{book}/annotations", headers=H,
                json={"kind": "highlight", "blockId": p["id"], "start": 3, "end": 25, "color": "pink", "note": "n1"})
    backup = client.get("/api/backup.json").json()
    assert backup["format"] == "proseway-backup" and len(backup["books"][0]["annotations"]) == 1

    app2 = create_app(AppConfig(tmp_path / "lib2", 8765), start_jobs=False)
    with TestClient(app2, base_url=BASE) as c2:
        # Restore before the book exists: notes wait for the matching PDF.
        r = c2.post("/api/restore", headers=H, files={"file": ("b.json", json.dumps(backup), "application/json")})
        assert r.json()["result"]["books_waiting"] == 1
        book2 = import_and_convert(c2, app2, tmp_path / "novel.pdf")
        anns = c2.get(f"/api/books/{book2}/annotations").json()["annotations"]
        assert len(anns) == 1 and anns[0]["note"] == "n1" and anns[0]["exact"] == p["text"][3:25]
        assert not anns[0]["orphaned"]
        # Restoring again is idempotent.
        r = c2.post("/api/restore", headers=H, files={"file": ("b.json", json.dumps(backup), "application/json")})
        assert r.json()["result"]["annotations_added"] == 0


def test_restore_rejects_bad_files(client):
    for payload in ("not json", json.dumps({"format": "other"}),
                    json.dumps({"format": "proseway-backup", "version": 1, "books": [{"sha256": "../../x"}]})):
        r = client.post("/api/restore", headers=H, files={"file": ("b.json", payload, "application/json")})
        assert r.status_code == 400


def test_delete_keeps_notes_and_reimport_restores_them(client, app, book, tmp_path):
    p = first_paragraph(client, book)
    client.post(f"/api/books/{book}/annotations", headers=H,
                json={"kind": "highlight", "blockId": p["id"], "start": 0, "end": 10})
    assert client.delete(f"/api/books/{book}", headers=H).status_code == 200
    assert client.get("/api/books").json()["books"] == []
    again = import_and_convert(client, app, tmp_path / "novel.pdf")
    assert len(client.get(f"/api/books/{again}/annotations").json()["annotations"]) == 1


def test_reconversion_keeps_highlights(client, app, book):
    p = first_paragraph(client, book)
    a = client.post(f"/api/books/{book}/annotations", headers=H,
                    json={"kind": "highlight", "blockId": p["id"], "start": 10, "end": 40}).json()["annotation"]
    # Simulate a pipeline change that alters block ids: corrupt the stored id.
    with app.state.db.connect() as c:
        c.execute("UPDATE annotations SET block_id='stale' WHERE id=?", (a["id"],))
    run_conversion(str(app.state.paths.db), str(app.state.paths.root), book)
    after = client.get(f"/api/books/{book}/annotations").json()["annotations"][0]
    assert after["blockId"] == p["id"] and after["exact"] == a["exact"] and not after["orphaned"]


def test_epub_export_is_valid(client, book):
    r = client.get(f"/api/books/{book}/export.epub")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert names[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype") == b"application/epub+zip"
    for n in names:
        if n.endswith((".xhtml", ".opf", ".xml")):
            ElementTree.fromstring(z.read(n))  # well-formed XML
    assert any("Chapter One" in z.read(n).decode() for n in names if n.endswith(".xhtml"))


# ------------------------------------------------------------------ security


def test_requests_with_foreign_host_are_refused(client):
    assert client.get("/api/books", headers={"Host": "evil.example:8765"}).status_code == 421


def test_writes_need_the_csrf_header(client, book):
    p = first_paragraph(client, book)
    body = {"kind": "highlight", "blockId": p["id"], "start": 0, "end": 5}
    assert client.post(f"/api/books/{book}/annotations", json=body).status_code == 403
    r = client.post(f"/api/books/{book}/annotations", json=body, headers={**H, "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_asset_names_cannot_traverse(client, book):
    for name in ("..%2F..%2Fproseway.sqlite3", "..\\..\\x.jpg", "a/b.jpg"):
        assert client.get(f"/api/books/{book}/assets/{name}").status_code == 404


def test_security_headers(client):
    r = client.get("/api/info")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.fixture
def lan(app, monkeypatch):
    """Pretend requests arrive on the LAN listener (192.168.1.20:8765)."""
    s = app.state.sharing
    s.state.enabled = True
    s.state.address, s.state.port = "192.168.1.20", 8765
    s.new_pairing()
    monkeypatch.setattr(s, "is_lan_request", lambda server: True)
    with TestClient(app, base_url="http://192.168.1.20:8765") as c:
        yield c, s


def test_lan_requires_pairing(book, lan):
    c, _s = lan
    assert c.get("/api/books").status_code == 401
    assert c.get("/api/session").json() == {"listener": "lan", "paired": False}


def test_lan_pairing_flow_and_local_only_endpoints(book, lan):
    c, s = lan
    bad = c.post("/api/pair", headers=H, json={"secret": "000000" if s.state.pairing.code != "000000" else "111111"})
    assert bad.status_code == 403
    code = s.state.pairing.code
    r = c.post("/api/pair", headers=H, json={"secret": code})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=strict" in cookie.lower()
    # Paired phone can read and annotate.
    assert c.get("/api/books").status_code == 200
    p = first_paragraph(c, book)
    assert c.post(f"/api/books/{book}/annotations", headers=H,
                  json={"kind": "highlight", "blockId": p["id"], "start": 0, "end": 5}).status_code == 200
    # ...but can't manage the library or sharing.
    assert c.delete(f"/api/books/{book}", headers=H).status_code == 403
    assert c.post("/api/sharing", headers=H, json={"enabled": False}).status_code == 403
    assert c.get("/api/backup.json").status_code == 403
    # The code is single-use.
    c2 = TestClient(c.app, base_url="http://192.168.1.20:8765")
    assert c2.post("/api/pair", headers=H, json={"secret": code}).status_code == 403


def test_lan_wrong_host_and_lockout(book, lan):
    c, s = lan
    assert c.get("/api/session", headers={"Host": "attacker.example"}).status_code == 421
    for _ in range(8):
        c.post("/api/pair", headers=H, json={"secret": "999999" if s.state.pairing.code != "999999" else "888888"})
    assert s.state.locked
    assert c.post("/api/pair", headers=H, json={"secret": s.state.pairing.code}).status_code == 403


def test_revoked_device_loses_access(book, lan):
    c, s = lan
    c.post("/api/pair", headers=H, json={"secret": s.state.pairing.code})
    assert c.get("/api/books").status_code == 200
    for d in s.devices():
        s.revoke(d["id"])
    assert c.get("/api/books").status_code == 401

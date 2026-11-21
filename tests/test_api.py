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
    wrong = "999999" if s.state.pairing.code != "999999" else "888888"
    for _ in range(8):
        c.post("/api/pair", headers=H, json={"secret": wrong})
    # This device is now locked out, even with the right code...
    assert c.post("/api/pair", headers=H, json={"secret": s.state.pairing.code}).status_code == 403
    # ...but one guessing device can't lock everyone else out.
    assert not s.state.locked
    assert s.pair(s.state.pairing.code, "Phone", client="192.168.1.50") is not None


def test_global_pairing_lock(lan):
    _c, s = lan
    wrong = "999999" if s.state.pairing.code != "999999" else "888888"
    for i in range(30):
        s.pair(wrong, "x", client=f"10.0.0.{i}")
    assert s.state.locked
    assert s.pair(s.state.pairing.code, "Phone", client="10.0.0.200") is None


def test_pairing_rejects_odd_input_without_crashing(book, lan):
    c, _s = lan
    for secret in ("é" * 6, "", "\x00" * 6, 123456):
        assert c.post("/api/pair", headers=H, json={"secret": secret}).status_code == 403


def test_revoked_device_loses_access(book, lan):
    c, s = lan
    c.post("/api/pair", headers=H, json={"secret": s.state.pairing.code})
    assert c.get("/api/books").status_code == 200
    for d in s.devices():
        s.revoke(d["id"])
    assert c.get("/api/books").status_code == 401


def test_restore_rejects_bad_fields_without_partial_writes(client, book):
    p = first_paragraph(client, book)
    good = client.get("/api/backup.json").json()
    sha = good["books"][0]["sha256"]
    ann = {"id": "a" * 32, "kind": "highlight", "block_id": p["id"], "start": 0, "end": 5,
           "exact": p["text"][:5], "created_at": 1.0, "updated_at": 2.0, "color": "yellow"}
    for bad in ({"updated_at": "yesterday"}, {"color": "red;"}, {"group_id": "../x"}, {"start": True}):
        payload = {"format": "proseway-backup", "version": 1,
                   "books": [{"sha256": sha, "annotations": [ann]},
                             {"sha256": sha, "annotations": [{**ann, "id": "b" * 32, **bad}]}]}
        r = client.post("/api/restore", headers=H, files={"file": ("b.json", json.dumps(payload), "application/json")})
        assert r.status_code == 400, bad
    # Nothing from the rejected files was written.
    assert client.get(f"/api/books/{book}/annotations").json()["annotations"] == []


def test_epub_strips_xml_invalid_characters(client, app, book):
    with app.state.db.connect() as c:
        c.execute("UPDATE books SET title=? WHERE id=?", ("Bad\x18Title\x01", book))
        c.execute("UPDATE blocks SET text=text || ? WHERE book_id=? AND seq=1", ("\x18\x0b", book))
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/books/{book}/export.epub").content))
    for n in z.namelist():
        if n.endswith((".xhtml", ".opf")):
            ElementTree.fromstring(z.read(n))


def test_skipped_page_is_visible_not_silent(app, tmp_path):
    from proseway.pipeline import layout

    pages = [
        {"n": 1, "w": 612, "h": 792, "lines": [{"t": "First page text.", "x0": 72, "x1": 300, "top": 100, "bot": 111,
                                                 "sz": 11, "font": "Times", "b": False, "i": False, "m": False,
                                                 "mt": 0, "sp": []}], "images": [], "tables": []},
        {"n": 2, "w": 612, "h": 792, "lines": [], "images": [], "tables": [], "failed": True},
    ]
    result = layout.assemble(pages)
    assert [b.type for b in result["blocks"]][-1] == "page_image"
    assert result["blocks"][-1].data == {"failed": True}
    assert result["stats"]["failed_pages"] == [2]


# ------------------------------------------------------------------ body size limits


def chunked(data: bytes, size: int = 64 * 1024):
    """A request body with no Content-Length (sent as Transfer-Encoding: chunked)."""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def multipart(field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "proseway-test-boundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def test_chunked_upload_over_the_limit_is_refused(client, app, monkeypatch):
    from proseway import library
    from proseway import server as server_mod

    monkeypatch.setattr(library, "MAX_UPLOAD_BYTES", 4096)
    monkeypatch.setattr(server_mod, "UPLOAD_SLACK", 1024)
    body, ctype = multipart("files", "big.pdf", b"%PDF-1.4\n" + b"x" * 200_000)
    r = client.post("/api/books", content=chunked(body), headers={**H, "Content-Type": ctype})
    assert "content-length" not in {k.lower() for k in r.request.headers}
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
    assert r.headers["x-content-type-options"] == "nosniff"  # still gets the security headers
    assert client.get("/api/books").json()["books"] == []
    # The same upload with a declared length is refused before anything is read.
    assert client.post("/api/books", content=body, headers={**H, "Content-Type": ctype}).status_code == 413


def test_chunked_restore_over_the_limit_is_refused(client, monkeypatch):
    from proseway import server as server_mod

    monkeypatch.setattr(server_mod, "RESTORE_LIMIT", 1000)
    body, ctype = multipart("file", "b.json", b"[" + b" " * (2**20 + 5000) + b"]")
    r = client.post("/api/restore", content=chunked(body), headers={**H, "Content-Type": ctype})
    # "too_large" comes from the body limit, before the multipart parser spooled it all.
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_small_chunked_bodies_still_work(client, book):
    p = first_paragraph(client, book)
    data = json.dumps({"kind": "highlight", "blockId": p["id"], "start": 0, "end": 4}).encode()
    r = client.post(f"/api/books/{book}/annotations", content=chunked(data, 7),
                    headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text


def test_bad_content_length_is_refused(client):
    r = client.post("/api/sharing", content=b"{}", headers={**H, "Content-Length": "abc",
                                                            "Content-Type": "application/json"})
    assert r.status_code == 400


def test_paired_phone_json_is_capped(book, lan):
    c, s = lan
    assert c.post("/api/pair", headers=H, json={"secret": s.state.pairing.code}).status_code == 200
    p = first_paragraph(c, book)
    huge = json.dumps({"kind": "highlight", "blockId": p["id"], "start": 0, "end": 4,
                       "note": "n" * (2 * 2**20)}).encode()
    hj = {**H, "Content-Type": "application/json"}
    assert c.post(f"/api/books/{book}/annotations", content=huge, headers=hj).status_code == 413
    assert c.post(f"/api/books/{book}/annotations", content=chunked(huge), headers=hj).status_code == 413
    # A long note within reason still works from the phone.
    ok = json.dumps({"kind": "highlight", "blockId": p["id"], "start": 0, "end": 4, "note": "n" * 20000})
    assert c.post(f"/api/books/{book}/annotations", content=ok, headers=hj).status_code == 200


# ------------------------------------------------------------------ EPUB language


def _opf(client, book) -> str:
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/books/{book}/export.epub").content))
    return z.read("OEBPS/content.opf").decode(), z.read("OEBPS/ch0000.xhtml").decode()


def test_epub_language_is_und_without_pdf_metadata(client, book):
    opf, chapter = _opf(client, book)
    assert "<dc:language>und</dc:language>" in opf
    assert 'xml:lang="und"' in chapter


def test_epub_language_comes_from_the_pdf(client, app, tmp_path):
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    src, pdf = tmp_path / "plain.pdf", tmp_path / "roman.pdf"
    pdfgen.make_novel(src, pages=2)
    doc = pdfium.PdfDocument(str(src))
    lang = ctypes.create_string_buffer("de-AT\x00".encode("utf-16-le"))
    assert pdfium_c.FPDFCatalog_SetLanguage(doc.raw, ctypes.cast(lang, ctypes.POINTER(ctypes.c_ushort)))
    doc.save(str(pdf))
    doc.close()
    book = import_and_convert(client, app, pdf)
    opf, chapter = _opf(client, book)
    assert "<dc:language>de-AT</dc:language>" in opf
    assert 'lang="de-AT"' in chapter

"""HTTP API and static web app."""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import __version__, epub, export, library
from . import sharing as sharing_mod
from .anchoring import make_anchor
from .db import Database, now
from .jobs import JobManager
from .paths import DataPaths
from .pipeline import errors, ocr
from .sharing import COOKIE_MAX_AGE, COOKIE_NAME, SharingManager

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
ASSET_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}\.(?:jpg|png)$")
RESTORE_LIMIT = 50 * 2**20
UPLOAD_SLACK = 10 * 2**20  # multipart framing around the file(s)
LOCAL_BODY_LIMIT = 20 * 2**20
LAN_BODY_LIMIT = 2**20  # a phone only sends small JSON: annotations, notes, positions
COLORS = {"yellow", "green", "blue", "pink", "purple"}

# What a paired phone may do. Everything else is local-only.
LAN_ALLOWED = [
    ("GET", re.compile(r"^/api/(info|books)$")),
    ("GET", re.compile(r"^/api/books/[0-9a-f]{32}(/(manifest|cover|annotations|position|search|export\.md|export\.epub))?$")),
    ("GET", re.compile(r"^/api/books/[0-9a-f]{32}/chapters/\d+$")),
    ("GET", re.compile(r"^/api/books/[0-9a-f]{32}/assets/[A-Za-z0-9._-]+$")),
    ("POST", re.compile(r"^/api/books/[0-9a-f]{32}/annotations$")),
    ("PATCH", re.compile(r"^/api/annotations/[0-9a-f]{32}$")),
    ("DELETE", re.compile(r"^/api/annotations/[0-9a-f]{32}$")),
    ("PUT", re.compile(r"^/api/books/[0-9a-f]{32}/position$")),
]
LAN_PUBLIC = [("POST", re.compile(r"^/api/pair$")), ("GET", re.compile(r"^/api/session$"))]

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class AppConfig:
    def __init__(self, data_dir: Path, port: int = 8765):
        self.paths = DataPaths(data_dir).ensure()
        self.port = port


def _static_dir() -> Path | None:
    try:
        d = Path(str(resources.files("proseway") / "static"))
    except Exception:
        return None
    return d if (d / "index.html").exists() else None


def _error(status: int, message: str, code: str = "error") -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def body_limit(path: str, is_lan: bool) -> int:
    if is_lan:
        return LAN_BODY_LIMIT
    if path == "/api/books":
        return library.MAX_UPLOAD_BYTES + UPLOAD_SLACK
    if path == "/api/restore":
        return RESTORE_LIMIT + 2**20
    return LOCAL_BODY_LIMIT


class BodyLimit:
    """Refuse request bodies over the limit, whether or not they declare a Content-Length.

    A declared length over the limit is refused before reading anything. Chunked bodies are
    counted as they arrive; once one goes over, the app sees a disconnect and the client gets
    a 413, so a multipart parser never spools more than the limit to disk.
    """

    def __init__(self, app, is_lan):
        self.app = app
        self.is_lan = is_lan

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return
        limit = body_limit(scope["path"], self.is_lan(scope))
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            if not declared.isdigit():
                await _error(400, "Bad Content-Length.", "bad_request")(scope, receive, send)
                return
            if int(declared) > limit:
                await _error(413, "That's too large.", "too_large")(scope, receive, send)
                return

        received = 0
        started = refused = False

        async def counted_receive():
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    refused = True
                    if not started:
                        await _error(413, "That's too large.", "too_large")(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal started
            if refused:
                return  # we already answered 413
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except Exception:
            if not refused:
                raise
            # The app gave up reading (ClientDisconnect or similar); the 413 is already sent.


def create_app(config: AppConfig, start_jobs: bool = True) -> FastAPI:
    paths = config.paths
    db = Database(paths.db).init()
    jobs = JobManager(db, paths)
    sharing = SharingManager(db, cert_dir=paths.root / "certs")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_jobs:
            jobs.start()
        yield
        sharing.disable()
        jobs.shutdown()

    app = FastAPI(title="Proseway", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.db = db
    app.state.paths = paths
    app.state.jobs = jobs
    app.state.sharing = sharing
    app.state.port = config.port
    sharing.app = app

    # ------------------------------------------------------------------ security

    # Added first, so it runs inside `guard` (Host and CSRF checks come first, and its 413s
    # still get the security headers).
    app.add_middleware(BodyLimit, is_lan=lambda scope: sharing.is_lan_request(scope))

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host", "")
        path = request.url.path
        method = request.method
        is_lan = sharing.is_lan_request(request.scope)
        request.state.is_lan = is_lan
        request.state.device = None

        if is_lan:
            if not sharing.lan_host_ok(host):
                return _error(421, "Unexpected host.", "bad_host")
            if path.startswith("/api/"):
                public = any(m == method and rx.match(path) for m, rx in LAN_PUBLIC)
                if not public:
                    device = sharing.check_device(request.cookies.get(COOKIE_NAME))
                    if device is None:
                        return _error(401, "This device isn't paired yet.", "not_paired")
                    if not any(m == method and rx.match(path) for m, rx in LAN_ALLOWED):
                        return _error(403, "That can only be done on the computer running Proseway.", "local_only")
                    request.state.device = device
        else:
            hostname = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
            if hostname.lower() not in LOCAL_HOSTS:
                # Blocks DNS-rebinding attacks against the local listener.
                return _error(421, "Unexpected host.", "bad_host")

        if path.startswith("/api/") and method in ("POST", "PUT", "PATCH", "DELETE"):
            # CSRF: browsers can't send this header cross-origin without a CORS preflight,
            # and we never answer preflights.
            if request.headers.get("x-proseway") != "1":
                return _error(403, "Missing request header.", "csrf")
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1].lower() != host.lower():
                return _error(403, "Cross-origin request refused.", "csrf")
            # Body size limits: see BodyLimit.

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # ------------------------------------------------------------------ helpers

    def get_book(book_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", book_id):
            raise HTTPException(404, "No such book.")
        with db.connect() as c:
            row = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such book.")
        return row

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return _error(exc.status_code, str(exc.detail))

    # ------------------------------------------------------------------ info

    @app.get("/api/info")
    def info(request: Request) -> dict[str, Any]:
        return {
            "version": __version__,
            "ocrAvailable": ocr.available(),
            "listener": "lan" if request.state.is_lan else "local",
            "sharing": sharing.state.enabled,
        }

    @app.get("/api/session")
    def session(request: Request) -> dict[str, Any]:
        paired = bool(sharing.check_device(request.cookies.get(COOKIE_NAME))) if request.state.is_lan else True
        return {"listener": "lan" if request.state.is_lan else "local", "paired": paired}

    # ------------------------------------------------------------------ books

    @app.get("/api/books")
    def list_books() -> dict[str, Any]:
        with db.connect() as c:
            rows = c.execute(
                "SELECT b.*, p.progress AS progress FROM books b LEFT JOIN positions p ON p.book_id=b.id "
                "ORDER BY COALESCE(b.last_opened_at, b.created_at) DESC"
            ).fetchall()
            counts = {r["book_id"]: r["n"] for r in c.execute(
                "SELECT book_id, COUNT(*) AS n FROM annotations WHERE kind='highlight' GROUP BY book_id")}
        books = []
        for r in rows:
            b = library.book_public(r)
            b["progress"] = r["progress"] or 0
            b["highlights"] = counts.get(r["id"], 0)
            books.append(b)
        return {"books": books}

    @app.post("/api/books")
    def import_books(files: list[UploadFile]) -> dict[str, Any]:
        results = []
        for f in files:
            name = f.filename or "book.pdf"
            try:
                tmp, sha, size = library.save_upload(paths, f.file)
            except library.UploadTooLarge:
                results.append({"fileName": name, "error": {"code": "too_large", "message": "That file is larger than 1 GB."}})
                continue
            except errors.ConversionError as exc:
                results.append({"fileName": name, "error": {"code": exc.code, "message": exc.message}})
                continue
            book_id, created = library.create_book(db, paths, tmp, sha, size, name)
            if created:
                library.reattach_annotations(db, paths, book_id, sha)
                jobs.enqueue(book_id)
            results.append({"fileName": name, "bookId": book_id, "duplicate": not created})
        return {"results": results}

    @app.get("/api/books/{book_id}")
    def book_detail(book_id: str) -> dict[str, Any]:
        b = library.book_public(get_book(book_id))
        return {"book": b}

    @app.patch("/api/books/{book_id}")
    def edit_book(book_id: str, body: dict = Body(...)) -> dict[str, Any]:
        get_book(book_id)
        fields = {}
        for key in ("title", "author"):
            if key in body:
                val = str(body[key]).strip()[:300]
                if key == "title" and not val:
                    raise HTTPException(400, "A title can't be empty.")
                fields[key] = val
        if fields:
            with db.connect() as c:
                c.execute(f"UPDATE books SET {', '.join(k + '=?' for k in fields)}, updated_at=? WHERE id=?",  # noqa: S608
                          (*fields.values(), now(), book_id))
        return book_detail(book_id)

    @app.delete("/api/books/{book_id}")
    def remove_book(book_id: str) -> dict[str, Any]:
        get_book(book_id)
        jobs.cancel(book_id)
        library.delete_book(db, paths, book_id)
        return {"ok": True}

    @app.post("/api/books/{book_id}/cancel")
    def cancel(book_id: str) -> dict[str, Any]:
        get_book(book_id)
        jobs.cancel(book_id)
        return book_detail(book_id)

    @app.post("/api/books/{book_id}/resume")
    def resume(book_id: str) -> dict[str, Any]:
        b = get_book(book_id)
        if b["status"] in ("paused", "cancelled", "error", "queued"):
            jobs.enqueue(book_id)
        return book_detail(book_id)

    @app.post("/api/books/{book_id}/reconvert")
    def reconvert(book_id: str) -> dict[str, Any]:
        get_book(book_id)
        jobs.reconvert(book_id)
        return book_detail(book_id)

    @app.get("/api/books/{book_id}/cover")
    def cover(book_id: str):
        get_book(book_id)
        f = paths.book_dir(book_id) / "cover.jpg"
        if not f.exists():
            raise HTTPException(404, "No cover.")
        return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/books/{book_id}/assets/{name}")
    def asset(book_id: str, name: str):
        get_book(book_id)
        if not ASSET_NAME.fullmatch(name):
            raise HTTPException(404, "Not found.")
        f = paths.assets_dir(book_id) / name
        if not f.is_file():
            raise HTTPException(404, "Not found.")
        media = "image/png" if name.endswith(".png") else "image/jpeg"
        return FileResponse(f, media_type=media, headers={"Cache-Control": "max-age=604800, immutable"})

    # ------------------------------------------------------------------ content

    @app.get("/api/books/{book_id}/manifest")
    def manifest(book_id: str) -> dict[str, Any]:
        b = get_book(book_id)
        with db.connect() as c:
            chapters = [
                dict(r) for r in c.execute(
                    "SELECT chapter AS idx, MIN(seq) AS firstSeq, COUNT(*) AS blocks, MIN(page) AS startPage, "
                    "MAX(page) AS endPage, SUM(LENGTH(text)) AS chars FROM blocks WHERE book_id=? GROUP BY chapter "
                    "ORDER BY chapter", (book_id,))
            ]
            c.execute("UPDATE books SET last_opened_at=? WHERE id=?", (now(), book_id))
        toc = json.loads(b["toc_json"] or "[]")
        return {
            "book": library.book_public(b),
            "toc": toc,
            "chapters": chapters,
            "totalBlocks": sum(ch["blocks"] for ch in chapters),
            "totalChars": sum(ch["chars"] or 0 for ch in chapters),
            "stats": json.loads(b["stats_json"] or "{}"),
        }

    @app.get("/api/books/{book_id}/chapters/{index}")
    def chapter(book_id: str, index: int) -> dict[str, Any]:
        get_book(book_id)
        with db.connect() as c:
            rows = c.execute(
                "SELECT seq, id, type, page, level, text, data_json FROM blocks WHERE book_id=? AND chapter=? ORDER BY seq",
                (book_id, index),
            ).fetchall()
        if not rows:
            raise HTTPException(404, "No such chapter.")
        return {
            "index": index,
            "blocks": [
                {"seq": r["seq"], "id": r["id"], "type": r["type"], "page": r["page"], "level": r["level"],
                 "text": r["text"], "data": json.loads(r["data_json"])}
                for r in rows
            ],
        }

    @app.get("/api/books/{book_id}/search")
    def search(book_id: str, q: str = "", limit: int = 50) -> dict[str, Any]:
        get_book(book_id)
        tokens = re.findall(r"\w+", q, flags=re.UNICODE)[:12]
        if not tokens:
            return {"results": [], "total": 0}
        fts = " ".join(f'"{t}"' for t in tokens[:-1]) + (" " if len(tokens) > 1 else "") + f'"{tokens[-1]}"*'
        limit = max(1, min(limit, 200))
        with db.connect() as c:
            rows = c.execute(
                "SELECT f.block_id AS id, snippet(blocks_fts, 0, char(2), char(3), '…', 14) AS snip, "
                "b.seq, b.page, b.chapter, b.type FROM blocks_fts f JOIN blocks b "
                "ON b.book_id=f.book_id AND b.id=f.block_id WHERE blocks_fts MATCH ? AND f.book_id=? "
                "ORDER BY b.seq LIMIT ?",
                (fts, book_id, limit),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) AS n FROM blocks_fts WHERE blocks_fts MATCH ? AND book_id=?",
                              (fts, book_id)).fetchone()["n"]
        return {
            "results": [{"blockId": r["id"], "seq": r["seq"], "page": r["page"], "chapter": r["chapter"],
                         "type": r["type"], "snippet": r["snip"]} for r in rows],
            "total": total,
        }

    # ------------------------------------------------------------------ annotations

    def ann_public(r) -> dict[str, Any]:
        return {
            "id": r["id"], "kind": r["kind"], "color": r["color"], "groupId": r["group_id"],
            "blockId": r["block_id"], "start": r["start"], "end": r["end"], "exact": r["exact"],
            "note": r["note"], "page": r["page"], "seq": r["seq"], "orphaned": bool(r["orphaned"]),
            "createdAt": r["created_at"], "updatedAt": r["updated_at"],
        }

    @app.get("/api/books/{book_id}/annotations")
    def list_annotations(book_id: str) -> dict[str, Any]:
        get_book(book_id)
        with db.connect() as c:
            rows = c.execute("SELECT * FROM annotations WHERE book_id=? ORDER BY COALESCE(seq,0), start",
                             (book_id,)).fetchall()
        return {"annotations": [ann_public(r) for r in rows]}

    @app.post("/api/books/{book_id}/annotations")
    def create_annotation(book_id: str, body: dict = Body(...)) -> dict[str, Any]:
        get_book(book_id)
        kind = body.get("kind", "highlight")
        if kind not in ("highlight", "bookmark"):
            raise HTTPException(400, "Unknown annotation kind.")
        block_id = str(body.get("blockId", ""))[:64]
        with db.connect() as c:
            blk = c.execute("SELECT seq, page, text FROM blocks WHERE book_id=? AND id=?", (book_id, block_id)).fetchone()
        if blk is None:
            raise HTTPException(400, "That passage isn't in this book.")
        try:
            start, end = int(body.get("start", 0)), int(body.get("end", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "Bad range.") from exc
        if kind == "highlight":
            if not (0 <= start < end <= len(blk["text"])):
                raise HTTPException(400, "Bad range.")
            anchor = make_anchor(block_id, blk["text"], start, end)
        else:
            anchor = make_anchor(block_id, blk["text"], 0, 0)
            anchor.exact = blk["text"][:120]
        color = body.get("color") or ("yellow" if kind == "highlight" else None)
        if color is not None and color not in COLORS:
            raise HTTPException(400, "Unknown color.")
        note = str(body.get("note", ""))[:20000]
        group_id = body.get("groupId")
        if group_id is not None and not re.fullmatch(r"[0-9a-f]{32}", str(group_id)):
            raise HTTPException(400, "Bad group.")
        aid = uuid.uuid4().hex
        t = now()
        with db.connect() as c:
            c.execute(
                "INSERT INTO annotations(id, book_id, kind, color, group_id, block_id, start, end, exact, prefix, "
                "suffix, note, page, seq, orphaned, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (aid, book_id, kind, color, group_id, block_id, anchor.start, anchor.end, anchor.exact,
                 anchor.prefix, anchor.suffix, note, blk["page"], blk["seq"], t, t),
            )
            row = c.execute("SELECT * FROM annotations WHERE id=?", (aid,)).fetchone()
        return {"annotation": ann_public(row)}

    def get_ann(aid: str):
        if not re.fullmatch(r"[0-9a-f]{32}", aid):
            raise HTTPException(404, "Not found.")
        with db.connect() as c:
            row = c.execute("SELECT * FROM annotations WHERE id=?", (aid,)).fetchone()
        if row is None:
            raise HTTPException(404, "Not found.")
        return row

    @app.patch("/api/annotations/{aid}")
    def update_annotation(aid: str, body: dict = Body(...)) -> dict[str, Any]:
        get_ann(aid)
        fields: dict[str, Any] = {}
        if "color" in body:
            if body["color"] not in COLORS:
                raise HTTPException(400, "Unknown color.")
            fields["color"] = body["color"]
        if "note" in body:
            fields["note"] = str(body["note"])[:20000]
        if fields:
            fields["updated_at"] = now()
            with db.connect() as c:
                c.execute(f"UPDATE annotations SET {', '.join(k + '=?' for k in fields)} WHERE id=?",  # noqa: S608
                          (*fields.values(), aid))
                if "color" in fields:
                    grp = c.execute("SELECT group_id FROM annotations WHERE id=?", (aid,)).fetchone()["group_id"]
                    if grp:
                        c.execute("UPDATE annotations SET color=?, updated_at=? WHERE group_id=?",
                                  (fields["color"], fields["updated_at"], grp))
        return {"annotation": ann_public(get_ann(aid))}

    @app.delete("/api/annotations/{aid}")
    def delete_annotation(aid: str) -> dict[str, Any]:
        row = get_ann(aid)
        with db.connect() as c:
            if row["group_id"]:
                c.execute("DELETE FROM annotations WHERE group_id=?", (row["group_id"],))
            else:
                c.execute("DELETE FROM annotations WHERE id=?", (aid,))
        return {"ok": True}

    # ------------------------------------------------------------------ reading position

    @app.get("/api/books/{book_id}/position")
    def get_position(book_id: str) -> dict[str, Any]:
        get_book(book_id)
        with db.connect() as c:
            row = c.execute("SELECT * FROM positions WHERE book_id=?", (book_id,)).fetchone()
        return {"position": {"blockId": row["block_id"], "seq": row["seq"], "progress": row["progress"],
                             "updatedAt": row["updated_at"]} if row else None}

    @app.put("/api/books/{book_id}/position")
    def put_position(book_id: str, body: dict = Body(...)) -> dict[str, Any]:
        get_book(book_id)
        block_id = str(body.get("blockId", ""))[:64]
        with db.connect() as c:
            blk = c.execute("SELECT seq FROM blocks WHERE book_id=? AND id=?", (book_id, block_id)).fetchone()
            if blk is None:
                raise HTTPException(400, "Unknown position.")
            progress = max(0.0, min(1.0, float(body.get("progress", 0) or 0)))
            c.execute("INSERT OR REPLACE INTO positions(book_id, block_id, seq, progress, updated_at) VALUES (?,?,?,?,?)",
                      (book_id, block_id, blk["seq"], progress, now()))
        return {"ok": True}

    # ------------------------------------------------------------------ export / backup

    @app.get("/api/books/{book_id}/export.md")
    def export_md(book_id: str):
        b = get_book(book_id)
        md = export.markdown_for_book(db, book_id)
        name = _safe_filename(library.book_public(b)["title"]) + " - notes.md"
        return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": _attachment(name)})

    @app.get("/api/books/{book_id}/export.epub")
    def export_epub(book_id: str):
        b = get_book(book_id)
        if b["status"] != "ready":
            raise HTTPException(409, "This book hasn't finished converting yet.")
        data = epub.build_epub(db, paths, book_id)
        name = _safe_filename(library.book_public(b)["title"]) + ".epub"
        return Response(data, media_type="application/epub+zip", headers={"Content-Disposition": _attachment(name)})

    @app.get("/api/backup.json")
    def backup():
        data = export.build_backup(db)
        stamp = __import__("datetime").date.today().isoformat()
        return Response(json.dumps(data, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": _attachment(f"proseway-backup-{stamp}.json")})

    @app.post("/api/restore")
    async def restore(file: UploadFile) -> dict[str, Any]:
        raw = await file.read(RESTORE_LIMIT + 1)
        if len(raw) > RESTORE_LIMIT:
            raise HTTPException(413, "That backup is too large.")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "That file isn't valid JSON.") from exc
        try:
            return {"result": export.restore_backup(db, paths, data)}
        except export.BackupError as exc:
            raise HTTPException(400, f"Couldn't restore this backup: {exc}") from exc

    # ------------------------------------------------------------------ sharing

    @app.get("/api/sharing")
    def sharing_state() -> dict[str, Any]:
        return sharing.public_state()

    @app.post("/api/sharing")
    def sharing_set(body: dict = Body(...)) -> dict[str, Any]:
        if body.get("enabled"):
            addrs = [a["address"] for a in sharing.public_state()["addresses"]]
            address = body.get("address") or (addrs[0] if addrs else "")
            if not address:
                raise HTTPException(400, "This computer doesn't seem to be on a local network.")
            try:
                minutes = int(body.get("minutes") or 120)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "Choose how long sharing should stay on.") from exc
            try:
                sharing.enable(address, app.state.port, minutes=min(max(minutes, 5), 24 * 60),
                               secure=bool(body.get("secure")))
            except (ValueError, OSError) as exc:
                raise HTTPException(400, str(exc)) from exc
        else:
            sharing.disable()
        return sharing.public_state()

    @app.post("/api/sharing/new-code")
    def sharing_new_code() -> dict[str, Any]:
        if sharing.state.enabled:
            sharing.new_pairing()
        return sharing.public_state()

    @app.get("/api/sharing/ca.crt")
    def sharing_ca():
        # Local only (not in LAN_ALLOWED): for sending the certificate to a phone some other
        # way, such as AirDrop or a USB cable, instead of the plain-HTTP setup page.
        return Response(sharing.ca_der(), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": _attachment(sharing_mod.CA_DOWNLOAD_NAME)})

    @app.get("/api/sharing/qr.svg")
    def sharing_qr(target: str = "pair"):
        import segno

        if target == "setup":
            if not sharing.setup_url():
                raise HTTPException(404, "There's no setup page right now.")
            content = sharing.setup_url()
        else:
            p = sharing.current_pairing()
            if p is None:
                raise HTTPException(404, "Sharing is off.")
            content = f"{sharing.url()}/pair#t={p.token}"
        qr = segno.make(content, error="m")
        import io

        buf = io.BytesIO()
        qr.save(buf, kind="svg", scale=6, border=2, dark="#1d1b18", light=None, xmldecl=False, svgns=True)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.delete("/api/devices/{device_id}")
    def revoke_device(device_id: str) -> dict[str, Any]:
        sharing.revoke(device_id)
        return sharing.public_state()

    @app.post("/api/pair")
    def pair(request: Request, body: dict = Body(...)):
        if not request.state.is_lan:
            raise HTTPException(400, "Pairing happens on the phone.")
        ua = request.headers.get("user-agent", "")
        name = _device_name(ua)
        client = request.client.host if request.client else "?"
        token = sharing.pair(str(body.get("secret", ""))[:100], name, client)
        if token is None:
            return _error(403, "That code didn't work. Check the code on your computer, or ask it for a new one.",
                          "bad_code")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE_NAME, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="strict",
                        secure=sharing.state.scheme == "https", path="/")
        return resp

    # ------------------------------------------------------------------ web app

    static = _static_dir()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        if static is None:
            return HTMLResponse(
                "<h1>Proseway</h1><p>The web app hasn't been built. Run <code>pnpm --dir web build</code>, "
                "or use the dev server: <code>pnpm --dir web dev</code>.</p>", status_code=200)
        candidate = (static / full_path).resolve()
        if full_path and candidate.is_file() and static.resolve() in candidate.parents:
            headers = {"Cache-Control": "max-age=31536000, immutable"} if "/assets/" in f"/{full_path}" else {}
            if candidate.name == "sw.js":
                headers = {"Cache-Control": "no-cache"}
            return FileResponse(candidate, headers=headers)
        return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name).strip()
    return (cleaned or "book")[:120]


def _attachment(name: str) -> str:
    from urllib.parse import quote

    ascii_name = name.encode("ascii", "ignore").decode() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _device_name(ua: str) -> str:
    ua_l = ua.lower()
    if "iphone" in ua_l:
        return "iPhone"
    if "ipad" in ua_l:
        return "iPad"
    if "android" in ua_l:
        return "Android phone" if "mobile" in ua_l else "Android tablet"
    if "mac os" in ua_l:
        return "Mac"
    if "windows" in ua_l:
        return "Windows PC"
    return "Device"

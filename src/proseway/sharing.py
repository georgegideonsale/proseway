"""Reading on your phone: an opt-in second listener on the home network, with pairing.

Security model (see docs/decisions/0005-phone-sharing.md):

* Off by default and off again at every launch. While off, Proseway only listens on 127.0.0.1.
* Turning it on binds one extra listener to the chosen private LAN address (never 0.0.0.0).
* A phone must pair first: scan the QR code (one-time token in the URL fragment) or type the
  6-digit code. Pairing gives the phone a random device token in an HttpOnly, SameSite=Strict
  cookie. Only a SHA-256 hash of the token is stored. Tokens issued over HTTPS live in a
  ``__Host-`` cookie and are hashed in their own domain, so a token that ever travelled in
  clear text (plain-HTTP sharing) is never accepted on the HTTPS listener.
* Every API request on the LAN listener needs a valid device cookie, and only reading and
  annotating endpoints are reachable from the LAN at all. Managing sharing, devices, imports,
  deletions and restore are local-only.
* Pairing codes expire after 5 minutes and are single-use. Each device gets 8 wrong guesses per
  5 minutes; after 30 wrong guesses in total, pairing locks until the computer shows a new code.
* Sharing switches itself off after a chosen time (default 2 hours).
* Optionally over HTTPS ("secure connection"), with a certificate from a local CA that the
  user trusts once on the phone (see certs.py). A second, plain-HTTP "setup" listener on the
  next port then serves only that CA certificate and instructions, nothing from the library.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import logging
import secrets
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from . import certs
from .db import Database, now

log = logging.getLogger(__name__)

PAIRING_TTL = 300.0
MAX_FAILURES = 8  # per device (client address) within the window
MAX_GLOBAL_FAILURES = 30  # all devices together, then pairing locks until a new code
FAILURE_WINDOW = 300.0
COOKIE_NAME = "pw_device"  # plain HTTP
SECURE_COOKIE_NAME = "__Host-pw_device"  # HTTPS: browsers enforce Secure, Path=/ and no Domain
COOKIE_MAX_AGE = 180 * 24 * 3600
# TLS 1.2 suites with forward secrecy and AEAD only (TLS 1.3 suites are always on). Without
# this, uvicorn's default cipher string is "TLSv1".
TLS_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20"
CA_DOWNLOAD_NAME = "proseway-ca.crt"
SETUP_BODY_LIMIT = 64 * 1024  # the setup page takes no bodies; small ones are read and dropped


def hash_token(token: str, https: bool = False) -> str:
    """The stored form of a device token. HTTPS tokens are hashed with a prefix, so the two
    kinds can never be mistaken for each other (and plain-HTTP rows stay as they were)."""
    data = ("https:" + token if https else token).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def cookie_name(https: bool) -> str:
    return SECURE_COOKIE_NAME if https else COOKIE_NAME


def lan_addresses() -> list[dict[str, str]]:
    """Private IPv4 addresses of network interfaces that are up."""
    out: list[dict[str, str]] = []
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        st = stats.get(name)
        if st is not None and not st.isup:
            continue
        for a in addrs:
            if a.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.ip_address(a.address)
            except ValueError:
                continue
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                out.append({"interface": name, "address": a.address})
    lowered = [n.lower() for n in ("wi-fi", "wlan", "wireless", "en0", "eth", "ethernet", "en")]

    def rank(entry: dict[str, str]) -> tuple[int, str]:
        n = entry["interface"].lower()
        virtual = any(v in n for v in ("vethernet", "virtual", "vmware", "vbox", "docker", "wsl", "hyper-v", "tailscale", "zerotier"))
        preferred = any(n.startswith(p) or p in n for p in lowered)
        return (2 if virtual else (0 if preferred else 1), entry["address"])

    return sorted(out, key=rank)


@dataclass
class Pairing:
    code: str
    token: str
    expires: float
    used: bool = False


@dataclass
class SharingState:
    enabled: bool = False
    address: str = ""
    port: int = 0
    scheme: str = "http"
    setup_port: int = 0  # plain-HTTP certificate download, only in secure mode
    started_at: float = 0.0
    expires_at: float = 0.0
    pairing: Pairing | None = None
    failures: deque = field(default_factory=deque)
    locked: bool = False


class SharingManager:
    def __init__(self, db: Database, cert_dir: Path | None = None):
        self.db = db
        self.state = SharingState()
        self._lock = threading.RLock()
        self._server = None
        self._thread: threading.Thread | None = None
        self._setup_server = None
        self._setup_thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self.app = None  # set by the server factory
        self.cert_root = cert_dir
        # The certificate the running HTTPS listener presents. The dialog and the setup page
        # show and serve this CA, never whatever is on disk now.
        self.issued: certs.Issued | None = None

    # -- listener control ------------------------------------------------------------

    @staticmethod
    def _start_listener(app, address: str, port: int, name: str, **kwargs):
        import uvicorn

        # lifespan="off": the app's startup/shutdown (job supervisor) belongs to the main
        # listener; extra listeners only serve requests.
        config = uvicorn.Config(app, host=address, port=port, log_level="warning",
                                access_log=False, server_header=False, lifespan="off", **kwargs)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name=name, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            server.should_exit = True
            raise OSError(f"Couldn't listen on {address}:{port}. Is the port in use?")
        return server, thread

    def enable(self, address: str, port: int, minutes: int = 120, secure: bool = False) -> SharingState:
        allowed = {a["address"] for a in lan_addresses()}
        if address not in allowed:
            raise ValueError("That address isn't a private network address of this computer.")
        with self._lock:
            self.disable()
            if not 1 <= port <= 65535:
                raise ValueError("That port number isn't valid.")
            issued = None
            if secure:
                if self.cert_root is None:
                    raise ValueError("Secure connections aren't available here.")
                issued = certs.ensure_server_cert(self.cert_root, address)
            kwargs = {}
            if issued:
                kwargs = {"ssl_certfile": issued.certfile, "ssl_keyfile": issued.keyfile,
                          "ssl_ciphers": TLS_CIPHERS}
            inner = self.app
            https = issued is not None

            async def lan_app(scope, receive, send):
                # Requests on this listener are marked here, so "is this from the network?"
                # and "did it come over HTTPS?" never depend on comparing addresses or on
                # mutable sharing state.
                scope = dict(scope)
                scope["proseway.lan"] = True
                scope["proseway.https"] = https
                await inner(scope, receive, send)

            self._server, self._thread = self._start_listener(lan_app, address, port, "proseway-lan", **kwargs)
            s = self.state
            s.enabled, s.address, s.port = True, address, port
            self.issued = issued
            s.scheme = "https" if issued else "http"
            s.setup_port = 0
            if issued and port + 1 <= 65535:
                # Best effort: without it, the certificate can still be sent from the computer.
                try:
                    self._setup_server, self._setup_thread = self._start_listener(
                        self._setup_app(), address, port + 1, "proseway-setup")
                    s.setup_port = port + 1
                except OSError as exc:
                    log.warning("certificate setup page unavailable: %s", exc)
            s.started_at = now()
            s.expires_at = s.started_at + max(5, minutes) * 60
            s.failures.clear()
            s.locked = False
            self.new_pairing()
            self._timer = threading.Timer(s.expires_at - s.started_at, self.disable)
            self._timer.daemon = True
            self._timer.start()
            log.info("phone sharing on at %s://%s:%s", s.scheme, address, port)
            return s

    def disable(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            was_on = self._server is not None
            for server, thread in ((self._setup_server, self._setup_thread), (self._server, self._thread)):
                if server is not None:
                    server.should_exit = True
                    if thread is not None and thread is not threading.current_thread():
                        thread.join(timeout=5)
            if was_on:
                log.info("phone sharing off")
            self._server = self._setup_server = None
            self._thread = self._setup_thread = None
            self.state.enabled = False
            self.state.setup_port = 0
            self.state.pairing = None
            self.issued = None

    def is_lan_request(self, scope: dict) -> bool:
        return bool(scope.get("proseway.lan"))

    @staticmethod
    def is_https_request(scope: dict) -> bool:
        return bool(scope.get("proseway.https"))

    def device_for(self, scope: dict, cookies: dict[str, str]) -> str | None:
        """The paired device behind a LAN request: only the cookie for this scheme counts."""
        https = self.is_https_request(scope)
        return self.check_device(cookies.get(cookie_name(https)), https=https)

    def lan_host_ok(self, host_header: str) -> bool:
        s = self.state
        return host_header.lower() in {f"{s.address}:{s.port}".lower()}

    def url(self) -> str:
        s = self.state
        return f"{s.scheme}://{s.address}:{s.port}"

    def setup_url(self) -> str:
        s = self.state
        return f"http://{s.address}:{s.setup_port}/" if s.enabled and s.setup_port else ""

    def ca_info(self) -> dict | None:
        issued = self.issued
        return issued.ca_info if issued is not None else None

    def ca_der(self) -> bytes | None:
        issued = self.issued
        return issued.ca_der if issued is not None else None

    # -- the plain-HTTP certificate setup page ------------------------------------------

    def _setup_app(self):
        """A tiny ASGI app for the setup port: the CA certificate and how to trust it. Nothing else.

        It is plain HTTP on purpose: until the phone trusts the CA, it can't open the HTTPS
        listener without a warning. The page shows the certificate's fingerprint so it can be
        compared with what the computer shows.
        """
        manager = self

        async def app(scope, receive, send):
            if scope["type"] != "http":
                return
            s = manager.state
            host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1").lower()
            path, method = scope.get("path", ""), scope.get("method", "")
            status, ctype, body, extra = 404, "text/plain; charset=utf-8", b"Not found.", []
            # Read (and discard) any request body before answering. Closing a connection with
            # unread data makes Windows send a reset instead of the response, so a client that
            # POSTs here would see a connection error rather than the 405.
            received, more = 0, True
            while more and received <= SETUP_BODY_LIMIT:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                received += len(message.get("body", b""))
                more = message.get("more_body", False)
            if received > SETUP_BODY_LIMIT:
                # Not worth reading further; this page never takes a body.
                status, body = 413, b"Too large."
                extra = [(b"connection", b"close")]
            elif host != f"{s.address}:{s.setup_port}".lower():
                status, body = 421, b"Unexpected host."
            elif method not in ("GET", "HEAD"):
                status, body = 405, b"Method not allowed."
            elif path == "/" + CA_DOWNLOAD_NAME and (der := manager.ca_der()):
                status, ctype, body = 200, "application/x-x509-ca-cert", der
                extra = [(b"content-disposition", f'attachment; filename="{CA_DOWNLOAD_NAME}"'.encode())]
            elif path == "/":
                info = manager.ca_info() or {}
                status, ctype = 200, "text/html; charset=utf-8"
                body = SETUP_PAGE.format(
                    fingerprint=html.escape(info.get("fingerprint", "")),
                    name=html.escape(info.get("name", "")),
                    https_url=html.escape(manager.url() + "/pair"),
                    file=CA_DOWNLOAD_NAME,
                ).encode("utf-8")
            headers = [
                (b"content-type", ctype.encode()),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
                (b"referrer-policy", b"no-referrer"),
                (b"x-frame-options", b"DENY"),
                (b"content-security-policy",
                 b"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"),
                *extra,
            ]
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": b"" if method == "HEAD" else body})

        return app

    # -- pairing ---------------------------------------------------------------------

    def new_pairing(self) -> Pairing:
        with self._lock:
            code = f"{secrets.randbelow(10**6):06d}"
            self.state.pairing = Pairing(code=code, token=secrets.token_urlsafe(24), expires=time.time() + PAIRING_TTL)
            self.state.locked = False
            self.state.failures.clear()
            return self.state.pairing

    def current_pairing(self) -> Pairing | None:
        with self._lock:
            p = self.state.pairing
            if p is None or p.used or p.expires < time.time():
                if self.state.enabled and not self.state.locked:
                    p = self.new_pairing()
                else:
                    return None
            return p

    def pair(self, secret: str, device_name: str, client: str = "?", https: bool = False) -> str | None:
        """Exchange a pairing code or token for a device token. Returns None on failure."""
        with self._lock:
            s = self.state
            t = time.time()
            while s.failures and t - s.failures[0][0] > FAILURE_WINDOW:
                s.failures.popleft()
            p = s.pairing
            if s.locked or p is None or p.used or p.expires < t:
                return None
            # One device guessing can only lock itself out; the overall cap is a backstop
            # (a 6-digit code with ~MAX_GLOBAL_FAILURES guesses is still a 1-in-30,000 chance).
            if sum(1 for _t, c in s.failures if c == client) >= MAX_FAILURES:
                return None
            raw = (secret or "").strip().encode("utf-8")
            ok = hmac.compare_digest(raw, p.token.encode()) or (
                len(raw) == 6 and hmac.compare_digest(raw, p.code.encode())
            )
            if not ok:
                s.failures.append((t, client))
                if len(s.failures) >= MAX_GLOBAL_FAILURES:
                    s.locked = True  # the desktop has to show a fresh code
                    log.warning("pairing locked after repeated failures")
                return None
            p.used = True
            token = secrets.token_urlsafe(32)
            with self.db.connect() as c:
                c.execute(
                    "INSERT INTO devices(id, name, token_hash, created_at, last_seen) VALUES (?,?,?,?,?)",
                    (uuid.uuid4().hex, device_name[:80] or "Phone", hash_token(token, https), now(), now()),
                )
            self.new_pairing()
            return token

    def check_device(self, token: str | None, https: bool = False) -> str | None:
        if not token or len(token) > 200:
            return None
        h = hash_token(token, https)
        with self.db.connect() as c:
            row = c.execute("SELECT id, last_seen FROM devices WHERE token_hash=?", (h,)).fetchone()
            if row is None:
                return None
            if (row["last_seen"] or 0) < now() - 60:
                c.execute("UPDATE devices SET last_seen=? WHERE id=?", (now(), row["id"]))
        return row["id"]

    def devices(self) -> list[dict]:
        with self.db.connect() as c:
            return [
                {"id": r["id"], "name": r["name"], "createdAt": r["created_at"], "lastSeen": r["last_seen"]}
                for r in c.execute("SELECT * FROM devices ORDER BY created_at DESC")
            ]

    def revoke(self, device_id: str) -> None:
        with self.db.connect() as c:
            c.execute("DELETE FROM devices WHERE id=?", (device_id,))

    def public_state(self) -> dict:
        s = self.state
        p = self.current_pairing() if s.enabled else None
        return {
            "enabled": s.enabled,
            "address": s.address,
            "port": s.port,
            "url": self.url() if s.enabled else "",
            "scheme": s.scheme,
            "secure": s.enabled and s.scheme == "https",
            "secureAvailable": self.cert_root is not None,
            "setupUrl": self.setup_url(),
            "ca": self.ca_info(),
            "expiresAt": s.expires_at if s.enabled else None,
            "pairing": {"code": p.code, "expiresAt": p.expires, "url": f"{self.url()}/pair#t={p.token}"}
            if p else None,
            "locked": s.locked,
            "addresses": lan_addresses(),
            "devices": self.devices(),
        }


SETUP_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up a secure connection to Proseway</title>
<style>
body {{ font: 17px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 36rem; padding: 1rem 1.2rem 3rem;
       color: #1d1b18; background: #faf8f4; }}
h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 1.6rem; }}
a.btn {{ display: inline-block; padding: .7rem 1.1rem; border-radius: .5rem; background: #1d1b18; color: #fff;
        text-decoration: none; font-weight: 600; }}
code {{ word-break: break-all; font-size: .85rem; }}
li {{ margin: .3rem 0; }}
.note {{ font-size: .92rem; color: #5b554c; }}
@media (prefers-color-scheme: dark) {{ body {{ color: #ece7df; background: #1b1a18; }}
  a.btn {{ background: #ece7df; color: #1b1a18; }} .note {{ color: #b5ad9f; }} }}
</style></head><body>
<h1>Set up a secure connection</h1>
<p>Do this once on each phone. Afterwards your phone can open Proseway over HTTPS, add it to
the home screen, and keep the chapters you have opened for offline reading.</p>
<p><a class="btn" href="/{file}">Download the certificate</a></p>
<p class="note">Certificate: <strong>{name}</strong><br>SHA-256 fingerprint:<br><code>{fingerprint}</code><br>
Check that it matches the fingerprint Proseway shows on your computer. If it doesn't, don't install it:
someone on this network may be tampering with the connection.</p>
<p class="note"><strong>Why this matters:</strong> this page comes over an unencrypted connection. If someone
swapped the certificate, theirs would have none of the limits Proseway's has: your phone would trust them for
<em>every</em> website, so they could read and change everything it opens. If you can, send the certificate
from your computer instead (by AirDrop, a USB cable or a file share); Proseway's sharing window has a
download link.</p>
<h2>iPhone and iPad</h2>
<ol>
<li>Open this page in <strong>Safari</strong>, tap <em>Download the certificate</em>, then <em>Allow</em>.</li>
<li>Open <em>Settings</em>, tap <em>Profile Downloaded</em> (or <em>General &rarr; VPN &amp; Device Management</em>)
and install the Proseway profile.</li>
<li>Go to <em>Settings &rarr; General &rarr; About &rarr; Certificate Trust Settings</em> and switch on full
trust for the Proseway certificate.</li>
</ol>
<h2>Android</h2>
<ol>
<li>Tap <em>Download the certificate</em>.</li>
<li>Open <em>Settings</em> and search for <em>CA certificate</em> (usually <em>Security &rarr; More security
settings &rarr; Encryption &amp; credentials &rarr; Install a certificate &rarr; CA certificate</em>).</li>
<li>Tap <em>Install anyway</em> and choose <em>{file}</em> from your downloads.</li>
</ol>
<p class="note">Chrome and Samsung Internet use the certificate. Firefox only does after you turn on
<em>Use third party CA certificates</em> in its secret settings.</p>
<h2>Then</h2>
<p>Open <a href="{https_url}">{https_url}</a> and enter the code shown on your computer, or scan the
pairing code again.</p>
<p class="note">This certificate can only vouch for this one address on your network, never for
websites or other devices.
You can remove it at any time in the same settings.</p>
</body></html>
"""

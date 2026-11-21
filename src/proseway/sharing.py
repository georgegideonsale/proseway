"""Reading on your phone: an opt-in second listener on the home network, with pairing.

Security model (see docs/decisions/0005-phone-sharing.md):

* Off by default and off again at every launch. While off, Proseway only listens on 127.0.0.1.
* Turning it on binds one extra listener to the chosen private LAN address (never 0.0.0.0).
* A phone must pair first: scan the QR code (one-time token in the URL fragment) or type the
  6-digit code. Pairing gives the phone a random device token in an HttpOnly, SameSite=Strict
  cookie. Only a SHA-256 hash of the token is stored.
* Every API request on the LAN listener needs a valid device cookie, and only reading and
  annotating endpoints are reachable from the LAN at all. Managing sharing, devices, imports,
  deletions and restore are local-only.
* Pairing codes expire after 5 minutes, are single-use, and lock after repeated failures.
* Sharing switches itself off after a chosen time (default 2 hours).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

import psutil

from .db import Database, now

log = logging.getLogger(__name__)

PAIRING_TTL = 300.0
MAX_FAILURES = 8
FAILURE_WINDOW = 300.0
COOKIE_NAME = "pw_device"
COOKIE_MAX_AGE = 180 * 24 * 3600


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
    started_at: float = 0.0
    expires_at: float = 0.0
    pairing: Pairing | None = None
    failures: deque = field(default_factory=deque)
    locked: bool = False


class SharingManager:
    def __init__(self, db: Database):
        self.db = db
        self.state = SharingState()
        self._lock = threading.RLock()
        self._server = None
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self.app = None  # set by the server factory
        self.ssl_files: tuple[str, str] | None = None

    # -- listener control ------------------------------------------------------------

    def enable(self, address: str, port: int, minutes: int = 120) -> SharingState:
        import uvicorn

        allowed = {a["address"] for a in lan_addresses()}
        if address not in allowed:
            raise ValueError("That address isn't a private network address of this computer.")
        with self._lock:
            self.disable()
            kwargs = {}
            if self.ssl_files:
                kwargs = {"ssl_certfile": self.ssl_files[0], "ssl_keyfile": self.ssl_files[1]}
            # lifespan="off": the app's startup/shutdown (job supervisor) belongs to the main
            # listener; this second listener only serves requests.
            config = uvicorn.Config(self.app, host=address, port=port, log_level="warning",
                                    access_log=False, server_header=False, lifespan="off", **kwargs)
            server = uvicorn.Server(config)
            thread = threading.Thread(target=server.run, name="proseway-lan", daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not server.started:
                server.should_exit = True
                raise OSError(f"Couldn't listen on {address}:{port}. Is the port in use?")
            self._server, self._thread = server, thread
            s = self.state
            s.enabled, s.address, s.port = True, address, port
            s.scheme = "https" if self.ssl_files else "http"
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
            if self._server is not None:
                self._server.should_exit = True
                if self._thread is not None and self._thread is not threading.current_thread():
                    self._thread.join(timeout=5)
                log.info("phone sharing off")
            self._server = None
            self._thread = None
            self.state.enabled = False
            self.state.pairing = None

    def is_lan_request(self, server_addr: tuple[str, int] | None) -> bool:
        s = self.state
        return bool(server_addr) and s.enabled and server_addr[0] == s.address and server_addr[1] == s.port

    def lan_host_ok(self, host_header: str) -> bool:
        s = self.state
        return host_header.lower() in {f"{s.address}:{s.port}".lower()}

    def url(self) -> str:
        s = self.state
        return f"{s.scheme}://{s.address}:{s.port}"

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

    def pair(self, secret: str, device_name: str) -> str | None:
        """Exchange a pairing code or token for a device token. Returns None on failure."""
        with self._lock:
            s = self.state
            t = time.time()
            while s.failures and t - s.failures[0] > FAILURE_WINDOW:
                s.failures.popleft()
            p = s.pairing
            if s.locked or p is None or p.used or p.expires < t:
                return None
            secret = (secret or "").strip()
            ok = hmac.compare_digest(secret, p.token) or (
                len(secret) == 6 and hmac.compare_digest(secret, p.code)
            )
            if not ok:
                s.failures.append(t)
                if len(s.failures) >= MAX_FAILURES:
                    s.locked = True  # the desktop has to show a fresh code
                    log.warning("pairing locked after repeated failures")
                return None
            p.used = True
            token = secrets.token_urlsafe(32)
            with self.db.connect() as c:
                c.execute(
                    "INSERT INTO devices(id, name, token_hash, created_at, last_seen) VALUES (?,?,?,?,?)",
                    (uuid.uuid4().hex, device_name[:80] or "Phone", hash_token(token), now(), now()),
                )
            self.new_pairing()
            return token

    def check_device(self, token: str | None) -> str | None:
        if not token or len(token) > 200:
            return None
        h = hash_token(token)
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
            "expiresAt": s.expires_at if s.enabled else None,
            "pairing": {"code": p.code, "expiresAt": p.expires, "url": f"{self.url()}/pair#t={p.token}"}
            if p else None,
            "locked": s.locked,
            "addresses": lan_addresses(),
            "devices": self.devices(),
        }

"""A real HTTPS LAN listener, verified against the generated CA, plus the plain-HTTP setup page."""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi.testclient import TestClient

from proseway import sharing as sharing_mod
from proseway.server import AppConfig, create_app

H = {"X-Proseway": "1", "Content-Type": "application/json"}


def free_port_pair() -> int:
    """A port p where p and p+1 are both free (LAN listener and setup page)."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            p = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", p + 1))
            return p
        except OSError:
            continue
    raise RuntimeError("no free port pair")


def request(url, ctx=None, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_https_listener_with_generated_ca(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing_mod, "lan_addresses", lambda: [{"interface": "test", "address": "127.0.0.1"}])
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=True)
    with TestClient(app, base_url="http://127.0.0.1:8765") as local:
        port = free_port_pair()
        app.state.port = port
        r = local.post("/api/sharing", headers=H, json={"enabled": True, "secure": True, "minutes": 5,
                                                         "address": "127.0.0.1"})
        assert r.status_code == 200, r.text
        st = r.json()
        try:
            assert st["secure"] and st["url"] == f"https://127.0.0.1:{port}"
            assert st["setupUrl"] == f"http://127.0.0.1:{port + 1}/"
            assert st["pairing"]["url"].startswith(f"https://127.0.0.1:{port}/pair#t=")
            fp = st["ca"]["fingerprint"]

            # Verify the server strictly against our CA only (not the system store), with
            # hostname (IP SAN) checking on.
            ca_pem = (tmp_path / "lib" / "certs" / "ca.pem").read_text()
            ctx = ssl.create_default_context(cadata=ca_pem)
            assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
            base = f"https://127.0.0.1:{port}"
            status, _h, body = request(base + "/api/session", ctx)
            assert (status, json.loads(body)) == (200, {"listener": "lan", "paired": False})
            assert request(base + "/api/books", ctx)[0] == 401

            # A client that doesn't trust the CA is refused by its own TLS check.
            try:
                request(base + "/api/session", ssl.create_default_context())
                raise AssertionError("untrusted certificate was accepted")
            except urllib.error.URLError as e:
                assert isinstance(e.reason, ssl.SSLCertVerificationError)

            # Pairing over TLS sets a Secure cookie, which then works.
            code = app.state.sharing.state.pairing.code
            status, headers, _ = request(base + "/api/pair", ctx, "POST",
                                         json.dumps({"secret": code}).encode(), H)
            assert status == 200
            cookie = headers["set-cookie"]
            assert "secure" in cookie.lower() and "httponly" in cookie.lower()
            token = cookie.split(";", 1)[0]
            assert request(base + "/api/books", ctx, headers={"Cookie": token})[0] == 200

            # The setup page: plain HTTP, the CA certificate and instructions, nothing else.
            setup = f"http://127.0.0.1:{port + 1}"
            status, headers, html = request(setup + "/")
            assert status == 200 and headers["Content-Type"].startswith("text/html")
            assert fp in html.decode() and "Certificate Trust Settings" in html.decode()
            assert "default-src 'none'" in headers["Content-Security-Policy"]
            status, headers, der = request(setup + "/proseway-ca.crt")
            assert status == 200 and headers["Content-Type"] == "application/x-x509-ca-cert"
            assert x509.load_der_x509_certificate(der).public_bytes(Encoding.PEM).decode() == ca_pem
            assert request(setup + "/api/books")[0] == 404
            assert request(setup + "/", method="POST", data=b"x")[0] == 405
            assert request(setup + "/", headers={"Host": "evil.example"})[0] == 421

            # The computer can download the same certificate; a phone can't reach that route.
            r = local.get("/api/sharing/ca.crt")
            assert r.status_code == 200 and r.content == der
            assert local.get("/api/sharing/qr.svg?target=setup").status_code == 200
            assert request(base + "/api/sharing/ca.crt", ctx, headers={"Cookie": token})[0] == 403
        finally:
            local.post("/api/sharing", headers=H, json={"enabled": False})
        for url in (f"https://127.0.0.1:{port}/api/session", f"http://127.0.0.1:{port + 1}/"):
            try:
                urllib.request.urlopen(url, timeout=2, context=ssl.create_default_context(cadata=ca_pem)
                                       if url.startswith("https") else None)
                raise AssertionError(f"still listening: {url}")
            except urllib.error.URLError:
                pass


def test_plain_http_sharing_still_works_and_has_no_setup_page(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing_mod, "lan_addresses", lambda: [{"interface": "test", "address": "127.0.0.1"}])
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=False)
    with TestClient(app, base_url="http://127.0.0.1:8765") as local:
        port = free_port_pair()
        app.state.port = port
        st = local.post("/api/sharing", headers=H, json={"enabled": True, "address": "127.0.0.1"}).json()
        try:
            assert not st["secure"] and st["url"] == f"http://127.0.0.1:{port}" and st["setupUrl"] == ""
            assert request(f"http://127.0.0.1:{port}/api/session")[0] == 200
            assert local.get("/api/sharing/qr.svg?target=setup").status_code == 404
        finally:
            local.post("/api/sharing", headers=H, json={"enabled": False})

"""A real HTTPS LAN listener, verified against the generated CA, plus the plain-HTTP setup page."""

from __future__ import annotations

import contextlib
import datetime as dt
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.request
from http.cookies import SimpleCookie

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi.testclient import TestClient

from proseway import certs
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


def code_of(body: bytes) -> str:
    return json.loads(body)["error"]["code"]


@contextlib.contextmanager
def running(tmp_path, monkeypatch, start_jobs=False):
    monkeypatch.setattr(sharing_mod, "lan_addresses", lambda: [{"interface": "test", "address": "127.0.0.1"}])
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=start_jobs)
    with TestClient(app, base_url="http://127.0.0.1:8765") as local:
        app.state.port = free_port_pair()

        def share(secure: bool):
            r = local.post("/api/sharing", headers=H, json={"enabled": True, "secure": secure, "minutes": 5,
                                                             "address": "127.0.0.1"})
            assert r.status_code == 200, r.text
            return r.json()

        try:
            yield app, local, share
        finally:
            local.post("/api/sharing", headers=H, json={"enabled": False})


def ca_context(tmp_path) -> ssl.SSLContext:
    """Trust only our CA (not the system store), with hostname (IP SAN) checking on."""
    ctx = ssl.create_default_context(cafile=str(tmp_path / "lib" / "certs" / "127.0.0.1" / "ca.pem"))
    assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
    return ctx


def pair(app, base, ctx=None) -> tuple[str, str]:
    """Pair over the LAN listener; returns (raw Set-Cookie header, "name=value")."""
    code = app.state.sharing.state.pairing.code
    status, headers, _ = request(base + "/api/pair", ctx, "POST", json.dumps({"secret": code}).encode(), H)
    assert status == 200
    raw = headers["set-cookie"]
    return raw, raw.split(";", 1)[0]


def test_https_listener_with_generated_ca(tmp_path, monkeypatch):
    with running(tmp_path, monkeypatch, start_jobs=True) as (app, local, share):
        port = app.state.port
        st = share(True)
        assert st["secure"] and st["url"] == f"https://127.0.0.1:{port}"
        assert st["setupUrl"] == f"http://127.0.0.1:{port + 1}/"
        assert st["pairing"]["url"].startswith(f"https://127.0.0.1:{port}/pair#t=")
        fp = st["ca"]["fingerprint"]
        ca_pem = (tmp_path / "lib" / "certs" / "127.0.0.1" / "ca.pem").read_text()
        ctx = ca_context(tmp_path)
        base = f"https://127.0.0.1:{port}"

        status, _h, body = request(base + "/api/session", ctx)
        assert (status, json.loads(body)) == (200, {"listener": "lan", "paired": False})
        status, headers, body = request(base + "/api/books", ctx)
        assert (status, code_of(body)) == (401, "not_paired")
        # An unpaired phone is told to drop its offline copies.
        assert headers["Clear-Site-Data"] == '"cache", "storage"'

        # A client that doesn't trust the CA is refused by its own TLS check.
        with pytest.raises(urllib.error.URLError) as exc:
            request(base + "/api/session", ssl.create_default_context())
        assert isinstance(exc.value.reason, ssl.SSLCertVerificationError)

        # Pairing over TLS sets a __Host- cookie with exactly these attributes, which then works.
        raw, token = pair(app, base, ctx)
        jar = SimpleCookie()
        jar.load(raw)
        assert list(jar) == ["__Host-pw_device"]
        c = jar["__Host-pw_device"]
        assert c["secure"] is True and c["httponly"] is True
        assert c["samesite"].lower() == "strict" and c["path"] == "/" and c["domain"] == ""
        assert int(c["max-age"]) == sharing_mod.COOKIE_MAX_AGE
        assert request(base + "/api/books", ctx, headers={"Cookie": token})[0] == 200

        # The setup page: plain HTTP, the CA certificate and instructions, nothing else.
        setup = f"http://127.0.0.1:{port + 1}"
        status, headers, html = request(setup + "/")
        assert status == 200 and headers["Content-Type"].startswith("text/html")
        page = html.decode()
        assert fp in page and "Certificate Trust Settings" in page and "every</em> website" in page
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

        local.post("/api/sharing", headers=H, json={"enabled": False})
        assert local.get("/api/sharing/ca.crt").status_code == 404  # nothing to hand out while off
    for url in (f"https://127.0.0.1:{port}/api/session", f"http://127.0.0.1:{port + 1}/"):
        with pytest.raises(urllib.error.URLError):
            urllib.request.urlopen(url, timeout=2, context=ctx if url.startswith("https") else None)


def test_protections_hold_over_tls(tmp_path, monkeypatch):
    with running(tmp_path, monkeypatch) as (app, local, share):
        share(True)
        ctx = ca_context(tmp_path)
        base = f"https://127.0.0.1:{app.state.port}"
        _raw, token = pair(app, base, ctx)
        ok = {"Cookie": token, **H}
        body = json.dumps({"blockId": "x", "progress": 0.5}).encode()
        position = base + "/api/books/" + "0" * 32 + "/position"

        # A Host other than the address being shared (DNS rebinding): refused.
        assert request(base + "/api/books", ctx, headers={"Cookie": token, "Host": "evil.example"})[0] == 421
        # Writes need the CSRF header, and a same-origin Origin if there is one.
        status, _h, b = request(position, ctx, "PUT", body, {"Cookie": token, "Content-Type": "application/json"})
        assert (status, code_of(b)) == (403, "csrf")
        status, _h, b = request(position, ctx, "PUT", body, {**ok, "Origin": "https://evil.example"})
        assert (status, code_of(b)) == (403, "csrf")
        # The same request with the right headers gets through the guard (404: no such book).
        assert request(position, ctx, "PUT", body, {**ok, "Origin": base})[0] == 404
        # A paired phone still can't manage the library or sharing.
        for method, path in (("DELETE", "/api/books/" + "0" * 32), ("POST", "/api/sharing"),
                             ("POST", "/api/sharing/new-code"), ("DELETE", "/api/devices/" + "0" * 32),
                             ("GET", "/api/sharing"), ("POST", "/api/restore")):
            data = b"{}" if method == "POST" else None
            status, _h, b = request(base + path, ctx, method, data, ok)
            assert (status, code_of(b)) == (403, "local_only"), (method, path)


def test_tls_only_offers_modern_ciphers(tmp_path, monkeypatch):
    with running(tmp_path, monkeypatch) as (app, _local, share):
        share(True)
        base = f"https://127.0.0.1:{app.state.port}/api/session"

        good = ca_context(tmp_path)
        good.maximum_version = ssl.TLSVersion.TLSv1_2
        good.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        assert request(base, good)[0] == 200

        no_forward_secrecy = ca_context(tmp_path)
        no_forward_secrecy.maximum_version = ssl.TLSVersion.TLSv1_2
        no_forward_secrecy.set_ciphers("AES128-SHA256:AES128-GCM-SHA256:AES128-SHA")
        with pytest.raises((urllib.error.URLError, ssl.SSLError, ConnectionError)):
            request(base, no_forward_secrecy)

        cbc = ca_context(tmp_path)
        cbc.maximum_version = ssl.TLSVersion.TLSv1_2
        cbc.set_ciphers("ECDHE-ECDSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA")
        with pytest.raises((urllib.error.URLError, ssl.SSLError, ConnectionError)):
            request(base, cbc)

        assert sharing_mod.TLS_CIPHERS == "ECDHE+AESGCM:ECDHE+CHACHA20"


def test_device_tokens_are_bound_to_the_scheme_they_were_issued_on(tmp_path, monkeypatch):
    with running(tmp_path, monkeypatch) as (app, _local, share):
        port = app.state.port
        http_base, https_base = f"http://127.0.0.1:{port}", f"https://127.0.0.1:{port}"

        # Pair over plain HTTP: an ordinary cookie (it can't be Secure), sniffable on the network.
        share(False)
        raw, http_cookie = pair(app, http_base)
        assert http_cookie.startswith("pw_device=") and "secure" not in raw.lower()
        http_token = http_cookie.split("=", 1)[1]
        assert request(http_base + "/api/books", headers={"Cookie": http_cookie})[0] == 200

        # The same token is worthless on the HTTPS listener, under either cookie name.
        share(True)
        ctx = ca_context(tmp_path)
        for cookie in (f"__Host-pw_device={http_token}", f"pw_device={http_token}"):
            status, _h, body = request(https_base + "/api/books", ctx, headers={"Cookie": cookie})
            assert (status, code_of(body)) == (401, "not_paired"), cookie
            assert json.loads(request(https_base + "/api/session", ctx, headers={"Cookie": cookie})[2])["paired"] is False

        # Pairing over HTTPS works (the plain cookie doesn't get in the way) and gives a __Host- cookie.
        _raw, https_cookie = pair(app, https_base, ctx)
        assert https_cookie.startswith("__Host-pw_device=")
        https_token = https_cookie.split("=", 1)[1]
        assert request(https_base + "/api/books", ctx, headers={"Cookie": https_cookie})[0] == 200

        # Back on plain HTTP, the HTTPS token isn't accepted either, and the HTTP pairing still is.
        share(False)
        assert request(http_base + "/api/books", headers={"Cookie": f"pw_device={https_token}"})[0] == 401
        assert request(http_base + "/api/books", headers={"Cookie": http_cookie})[0] == 200
        assert len(app.state.sharing.devices()) == 2


def test_dialog_and_setup_page_show_the_certificate_in_use(tmp_path, monkeypatch):
    """Replacing the CA on disk (proseway --new-phone-certificate) while sharing is on doesn't
    make the dialog show a fingerprint the listener isn't presenting."""
    with running(tmp_path, monkeypatch) as (app, local, share):
        st = share(True)
        before = st["ca"]["fingerprint"]
        root = tmp_path / "lib" / "certs"
        der = local.get("/api/sharing/ca.crt").content
        certs.remove_all(root)
        certs.ensure_server_cert(root, "127.0.0.1")  # a different CA now on disk
        assert local.get("/api/sharing").json()["ca"]["fingerprint"] == before
        assert local.get("/api/sharing/ca.crt").content == der
        setup = f"http://127.0.0.1:{app.state.port + 1}"
        assert request(setup + "/proseway-ca.crt")[2] == der
        # Turning sharing off and on picks up the new one.
        assert share(True)["ca"]["fingerprint"] != before


def test_no_setup_page_above_the_last_port(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing_mod, "lan_addresses", lambda: [{"interface": "test", "address": "127.0.0.1"}])
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=False)
    sharing = app.state.sharing
    started = []
    monkeypatch.setattr(sharing, "_start_listener",
                        lambda _app, address, port, name, **kw: started.append((port, name)) or (None, None))
    sharing.enable("127.0.0.1", 65535, secure=True)
    try:
        assert started == [(65535, "proseway-lan")]
        assert sharing.setup_url() == "" and sharing.state.setup_port == 0
        with pytest.raises(ValueError):
            sharing.enable("127.0.0.1", 65536)
    finally:
        sharing.disable()


# -- OpenSSL's own chain check (what Python, curl and many apps use) ------------------------

def _handshake(server_ctx: ssl.SSLContext, client_ctx: ssl.SSLContext, hostname: str) -> None:
    """A TLS handshake in memory, no sockets."""
    c_in, c_out, s_in, s_out = ssl.MemoryBIO(), ssl.MemoryBIO(), ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_ctx.wrap_bio(c_in, c_out, server_hostname=hostname)
    server = server_ctx.wrap_bio(s_in, s_out, server_side=True)
    done = {"c": False, "s": False}
    for _ in range(20):
        for name, obj in (("c", client), ("s", server)):
            if not done[name]:
                try:
                    obj.do_handshake()
                    done[name] = True
                except ssl.SSLWantReadError:
                    pass
        s_in.write(c_out.read())
        c_in.write(s_out.read())
        if all(done.values()):
            return
    raise AssertionError("handshake didn't finish")


def _server_ctx(tmp_path, leaf: x509.Certificate, key) -> ssl.SSLContext:
    cert_file, key_file = tmp_path / "leaf.pem", tmp_path / "leaf-key.pem"
    cert_file.write_bytes(leaf.public_bytes(Encoding.PEM))
    key_file.write_bytes(key.private_bytes(Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    return ctx


def _forge(files: certs.CertFiles, names: list[x509.GeneralName]):
    ca = x509.load_pem_x509_certificate(files.ca_cert.read_bytes())
    ca_key = serialization.load_pem_private_key(files.ca_key.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "forged")]))
        .issuer_name(ca.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return leaf, key


def test_openssl_rejects_certificates_outside_the_ca_constraints(tmp_path):
    root = tmp_path / "certs"
    issued = certs.ensure_server_cert(root, "127.0.0.1")
    files = certs.files_for(root, "127.0.0.1")
    client = ssl.create_default_context(cafile=str(files.ca_cert))

    # The real certificate passes.
    real = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    real.load_cert_chain(issued.certfile, issued.keyfile)
    _handshake(real, client, "127.0.0.1")

    ip = lambda a: x509.IPAddress(ipaddress.ip_address(a))  # noqa: E731
    cases = [
        ("127.0.0.2", [ip("127.0.0.2")]),  # another address
        ("127.0.0.1", [ip("127.0.0.1"), x509.RFC822Name("someone@example.com")]),  # an email address
        ("127.0.0.1", [ip("127.0.0.1"), x509.UniformResourceIdentifier("https://example.com/")]),  # a URI
        ("127.0.0.1", [ip("127.0.0.1"), x509.DNSName("example.com")]),  # a website
    ]
    for hostname, names in cases:
        leaf, key = _forge(files, names)
        with pytest.raises(ssl.SSLCertVerificationError, match="subtree|name constraint|permitted"):
            _handshake(_server_ctx(tmp_path, leaf, key), client, hostname)

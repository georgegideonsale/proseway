"""The local CA and server certificates used for HTTPS phone sharing."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import shutil
import stat
import sys
import threading
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from proseway import certs

ADDR = "192.168.1.20"


@pytest.fixture
def root(tmp_path):
    return tmp_path / "certs"


def load(path):
    return x509.load_pem_x509_certificate(Path(path).read_bytes())


def ip(a: str) -> x509.IPAddress:
    return x509.IPAddress(ipaddress.ip_address(a))


def test_server_cert_has_the_ip_as_san_and_chains_to_the_ca(root):
    issued = certs.ensure_server_cert(root, ADDR)
    files = certs.files_for(root, ADDR)
    leaf, ca = load(files.server_cert), load(files.ca_cert)
    assert issued.ca == ca
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address(ADDR)]
    assert sans.get_values_for_type(x509.DNSName) == []
    leaf.verify_directly_issued_by(ca)
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    # The cert file carries the chain (leaf, then CA), so phones get the whole path.
    chain = x509.load_pem_x509_certificates(Path(issued.certfile).read_bytes())
    assert [c.subject for c in chain] == [leaf.subject, ca.subject]
    key = serialization.load_pem_private_key(Path(issued.keyfile).read_bytes(), password=None)
    assert key.public_key().public_numbers() == leaf.public_key().public_numbers()


def test_expiry_fits_phone_rules(root):
    certs.ensure_server_cert(root, "10.0.0.5")
    files = certs.files_for(root, "10.0.0.5")
    leaf, ca = load(files.server_cert), load(files.ca_cert)
    leaf_days = (leaf.not_valid_after_utc - leaf.not_valid_before_utc).days
    assert 390 <= leaf_days <= 397  # Apple: <= 825; public CAs: <= 398
    assert (ca.not_valid_after_utc - ca.not_valid_before_utc).days >= 3000
    assert leaf.not_valid_before_utc <= dt.datetime.now(dt.timezone.utc)


def test_ca_is_constrained_to_exactly_its_own_address(root):
    ca = certs.ensure_server_cert(root, ADDR).ca
    bc = ca.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.critical and bc.value.ca and bc.value.path_length == 0
    nc = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert nc.critical and nc.value.excluded_subtrees is None
    assert set(nc.value.permitted_subtrees) == {
        x509.IPAddress(ipaddress.ip_network(f"{ADDR}/32")),
        x509.DNSName("invalid"),
        x509.RFC822Name("invalid"),
        x509.UniformResourceIdentifier("invalid"),
    }
    eku = ca.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(eku) == [ExtendedKeyUsageOID.SERVER_AUTH]


def _forge(files, *names: x509.GeneralName) -> x509.Certificate:
    """What someone holding the CA key could sign: a leaf for arbitrary names."""
    ca = load(files.ca_cert)
    ca_key = serialization.load_pem_private_key(files.ca_key.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "x")]))
        .issuer_name(ca.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(list(names)), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )


def _verify(files, leaf, subject):
    store = verification.Store([load(files.ca_cert)])
    verifier = verification.PolicyBuilder().store(store).build_server_verifier(subject)
    return verifier.verify(leaf, [])


def test_a_stolen_ca_key_cannot_impersonate_anything_else(root):
    certs.ensure_server_cert(root, ADDR)
    files = certs.files_for(root, ADDR)
    # The real certificate verifies...
    _verify(files, load(files.server_cert), ip(ADDR))
    # ...but certificates for anything else don't, even when signed by the CA's own key:
    for name in (
        x509.DNSName("example.com"),  # a website
        ip("8.8.8.8"),  # a public address
        ip("192.168.1.1"),  # the router on the same network
        ip("10.0.0.2"),  # another private address
    ):
        with pytest.raises(verification.VerificationError):
            _verify(files, _forge(files, name), name)
    # Smuggling an extra name into an otherwise valid certificate fails too.
    for extra in (x509.RFC822Name("someone@example.com"), x509.UniformResourceIdentifier("https://example.com/")):
        with pytest.raises(verification.VerificationError):
            _verify(files, _forge(files, ip(ADDR), extra), ip(ADDR))


def test_refuses_public_addresses(root):
    for bad in ("8.8.8.8", "not an ip", "::1", "169.254.1.1"):
        with pytest.raises(ValueError):
            certs.ensure_server_cert(root, bad)


def test_reuses_and_renews(root, monkeypatch):
    first = certs.ensure_server_cert(root, ADDR)
    leaf1 = load(first.certfile)
    again = certs.ensure_server_cert(root, ADDR)
    assert load(again.certfile).serial_number == leaf1.serial_number  # kept
    assert again.ca == first.ca
    # Another address has its own CA (each one only vouches for its own address), and the
    # first stays as it was, so switching back needs no new trust.
    other = certs.ensure_server_cert(root, "192.168.1.30")
    assert other.ca != first.ca
    assert certs.ensure_server_cert(root, ADDR).ca == first.ca
    # Close to expiry, the server certificate renews; the CA stays.
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=380)
    monkeypatch.setattr(certs, "_utcnow", lambda: later)
    renewed = certs.ensure_server_cert(root, ADDR)
    assert load(renewed.certfile).serial_number != leaf1.serial_number
    assert renewed.ca == first.ca


@pytest.mark.parametrize("damage", ["garbage key", "missing key", "missing cert", "other key", "moved"])
def test_a_damaged_ca_is_an_error_not_silently_replaced(root, damage):
    certs.ensure_server_cert(root, ADDR)
    files = certs.files_for(root, ADDR)
    if damage == "garbage key":
        files.ca_key.write_bytes(b"garbage")
    elif damage == "missing key":
        files.ca_key.unlink()
    elif damage == "missing cert":
        files.ca_cert.unlink()
    elif damage == "other key":
        key = ec.generate_private_key(ec.SECP256R1())
        files.ca_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    elif damage == "moved":  # a folder copied to another address's name
        shutil.copytree(files.dir, root / "192.168.1.99")
        files = certs.files_for(root, "192.168.1.99")
    before = {p.name: p.read_bytes() for p in files.dir.iterdir()}
    with pytest.raises(certs.CertError, match="new-phone-certificate"):
        certs.ensure_server_cert(root, "192.168.1.99" if damage == "moved" else ADDR)
    assert {p.name: p.read_bytes() for p in files.dir.iterdir()} == before  # nothing replaced


def test_an_expired_ca_is_an_error(root, monkeypatch):
    certs.ensure_server_cert(root, ADDR)
    much_later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=certs.CA_DAYS)
    monkeypatch.setattr(certs, "_utcnow", lambda: much_later)
    with pytest.raises(certs.CertError, match="expired"):
        certs.ensure_server_cert(root, ADDR)


def test_concurrent_first_use_makes_one_ca(root):
    results, errors = [], []

    def go():
        try:
            results.append(certs.ensure_server_cert(root, ADDR).ca)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len({c.serial_number for c in results}) == 1
    assert results[0] == load(certs.files_for(root, ADDR).ca_cert)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX permission bits")
def test_private_keys_are_owner_only_posix(root):
    certs.ensure_server_cert(root, ADDR)
    files = certs.files_for(root, ADDR)
    for p in (files.ca_key, files.server_key):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, p
    assert stat.S_IMODE(os.stat(files.dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(files.ca_cert).st_mode) == 0o644


def _windows_dacl(path: Path) -> str:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.DWORD)]
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p]
    need = wintypes.DWORD()
    advapi32.GetFileSecurityW(str(path), 4, None, 0, ctypes.byref(need))  # DACL_SECURITY_INFORMATION
    buf = ctypes.create_string_buffer(need.value)
    assert advapi32.GetFileSecurityW(str(path), 4, buf, need, ctypes.byref(need)), ctypes.get_last_error()
    out = wintypes.LPWSTR()
    assert advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(buf, 1, 4, ctypes.byref(out), None)
    return out.value


@pytest.mark.skipif(sys.platform != "win32", reason="Windows access lists")
def test_private_keys_are_owner_only_windows(root):
    certs.ensure_server_cert(root, ADDR)
    files = certs.files_for(root, ADDR)
    for p in (files.ca_key, files.server_key, files.dir):
        dacl = _windows_dacl(p)
        # Protected (nothing inherited from the data folder), and exactly two entries:
        # the current user and SYSTEM. No Everyone (WD), Users (BU) or Authenticated Users (AU).
        assert dacl.startswith("D:P"), (p, dacl)
        assert dacl.count("(A;") == 2 and ";;;SY)" in dacl, (p, dacl)
        for group in ("WD", "BU", "AU", "BA"):
            assert f";;;{group})" not in dacl, (p, dacl)


def test_issued_info_and_der(root):
    issued = certs.ensure_server_cert(root, ADDR)
    ca = x509.load_der_x509_certificate(issued.ca_der)
    assert ca == issued.ca
    info = issued.ca_info
    assert info["fingerprint"] == certs.fingerprint(ca)
    assert len(info["fingerprint"].split(":")) == 32
    assert "Proseway local CA" in info["name"] and ADDR in info["name"]


def test_remove_all(root):
    certs.ensure_server_cert(root, ADDR)
    certs.ensure_server_cert(root, "10.0.0.5")
    assert certs.remove_all(root) == 2
    assert not root.exists()
    assert certs.remove_all(root) == 0

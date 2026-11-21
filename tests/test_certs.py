"""The local CA and server certificates used for HTTPS phone sharing."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import stat
import sys
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from proseway import certs


@pytest.fixture
def files(tmp_path):
    return certs.CertFiles(tmp_path / "certs")


def load(path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def test_server_cert_has_the_ip_as_san_and_chains_to_the_ca(files):
    certfile, keyfile = certs.ensure_server_cert(files, "192.168.1.20")
    leaf = load(files.server_cert)
    ca = load(files.ca_cert)
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("192.168.1.20")]
    assert sans.get_values_for_type(x509.DNSName) == []
    leaf.verify_directly_issued_by(ca)
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    # The cert file carries the chain (leaf, then CA), so phones get the whole path.
    chain = x509.load_pem_x509_certificates(Path(certfile).read_bytes())
    assert [c.subject for c in chain] == [leaf.subject, ca.subject]
    key = serialization.load_pem_private_key(Path(keyfile).read_bytes(), password=None)
    assert key.public_key().public_numbers() == leaf.public_key().public_numbers()


def test_expiry_fits_phone_rules(files):
    certs.ensure_server_cert(files, "10.0.0.5")
    leaf, ca = load(files.server_cert), load(files.ca_cert)
    leaf_days = (leaf.not_valid_after_utc - leaf.not_valid_before_utc).days
    assert 390 <= leaf_days <= 397  # Apple: <= 825; public CAs: <= 398
    assert (ca.not_valid_after_utc - ca.not_valid_before_utc).days >= 3000
    assert leaf.not_valid_before_utc <= dt.datetime.now(dt.timezone.utc)


def test_ca_is_constrained_to_private_addresses(files):
    ca, _ = certs.ensure_ca(files)
    bc = ca.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.critical and bc.value.ca and bc.value.path_length == 0
    nc = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert nc.critical
    permitted = nc.value.permitted_subtrees
    assert x509.IPAddress(ipaddress.ip_network("192.168.0.0/16")) in permitted
    assert [n for n in permitted if isinstance(n, x509.DNSName)] == [x509.DNSName("invalid")]


def _forge(files, name: x509.GeneralName) -> x509.Certificate:
    """What someone holding the CA key could sign: a leaf for an arbitrary name."""
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
        .add_extension(x509.SubjectAlternativeName([name]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )


def _verify(files, leaf, subject):
    store = verification.Store([load(files.ca_cert)])
    verifier = verification.PolicyBuilder().store(store).build_server_verifier(subject)
    return verifier.verify(leaf, [])


def test_a_stolen_ca_key_cannot_impersonate_websites(files):
    certs.ensure_server_cert(files, "192.168.1.20")
    # The real certificate verifies...
    _verify(files, load(files.server_cert), x509.IPAddress(ipaddress.ip_address("192.168.1.20")))
    # ...but certificates for a public name or a public address don't, even when signed by the CA.
    with pytest.raises(verification.VerificationError):
        _verify(files, _forge(files, x509.DNSName("example.com")), x509.DNSName("example.com"))
    with pytest.raises(verification.VerificationError):
        ip = x509.IPAddress(ipaddress.ip_address("8.8.8.8"))
        _verify(files, _forge(files, ip), ip)


def test_refuses_public_addresses(files):
    with pytest.raises(ValueError):
        certs.ensure_server_cert(files, "8.8.8.8")
    with pytest.raises(ValueError):
        certs.ensure_server_cert(files, "not an ip")


def test_reuses_and_renews(files, monkeypatch):
    certs.ensure_server_cert(files, "192.168.1.20")
    ca1, leaf1 = load(files.ca_cert), load(files.server_cert)
    certs.ensure_server_cert(files, "192.168.1.20")
    assert load(files.server_cert).serial_number == leaf1.serial_number  # kept
    # A new address gets a new server certificate from the same CA: no re-trusting needed.
    certs.ensure_server_cert(files, "192.168.1.30")
    leaf2 = load(files.server_cert)
    assert leaf2.serial_number != leaf1.serial_number
    assert load(files.ca_cert).serial_number == ca1.serial_number
    # Close to expiry, it renews.
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=380)
    monkeypatch.setattr(certs, "_utcnow", lambda: later)
    certs.ensure_server_cert(files, "192.168.1.30")
    assert load(files.server_cert).serial_number != leaf2.serial_number
    assert load(files.ca_cert).serial_number == ca1.serial_number


def test_unreadable_ca_is_replaced(files):
    certs.ensure_server_cert(files, "192.168.1.20")
    files.ca_key.write_bytes(b"garbage")
    old = load(files.ca_cert).serial_number
    certs.ensure_server_cert(files, "192.168.1.20")
    assert load(files.ca_cert).serial_number != old
    load(files.server_cert).verify_directly_issued_by(load(files.ca_cert))


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX permission bits")
def test_private_keys_are_owner_only(files):
    certs.ensure_server_cert(files, "192.168.1.20")
    for p in (files.ca_key, files.server_key):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, p
    assert stat.S_IMODE(os.stat(files.dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(files.ca_cert).st_mode) == 0o644


def test_info_and_der_download(files):
    assert certs.ca_info(files) is None  # doesn't create one just by asking
    der = certs.ca_der(files)
    ca = x509.load_der_x509_certificate(der)
    info = certs.ca_info(files)
    assert info["fingerprint"] == certs.fingerprint(ca)
    assert len(info["fingerprint"].split(":")) == 32
    assert "Proseway local CA" in info["name"]

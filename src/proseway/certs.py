"""A small local certificate authority, so a paired phone can use HTTPS.

Phones only treat a page as a *secure context* (installable PWA, service worker, offline
reading) when it comes over HTTPS with a certificate they trust. A home network address like
``192.168.1.20`` can't get a public certificate, so Proseway makes its own:

* a **CA certificate** that the user trusts once on each phone, and
* a **server certificate** for the chosen LAN address (the address is the SAN), signed by it.

The CA is deliberately weak at anything else. Its *name constraints* (a critical extension
phones and browsers enforce) only allow private and loopback IPv4 addresses and no DNS names
at all, so even a stolen CA key can't impersonate a real website to a phone that trusts it.

Private keys are written with owner-only permissions (0600; on Windows the folder sits in the
user's own profile, which other accounts can't read by default).
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

log = logging.getLogger(__name__)

CA_DAYS = 10 * 365
# Apple refuses TLS server certificates valid for more than 825 days, and public CAs are held
# to 398. Stay under both; Proseway renews well before expiry.
SERVER_DAYS = 397
RENEW_BEFORE = dt.timedelta(days=30)

# Addresses the CA may ever vouch for. Everything else, including every DNS name, is refused.
PERMITTED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
]


@dataclass(frozen=True)
class CertFiles:
    dir: Path

    @property
    def ca_cert(self) -> Path:
        return self.dir / "ca.pem"

    @property
    def ca_key(self) -> Path:
        return self.dir / "ca-key.pem"

    @property
    def server_cert(self) -> Path:
        return self.dir / "server.pem"

    @property
    def server_key(self) -> Path:
        return self.dir / "server-key.pem"


def address_allowed(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and any(ip in n for n in PERMITTED_NETWORKS)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write(path: Path, data: bytes, private: bool) -> None:
    """Write atomically; private files are created 0600 so they are never briefly readable."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    mode = 0o600 if private else 0o644
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), mode)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _ensure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass


def _load_ca(files: CertFiles) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey] | None:
    try:
        cert = x509.load_pem_x509_certificate(files.ca_cert.read_bytes())
        key = serialization.load_pem_private_key(files.ca_key.read_bytes(), password=None)
    except (OSError, ValueError) as exc:
        if files.ca_cert.exists() or files.ca_key.exists():
            log.warning("local CA unreadable, making a new one: %s", exc)
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        return None
    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        return None
    if cert.not_valid_after_utc - _utcnow() < RENEW_BEFORE:
        return None
    return cert, key


def ensure_ca(files: CertFiles) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Load the local CA, or create one. A new CA means phones must trust it again."""
    _ensure_dir(files.dir)
    loaded = _load_ca(files)
    if loaded:
        return loaded
    key = ec.generate_private_key(ec.SECP256R1())
    # A random suffix keeps two installs (two computers) from showing the same name on a phone.
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Proseway"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"Proseway local CA {secrets.token_hex(3).upper()}"),
    ])
    start = _utcnow() - dt.timedelta(minutes=5)
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[x509.IPAddress(n) for n in PERMITTED_NETWORKS]
            # Only names under the reserved ".invalid" domain, which never resolves: in
            # practice, no DNS names at all.
            + [x509.DNSName("invalid")],
            excluded_subtrees=None), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA256())
    )
    _write(files.ca_key, _key_pem(key), private=True)
    _write(files.ca_cert, cert.public_bytes(serialization.Encoding.PEM), private=False)
    # Any old server certificate was signed by a CA that's gone now.
    for p in (files.server_cert, files.server_key):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    log.info("created a new local CA (%s)", fingerprint(cert))
    return cert, key


def _server_cert_ok(files: CertFiles, address: str, ca: x509.Certificate) -> bool:
    try:
        cert = x509.load_pem_x509_certificate(files.server_cert.read_bytes())
        key = serialization.load_pem_private_key(files.server_key.read_bytes(), password=None)
    except (OSError, ValueError):
        return False
    try:
        cert.verify_directly_issued_by(ca)
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except Exception:
        return False
    return (
        cert.public_key().public_numbers() == key.public_key().public_numbers()  # type: ignore[union-attr]
        and ipaddress.ip_address(address) in sans.get_values_for_type(x509.IPAddress)
        and cert.not_valid_after_utc - _utcnow() > RENEW_BEFORE
    )


def ensure_server_cert(files: CertFiles, address: str) -> tuple[str, str]:
    """Return (certfile, keyfile) for an HTTPS listener on ``address``, issuing one if needed.

    The certificate file holds the server certificate followed by the CA, so phones that
    trust the CA get the complete chain.
    """
    if not address_allowed(address):
        raise ValueError("A secure connection only works on a home-network address (10.x, 172.16-31.x or 192.168.x).")
    ca, ca_key = ensure_ca(files)
    if not _server_cert_ok(files, address, ca):
        key = ec.generate_private_key(ec.SECP256R1())
        start = _utcnow() - dt.timedelta(minutes=5)
        cert = (
            x509.CertificateBuilder()
            # Not the address itself: verifiers treat a hostname-like CN as a DNS name, which
            # the CA's name constraints (rightly) forbid. The SAN carries the address.
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Proseway on {address}")]))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(start)
            .not_valid_after(min(start + dt.timedelta(days=SERVER_DAYS), ca.not_valid_after_utc))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]),
                           critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False,
                                         content_commitment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=False, crl_sign=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                           critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _write(files.server_key, _key_pem(key), private=True)
        chain = cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM)
        _write(files.server_cert, chain, private=False)
        log.info("issued a server certificate for %s", address)
    return str(files.server_cert), str(files.server_key)


def fingerprint(cert: x509.Certificate) -> str:
    """SHA-256 fingerprint as phones show it: colon-separated hex pairs."""
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


def ca_info(files: CertFiles) -> dict | None:
    """Public facts about the existing CA, without creating one."""
    loaded = _load_ca(files)
    if not loaded:
        return None
    cert = loaded[0]
    return {"fingerprint": fingerprint(cert), "name": cert.subject.rfc4514_string(),
            "expiresAt": cert.not_valid_after_utc.timestamp()}


def ca_der(files: CertFiles) -> bytes:
    """The CA certificate in DER form, the format phones install most readily from a .crt file."""
    cert, _key = ensure_ca(files)
    return cert.public_bytes(serialization.Encoding.DER)

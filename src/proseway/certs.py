"""A small local certificate authority, so a paired phone can use HTTPS.

Phones only treat a page as a *secure context* (installable PWA, service worker, offline
reading) when it comes over HTTPS with a certificate they trust. A home network address like
``192.168.1.20`` can't get a public certificate, so Proseway makes its own:

* a **CA certificate** that the user trusts once on each phone, and
* a **server certificate** for the chosen LAN address (the address is the SAN), signed by it.

The CA is deliberately useless for anything else. Each address gets its own CA, and that
CA's *name constraints* (a critical extension) allow exactly that one IPv4 address and nothing
else: no other address on the network (so not the router, a NAS or a printer), no DNS names,
no email addresses, no URIs. Even a stolen CA key can't impersonate a website, another device,
or a mail sender to a phone that trusts it.

Private keys are owner-only: created 0600 in a 0700 folder on macOS and Linux, and with an
explicit owner-only access list on Windows (where ``chmod`` can't do this).

A CA is only ever created when none exists for that address. A damaged or expired one is an
error the user has to resolve (``proseway --new-phone-certificate``), because a silently
replaced CA would make every phone that trusted the old one stop connecting.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
import secrets
import shutil
import sys
import threading
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

# Addresses that may get a CA at all (each CA then covers only its own address).
PERMITTED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
]
# A name under the reserved ".invalid" top-level domain never exists. Permitting only it is
# the standard way to say "no names of this type at all".
NO_NAMES = "invalid"

_lock = threading.Lock()


class CertError(ValueError):
    """The certificate files can't be used; the message says what to do."""


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


def files_for(root: Path, address: str) -> CertFiles:
    """The certificate folder for one address (each address has its own CA)."""
    if not address_allowed(address):
        raise CertError("A secure connection only works on a home-network address (10.x, 172.16-31.x or 192.168.x).")
    return CertFiles(Path(root) / str(ipaddress.ip_address(address)))


def address_allowed(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and any(ip in n for n in PERMITTED_NETWORKS)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# -- owner-only files ------------------------------------------------------------------------

def _windows_owner_only(path: Path, inherit: bool) -> None:
    """Replace the file's or folder's access list with: this user and SYSTEM, full control.

    ``chmod`` on Windows only toggles the read-only flag, so with a data folder outside the
    user profile (another drive, say) other accounts could otherwise read the CA key.
    Administrators can still take ownership; nothing on Windows prevents that.
    """
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi32.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def fail(what: str) -> OSError:
        return ctypes.WinError(ctypes.get_last_error(), what)

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        raise fail("OpenProcessToken")
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # 1 = TokenUser
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise fail("GetTokenInformation")
        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER.User.Sid
        sid_str = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str)):
            raise fail("ConvertSidToStringSidW")
        sid = sid_str.value
        kernel32.LocalFree(sid_str)
    finally:
        kernel32.CloseHandle(token)

    flags = "OICI" if inherit else ""
    sddl = f"D:P(A;{flags};FA;;;{sid})(A;{flags};FA;;;SY)"  # P = protected: no inherited entries
    sd = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
        raise fail("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    try:
        # DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
        if not advapi32.SetFileSecurityW(str(path), 0x00000004 | 0x80000000, sd):
            raise fail("SetFileSecurityW")
    finally:
        kernel32.LocalFree(sd)


def _owner_only(path: Path, directory: bool = False) -> None:
    if sys.platform == "win32":
        try:
            _windows_owner_only(path, inherit=directory)
        except OSError as exc:
            log.warning("couldn't restrict access to %s: %s", path, exc)
    else:
        try:
            os.chmod(path, 0o700 if directory else 0o600)
        except OSError as exc:
            if not directory:
                raise
            log.warning("couldn't restrict access to %s: %s", path, exc)


def _write(path: Path, data: bytes, private: bool) -> None:
    """Write atomically; private files are restricted before any data goes in."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    mode = 0o600 if private else 0o644
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), mode)
    try:
        with os.fdopen(fd, "wb") as fh:
            if private:
                _owner_only(tmp)
            fh.write(data)
        if not private:
            os.chmod(tmp, mode)
        os.replace(tmp, path)  # a rename keeps the access list
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _ensure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    _owner_only(d, directory=True)


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


# -- the CA ------------------------------------------------------------------------------------

def _damaged(files: CertFiles, why: str) -> CertError:
    return CertError(
        f"Proseway's phone certificate in {files.dir} can't be used ({why}). "
        "Run `proseway --new-phone-certificate` to replace it; each phone then has to trust the new one."
    )


def _load_ca(files: CertFiles) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey] | None:
    """The CA for this folder, or None if there isn't one yet. Raises CertError if it's unusable."""
    has_cert, has_key = files.ca_cert.exists(), files.ca_key.exists()
    if not has_cert and not has_key:
        return None
    if not (has_cert and has_key):
        raise _damaged(files, "a file is missing")
    try:
        cert = x509.load_pem_x509_certificate(files.ca_cert.read_bytes())
        key = serialization.load_pem_private_key(files.ca_key.read_bytes(), password=None)
    except (OSError, ValueError) as exc:
        raise _damaged(files, f"unreadable: {exc}") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise _damaged(files, "unexpected key type")
    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        raise _damaged(files, "the key doesn't match the certificate")
    if cert.not_valid_after_utc - _utcnow() < RENEW_BEFORE:
        raise _damaged(files, "it has expired or is about to")
    return cert, key


def _new_ca(address: str) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    # A random suffix keeps two installs (two computers) from showing the same name on a phone.
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Proseway"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"Proseway local CA {secrets.token_hex(3).upper()} ({address})"),
    ])
    start = _utcnow() - dt.timedelta(minutes=5)
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
            permitted_subtrees=[
                x509.IPAddress(ipaddress.ip_network(f"{address}/32")),
                x509.DNSName(NO_NAMES),
                x509.RFC822Name(NO_NAMES),
                x509.UniformResourceIdentifier(NO_NAMES),
            ],
            excluded_subtrees=None), critical=True)
        # Server authentication only. Not every verifier applies a CA's EKU to what it
        # signs, so this is defence in depth on top of the name constraints.
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def ensure_ca(files: CertFiles, address: str) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Load the CA for ``address``, creating it only if none exists. A new CA must be trusted again."""
    with _lock:
        _ensure_dir(files.dir)
        loaded = _load_ca(files)
        if loaded:
            if ipaddress.ip_network(f"{address}/32") not in _permitted_ips(loaded[0]):
                raise _damaged(files, "it belongs to a different address")
            return loaded
        cert, key = _new_ca(address)
        _write(files.ca_key, _key_pem(key), private=True)
        _write(files.ca_cert, cert.public_bytes(serialization.Encoding.PEM), private=False)
        for p in (files.server_cert, files.server_key):  # signed by a CA that's gone
            p.unlink(missing_ok=True)
        # Re-read what is on disk: if another process raced us, use (or reject) its files
        # rather than serving a certificate whose key isn't the one stored.
        loaded = _load_ca(files)
        if loaded is None or loaded[0] != cert:
            raise _damaged(files, "another process changed it while it was being created")
        log.info("created a new local CA for %s (%s)", address, fingerprint(cert))
        return cert, key


def _permitted_ips(ca: x509.Certificate) -> list:
    nc = ca.extensions.get_extension_for_class(x509.NameConstraints).value
    return [g.value for g in (nc.permitted_subtrees or []) if isinstance(g, x509.IPAddress)]


# -- the server certificate ----------------------------------------------------------------

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


@dataclass(frozen=True)
class Issued:
    certfile: str
    keyfile: str
    ca: x509.Certificate

    @property
    def ca_der(self) -> bytes:
        return self.ca.public_bytes(serialization.Encoding.DER)

    @property
    def ca_info(self) -> dict:
        return info(self.ca)


def ensure_server_cert(root: Path, address: str) -> Issued:
    """Certificate and key files for an HTTPS listener on ``address``, issuing them if needed.

    The certificate file holds the server certificate followed by the CA, so phones that
    trust the CA get the complete chain. The returned CA is the one that signed it, so what
    Proseway shows and serves always matches what the listener presents.
    """
    files = files_for(root, address)
    ca, ca_key = ensure_ca(files, address)
    with _lock:
        if not _server_cert_ok(files, address, ca):
            key = ec.generate_private_key(ec.SECP256R1())
            start = _utcnow() - dt.timedelta(minutes=5)
            cert = (
                x509.CertificateBuilder()
                # Not the address itself: verifiers treat a hostname-like CN as a DNS name,
                # which the CA's name constraints (rightly) forbid. The SAN carries the address.
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
    return Issued(str(files.server_cert), str(files.server_key), ca)


def fingerprint(cert: x509.Certificate) -> str:
    """SHA-256 fingerprint as phones show it: colon-separated hex pairs."""
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


def info(cert: x509.Certificate) -> dict:
    """Public facts about a CA certificate, for the dialog and the setup page."""
    return {"fingerprint": fingerprint(cert), "name": cert.subject.rfc4514_string(),
            "expiresAt": cert.not_valid_after_utc.timestamp()}


def remove_all(root: Path) -> int:
    """Delete every local CA and server certificate. Returns how many addresses had one."""
    root = Path(root)
    if not root.exists():
        return 0
    count = sum(1 for d in root.iterdir() if d.is_dir() and (d / "ca.pem").exists())
    shutil.rmtree(root)
    return count

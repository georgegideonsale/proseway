# 5. Phone reading: opt-in LAN sharing with pairing, plus EPUB export

- Status: accepted
- Date: 2026-11-21

## Context

The original problem is reading on a phone. The options we researched:

- **(a) A responsive reader served over home Wi-Fi.** Live access to the whole library and notes. Needs network exposure.
- **(b) An installable PWA.** Service workers only run in a *secure context*. `http://192.168.x.x` isn't one, so a PWA on the phone needs HTTPS with a certificate the phone trusts.
- **(c) EPUB export.** Works offline in any EPUB app. Highlights made there stay in that app.

## Decision

Ship (a) and (c) now, and leave (b) as a documented option for later.

- Network access is **off by default** and **off again at every launch**. Proseway only binds `127.0.0.1`.
- "Read on your phone" starts a *second* listener bound to one chosen private LAN address, never `0.0.0.0`. It switches itself off after a chosen time (default 2 hours).
- **Pairing:** the desktop shows a QR code, whose one-time token sits in the URL fragment, and a 6-digit code. Codes expire after 5 minutes and are single-use. Each device gets 8 wrong guesses per 5 minutes, and pairing locks for everyone after 30. Requests are marked as coming from the LAN by the listener itself, not by comparing addresses. A successful pairing sets a random 256-bit device token in an `HttpOnly; SameSite=Strict` cookie. Only its SHA-256 is stored. Devices can be revoked.
- **On the LAN listener:**
  - Every API call needs a valid device cookie.
  - Only reading, searching, annotating and position endpoints are allowed.
  - Imports, deletions, sharing control, backup and restore stay local-only.
- **Both listeners check:**
  - the `Host` header, against DNS rebinding;
  - a custom `X-Proseway` header and the `Origin` on every write, against CSRF.
- **Response headers:** a strict CSP and `nosniff`.
- **EPUB 3 export:** written by us, because EbookLib is AGPL. Page-break markers are kept, so citations still work.

## Consequences

- On an untrusted shared network, plain HTTP can be sniffed. The UI says to use this on a trusted home network, and SECURITY.md describes the risk.
- The phone needs the computer to be on. Offline phone reading is EPUB, for now.

## Update (v0.2): optional HTTPS, which makes (b) possible

- Status: accepted
- Date: 2026-11-21

### Decision

Sharing can run over HTTPS ("Secure connection (recommended)", ticked by default in the dialog). Plain HTTP stays available as an opt-in fallback.

- **Certificates, one CA per address.** For each LAN address it shares on, Proseway makes a local CA (ECDSA P-256, 10 years) and a server certificate signed by it (SAN = that IP only, 397 days, renewed automatically within 30 days of expiry). They live in `<data dir>/certs/<address>/`, private keys owner-only (`0600`/`0700` on POSIX, an explicit owner-and-SYSTEM access list on Windows). Code: `src/proseway/certs.py`.
- **The CA is name-constrained to that one address** (critical extension): permitted subtrees are the address as a `/32`, and the reserved `invalid` name for DNS names, email addresses and URIs, which in practice means none. A stolen CA key can't be used against a phone that trusts it to impersonate websites, other devices on the same network (the router, a NAS), public addresses or mail senders. The CA also has an EKU of server authentication only. The server certificate's CN is deliberately not the IP, because verifiers treat a hostname-like CN as a DNS name and the constraints would reject it.
- **A CA is only created when none exists for the address.** A damaged, mismatched, misplaced or expiring one is an error that points to `proseway --new-phone-certificate`; it is never replaced silently, and nothing a phone requests creates one. Creation is serialised in-process, and the files are re-read after writing so a concurrent writer is detected rather than silently mixed.
- **Trusting the CA once per phone.** While secure sharing is on, a second plain-HTTP listener on the next port serves only an instructions page and `proseway-ca.crt` (DER). The desktop dialog shows a QR code for it and the CA's SHA-256 fingerprint, and the computer can also download the certificate (`/api/sharing/ca.crt`, local only) to send it another way.
- **Cookies are separate per scheme.** Over HTTPS the device cookie is `__Host-pw_device` (`Secure; HttpOnly; SameSite=Strict; Path=/`, no `Domain`); over plain HTTP it stays `pw_device`. HTTPS tokens are stored as `sha256("https:" + token)`, plain ones as `sha256(token)` as before, so each listener only accepts tokens issued on its own scheme. That needs no schema change, and existing (plain-HTTP) pairings keep working. Without the split, a browser holding a `Secure` cookie refuses to let the plain-HTTP origin overwrite it, so re-pairing over the fallback silently used up the code; and a token issued in clear text would have been accepted over HTTPS.
- **TLS settings.** `ssl_ciphers = "ECDHE+AESGCM:ECDHE+CHACHA20"` (uvicorn's default is `"TLSv1"`, which also offers CBC suites); TLS 1.3 suites are unaffected.
- **What the dialog and setup page show** is a snapshot of the CA that signed the running listener's certificate, taken when sharing was turned on. Replacing the CA on disk while sharing is on can't make them show or serve a certificate the listener isn't presenting.
- **Service worker:** registers whenever `isSecureContext` is true, which on a phone now means "secure sharing with the CA trusted". No separate switch. Book data, images included, is network-first (only content-hashed build assets are cache-first), so a revoked phone that can reach the computer gets a 401 instead of cached pages. The 401 carries `Clear-Site-Data: "cache", "storage"`, and the service worker and the page also delete their caches on a 401 or on a "not paired" session.
- **Replacing the CA:** `proseway --new-phone-certificate`.

### Alternatives considered

- **A self-signed server certificate that the phone trusts directly.** Simpler, but it must be re-trusted whenever the LAN address changes, and a self-signed *leaf* can't carry name constraints, so a leaked key would be unconstrained.
- **mkcert-style unconstrained CA.** Same user steps, much worse failure mode.
- **One CA for all private ranges (the first v0.2 draft).** No re-trusting when the address changes, but a leaked key could impersonate any private-address device the phone talks to, on any network. Rejected in review.
- **One CA constrained to the current subnet.** Survives DHCP changes within the subnet, but still covers the router and every other device on it. A `/32` per address costs the same re-trust on a subnet change and covers nothing else.
- **Public certificates via a DNS name (e.g. a wildcard for `*.local-ip` services) or ACME.** Needs an outside service and internet access, which contradicts "nothing leaves your computer".
- **Serving the CA over the HTTPS listener itself.** The phone would have to click through a certificate warning first, which teaches the wrong habit and protects nothing extra.

### Consequences

- The user has a real one-time step on each phone (iOS: install a profile, then enable full trust; Android: install a CA certificate from settings). We say so plainly in the dialog, the setup page and the README.
- The setup page is plain HTTP, so an attacker actively on the network at that moment could swap the certificate, and theirs would carry no name constraints at all: the phone would trust them for every website. The fingerprint check and the "send it from the computer" path (recommended on the setup page and in the dialog) are the mitigations; SECURITY.md states the worst case.
- When the computer's address changes, phones have to trust a new CA (switching back reuses the old one). A phone can end up with several Proseway CAs installed, each limited to one address.
- A phone that uses both secure and plain-HTTP sharing pairs once for each; each pairing is a separate device in the list. Pairing over the plain-HTTP fallback works normally even while the phone holds the HTTPS cookie.
- Unpairing can't wipe a phone that never reaches the computer again; its offline copies stay until it does (or the user clears them).
- No HSTS: the listener is an IP address that may later serve plain HTTP, and HSTS would lock the phone out.
- Unverified until tried on real phones: iOS/Android certificate install flows, name-constraint enforcement on each platform, PWA install and offline reading over the LAN. See `docs/progress/https-sharing.md`.

### Also in v0.2 (server hardening)

- Request body limits now hold for bodies without a `Content-Length` (chunked): a pure ASGI middleware counts bytes as they arrive and answers 413 at the limit, before a multipart parser spools the rest. Paired phones are capped at 1 MB per request.

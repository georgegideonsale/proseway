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

- **Certificates.** Proseway makes a local CA (ECDSA P-256, 10 years) and, for the chosen LAN address, a server certificate signed by it (SAN = that IP only, 397 days, renewed automatically within 30 days of expiry or when the address changes). Both live in `<data dir>/certs`, private keys owner-only. A new address reuses the same CA, so phones don't need to trust anything again. Code: `src/proseway/certs.py`.
- **The CA is name-constrained** (critical extension): it may only vouch for private and loopback IPv4 ranges and for no DNS names (permitted DNS subtree: the reserved `invalid` domain). A stolen CA key can't be used against a phone to impersonate real websites. The server certificate's CN is deliberately not the IP, because verifiers treat a hostname-like CN as a DNS name and the constraints would reject it.
- **Trusting the CA once per phone.** While secure sharing is on, a second plain-HTTP listener on the next port serves only an instructions page and `proseway-ca.crt` (DER). The desktop dialog shows a QR code for it and the CA's SHA-256 fingerprint, and the computer can also download the certificate (`/api/sharing/ca.crt`, local only) to send it another way.
- **Cookie:** `Secure` over HTTPS (already the rule; now it applies).
- **Service worker:** registers whenever `isSecureContext` is true, which on a phone now means "secure sharing with the CA trusted". No separate switch.
- **Replacing the CA:** `proseway --new-phone-certificate`.

### Alternatives considered

- **A self-signed server certificate that the phone trusts directly.** Simpler, but it must be re-trusted whenever the LAN address changes, and a self-signed *leaf* can't carry name constraints, so a leaked key would be unconstrained.
- **mkcert-style unconstrained CA.** Same user steps, much worse failure mode.
- **Public certificates via a DNS name (e.g. a wildcard for `*.local-ip` services) or ACME.** Needs an outside service and internet access, which contradicts "nothing leaves your computer".
- **Serving the CA over the HTTPS listener itself.** The phone would have to click through a certificate warning first, which teaches the wrong habit and protects nothing extra.

### Consequences

- The user has a real one-time step on each phone (iOS: install a profile, then enable full trust; Android: install a CA certificate from settings). We say so plainly in the dialog, the setup page and the README.
- The setup page is plain HTTP, so an attacker actively on the network at that moment could swap the certificate. The fingerprint check and the "download on the computer" path are the mitigations; SECURITY.md describes the risk.
- A phone paired over HTTPS holds a `Secure` cookie, which it won't send over plain HTTP. Switching a phone back to plain-HTTP sharing means pairing again.
- No HSTS: the listener is an IP address that may later serve plain HTTP, and HSTS would lock the phone out.
- Unverified until tried on real phones: iOS/Android certificate install flows, name-constraint enforcement on each platform, PWA install and offline reading over the LAN. See `docs/progress/https-sharing.md`.

### Also in v0.2 (server hardening)

- Request body limits now hold for bodies without a `Content-Length` (chunked): a pure ASGI middleware counts bytes as they arrive and answers 413 at the limit, before a multipart parser spools the rest. Paired phones are capped at 1 MB per request.

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
- **Pairing:** the desktop shows a QR code, whose one-time token sits in the URL fragment, and a 6-digit code. Codes expire after 5 minutes, are single-use, and lock after 8 failures in 5 minutes. A successful pairing sets a random 256-bit device token in an `HttpOnly; SameSite=Strict` cookie. Only its SHA-256 is stored. Devices can be revoked.
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

# HTTPS phone sharing + server hardening (branch `claude/https-sharing-4902f2`)

Worker notes for the v0.2 "https-sharing" task. PROGRESS.md is untouched; the coordinator
folds this in.

## What changed

- **`src/proseway/certs.py` (new):** a local CA (ECDSA P-256, 10 years) plus a server
  certificate for the chosen LAN IP (SAN = that IP only, 397 days, reissued within 30 days of
  expiry, when the IP changes, or when the CA changes). The CA has critical name constraints:
  only `10/8`, `172.16/12`, `192.168/16`, `127/8`, and no DNS names (permitted DNS subtree is
  the reserved `invalid`). Keys are written atomically and created `0600`; the folder is
  `0700`. Stored in `<data dir>/certs/`.
- **`sharing.py`:** `enable(..., secure=True)` issues/loads the certificate and starts the LAN
  listener with TLS (the existing `ssl_files` hook). In secure mode a second, plain-HTTP
  listener on port+1 serves only `/` (iPhone and Android steps, CA name and SHA-256
  fingerprint) and `/proseway-ca.crt` (DER, `application/x-x509-ca-cert`). It checks the Host
  header, allows only GET/HEAD, sends a `default-src 'none'` CSP, and stops with sharing. If
  port+1 is busy, sharing still starts, and the dialog offers the download from the computer
  instead. `public_state()` adds `secure`, `secureAvailable`, `setupUrl`, `ca`.
- **`server.py`:**
  - `POST /api/sharing` takes `secure`.
  - New local-only `GET /api/sharing/ca.crt`.
  - `GET /api/sharing/qr.svg?target=setup` serves the setup-page QR code.
  - The device cookie was already `Secure` when the scheme is https; it now actually applies.
  - New **`BodyLimit` ASGI middleware**: refuses a declared Content-Length over the limit
    (and a malformed one, with a 400). It counts chunked bodies as they arrive and answers
    413 at the limit; the app then sees a disconnect, so the multipart parser stops spooling.
  - Limits: `/api/books` 1 GB + 10 MB, `/api/restore` 50 MB + 1 MB, other local requests
    20 MB, **anything from a paired phone 1 MB**. The old Content-Length-only check in `guard`
    is gone.
- **`cli.py`:** `proseway --new-phone-certificate` replaces the CA and prints the new
  fingerprint.
- **EPUB language:** `extract.read_metadata` now also returns the catalog `/Lang`, through
  pdfium's `FPDFCatalog_GetLanguage`; only those lines changed in `extract.py`. `epub.py`
  writes it as `dc:language` and as `lang`/`xml:lang` on each chapter, if it looks like a
  BCP 47 tag; otherwise it writes `und`. It never guesses from the text.
- **Web:**
  - `SharingDialog.tsx` has a "Secure connection (recommended)" checkbox, ticked by default
    and remembered in localStorage.
  - In secure mode the dialog shows a "First time on this phone? Set up this phone" step,
    which switches the QR code to the setup page, shows the fingerprint grouped in fours,
    and offers a "Download the certificate" link.
  - The dialog explains plain HTTP honestly.
  - `main.tsx` already registered the service worker only when `isSecureContext`; the
    comment now says that's what makes it work on a phone over secure sharing.
  - Types and the API client were updated.
- **Docs:** SECURITY.md (secure and plain sections, limits, the TOFU risk of the setup page),
  ADR 0005 (an update section with the alternatives considered), README phone section, and
  `docs/research/licenses.md` (cryptography is now a direct dependency; it was already pulled
  in by pdfminer.six).
- **Dependency:** `cryptography>=42` in core dependencies. `uv.lock` was updated; no new
  packages were installed.

## Verified (Working)

- `uv run pytest`: **60 passed, 1 skipped**. The skip is the POSIX key-permission test on
  Windows; it runs on Linux/macOS CI. New tests:
  - `tests/test_certs.py`:
    - SAN is the IP only, and the chain is leaf then CA.
    - EKU serverAuth, and the private key matches.
    - Validity: leaf ≤ 397 days, CA ≥ 3000 days.
    - CA BasicConstraints and NameConstraints are critical.
    - **A certificate forged with the CA key for `example.com` or `8.8.8.8` fails
      verification** (cryptography's verifier).
    - Public IPs are refused.
    - Reuse, re-issue on IP change (same CA), renewal near expiry, and replacement of an
      unreadable CA.
    - `0600`/`0700` permissions (POSIX only).
    - DER download and fingerprint.
  - `tests/test_sharing_tls.py`:
    - Starts the real uvicorn LAN listener over TLS on 127.0.0.1 and verifies it with
      `ssl.create_default_context(cadata=<our CA>)`, with hostname checking on. **OpenSSL
      3.5 enforces the name constraints here.** The first version put the IP in the leaf
      CN, and OpenSSL rejected it with "permitted subtree violation"; the CN is now
      "Proseway on <ip>".
    - An untrusting client is refused.
    - Pairing over TLS sets a `Secure; HttpOnly` cookie that then works.
    - The setup page serves HTML with the fingerprint and the exact CA bytes; it returns
      404 for anything else, 405 for POST and 421 for a foreign Host.
    - `/api/sharing/ca.crt` is reachable locally and gets 403 from a phone.
    - Both listeners are gone after disable.
    - Plain-HTTP mode still works and has no setup page.
  - `tests/test_api.py`:
    - Chunked (no Content-Length) uploads to `/api/books` and `/api/restore` over the limit
      get 413 `too_large`, with security headers, and nothing is stored.
    - A declared length over the limit gets 413.
    - A malformed Content-Length gets 400.
    - Small chunked JSON still works.
    - A paired phone's 2 MB JSON gets 413, both declared and chunked, while a 20,000-char
      note still saves.
    - EPUB `dc:language` is `und` without metadata and `de-AT` when the PDF's `/Lang` says
      so.
- `uv run ruff check .`: clean.
- `pnpm --dir web build` (tsc and vite): clean. `pnpm --dir web test` (vitest): 8 passed.
- Playwright, new `web/e2e/sharing.spec.ts`:
  - It mocks `/api/sharing`, because CI may have no LAN address.
  - It checks that secure is ticked by default and that turning on posts `secure: true`.
  - It checks the pairing code, the setup QR code with its fingerprint, and back.
  - It checks that unticking posts `secure: false` and is remembered.
  - An axe audit runs in each state.
  - **Passed on desktop and on phone** (Pixel 7) when run on its own. Screenshots of the
    off, on and setup states were reviewed by eye.
- Full Playwright `--project=desktop`: **9 passed**. The first attempt hit the machine's
  "Unable to create process" spawn quirk in the fixture step; the retry passed.
- Full Playwright `--project=phone`: **not cleanly green on this machine today.** Several
  runs failed with `browserContext.newPage: Target crashed`, and servers failed to start,
  in specs this branch doesn't touch (`reading.spec.ts`, `a11y.spec.ts`) as well as the new
  one. Free RAM was ~880 MB while other sessions ran their own suites. Please re-run the
  phone project on CI or on a quieter machine.

## Needs a real phone (Untested)

- **iOS:**
  - Safari downloads `proseway-ca.crt` (DER, `application/x-x509-ca-cert`) as a profile.
  - It installs under VPN & Device Management.
  - Full trust can be enabled in Certificate Trust Settings.
  - The HTTPS listener then loads without a warning.
- **Android:**
  - The CA installs under Encryption & credentials → CA certificate.
  - Chrome accepts the IP-SAN leaf from a user-installed, name-constrained CA.
  - Samsung Internet behaves the same.
  - Firefox needs "Use third party CA certificates".
- **Name-constraint enforcement on phones.** OpenSSL and cryptography enforce it, but iOS
  and Android verifiers haven't been checked against a forged certificate. Also check that
  a critical NameConstraints extension doesn't make either platform refuse the CA
  outright.
- **PWA:** "Add to Home Screen" or "Install app" over `https://<lan-ip>:<port>`, then the
  service worker registering and offline reading of opened chapters with the computer
  switched off.
- **Fingerprint display:** that the fingerprint the phone shows (iOS: profile → More
  Details; Android: Trusted credentials → User) matches the dialog's format.
- **Windows Firewall:** the "allow access" prompt for the second (setup) port.

## Open issues and follow-ups

- **Windows key permissions:** on Windows, key files rely on the user-profile ACL
  (`os.chmod` only toggles read-only). Tightening with an explicit ACL is possible but
  wasn't done.
- **Plain-HTTP setup page (TOFU):** an active attacker on the network at setup time could
  swap the certificate. Mitigations: the fingerprint check, and downloading on the computer
  to transfer it another way. Documented in SECURITY.md.
- **Batched imports (pre-existing):** a batch import of several PDFs is one request, so the
  1 GB + 10 MB limit applies to the whole batch, not per file. Unchanged; it could be fixed
  by uploading one file per request in `api.importBooks`.
- **Re-pairing after switching back:** a phone paired over HTTPS has a `Secure` cookie, so
  switching that phone back to plain-HTTP sharing means pairing again. The ADR notes this;
  the UI doesn't say it.
- **e2e ports:** `sharing.spec.ts` uses 18781/18782, because 18769/18770 were already used
  by another branch's e2e server during this work. The coordinator may want to allocate e2e
  ports per spec in one place.

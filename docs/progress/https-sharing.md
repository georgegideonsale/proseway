# HTTPS phone sharing + server hardening (branch `claude/https-sharing-4902f2`)

Worker notes for the v0.2 "https-sharing" task. PROGRESS.md is untouched; the coordinator
folds this in.

## What changed

- **`src/proseway/certs.py` (new):**
  - One local CA per LAN address (ECDSA P-256, 10 years) plus a server certificate for that
    address (SAN = the IP only, 397 days, reissued within 30 days of expiry).
  - Stored in `<data dir>/certs/<address>/`.
  - The CA has critical name constraints: exactly that IP as a `/32`, plus `invalid` for DNS
    names, email addresses (rfc822Name) and URIs, which permits no names of those kinds. Its
    EKU is serverAuth only.
  - A CA is created only when neither file exists. A damaged, mismatched, misplaced or
    expiring CA raises `CertError`, which points to `--new-phone-certificate`; it is never
    re-minted silently.
  - Creation holds a lock, and the files are re-read after writing.
  - Keys are written atomically and restricted before any data goes in: `0600` in a `0700`
    folder on POSIX; on Windows a protected access list (current user + SYSTEM) set with
    `SetFileSecurityW`.
- **`sharing.py`:**
  - `enable(..., secure=True)` issues or loads the certificate and starts the LAN listener
    with TLS, `ssl_ciphers="ECDHE+AESGCM:ECDHE+CHACHA20"`.
  - It keeps a snapshot (`self.issued`) of the CA that signed the running certificate. The
    dialog's fingerprint, `/api/sharing/ca.crt` and the setup page all use it, never the
    files on disk.
  - In secure mode a second, plain-HTTP listener on port+1 serves only `/` (iPhone and
    Android steps, the fingerprint, and the worst case if the page is tampered with) and
    `/proseway-ca.crt`. It is skipped if port+1 > 65535.
  - Ports outside 1-65535 are refused.
  - **Cookies are split by scheme.** Over HTTPS the cookie is `__Host-pw_device` and the token
    is stored as `sha256("https:"+token)`. Over HTTP it stays `pw_device` with
    `sha256(token)`, so existing pairings keep working. Each listener reads only its own
    cookie name and hash domain, via `device_for(scope, cookies)`, and the scheme comes from
    the listener's own scope mark. No DB schema change.
- **`server.py`:**
  - `POST /api/sharing` takes `secure`.
  - Local-only `GET /api/sharing/ca.crt` returns 404 when secure sharing is off.
  - `qr.svg?target=setup`.
  - The pair route sets the cookie for its scheme.
  - The LAN `not_paired` 401 and an unpaired `/api/session` send
    `Clear-Site-Data: "cache", "storage"`.
  - **`BodyLimit` ASGI middleware:**
    - It refuses a declared or chunked body over the limit with 413, and a bad Content-Length
      with 400.
    - Limits: `/api/books` 1 GB + 10 MB, `/api/restore` 50 MB + 1 MB, other local requests
      20 MB, anything from a paired phone 1 MB.
- **`cli.py`:** `proseway --new-phone-certificate` deletes every per-address CA. A new one is
  made the next time secure sharing is turned on.
- **EPUB language:**
  - `epub.py` reads the catalog `/Lang` with pdfminer (pure Python, `fallback=False`). It is
    written as `dc:language` and as `lang`/`xml:lang` on each chapter if it looks like a BCP 47
    tag, else `und`.
  - **`pipeline/extract.py` is back to main**: this branch no longer touches `pipeline/`.
    Export runs on the threadpool and is reachable by a phone, so it must not use pdfium (not
    thread-safe). A test makes any pdfium use during export fail.
- **Web:**
  - `SharingDialog.tsx` has the secure checkbox, ticked by default and remembered. The hint is
    now a separate paragraph referenced by `aria-describedby`, so it isn't read twice.
  - The setup and pairing views each have an `h3` that receives focus when the view is
    switched by "Set up this phone" or "Done, show the pairing code". That also announces the
    change.
  - Fingerprint and pairing code use visually hidden text instead of `aria-label` on
    `<code>`/`<span>`.
  - The setup step recommends sending the certificate from the computer, with a download link.
  - `api.ts` has `forgetOfflineData()`, which deletes CacheStorage on any 401 and when
    `/api/session` says a LAN client isn't paired.
- **`web/public/sw.js` (v2):**
  - Only content-hashed `/assets/` are cache-first. Book images are now network-first like
    chapters, so a revoked phone gets a 401 instead of cached images.
  - Any 401 on book data deletes every cache.
- **Docs:**
  - SECURITY.md: the one-address CA and what's left; the worst case of a tampered setup page;
    the `__Host-` cookie and scheme separation; TLS suites; Windows ACLs; no silent re-mint;
    what unpairing can't remove.
  - ADR 0005 update: decisions, the rejected "all private ranges" and "subnet" options, and
    corrected consequences; the old "pair again" claim is replaced.
  - README phone section.
  - licenses.

## Review round 2 (coordinator review): how each item was handled

1. **Cookies:** `__Host-pw_device` over HTTPS, with each device's issuing scheme recorded in
   its hash domain. HTTP-issued tokens are refused over HTTPS, and the reverse too. Re-pairing
   over the HTTP fallback works. ADR corrected.
2. **CA scope:** constrained to the one address (`/32`), which is stricter than the subnet, and
   regenerated per address (one folder each, so switching back needs no new trust). rfc822Name
   and URI are constrained to `invalid`. dirName is not constrained: it plays no part in TLS
   server authentication. Chromium (BoringSSL `pki/name_constraints.cc`) supports IP, DNS,
   rfc822 and dirName constraints, and for a critical URI constraint rejects only leaves that
   actually carry a URI SAN, so our leaves are unaffected.
3. **Docs:** the worst case (an unconstrained attacker CA means full interception) is stated
   in SECURITY.md, the setup page, the dialog, the README and the ADR. They recommend sending
   the certificate from the computer.
4. **`extract.py`:** reverted to main. `/Lang` is now read with pdfminer in `epub.py`.
5. **Service worker:** `Clear-Site-Data` on the 401 (and on an unpaired session). The SW and
   the page drop caches on a 401. Book images are network-first. What remains is documented in
   SECURITY.md.
6. **No silent CA re-mint:** the CA is created only when both files are missing; otherwise an
   error. A lock guards concurrent creation. Unpaired devices can't trigger anything:
   `/proseway-ca.crt` serves the snapshot.
7. **Windows key permissions:** an owner-only protected DACL via `SetFileSecurityW`; tested on
   Windows by reading the DACL back.
8. **TLS ciphers:** set explicitly. A mutation check (putting back uvicorn's `"TLSv1"`) makes
   the cipher test fail.
9. **Tests:** see below.
10. **Accessibility:** focus management, visually hidden labels, the hint no longer read twice.

Nits:
- The setup port is skipped above 65535, and invalid ports are refused.
- A stale fingerprint after `--new-phone-certificate` is impossible now: the snapshot is what's
  shown and served, and the CLI says to toggle sharing.

## Verified (Working)

- `uv run pytest`: **74 passed, 1 skipped**. The skip is the POSIX permission test on Windows;
  the Windows ACL test ran.
  - `tests/test_certs.py`:
    - SAN and chain.
    - Expiry.
    - The exact NameConstraints set and the CA's EKU.
    - **Certificates forged with the CA key are rejected** (cryptography verifier): for
      `example.com`, `8.8.8.8`, the router `192.168.1.1`, `10.0.0.2`, and a valid IP leaf with
      an added email or URI SAN.
    - Public, IPv6 and link-local addresses refused.
    - Reuse, separate CAs per address, renewal.
    - Damaged CA (garbage, missing key, missing cert, wrong key, folder copied to another
      address) → `CertError` and nothing on disk changed.
    - Expired CA → error.
    - 8 concurrent first uses → one CA.
    - POSIX modes; Windows DACL (`D:P`, exactly the user + SYSTEM, no Everyone, Users,
      Authenticated Users or Administrators).
    - `remove_all`.
  - `tests/test_sharing_tls.py`, over a real uvicorn TLS listener on 127.0.0.1:
    - Verified against our CA with hostname checks on; an untrusting client is refused.
    - 401 with `Clear-Site-Data`.
    - The exact cookie attributes: only `__Host-pw_device`; `Secure`, `HttpOnly`,
      `SameSite=strict`, `Path=/`, no Domain, and Max-Age.
    - The setup page (200, 404, 405, 421) mentions the worst case.
    - `ca.crt` returns 403 from the phone, and 404 when sharing is off.
    - Listeners stop.
    - **Negative tests over TLS:**
      - a wrong Host → 421;
      - a missing `X-Proseway` header → 403 `csrf`;
      - a foreign Origin → 403 `csrf`;
      - a paired phone calling DELETE book, POST/GET sharing, new-code, DELETE device or
        restore → 403 `local_only`.
    - **TLS suites:** a TLS 1.2 ECDHE-ECDSA-AES128-GCM client works; non-ECDHE suites and
      ECDHE CBC suites are refused.
    - **Scheme separation:**
      - An HTTP-issued token gets 401 over HTTPS under either cookie name.
      - Pairing over HTTPS then works.
      - The HTTPS token is refused over HTTP.
      - The HTTP pairing still works; two devices are listed.
    - Snapshot: after the CA on disk is replaced, the dialog, `ca.crt` and the setup page
      still show and serve the running CA until sharing is toggled.
    - No setup listener at port 65535; port 65536 is refused.
    - **OpenSSL's own chain check** (in-memory handshakes) rejects forged leaves for another
      IP, and for a valid IP plus an email, URI or DNS SAN, with "permitted subtree violation".
  - `tests/test_api.py`: chunked and declared body limits (413), a bad Content-Length (400),
    phone JSON caps, EPUB language `und` and `de-AT`. The `de-AT` test now also fails if
    export uses pdfium.
- `uv run ruff check .`: clean.
- `pnpm --dir web test` (vitest): **11 passed**. The new `src/api.test.ts` checks that caches
  are dropped on a 401 and on an unpaired LAN session, and kept for a paired phone, on the
  computer, and on a 403.
- `pnpm --dir web build`: clean. Two attempts crashed with 0xC0000005 (the machine quirk); the
  third passed.
- Playwright desktop, full: **9/9**. In the first full run the a11y "library (night)" test
  failed with `Target crashed` (not an axe result); rerunning `a11y.spec.ts`: 4/4.
- Playwright `sharing.spec.ts`, which now also checks the accessible name and description, the
  heading focus after each view switch, and the visually hidden fingerprint and code text:
  **2/2 on desktop and 2/2 on phone**.
- Playwright phone, full suite: not re-run in this round, because of the machine's memory
  pressure; the coordinator plans a re-run.

## Review round 3: `reading.spec.ts` failing on desktop

The coordinator saw `reading.spec.ts:59` fail ("Notes and highlights" outside the viewport),
then `:125` and `:140` time out waiting for `.book a`. It wasn't the code in c0ed17d: for the
local listener none of it changes behaviour (no 401, `forgetOfflineData` only runs for LAN
sessions, and the e2e book has no images). The cause was the **e2e harness sharing fixed ports
across worktrees.** While I investigated, port 18765 was held by
`reader-chapter-window-39d481`'s own e2e server.

- `proseway --port 18765` exits when the port is taken, but `Server.start()` only polled
  `/api/info`, got the other worktree's answer, and the test carried on against another
  branch's build and library.
- `reading.spec.ts:59` restarts the server mid-test, which opens the same window again.
- Reproduced here: with the other worktree's server on 18765, a run failed because "Test Book"
  was already in the library. In another run my new guard reported "port 18765 was taken by
  another process while the server restarted", and `:125` then timed out on `.book a`: the
  coordinator's symptom.

Fix, in `web/e2e/server.ts`:
- Each `Server` gets a free port from the OS and keeps it across restarts.
- A restart fails loudly if something else is serving on the port. This is checked by asking
  `/api/info`, not by a bind probe: on Windows, the old server's connections in TIME_WAIT make
  an exclusive bind fail even though nothing is listening. A bind-probe version gave a false
  alarm on the phone project.
- The readiness check only accepts an answer while our own process is still running.
- `PROSEWAY_E2E_FIXED_PORTS=1` brings back the ports the specs name, for debugging.
- Specs only use `server.url`, so they're unchanged.
- Regression check: run `reading.spec.ts` while something else listens on 18765. It passed
  3/3 that way, with the other worktree's server still on the port.

## Needs a real phone (Untested)

- **iOS:**
  - Safari downloads `proseway-ca.crt` as a profile.
  - It installs under VPN & Device Management.
  - Full trust is enabled in Certificate Trust Settings.
  - The HTTPS listener loads without a warning.
- **Android:**
  - The CA installs as a CA certificate.
  - Chrome accepts the IP-SAN leaf from a user-installed, name-constrained CA.
  - Samsung Internet behaves the same.
  - Firefox needs "Use third party CA certificates".
- **Name-constraint enforcement on phones**, including that a critical NameConstraints with
  `/32` IP, DNS, rfc822 and URI subtrees doesn't make either platform refuse the CA outright.
  Apple's verifier hasn't been checked at all.
- **PWA:** install, the service worker, offline reading; and that unpairing then deleting
  offline data works on a real phone (`Clear-Site-Data` support on iOS Safari is unverified).
- **Fingerprint display format** on each platform.
- **Windows Firewall** prompt for the setup port.

## Open issues and follow-ups

- **Per-address CAs:** a DHCP address change means re-trusting on each phone. A phone can
  accumulate several Proseway CAs (each limited to one address).
- **Plain-HTTP setup page (TOFU):** documented worst case; the mitigation is to send the
  certificate from the computer.
- **Concurrent `ensure_ca` across processes** (CLI and server at once) is detected, not
  prevented: the loser gets an error instead of mixed files.
- **Windows:** administrators can always take ownership. The ACL is best effort: a failure is
  logged, not fatal.
- **Batched imports (pre-existing):** one request for several PDFs, so the 1 GB + 10 MB limit
  applies to the batch.
- **e2e ports:** no longer fixed (see review round 3). If another branch also edits
  `web/e2e/server.ts`, keep the free-port logic when merging.

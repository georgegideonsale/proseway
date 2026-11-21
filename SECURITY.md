# Security

## Reporting a vulnerability

Please report security problems privately, using GitHub's **"Report a vulnerability"** button on the repository's Security tab. Don't open a public issue. We'll acknowledge reports within a week and keep you informed while we fix them.

## Threat model

Proseway is a local application. It is designed around these assumptions.

### PDFs are untrusted input

- **Parsing:** PDFs are parsed by PDFium (through pypdfium2) and pdfminer/pdfplumber, in a separate worker process. A crash or hang in a parser can't take down the server. A watchdog stops a worker that makes no progress for 3 minutes or uses more than 3 GB of memory.
- **Nothing in a PDF runs:** we never execute embedded JavaScript, forms or attachments.
- **Converted text is escaped:** it's rendered as text through React or escaped HTML in EPUB export. Nothing from the PDF is ever inserted as raw HTML.
- **Uploads:** the file must have a PDF header (`%PDF-`) in its first kilobyte and be under 1 GB. Duplicates are detected by SHA-256.
- **Password-protected PDFs** are refused with a friendly message, and so are PDFs whose author turned off text extraction.

### The local server

- **Listens on `127.0.0.1` only** unless phone sharing is switched on.
- **Every request's `Host` header is checked,** to block DNS-rebinding attacks from websites in your browser.
- **Every state-changing API request needs a custom `X-Proseway: 1` header,** and its `Origin` (if present) must match. Browsers can't send that header cross-origin without a preflight, which we never answer, so this blocks CSRF.
- **Responses carry a strict Content-Security-Policy** (`default-src 'self'`, no inline scripts, `frame-ancestors 'none'`), plus `nosniff`, `no-referrer` and `X-Frame-Options: DENY`.
- **No network requests:** the app makes none of its own, and loads no remote fonts or scripts.

### Phone sharing (opt-in)

- **Off at every launch.** When on, it binds a second listener to one chosen private LAN address, never `0.0.0.0`, and switches off after a chosen time.
- **Pairing:** a QR code with a one-time token, or a 6-digit code.
  - Codes expire after 5 minutes and work once.
  - Each device gets 8 wrong guesses per 5 minutes, so one device can't lock others out.
  - After 30 wrong guesses in total, pairing locks until you ask for a new code on the computer.
- **Device tokens:** pairing sets a random 256-bit device token in an `HttpOnly; SameSite=Strict` cookie. Only its SHA-256 is stored. Devices can be unpaired at any time.
- **Unpairing and offline copies:** when a phone that has been unpaired next reaches the computer, the server answers `401` with `Clear-Site-Data: "cache", "storage"`, and the web app and service worker delete their caches too. Browsers only honour that header over HTTPS, which is also the only place offline copies exist. What can't be removed this way: anything on a phone that never reaches the computer again (switched off, or out of Wi-Fi range), and files the phone's user exported or saved deliberately. Unpairing stops access; it can't wipe a phone remotely.
- **What a phone can reach:** only reading, search, annotation and reading-position endpoints. Importing, deleting, backups, restore, sharing control and device management are local-only.
- **Request size limits** apply whether or not a request declares its length: uploads stop at 1 GB, backups at 50 MB, other requests at 20 MB, and anything a paired phone sends at 1 MB. Chunked bodies are counted as they arrive and cut off at the limit.

#### Secure connection (HTTPS, the default)

- **A local certificate authority per address.** The first time you choose a secure connection on an address, Proseway makes a CA certificate for that address and, signed by it, a server certificate whose only name is that address. They're kept in `certs/<address>/` in your library. If your computer's address changes (another Wi-Fi network, or the router hands out a new one), it gets a new CA, and each phone has to trust that one too; switching back reuses the old one.
- **The CA can vouch for one thing only: that address.** It carries critical *name constraints* that permit exactly that one IPv4 address, and, through the reserved `.invalid` domain, no DNS names, email addresses or URIs. Even with the CA's private key, nobody could make a certificate that a phone trusting it would accept for a website, for another device on your network (your router, a NAS, a printer), for a public address, or for signing email. It also only allows server authentication (extended key usage). Tests check all of this with OpenSSL and with `cryptography`'s verifier. What's left: on *another* network where some other device happens to have the same address, a stolen key could impersonate that device to your phone.
- **Name constraints on phones are not yet verified.** We haven't yet confirmed on real iPhones and Android phones that their verifiers enforce name constraints the same way. Chrome's verifier enforces IP, DNS, email and directory-name constraints, and rejects certificates that carry a URI when a critical constraint mentions URIs. Until phones are checked, treat the CA like any root certificate you install: only on your own phones, and remove it when you stop using Proseway.
- **You have to trust the CA once on each phone, and the setup page is the weak spot.** The setup page that serves it is plain HTTP, because the phone can't trust the HTTPS listener yet. It runs on the next port, serves only the certificate and instructions, and stops with sharing. **Worst case:** someone actively tampering with your network at that moment swaps in a certificate of their own. Theirs would have *none* of the limits above, so your phone would trust them for every website, and they could read and change everything it opens until you remove that certificate. To avoid this, send the certificate from the computer when you can (the sharing window has a download link; use AirDrop, a USB cable or a file share). If you do use the setup page, compare the SHA-256 fingerprint your phone shows with the one on your computer before you trust it, and do it on a network you trust.
- **Private keys are owner-only.** They're ECDSA P-256. On macOS and Linux they're created `0600` in a `0700` folder. On Windows, Proseway replaces their access list with one that allows only your account and SYSTEM (nothing inherited), because `chmod` can't do that there; this also covers a library on another drive. Administrators can still take ownership of any file on Windows. Server certificates last 397 days and renew automatically; the CA lasts 10 years.
- **A damaged CA is never replaced silently.** If its files are missing, unreadable, mismatched, belong to another address or are about to expire, turning on secure sharing fails with a message telling you to run `proseway --new-phone-certificate`. Replacing it quietly would make every phone that trusted the old one stop connecting, and nothing a phone can request creates or replaces a CA.
- **Over HTTPS the device cookie is `__Host-pw_device`:** `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Domain`. The `__Host-` prefix makes browsers enforce those attributes, and a plain-HTTP page can't set or overwrite it. Tokens issued over HTTPS are stored hashed in their own domain, so **a token issued over plain HTTP (which may have been sniffed) is never accepted on the HTTPS listener**, and an HTTPS token isn't accepted over plain HTTP. A phone that uses both pairs once for each.
- **TLS:** TLS 1.3, or TLS 1.2 with forward-secret AEAD suites only (`ECDHE+AESGCM:ECDHE+CHACHA20`). Older protocol versions and CBC or non-ECDHE suites are refused.
- **To replace the CA** (for example if you think its key leaked), run `proseway --new-phone-certificate`, then remove the old Proseway certificate from your phones. If Proseway is running with sharing on, turn sharing off and on again; until then it keeps presenting, and showing the fingerprint of, the certificate it started with.

#### Plain HTTP (opt-in fallback)

If you untick *Secure connection*, sharing uses plain HTTP. Someone on the same network who can capture traffic could read what you're reading, and could copy a device cookie to read your library over plain HTTP until you unpair that device (that cookie never works on the secure listener). Use it only on a network you trust, and unpair devices you no longer use.

### What we don't protect against

Other software, or other users, with access to your computer account can read your library. It's stored unencrypted in your user data folder, like any other document.

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
- **What a phone can reach:** only reading, search, annotation and reading-position endpoints. Importing, deleting, backups, restore, sharing control and device management are local-only.
- **Request size limits** apply whether or not a request declares its length: uploads stop at 1 GB, backups at 50 MB, other requests at 20 MB, and anything a paired phone sends at 1 MB. Chunked bodies are counted as they arrive and cut off at the limit.

#### Secure connection (HTTPS, the default)

- **A local certificate authority.** The first time you choose a secure connection, Proseway makes its own CA certificate and, signed by it, a server certificate whose only name is the chosen LAN address. They're kept in the `certs` folder of your library. Private keys are ECDSA P-256 and are written owner-only (`0600`) on macOS and Linux. On Windows they rely on your user profile's permissions, like the rest of your library. Server certificates last 397 days and renew automatically; the CA lasts 10 years.
- **The CA can't vouch for websites.** It carries critical *name constraints* that only permit private and loopback IPv4 addresses (`10/8`, `172.16/12`, `192.168/16`, `127/8`) and no DNS names. Even if someone stole the CA's private key from your computer, a phone that trusts it would refuse their certificate for any real website or public address. (Tests check this with OpenSSL and with `cryptography`'s verifier. We haven't yet confirmed on real phones that their verifiers enforce name constraints the same way. Until then, treat the CA like any root certificate you install: only on your own phones, and remove it when you stop using Proseway.)
- **You have to trust the CA once on each phone.** The setup page that serves it is plain HTTP, because the phone can't trust the HTTPS listener yet. It runs on the next port, serves only the certificate and instructions, and stops with sharing. Someone actively tampering with your network at that moment could swap in their own certificate. That's why the computer and the setup page both show the certificate's SHA-256 fingerprint: compare it with what your phone shows before you trust it, or download the certificate on the computer and send it to the phone another way (AirDrop, USB).
- **Over HTTPS the device cookie is `Secure`,** so it's never sent in clear text, and the whole connection is encrypted.
- **To replace the CA** (for example if you think its key leaked), run `proseway --new-phone-certificate` and remove the old Proseway certificate from your phones.

#### Plain HTTP (opt-in fallback)

If you untick *Secure connection*, sharing uses plain HTTP. Someone on the same network who can capture traffic could read what you're reading, and could copy a device cookie to read your library until you unpair that device. Use it only on a network you trust, and unpair devices you no longer use.

### What we don't protect against

Other software, or other users, with access to your computer account can read your library. It's stored unencrypted in your user data folder, like any other document.

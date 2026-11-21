# Security

## Reporting a vulnerability

Please report security problems privately, using GitHub's **"Report a vulnerability"** button on the repository's Security tab. Don't open a public issue. We'll acknowledge reports within a week and keep you informed while we fix them.

## Threat model

Proseway is a local application. It is designed around these assumptions.

### PDFs are untrusted input

- **Parsing:** PDFs are parsed by PDFium (through pypdfium2) and pdfminer/pdfplumber, in a separate worker process. A crash or hang in a parser can't take down the server. A watchdog stops a worker that makes no progress for 3 minutes or uses more than 3 GB of memory.
- **Nothing in a PDF runs:** we never execute embedded JavaScript, forms or attachments.
- **Converted text is escaped:** it's rendered as text through React or escaped HTML in EPUB export. Nothing from the PDF is ever inserted as raw HTML.
- **Uploads:** the file must start with a PDF header and be under 1 GB. Duplicates are detected by SHA-256.
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
  - Eight wrong codes within 5 minutes lock pairing until you ask for a new code on the computer.
- **Device tokens:** pairing sets a random 256-bit device token in an `HttpOnly; SameSite=Strict` cookie. Only its SHA-256 is stored. Devices can be unpaired at any time.
- **What a phone can reach:** only reading, search, annotation and reading-position endpoints. Importing, deleting, backups, restore, sharing control and device management are local-only.

**Known limitation:** sharing uses plain HTTP on your local network. Someone on the same network who can capture traffic could read what you're reading, and could copy a device cookie to read your library until you unpair that device. Use sharing on a network you trust, and unpair devices you no longer use. An HTTPS option is on the roadmap.

### What we don't protect against

Other software, or other users, with access to your computer account can read your library. It's stored unencrypted in your user data folder, like any other document.

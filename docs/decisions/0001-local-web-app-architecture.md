# 1. A local Python server with a web reader

- Status: accepted
- Date: 2026-11-21

## Context

People need to install Proseway with one command on macOS, Windows and Linux and read on both a laptop and a phone. PDF conversion is CPU-heavy and has to run in the background. Everything must stay on the user's machine.

We considered three shapes:

1. A native desktop app (Tauri or Electron) with a converter sidecar.
2. A local server plus a web app, installed as a Python package.
3. A pure browser app (PDF.js plus WASM, no server).

## Decision

Option 2. `proseway` is a Python package. Its command starts a FastAPI server on `127.0.0.1` and opens the default browser. The reader is a React single-page app, built ahead of time and shipped inside the wheel, so users don't need Node.

## Consequences

- **Install:** one step (`uv tool install …` or `pipx install …`), on any OS where Python 3.10+ runs. There's no code signing or notarisation to manage.
- **Phone reading:** comes almost for free. The same web app can be served on the home network once the user turns sharing on (see ADR 0005).
- **Converter:** uses the strongest PDF tooling, which is Python's (pdfplumber, PDFium bindings, optional OCR).
- **Downside:** it feels less like a native app. We soften this with an installable PWA on `localhost`, a calm full-window reader, and auto-opening the browser.
- **Option 3 rejected:** it would need the conversion pipeline rewritten in JS/WASM, and large books would stress browser memory.

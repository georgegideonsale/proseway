"""Command line entry point: `proseway` starts the app and opens your browser."""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .paths import default_data_dir


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform != "win32":
            # Match how uvicorn binds, so a port in TIME_WAIT after a restart counts as free.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="proseway",
        description="Turn book PDFs you own into calm, reflowable reading editions. Runs only on this computer.",
    )
    parser.add_argument("--port", type=int, default=None,
                        help="local port (default 8765, or the next free one)")
    parser.add_argument("--data-dir", type=Path, default=None, help="where to keep your library")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    parser.add_argument("--new-phone-certificate", action="store_true",
                        help="replace the certificate used for secure phone sharing, then exit "
                             "(phones must trust the new one again)")
    parser.add_argument("--version", action="version", version=f"proseway {__version__}")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.new_phone_certificate:
        from . import certs

        data_dir = (args.data_dir or default_data_dir()).expanduser().resolve()
        removed = certs.remove_all(data_dir / "certs")
        print(f"  Removed {removed} certificate{'' if removed == 1 else 's'} for secure phone sharing.")
        print("  A new one is made the next time you turn on secure sharing. Remove the old Proseway")
        print("  certificate from your phones, then trust the new one.")
        print("  If Proseway is running with sharing on, turn sharing off and on again.")
        return 0

    import uvicorn

    from .server import AppConfig, create_app

    port = args.port or 8765
    if not _port_free(port):
        if args.port:
            # The user asked for this port: don't silently move somewhere else.
            print(f"Port {port} is already in use. Choose another with --port.", file=sys.stderr)
            return 1
        for candidate in range(port + 1, port + 20):
            if _port_free(candidate):
                port = candidate
                break
        else:
            print(f"Port {port} is busy. Try --port.", file=sys.stderr)
            return 1

    data_dir = (args.data_dir or default_data_dir()).expanduser().resolve()
    app = create_app(AppConfig(data_dir, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  Proseway {__version__} is running at {url}")
    print(f"  Library: {data_dir}")
    print("  Only this computer can reach it. Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Bind to loopback only. Phone sharing adds a separate, opt-in listener.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, server_header=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Start a real second (LAN) listener while the app is running.

Regression test: the LAN listener used to re-run the app's startup hook, which tried to start
the job supervisor thread a second time and made enabling sharing fail.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from fastapi.testclient import TestClient

from proseway import sharing as sharing_mod
from proseway.server import AppConfig, create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, headers: dict | None = None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_second_listener_starts_and_enforces_pairing(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing_mod, "lan_addresses", lambda: [{"interface": "test", "address": "127.0.0.1"}])
    app = create_app(AppConfig(tmp_path / "lib", 8765), start_jobs=True)
    with TestClient(app, base_url="http://127.0.0.1:8765"):  # runs the lifespan (job supervisor)
        s = app.state.sharing
        port = free_port()
        s.enable("127.0.0.1", port, minutes=5)
        try:
            base = f"http://127.0.0.1:{port}"
            assert get(base + "/api/session") == (200, {"listener": "lan", "paired": False})
            assert get(base + "/api/books")[0] == 401
        finally:
            s.disable()
        # After disabling, nothing listens there any more.
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/session", timeout=2)
            raise AssertionError("listener still running")
        except urllib.error.URLError:
            pass

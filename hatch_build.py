"""Build hook: make sure the web app is built into the wheel.

Release wheels already contain `src/proseway/static`. When installing from a source checkout
(e.g. `uv tool install .` or `pip install git+https://...`), the built web app isn't in git,
so we build it here with pnpm (preferred) or npm. That needs Node.js 20+.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        index = root / "src" / "proseway" / "static" / "index.html"
        if index.exists() and not os.environ.get("PROSEWAY_REBUILD_WEB"):
            return
        web = root / "web"
        if not (web / "package.json").exists():
            raise RuntimeError("The web app sources are missing and no prebuilt web app was found.")
        pnpm = shutil.which("pnpm")
        npm = shutil.which("npm")
        if pnpm:
            cmds = [[pnpm, "install", "--frozen-lockfile"], [pnpm, "run", "build"]]
        elif npm:
            cmds = [[npm, "install", "--no-audit", "--no-fund"], [npm, "run", "build"]]
        else:
            raise RuntimeError(
                "Building Proseway from source needs Node.js 20+ (with npm or pnpm) to build the "
                "reader. Install Node.js, or install a prebuilt wheel from the Releases page instead."
            )
        for cmd in cmds:
            self.app.display_info(f"proseway: running {Path(cmd[0]).name} {' '.join(cmd[1:])} in web/")
            subprocess.run(cmd, cwd=web, check=True, shell=os.name == "nt" and cmd[0].lower().endswith((".cmd", ".bat")))  # noqa: S603
        if not index.exists():
            raise RuntimeError("The web app build finished but produced no index.html.")

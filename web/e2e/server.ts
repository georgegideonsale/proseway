import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PY = process.env.PROSEWAY_PYTHON ?? (process.platform === "win32" ? join(ROOT, ".venv", "Scripts", "python.exe") : join(ROOT, ".venv", "bin", "python"));

export function makeFixture(): string {
  const out = join(mkdtempSync(join(tmpdir(), "pw-fixture-")), "A Quiet Valley.pdf");
  const r = spawnSync(PY, [join(ROOT, "tests", "make_e2e_fixture.py"), out], { encoding: "utf8" });
  if (r.status !== 0) throw new Error(`fixture failed: ${r.stderr}`);
  return out;
}

export class Server {
  proc: ChildProcess | null = null;
  readonly dataDir = mkdtempSync(join(tmpdir(), "pw-lib-"));
  constructor(readonly port: number) {}

  get url() {
    return `http://127.0.0.1:${this.port}`;
  }

  async start() {
    this.proc = spawn(PY, ["-m", "proseway", "--no-browser", "--port", String(this.port), "--data-dir", this.dataDir], {
      cwd: ROOT,
      stdio: "ignore",
    });
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      try {
        const r = await fetch(`${this.url}/api/info`);
        if (r.ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    throw new Error("server did not start");
  }

  async stop() {
    if (!this.proc) return;
    const p = this.proc;
    this.proc = null;
    await new Promise<void>((done) => {
      p.once("exit", () => done());
      p.kill();
      setTimeout(done, 5000);
    });
  }
}

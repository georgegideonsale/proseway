import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { createServer } from "node:net";
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

/** Whether nothing is bound to 127.0.0.1:port right now. Port 0 asks the OS for a free one. */
function bindable(port: number): Promise<number | null> {
  return new Promise((done) => {
    const probe = createServer();
    probe.once("error", () => done(null));
    probe.listen({ port, host: "127.0.0.1", exclusive: true }, () => {
      const got = (probe.address() as { port: number }).port;
      probe.close(() => done(got));
    });
  });
}

/**
 * A real Proseway server for one spec, on its own data folder.
 *
 * Several worktrees (and sessions) run these specs on the same machine at once. With fixed
 * ports they collide: `proseway --port N` exits because N is taken, the readiness check gets
 * an answer from the other worktree's server, and the test silently runs against another
 * checkout's build and library (reading.spec.ts's mid-test restart made this likely). So each
 * server gets a free port from the OS and keeps it across restarts. Set
 * PROSEWAY_E2E_FIXED_PORTS=1 to use the port a spec names instead (for debugging).
 */
export class Server {
  proc: ChildProcess | null = null;
  readonly dataDir = mkdtempSync(join(tmpdir(), "pw-lib-"));
  port: number;
  private started = false;
  constructor(readonly preferredPort: number) {
    this.port = preferredPort;
  }

  get url() {
    return `http://127.0.0.1:${this.port}`;
  }

  log = "";

  private async answering(): Promise<boolean> {
    try {
      await fetch(`${this.url}/api/info`, { signal: AbortSignal.timeout(1000) });
      return true;
    } catch {
      return false;
    }
  }

  async start() {
    if (!this.started) {
      const fixed = process.env.PROSEWAY_E2E_FIXED_PORTS === "1";
      const port = await bindable(fixed ? this.preferredPort : 0);
      if (port === null) throw new Error(`port ${this.preferredPort} is already in use`);
      this.port = port;
      this.started = true;
    } else if (await this.answering()) {
      // A restart must come back on the same address (the page reloads it). If something else
      // is serving there now, say so rather than testing against it. (Not a bind probe: on
      // Windows the old server's connections in TIME_WAIT make an exclusive bind fail even
      // though nothing is listening; proseway itself binds the way uvicorn does.)
      throw new Error(`port ${this.port} was taken by another process while the server restarted`);
    }
    this.proc = spawn(PY, ["-m", "proseway", "--no-browser", "--port", String(this.port), "--data-dir", this.dataDir], {
      cwd: ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const collect = (d: Buffer) => {
      this.log = (this.log + d.toString()).slice(-4000);
    };
    this.proc.stdout?.on("data", collect);
    this.proc.stderr?.on("data", collect);
    let exited = false;
    this.proc.once("exit", () => (exited = true));
    this.proc.once("error", (e) => (this.log += `\nspawn error: ${e.message} (python: ${PY})`));
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !exited) {
      try {
        const r = await fetch(`${this.url}/api/info`);
        if (r.ok) {
          // Only our own process counts: make sure it's the one that answered and is still up.
          await new Promise((wait) => setTimeout(wait, 300));
          if (!exited) return;
          break;
        }
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    throw new Error(`server did not start (python: ${PY})\n${this.log}`);
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

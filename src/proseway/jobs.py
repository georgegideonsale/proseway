"""Background conversion jobs: one worker process per book, watched by a supervisor thread.

* Progress is written to SQLite by the worker after each few pages.
* Cancel marks the book cancelled; the worker notices and stops, and is killed if it doesn't.
* Resume restarts the worker, which skips pages that already have a checkpoint file.
* A watchdog kills a worker that stops making progress (a pathological page) or uses too
  much memory, then restarts it with that one page skipped so the rest of the book converts.
  The skipped page is shown in the reader as a page that couldn't be converted.
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import shutil
import threading
import time
from dataclasses import dataclass, field

import psutil

from .db import Database, now
from .paths import DataPaths
from .pipeline.convert import worker_main

log = logging.getLogger(__name__)

STALL_SECONDS = 180.0
MEMORY_LIMIT_BYTES = 3 * 1024**3
MAX_PARALLEL = 1  # one book at a time keeps a laptop responsive


@dataclass
class Job:
    book_id: str
    process: mp.Process | None = None
    started: float = 0.0
    last_progress: float = 0.0
    last_pages: int = -1
    skip_pages: list[int] = field(default_factory=list)
    restarts: int = 0


class JobManager:
    def __init__(self, db: Database, paths: DataPaths):
        self.db = db
        self.paths = paths
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._queue: list[str] = []
        self._ctx = mp.get_context("spawn")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._supervise, name="proseway-jobs", daemon=True)

    # -- lifecycle -------------------------------------------------------------------

    def start(self) -> None:
        # Anything that was converting when the app last stopped can be resumed.
        with self.db.connect() as c:
            c.execute("UPDATE books SET status='paused' WHERE status IN ('converting')")
            queued = [r["id"] for r in c.execute("SELECT id FROM books WHERE status='queued' ORDER BY created_at")]
        self._queue.extend(queued)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            for job in self._jobs.values():
                if job.process is not None and job.process.is_alive():
                    job.process.terminate()
        with self.db.connect() as c:
            c.execute("UPDATE books SET status='paused' WHERE status='converting'")

    # -- commands ----------------------------------------------------------------------

    def enqueue(self, book_id: str) -> None:
        with self._lock:
            if book_id in self._jobs or book_id in self._queue:
                return
            with self.db.connect() as c:
                c.execute("UPDATE books SET status='queued', error=NULL, updated_at=? WHERE id=?", (now(), book_id))
            self._queue.append(book_id)

    def cancel(self, book_id: str) -> None:
        with self._lock:
            if book_id in self._queue:
                self._queue.remove(book_id)
            with self.db.connect() as c:
                c.execute("UPDATE books SET status='cancelled', updated_at=? WHERE id=? AND status IN ('queued','converting','paused')",
                          (now(), book_id))
            job = self._jobs.pop(book_id, None)  # so Resume right after Stop starts afresh
        if job and job.process is not None:
            job.process.join(timeout=5)
            if job.process.is_alive():
                job.process.kill()
                job.process.join(timeout=5)

    def reconvert(self, book_id: str) -> None:
        self.cancel(book_id)
        with self._lock:
            self._jobs.pop(book_id, None)
        shutil.rmtree(self.paths.pages_dir(book_id), ignore_errors=True)
        self.enqueue(book_id)

    def is_active(self, book_id: str) -> bool:
        with self._lock:
            return book_id in self._jobs or book_id in self._queue

    # -- supervisor --------------------------------------------------------------------

    def _launch(self, job: Job) -> None:
        job.process = self._ctx.Process(
            target=worker_main,
            args=(str(self.db.path), str(self.paths.root), job.book_id, job.skip_pages),
            name=f"proseway-convert-{job.book_id[:8]}",
            daemon=True,
        )
        job.process.start()
        job.started = job.last_progress = time.monotonic()
        log.info("started converter pid=%s for %s", job.process.pid, job.book_id)

    def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("job supervisor error")
            self._stop.wait(0.5)

    def _tick(self) -> None:
        with self._lock:
            # Start queued work.
            while self._queue and len(self._jobs) < MAX_PARALLEL:
                book_id = self._queue.pop(0)
                job = Job(book_id)
                self._jobs[book_id] = job
                self._launch(job)
            jobs = list(self._jobs.values())

        for job in jobs:
            proc = job.process
            if proc is None:
                continue
            if not proc.is_alive():
                proc.join(timeout=1)
                with self._lock:
                    self._jobs.pop(job.book_id, None)
                self._after_exit(job, proc.exitcode)
                continue
            with self.db.connect() as c:
                row = c.execute("SELECT pages_done, status FROM books WHERE id=?", (job.book_id,)).fetchone()
            if row is None:
                proc.kill()
                continue
            if row["pages_done"] != job.last_pages:
                job.last_pages = row["pages_done"]
                job.last_progress = time.monotonic()
            reason = None
            try:
                rss = psutil.Process(proc.pid).memory_info().rss
                if rss > MEMORY_LIMIT_BYTES:
                    reason = f"memory {rss // 2**20} MB"
            except psutil.Error:
                pass
            if time.monotonic() - job.last_progress > STALL_SECONDS:
                reason = "no progress"
            if reason:
                log.warning("restarting stuck converter for %s (%s)", job.book_id, reason)
                proc.kill()
                proc.join(timeout=5)
                # Progress is written after every page, so the stuck page is the next one.
                stuck_page = (row["pages_done"] or 0) + 1
                job.skip_pages = sorted(set(job.skip_pages + [stuck_page]))
                job.restarts += 1
                if job.restarts > 5:
                    with self._lock:
                        self._jobs.pop(job.book_id, None)
                    self._fail(job.book_id, "The converter kept getting stuck on this file.")
                else:
                    self._launch(job)

    def _after_exit(self, job: Job, code: int | None) -> None:
        with self.db.connect() as c:
            row = c.execute("SELECT status FROM books WHERE id=?", (job.book_id,)).fetchone()
        if row is None:
            return
        if row["status"] == "converting":
            # Crashed without writing a final status (e.g. killed by the OS).
            self._fail(job.book_id, f"The converter stopped unexpectedly (exit code {code}). You can resume it.")

    def _fail(self, book_id: str, message: str) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE books SET status='error', error=?, updated_at=? WHERE id=?",
                      (json.dumps({"code": "worker", "message": message}), now(), book_id))

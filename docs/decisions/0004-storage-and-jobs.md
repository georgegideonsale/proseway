# 4. SQLite storage and a separate converter process

- Status: accepted
- Date: 2026-11-21

## Decision

- **Storage:** one SQLite file in the user's data directory (`%LOCALAPPDATA%\Proseway`, `~/Library/Application Support/Proseway`, or `$XDG_DATA_HOME/proseway`). It runs in WAL mode so the server and the converter can use it at the same time. Book text is indexed with FTS5 for search.
- **Per-book files:** the original PDF, a JSON checkpoint per page, cropped figures and equations, and a cover image.
- **Conversion:** runs in a `multiprocessing` worker started with the *spawn* method. It writes progress after every few pages.
  - **Cancel** sets the status and kills the worker if it doesn't stop.
  - **Resume** restarts it, and pages that already have a checkpoint are skipped.
  - **On server start,** books that were mid-conversion are marked *paused*.
- **Watchdog:** if a worker makes no progress for 3 minutes or uses more than 3 GB, it's killed. It is restarted with the stuck pages skipped and marked as failed, so one pathological page can't block a 1,000-page book.

## Consequences

- The UI stays responsive during large imports. A crash in a PDF parser can't take the server down.
- Only one book converts at a time, to keep a laptop usable. Others queue.

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { api, ApiError, coverUrl } from "../api";
import type { Session } from "../App";
import { navigate } from "../lib/router";
import { useToast } from "../lib/toast";
import type { Book } from "../types";
import { Dialog } from "./Dialog";
import { IconArchive, IconMore, IconPhone, IconPlus, IconUpload } from "./Icons";
import { Menu } from "./Menu";
import { SharingDialog } from "./SharingDialog";

const ACTIVE = new Set(["queued", "converting"]);

export function Library({ session }: { session: Session }) {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string[]>([]);
  const [sharingOpen, setSharingOpen] = useState(false);
  const [removing, setRemoving] = useState<Book | null>(null);
  const [renaming, setRenaming] = useState<Book | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const restoreInput = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const local = session.listener === "local";

  const refresh = useCallback(async () => {
    try {
      const { books } = await api.books();
      setBooks(books);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onVisible = () => document.visibilityState === "visible" && refresh();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  const anyActive = books?.some((b) => ACTIVE.has(b.status)) ?? false;
  useEffect(() => {
    if (!anyActive) return;
    const t = window.setInterval(refresh, 900);
    return () => window.clearInterval(t);
  }, [anyActive, refresh]);

  useEffect(() => {
    document.title = "Library — Proseway";
  }, []);

  async function importFiles(list: FileList | File[]) {
    const files = Array.from(list).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    const skipped = Array.from(list).length - files.length;
    if (skipped) toast(skipped === 1 ? "That file isn't a PDF, so it was skipped." : `${skipped} files weren't PDFs and were skipped.`);
    if (!files.length) return;
    setUploading(files.map((f) => f.name));
    try {
      const { results } = await api.importFiles(files);
      const failed = results.filter((r) => r.error);
      const dupes = results.filter((r) => r.duplicate);
      if (failed.length) toast(`${failed[0].fileName}: ${failed[0].error!.message}`);
      else if (dupes.length) toast(dupes.length === 1 ? "That book is already in your library." : `${dupes.length} books were already in your library.`);
    } catch (e) {
      toast((e as ApiError).message);
    } finally {
      setUploading([]);
      refresh();
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!local) return;
    if (e.dataTransfer.files.length) importFiles(e.dataTransfer.files);
  }

  async function act(fn: () => Promise<unknown>, done?: string) {
    try {
      await fn();
      if (done) toast(done);
    } catch (e) {
      toast((e as Error).message);
    }
    refresh();
  }

  async function onRestore(file: File) {
    try {
      const { result } = await api.restore(file);
      const added = result.annotations_added + result.annotations_updated;
      const waiting = result.books_waiting;
      toast(
        `Restored ${added} highlight${added === 1 ? "" : "s"} and notes.` +
          (waiting ? ` ${waiting} book${waiting === 1 ? " isn't" : "s aren't"} in your library yet; import ${waiting === 1 ? "it" : "them"} to bring the notes back.` : ""),
      );
    } catch (e) {
      toast((e as Error).message);
    }
    refresh();
  }

  const empty = books !== null && books.length === 0 && uploading.length === 0;

  return (
    <div
      className="library"
      onDragOver={(e) => {
        if (!local) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <a className="skip-link" href="#shelf">
        Skip to your books
      </a>
      <header className="lib-header">
        <div className="wordmark" aria-label="Proseway">
          <span className="wordmark-text">Proseway</span>
          <span className="wordmark-ribbon" aria-hidden="true" />
        </div>
        <div className="lib-actions">
          {local && (
            <>
              <button className="btn btn-quiet" onClick={() => setSharingOpen(true)}>
                <IconPhone width={18} height={18} />
                <span className="hide-sm">Read on your phone</span>
              </button>
              <Menu
                label="Library options"
                trigger={<IconArchive />}
                items={[
                  { label: "Download a backup of all notes", run: () => (location.href = "/api/backup.json") },
                  { label: "Restore from a backup…", run: () => restoreInput.current?.click() },
                ]}
              />
              <button className="btn btn-primary" onClick={() => fileInput.current?.click()}>
                <IconPlus width={18} height={18} />
                Add books
              </button>
            </>
          )}
        </div>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) importFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={restoreInput}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onRestore(f);
            e.target.value = "";
          }}
        />
      </header>

      <main id="shelf" className="lib-main">
        {loadError && (
          <div className="lib-error" role="alert">
            <p>{loadError}</p>
            <button className="btn" onClick={refresh}>
              Try again
            </button>
          </div>
        )}
        {books === null && !loadError && <ShelfSkeleton />}
        {empty && <EmptyShelf local={local} onPick={() => fileInput.current?.click()} />}
        {books !== null && !empty && (
          <>
            <h1 className="lib-title">Your library</h1>
            <ul className="shelf" aria-label="Books">
              {uploading.map((name) => (
                <li key={`up-${name}`} className="book book-uploading">
                  <div className="cover cover-placeholder">
                    <div className="spinner" aria-hidden="true" />
                  </div>
                  <div className="book-meta">
                    <p className="book-title">{name.replace(/\.pdf$/i, "")}</p>
                    <p className="book-status">Copying into your library</p>
                  </div>
                </li>
              ))}
              {books.map((b) => (
                <BookCard
                  key={b.id}
                  book={b}
                  local={local}
                  onOpen={() => navigate(`/book/${b.id}`)}
                  onCancel={() => act(() => api.cancel(b.id))}
                  onResume={() => act(() => api.resume(b.id))}
                  onReconvert={() => act(() => api.reconvert(b.id), "Converting again. Your highlights will be kept.")}
                  onRemove={() => setRemoving(b)}
                  onRename={() => setRenaming(b)}
                />
              ))}
            </ul>
          </>
        )}
      </main>

      {dragging && local && (
        <div className="drop-overlay" aria-hidden="true">
          <div className="drop-card">
            <IconUpload width={28} height={28} />
            <p>Drop to add to your library</p>
          </div>
        </div>
      )}

      {sharingOpen && <SharingDialog onClose={() => setSharingOpen(false)} />}
      {removing && (
        <Dialog title={`Remove “${removing.title}”?`} onClose={() => setRemoving(null)}>
          <p>
            The converted book and its copy of the PDF are removed from this computer. Your highlights and notes are
            kept: import the same PDF again and they come back.
          </p>
          <div className="dialog-actions">
            <button className="btn" onClick={() => setRemoving(null)}>
              Keep it
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                const b = removing;
                setRemoving(null);
                act(() => api.deleteBook(b.id), "Book removed. Your notes were kept.");
              }}
            >
              Remove book
            </button>
          </div>
        </Dialog>
      )}
      {renaming && <RenameDialog book={renaming} onClose={() => setRenaming(null)} onSaved={refresh} />}
    </div>
  );
}

function ShelfSkeleton() {
  return (
    <ul className="shelf" aria-busy="true" aria-label="Loading your books">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="book">
          <div className="cover skeleton" />
          <div className="book-meta">
            <div className="skeleton skeleton-line" />
            <div className="skeleton skeleton-line short" />
          </div>
        </li>
      ))}
    </ul>
  );
}

function EmptyShelf({ local, onPick }: { local: boolean; onPick: () => void }) {
  if (!local) {
    return (
      <section className="empty">
        <h1>No books yet</h1>
        <p>Add a PDF on the computer running Proseway and it will show up here.</p>
      </section>
    );
  }
  return (
    <section className="empty">
      <div className="empty-book" aria-hidden="true">
        <span />
      </div>
      <h1>Bring a book you want to read properly</h1>
      <p>
        Add a PDF and Proseway turns it into a calm, reflowable edition with page numbers kept for citing. Everything
        stays on this computer.
      </p>
      <button className="btn btn-primary btn-lg" onClick={onPick}>
        <IconPlus width={18} height={18} />
        Choose PDFs
      </button>
      <p className="empty-hint">or drop them anywhere on this page</p>
    </section>
  );
}

function statusLine(b: Book): string {
  switch (b.status) {
    case "queued":
      return "Waiting to convert";
    case "converting":
      return b.pageCount ? `Converting page ${Math.min(b.pagesDone + 1, b.pageCount)} of ${b.pageCount}` : "Reading the file";
    case "paused":
      return b.pageCount ? `Paused at page ${b.pagesDone} of ${b.pageCount}` : "Paused";
    case "cancelled":
      return "Conversion stopped";
    case "error":
      return b.error?.message ?? "Couldn't convert this book";
    case "ready": {
      const p = Math.round((b.progress ?? 0) * 100);
      if (!b.lastOpenedAt) return "Not started";
      if (p >= 99) return "Finished";
      return `${p}% read`;
    }
  }
}

function BookCard(props: {
  book: Book;
  local: boolean;
  onOpen: () => void;
  onCancel: () => void;
  onResume: () => void;
  onReconvert: () => void;
  onRemove: () => void;
  onRename: () => void;
}) {
  const { book: b, local } = props;
  const ready = b.status === "ready";
  const active = ACTIVE.has(b.status);
  const pct = b.pageCount ? Math.round((b.pagesDone / b.pageCount) * 100) : 0;
  const progress = Math.round((b.progress ?? 0) * 100);
  const items = [
    ...(ready
      ? [
          { label: "Export highlights and notes (Markdown)", run: () => (location.href = `/api/books/${b.id}/export.md`) },
          { label: "Download as EPUB", run: () => (location.href = `/api/books/${b.id}/export.epub`) },
        ]
      : []),
    ...(local
      ? [
          { label: "Rename…", run: props.onRename },
          ...(ready || b.status === "error" ? [{ label: "Convert again", run: props.onReconvert }] : []),
          { label: "Remove from library…", run: props.onRemove, danger: true },
        ]
      : []),
  ];
  return (
    <li className={`book book-${b.status}`}>
      <button className="cover-button" onClick={props.onOpen} disabled={!ready} aria-label={ready ? `Open ${b.title}` : b.title}>
        <Cover book={b} />
        {ready && progress > 0 && progress < 99 && (
          <span className="ribbon" style={{ height: `${Math.max(12, progress)}%` }} aria-hidden="true" />
        )}
        {active && (
          <span className="cover-progress" aria-hidden="true">
            <span style={{ width: `${pct}%` }} />
          </span>
        )}
      </button>
      <div className="book-meta">
        <div className="book-meta-row">
          <div>
            <p className="book-title">
              {ready ? (
                <a
                  href={`/book/${b.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    props.onOpen();
                  }}
                >
                  {b.title}
                </a>
              ) : (
                b.title
              )}
            </p>
            {b.author && <p className="book-author">{b.author}</p>}
          </div>
          {items.length > 0 && <Menu label={`Options for ${b.title}`} trigger={<IconMore />} items={items} />}
        </div>
        <p className={`book-status ${b.status === "error" ? "is-error" : ""}`} aria-live={active ? "polite" : undefined}>
          {statusLine(b)}
          {ready && (b.highlights ?? 0) > 0 && (
            <span className="book-count">
              {b.highlights} {b.highlights === 1 ? "highlight" : "highlights"}
            </span>
          )}
        </p>
        {local && active && (
          <button className="link-btn" onClick={props.onCancel}>
            Stop
          </button>
        )}
        {local && (b.status === "paused" || b.status === "cancelled" || b.status === "error") && (
          <div className="book-inline-actions">
            <button className="link-btn" onClick={props.onResume}>
              {b.status === "error" ? "Try again" : "Resume"}
            </button>
            <button className="link-btn" onClick={props.onRemove}>
              Remove
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

function hueFor(text: string): number {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function Cover({ book }: { book: Book }) {
  const [failed, setFailed] = useState(false);
  if (book.hasCover && !failed) {
    return (
      <img
        className="cover"
        src={coverUrl(book.id, book.updatedAt)}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
      />
    );
  }
  // A cloth-bound cover generated from the title when the PDF has no usable first page.
  return (
    <div className="cover cover-cloth" style={{ ["--cloth-h" as string]: hueFor(book.title) }}>
      <span className="cover-cloth-title">{book.title}</span>
      {book.author && <span className="cover-cloth-author">{book.author}</span>}
    </div>
  );
}

function RenameDialog({ book, onClose, onSaved }: { book: Book; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(book.title);
  const [author, setAuthor] = useState(book.author);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog title="Rename book" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.editBook(book.id, { title, author });
            onSaved();
            onClose();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <div className="field">
          <label htmlFor="rn-title">Title</label>
          <input id="rn-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
        </div>
        <div className="field" style={{ marginTop: 12 }}>
          <label htmlFor="rn-author">Author</label>
          <input id="rn-author" className="input" value={author} onChange={(e) => setAuthor(e.target.value)} />
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary">
            Save
          </button>
        </div>
      </form>
    </Dialog>
  );
}

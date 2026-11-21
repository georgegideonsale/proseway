import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { FONT_LABELS, FONT_VARS, type Prefs, type ReaderFont, type Theme } from "../../lib/prefs";
import { snippetParts } from "../../lib/segments";
import type { Annotation, HighlightColor, Manifest, SearchResult } from "../../types";
import { IconTrash } from "../Icons";
import { COLORS } from "./HighlightPopover";
import { Sheet } from "./Sheet";

export interface JumpTarget {
  blockId: string;
  seq: number;
  chapter: number;
  page?: number;
}

/* ------------------------------------------------------------------ contents */

export function TocPanel({ manifest, currentChapter, currentSeq, onJump, onClose }: {
  manifest: Manifest;
  currentChapter: number;
  currentSeq: number;
  onJump: (t: JumpTarget) => void;
  onClose: () => void;
}) {
  const seqOf = useMemo(() => {
    // Entries don't carry seq; approximate ordering by chapter then list position.
    return manifest.toc.map((t) => t.chapter);
  }, [manifest]);
  const activeIndex = useMemo(() => {
    let idx = -1;
    manifest.toc.forEach((t, i) => {
      if (t.chapter <= currentChapter) idx = i;
    });
    return idx;
  }, [manifest, currentChapter]);
  const activeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => activeRef.current?.scrollIntoView({ block: "center" }), []);

  return (
    <Sheet title="Contents" onClose={onClose}>
      {manifest.toc.length > 0 ? (
        <ol className="toc">
          {manifest.toc.map((t, i) => (
            <li key={`${t.block}-${i}`} className={`toc-l${Math.min(t.level, 3)}`}>
              <button
                ref={i === activeIndex ? activeRef : undefined}
                className={`toc-item ${i === activeIndex ? "is-current" : ""}`}
                aria-current={i === activeIndex ? "location" : undefined}
                onClick={() => onJump({ blockId: t.block, seq: -1, chapter: seqOf[i], page: t.page })}
              >
                <span className="toc-title">{t.title}</span>
                <span className="toc-page">{t.page}</span>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <>
          <p className="panel-note">This book doesn't have a table of contents, so here it is by page.</p>
          <ol className="toc">
            {manifest.chapters.map((c) => (
              <li key={c.idx}>
                <button
                  className={`toc-item ${c.idx === currentChapter ? "is-current" : ""}`}
                  onClick={() => onJump({ blockId: "", seq: c.firstSeq, chapter: c.idx, page: c.startPage })}
                >
                  <span className="toc-title">
                    Pages {c.startPage}–{c.endPage}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="panel-foot">
        {manifest.book.pageCount} pages in the original PDF{currentSeq >= 0 ? "" : ""}
      </p>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ search */

export function SearchPanel({ bookId, onJump, onClose, initial, onQuery }: {
  bookId: string;
  onJump: (t: JumpTarget, query: string) => void;
  onClose: () => void;
  initial: string;
  onQuery: (q: string) => void;
}) {
  const [q, setQ] = useState(initial);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onQuery(q);
    if (q.trim().length < 2) {
      setResults(null);
      return;
    }
    const t = window.setTimeout(() => {
      api
        .search(bookId, q)
        .then((r) => {
          setResults(r.results);
          setTotal(r.total);
          setError(null);
        })
        .catch((e) => setError(e.message));
    }, 220);
    return () => window.clearTimeout(t);
  }, [q, bookId, onQuery]);

  return (
    <Sheet title="Search" onClose={onClose}>
      <form role="search" onSubmit={(e) => e.preventDefault()} className="search-form">
        <label htmlFor="search-q" className="visually-hidden">
          Search this book
        </label>
        <input
          id="search-q"
          data-autofocus
          className="input search-input"
          type="search"
          placeholder="Search this book"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoComplete="off"
        />
      </form>
      {error && <p className="form-error">{error}</p>}
      {results && (
        <p className="panel-note" aria-live="polite">
          {total === 0 ? "No matches." : total === 1 ? "1 match" : `${total} matches${total > results.length ? `, showing the first ${results.length}` : ""}`}
        </p>
      )}
      {results && results.length > 0 && (
        <ol className="results">
          {results.map((r) => (
            <li key={`${r.blockId}-${r.seq}`}>
              <button className="result" onClick={() => onJump({ blockId: r.blockId, seq: r.seq, chapter: r.chapter, page: r.page }, q)}>
                <span className="result-page">p. {r.page}</span>
                <span className="result-snippet">
                  {snippetParts(r.snippet).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ notes */

export interface HighlightGroup {
  key: string;
  parts: Annotation[];
  color: HighlightColor | null;
  note: string;
  page: number | null;
  seq: number;
  quote: string;
  orphaned: boolean;
}

export function groupHighlights(anns: Annotation[]): HighlightGroup[] {
  const map = new Map<string, Annotation[]>();
  for (const a of anns) {
    if (a.kind !== "highlight") continue;
    const k = a.groupId ?? a.id;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(a);
  }
  return [...map.entries()]
    .map(([key, parts]) => {
      parts.sort((x, y) => (x.seq ?? 0) - (y.seq ?? 0) || x.start - y.start);
      return {
        key,
        parts,
        color: parts[0].color,
        note: parts.map((p) => p.note).filter(Boolean).join("\n"),
        page: parts[0].page,
        seq: parts[0].seq ?? 0,
        quote: parts.map((p) => p.exact).join(" "),
        orphaned: parts.some((p) => p.orphaned),
      };
    })
    .sort((a, b) => a.seq - b.seq);
}

export function NotesPanel({ bookId, annotations, onJump, onUpdate, onDelete, onClose, chapterOfSeq }: {
  bookId: string;
  annotations: Annotation[];
  onJump: (t: JumpTarget) => void;
  onUpdate: (a: Annotation, fields: { note?: string; color?: HighlightColor }) => void;
  onDelete: (a: Annotation) => void;
  onClose: () => void;
  chapterOfSeq: (seq: number) => number;
}) {
  const [tab, setTab] = useState<"highlights" | "bookmarks">("highlights");
  const [filter, setFilter] = useState<HighlightColor | "all" | "notes">("all");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const groups = useMemo(() => groupHighlights(annotations), [annotations]);
  const bookmarks = useMemo(() => annotations.filter((a) => a.kind === "bookmark").sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)), [annotations]);
  const shown = groups.filter((g) => filter === "all" || (filter === "notes" ? !!g.note : g.color === filter));
  const usedColors = COLORS.filter((c) => groups.some((g) => g.color === c.id));

  return (
    <Sheet
      title="Notes"
      onClose={onClose}
      actions={
        groups.length > 0 ? (
          <a className="btn btn-quiet btn-sm" href={`/api/books/${bookId}/export.md`} download>
            Export
          </a>
        ) : undefined
      }
    >
      <div
        className="tabs"
        role="tablist"
        aria-label="Notes view"
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
            e.preventDefault();
            const next = tab === "highlights" ? "bookmarks" : "highlights";
            setTab(next);
            document.getElementById(`tab-${next}`)?.focus();
          }
        }}
      >
        <button
          role="tab"
          id="tab-highlights"
          aria-controls="tabpanel-notes"
          aria-selected={tab === "highlights"}
          tabIndex={tab === "highlights" ? 0 : -1}
          className="tab"
          onClick={() => setTab("highlights")}
        >
          Highlights <span className="tab-count">{groups.length}</span>
        </button>
        <button
          role="tab"
          id="tab-bookmarks"
          aria-controls="tabpanel-notes"
          aria-selected={tab === "bookmarks"}
          tabIndex={tab === "bookmarks" ? 0 : -1}
          className="tab"
          onClick={() => setTab("bookmarks")}
        >
          Bookmarks <span className="tab-count">{bookmarks.length}</span>
        </button>
      </div>
      <div role="tabpanel" id="tabpanel-notes" aria-labelledby={`tab-${tab}`}>

      {tab === "highlights" && (
        <>
          {groups.length > 0 && (
            <div className="chips" role="group" aria-label="Filter highlights">
              <button className="chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
                All
              </button>
              <button className="chip" aria-pressed={filter === "notes"} onClick={() => setFilter("notes")}>
                With notes
              </button>
              {usedColors.map((c) => (
                <button key={c.id} className="chip" aria-pressed={filter === c.id} onClick={() => setFilter(c.id)} aria-label={`${c.label} highlights`}>
                  <span className={`chip-dot sw-${c.id}`} aria-hidden="true" />
                </button>
              ))}
            </div>
          )}
          {groups.length === 0 ? (
            <div className="panel-empty">
              <p className="panel-empty-title">Nothing highlighted yet</p>
              <p>Select a passage to highlight it in one of five colours or attach a note. Everything you mark collects here, with page numbers for citing.</p>
            </div>
          ) : (
            <ol className="notes">
              {shown.map((g) => (
                <li key={g.key} className={`note-card nc-${g.color ?? "yellow"}`}>
                  <button
                    className="note-quote"
                    onClick={() => {
                      const first = g.parts[0];
                      onJump({ blockId: first.blockId, seq: first.seq ?? 0, chapter: chapterOfSeq(first.seq ?? 0), page: first.page ?? undefined });
                    }}
                  >
                    <span className="note-quote-text">{g.quote}</span>
                  </button>
                  {editing === g.key ? (
                    <div className="note-edit">
                      <label className="visually-hidden" htmlFor={`ne-${g.key}`}>
                        Note
                      </label>
                      <textarea
                        id={`ne-${g.key}`}
                        className="input"
                        rows={3}
                        autoFocus
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                            onUpdate(g.parts[0], { note: draft.trim() });
                            setEditing(null);
                          }
                          if (e.key === "Escape") {
                            e.preventDefault();
                            e.stopPropagation();
                            setEditing(null);
                          }
                        }}
                      />
                      <div className="note-edit-actions">
                        <button className="btn btn-quiet btn-sm" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            onUpdate(g.parts[0], { note: draft.trim() });
                            setEditing(null);
                          }}
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  ) : (
                    g.note && <p className="note-text">{g.note}</p>
                  )}
                  <div className="note-meta">
                    <span>{g.page ? `p. ${g.page}` : ""}</span>
                    {g.orphaned && <span className="note-warn">Couldn't be placed after re-converting</span>}
                    <span className="note-actions">
                      {editing !== g.key && (
                        <button
                          className="link-btn"
                          onClick={() => {
                            setDraft(g.note);
                            setEditing(g.key);
                          }}
                        >
                          {g.note ? "Edit note" : "Add note"}
                        </button>
                      )}
                      <button className="icon-btn icon-btn-sm" aria-label="Remove highlight" onClick={() => onDelete(g.parts[0])}>
                        <IconTrash />
                      </button>
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      {tab === "bookmarks" &&
        (bookmarks.length === 0 ? (
          <div className="panel-empty">
            <p className="panel-empty-title">No bookmarks</p>
            <p>Use the ribbon button at the top of the page to mark your place. Press B on a keyboard.</p>
          </div>
        ) : (
          <ol className="notes">
            {bookmarks.map((b) => (
              <li key={b.id} className="bookmark-row">
                <button
                  className="note-quote"
                  onClick={() => onJump({ blockId: b.blockId, seq: b.seq ?? 0, chapter: chapterOfSeq(b.seq ?? 0), page: b.page ?? undefined })}
                >
                  <span className="bookmark-page">p. {b.page}</span>
                  <span className="note-quote-text">{b.exact}</span>
                </button>
                <button className="icon-btn icon-btn-sm" aria-label="Remove bookmark" onClick={() => onDelete(b)}>
                  <IconTrash />
                </button>
              </li>
            ))}
          </ol>
        ))}
      </div>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ appearance */

const THEMES: { id: Theme; label: string }[] = [
  { id: "auto", label: "Match system" },
  { id: "paper", label: "Paper" },
  { id: "sepia", label: "Sepia" },
  { id: "dusk", label: "Dusk" },
  { id: "night", label: "Night" },
];

const LEADINGS = [
  { v: 1.45, label: "Snug" },
  { v: 1.62, label: "Even" },
  { v: 1.85, label: "Airy" },
];

export function AppearancePanel({ prefs, update, onClose }: { prefs: Prefs; update: (p: Partial<Prefs>) => void; onClose: () => void }) {
  return (
    <Sheet title="Appearance" onClose={onClose}>
      <fieldset className="setting">
        <legend>Theme</legend>
        <div className="theme-row">
          {THEMES.map((t) => (
            <label key={t.id} className={`theme-opt th-${t.id}`}>
              <input type="radio" name="theme" checked={prefs.theme === t.id} onChange={() => update({ theme: t.id })} />
              <span className="theme-swatch" aria-hidden="true">
                Aa
              </span>
              <span className="theme-name">{t.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="setting">
        <legend>Typeface</legend>
        <div className="font-list">
          {(Object.keys(FONT_LABELS) as ReaderFont[]).map((f) => (
            <label key={f} className="font-opt">
              <input type="radio" name="font" checked={prefs.font === f} onChange={() => update({ font: f })} />
              <span style={{ fontFamily: FONT_VARS[f] }}>{FONT_LABELS[f]}</span>
              {f === "dyslexic" && <span className="font-note">Designed for readers with dyslexia</span>}
              {f === "atkinson" && <span className="font-note">Built for low-vision legibility</span>}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="setting">
        <legend>Text size</legend>
        <div className="stepper">
          <button className="btn" onClick={() => update({ size: Math.max(14, prefs.size - 1) })} aria-label="Smaller text" disabled={prefs.size <= 14}>
            A−
          </button>
          <input
            type="range"
            min={14}
            max={30}
            step={1}
            value={prefs.size}
            aria-label="Text size"
            aria-valuetext={`${prefs.size} pixels`}
            onChange={(e) => update({ size: Number(e.target.value) })}
          />
          <button className="btn" onClick={() => update({ size: Math.min(30, prefs.size + 1) })} aria-label="Larger text" disabled={prefs.size >= 30}>
            A+
          </button>
        </div>
      </fieldset>

      <fieldset className="setting">
        <legend>Line spacing</legend>
        <div className="segmented">
          {LEADINGS.map((l) => (
            <label key={l.v}>
              <input type="radio" name="leading" checked={Math.abs(prefs.leading - l.v) < 0.01} onChange={() => update({ leading: l.v })} />
              <span>{l.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="setting">
        <legend>Line length</legend>
        <div className="segmented">
          {(["narrow", "medium", "wide"] as const).map((m) => (
            <label key={m}>
              <input type="radio" name="measure" checked={prefs.measure === m} onChange={() => update({ measure: m })} />
              <span>{m === "narrow" ? "Short" : m === "medium" ? "Medium" : "Long"}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="toggle">
        <input type="checkbox" checked={prefs.justify} onChange={(e) => update({ justify: e.target.checked })} />
        <span>Justify text, with automatic hyphenation</span>
      </label>
      <label className="toggle" style={{ marginTop: 12 }}>
        <input type="checkbox" checked={prefs.shortcuts} onChange={(e) => update({ shortcuts: e.target.checked })} />
        <span>Single-key shortcuts (T contents, / search, N notes, A appearance, B bookmark, H highlight)</span>
      </label>
      <p className="panel-foot">These settings are saved on this device only, so your phone and computer can differ.</p>
    </Sheet>
  );
}

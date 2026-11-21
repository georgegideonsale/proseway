import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Session } from "../App";
import { usePrefs } from "../lib/prefs";
import { cpLength } from "../lib/offsets";
import { navigate } from "../lib/router";
import { rangesFromSelection, type BlockRange } from "../lib/selection";
import type { Mark } from "../lib/segments";
import { useToast } from "../lib/toast";
import type { Annotation, Block, HighlightColor, Manifest } from "../types";
import { IconBack, IconBookmark, IconContents, IconNotes, IconReturn, IconSearch, IconType } from "./Icons";
import { BlockView } from "./reader/BlockView";
import { HighlightPopover } from "./reader/HighlightPopover";
import { AppearancePanel, NotesPanel, SearchPanel, TocPanel, type JumpTarget } from "./reader/Panels";

type Panel = null | "toc" | "search" | "notes" | "appearance";

interface Position {
  blockId: string;
  seq: number;
  page: number;
  chapter: number;
}

interface PopoverState {
  rect: DOMRect;
  mode: "new" | "edit";
  ranges?: BlockRange[];
  annotation?: Annotation;
  startWithNote?: boolean;
}

const CHARS_PER_MINUTE = 1150; // ~230 words a minute

function uuidHex(): string {
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

export function Reader({ bookId, session }: { bookId: string; session: Session }) {
  const [prefs, updatePrefs] = usePrefs();
  const toast = useToast();
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chapters, setChapters] = useState<Map<number, Block[]>>(new Map());
  const [win, setWin] = useState<[number, number] | null>(null);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [panel, setPanel] = useState<Panel>(null);
  const [pop, setPop] = useState<PopoverState | null>(null);
  const [pos, setPos] = useState<Position | null>(null);
  const [chrome, setChrome] = useState(true);
  const [back, setBack] = useState<Position | null>(null);
  const [footnote, setFootnote] = useState<{ block: Block; rect: DOMRect } | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const articleRef = useRef<HTMLDivElement>(null);
  const loading = useRef(new Map<number, Promise<Block[]>>());
  const pendingScroll = useRef<{ blockId?: string; seq?: number; flash?: boolean; offset?: number } | null>(null);
  const anchor = useRef<{ id: string; top: number } | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const lastY = useRef(0);
  const local = session.listener === "local";

  /* ----------------------------------------------------------- loading */

  const loadChapter = useCallback(
    (idx: number): Promise<Block[]> => {
      const existing = loading.current.get(idx);
      if (existing) return existing;
      const p = api.chapter(bookId, idx).then((r) => {
        setChapters((m) => new Map(m).set(idx, r.blocks));
        return r.blocks;
      });
      p.catch(() => loading.current.delete(idx));
      loading.current.set(idx, p);
      return p;
    },
    [bookId],
  );

  const chapterOfSeq = useCallback(
    (seq: number): number => {
      if (!manifest) return 0;
      let found = 0;
      for (const c of manifest.chapters) if (c.firstSeq <= seq) found = c.idx;
      return found;
    },
    [manifest],
  );

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [m, p, a] = await Promise.all([api.manifest(bookId), api.position(bookId), api.annotations(bookId)]);
        if (!alive) return;
        if (m.book.status !== "ready") {
          setError("This book hasn't finished converting yet.");
          return;
        }
        setManifest(m);
        setAnnotations(a.annotations);
        document.title = `${m.book.title} — Proseway`;
        let start = 0;
        if (p.position) {
          for (const c of m.chapters) if (c.firstSeq <= p.position.seq) start = c.idx;
          pendingScroll.current = { blockId: p.position.blockId };
        }
        if (!m.chapters.length) {
          setError("This book came out empty. The PDF may contain only images; try converting it again with OCR installed.");
          return;
        }
        await api.chapter(bookId, start).then((r) => {
          loading.current.set(start, Promise.resolve(r.blocks));
          setChapters(new Map([[start, r.blocks]]));
        });
        setWin([start, start]);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [bookId]);

  /* ----------------------------------------------------------- window growth */

  const extend = useCallback(
    async (dir: "up" | "down") => {
      if (!win || !manifest) return;
      const [lo, hi] = win;
      const last = manifest.chapters[manifest.chapters.length - 1].idx;
      const next = dir === "down" ? hi + 1 : lo - 1;
      if (next < 0 || next > last) return;
      await loadChapter(next);
      if (dir === "up") {
        // Remember where the first visible block is, so prepending doesn't move the text.
        const el = firstVisibleBlock();
        if (el) anchor.current = { id: el.dataset.block!, top: el.getBoundingClientRect().top };
      }
      setWin((w) => {
        if (!w) return w;
        const [a, b] = w;
        return dir === "down" ? [a, Math.max(b, next)] : [Math.min(a, next), b];
      });
    },
    [win, manifest, loadChapter],
  );

  useLayoutEffect(() => {
    const a = anchor.current;
    if (a) {
      anchor.current = null;
      const el = document.getElementById(`b-${a.id}`);
      if (el) window.scrollBy(0, el.getBoundingClientRect().top - a.top);
    }
    const ps = pendingScroll.current;
    if (ps) {
      let el: HTMLElement | null = null;
      if (ps.blockId) el = document.getElementById(`b-${ps.blockId}`);
      if (!el && ps.seq !== undefined) el = document.querySelector(`[data-seq="${ps.seq}"]`);
      if (el) {
        pendingScroll.current = null;
        const top = el.getBoundingClientRect().top + window.scrollY - (ps.offset ?? 88);
        window.scrollTo({ top, behavior: "instant" as ScrollBehavior });
        if (ps.flash) {
          el.classList.remove("flash");
          void el.offsetWidth;
          el.classList.add("flash");
        }
        updatePosition();
      }
    }
  });

  useEffect(() => {
    if (!win) return;
    const top = document.getElementById("sentinel-top");
    const bottom = document.getElementById("sentinel-bottom");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          if (e.target === bottom) extend("down");
          if (e.target === top) extend("up");
        }
      },
      { rootMargin: "1600px 0px" },
    );
    if (top) io.observe(top);
    if (bottom) io.observe(bottom);
    return () => io.disconnect();
  }, [win, extend]);

  /* ----------------------------------------------------------- position */

  function firstVisibleBlock(): HTMLElement | null {
    const art = articleRef.current;
    if (!art) return null;
    const x = art.getBoundingClientRect().left + Math.min(art.clientWidth / 2, 160);
    for (const y of [96, 140, 200, 280]) {
      let el = document.elementFromPoint(x, y) as HTMLElement | null;
      while (el && !el.dataset?.block) el = el.parentElement;
      if (el) return el;
    }
    const blocks = art.querySelectorAll<HTMLElement>("[data-block]");
    for (const b of blocks) if (b.getBoundingClientRect().bottom > 80) return b;
    return null;
  }

  const blockIndex = useMemo(() => {
    const m = new Map<string, { block: Block; chapter: number }>();
    for (const [ch, blocks] of chapters) for (const b of blocks) m.set(b.id, { block: b, chapter: ch });
    return m;
  }, [chapters]);

  const updatePosition = useCallback(() => {
    const el = firstVisibleBlock();
    if (!el) return;
    const id = el.dataset.block!;
    const info = blockIndex.get(id);
    if (!info) return;
    const next = { blockId: id, seq: info.block.seq, page: info.block.page, chapter: info.chapter };
    setPos((p) => (p && p.blockId === id ? p : next));
  }, [blockIndex]);

  const progressOf = useCallback(
    (p: Position | null): { book: number; minutesLeft: number } => {
      if (!p || !manifest) return { book: 0, minutesLeft: 0 };
      let before = 0;
      for (const c of manifest.chapters) if (c.idx < p.chapter) before += c.chars ?? 0;
      const blocks = chapters.get(p.chapter) ?? [];
      let inChapter = 0;
      let remaining = 0;
      for (const b of blocks) {
        if (b.seq < p.seq) inChapter += b.text.length;
        else remaining += b.text.length;
      }
      const total = manifest.totalChars || 1;
      return { book: Math.min(1, (before + inChapter) / total), minutesLeft: Math.max(0, Math.round(remaining / CHARS_PER_MINUTE)) };
    },
    [manifest, chapters],
  );

  // Know where we are as soon as text is on screen, not only after the first scroll.
  useEffect(() => {
    if (!win) return;
    const id = window.requestAnimationFrame(() => updatePosition());
    return () => window.cancelAnimationFrame(id);
  }, [win, chapters, updatePosition]);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      const dy = y - lastY.current;
      if (Math.abs(dy) > 12) {
        setChrome(dy < 0 || y < 40);
        lastY.current = y;
      }
      window.requestAnimationFrame(updatePosition);
    };
    // Desktop: bring the toolbar back when the pointer heads for the top edge.
    const onMove = (e: MouseEvent) => {
      if (e.clientY < 72) setChrome(true);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("mousemove", onMove);
    };
  }, [updatePosition]);

  // Save the reading position shortly after it changes, and when the page is hidden.
  useEffect(() => {
    if (!pos) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      api.savePosition(bookId, pos.blockId, progressOf(pos).book).catch(() => {});
    }, 1200);
  }, [pos, bookId, progressOf]);

  useEffect(() => {
    const flush = () => {
      if (!pos) return;
      fetch(`/api/books/${bookId}/position`, {
        method: "PUT",
        keepalive: true,
        headers: { "Content-Type": "application/json", "X-Proseway": "1" },
        body: JSON.stringify({ blockId: pos.blockId, progress: progressOf(pos).book }),
      }).catch(() => {});
    };
    const onVis = () => document.visibilityState === "hidden" && flush();
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pagehide", flush);
    };
  }, [pos, bookId, progressOf]);

  /* ----------------------------------------------------------- jumping */

  const jump = useCallback(
    async (t: JumpTarget, opts: { flash?: boolean; remember?: boolean } = {}) => {
      if (opts.remember !== false && pos) setBack(pos);
      setPanel((p) => (window.matchMedia("(max-width: 900px)").matches ? null : p));
      await loadChapter(t.chapter);
      pendingScroll.current = { blockId: t.blockId || undefined, seq: t.seq >= 0 ? t.seq : undefined, flash: opts.flash };
      setWin((w) => {
        if (w && t.chapter >= w[0] && t.chapter <= w[1]) return [w[0], w[1]];
        return [t.chapter, t.chapter];
      });
    },
    [pos, loadChapter],
  );

  /* ----------------------------------------------------------- annotations */

  const marksByBlock = useMemo(() => {
    const m = new Map<string, Mark[]>();
    for (const a of annotations) {
      if (a.kind !== "highlight" || a.orphaned) continue;
      if (!m.has(a.blockId)) m.set(a.blockId, []);
      m.get(a.blockId)!.push({ id: a.id, start: a.start, end: a.end, color: a.color ?? "yellow", hasNote: !!a.note });
    }
    for (const list of m.values()) list.sort((x, y) => x.start - y.start);
    return m;
  }, [annotations]);

  const bookmarks = useMemo(() => new Map(annotations.filter((a) => a.kind === "bookmark").map((a) => [a.blockId, a])), [annotations]);

  async function createHighlight(ranges: BlockRange[], color: HighlightColor, note = "") {
    const groupId = ranges.length > 1 ? uuidHex() : undefined;
    try {
      const created: Annotation[] = [];
      for (let i = 0; i < ranges.length; i++) {
        const r = ranges[i];
        const { annotation } = await api.createAnnotation(bookId, {
          kind: "highlight",
          blockId: r.blockId,
          start: r.start,
          end: r.end,
          color,
          note: i === 0 ? note : "",
          groupId,
        });
        created.push(annotation);
      }
      setAnnotations((a) => [...a, ...created]);
      return created;
    } catch (e) {
      toast(`Couldn't save the highlight: ${(e as Error).message}`);
      return [];
    }
  }

  async function updateAnnotation(a: Annotation, fields: { color?: HighlightColor; note?: string }) {
    try {
      const { annotation } = await api.updateAnnotation(a.id, fields);
      setAnnotations((list) =>
        list.map((x) => {
          if (x.id === annotation.id) return annotation;
          if (fields.color && a.groupId && x.groupId === a.groupId) return { ...x, color: fields.color };
          return x;
        }),
      );
    } catch (e) {
      toast(`Couldn't save: ${(e as Error).message}`);
    }
  }

  async function deleteAnnotation(a: Annotation) {
    const removed = annotations.filter((x) => x.id === a.id || (a.groupId && x.groupId === a.groupId));
    setAnnotations((list) => list.filter((x) => !removed.includes(x)));
    try {
      await api.deleteAnnotation(a.id);
      if (a.kind === "highlight") {
        toast("Highlight removed.", {
          label: "Undo",
          run: async () => {
            const groupId = removed.length > 1 ? uuidHex() : undefined;
            const restored: Annotation[] = [];
            for (const r of removed) {
              const { annotation } = await api.createAnnotation(bookId, {
                kind: "highlight",
                blockId: r.blockId,
                start: r.start,
                end: r.end,
                color: r.color ?? "yellow",
                note: r.note,
                groupId,
              });
              restored.push(annotation);
            }
            setAnnotations((list) => [...list, ...restored]);
          },
        });
      }
    } catch (e) {
      setAnnotations((list) => [...list, ...removed]);
      toast(`Couldn't remove it: ${(e as Error).message}`);
    }
  }

  async function toggleBookmark() {
    if (!pos) return;
    const existing = bookmarks.get(pos.blockId);
    if (existing) {
      await deleteAnnotation(existing);
      toast("Bookmark removed.");
      return;
    }
    try {
      const { annotation } = await api.createAnnotation(bookId, { kind: "bookmark", blockId: pos.blockId });
      setAnnotations((a) => [...a, annotation]);
      toast(`Bookmarked page ${pos.page}.`);
    } catch (e) {
      toast((e as Error).message);
    }
  }

  /* ----------------------------------------------------------- selection */

  useEffect(() => {
    let timer: number | undefined;
    const check = () => {
      const art = articleRef.current;
      if (!art) return;
      const sel = window.getSelection();
      const ranges = rangesFromSelection(sel, art);
      if (!ranges.length || !sel || sel.rangeCount === 0) return;
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      if (!rect.width && !rect.height) return;
      setPop({ rect, mode: "new", ranges });
    };
    const onUp = (e: Event) => {
      const art = articleRef.current;
      if (!art || !(e.target instanceof Node) || !art.contains(e.target)) {
        // Releasing outside the text still counts if the selection is inside it.
        if (!art || !window.getSelection()?.anchorNode || !art.contains(window.getSelection()!.anchorNode)) return;
      }
      window.clearTimeout(timer);
      timer = window.setTimeout(check, 10);
    };
    const onSelChange = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        setPop((p) => (p && p.mode === "new" ? null : p));
        return;
      }
      // Touch devices don't fire a reliable pointerup at the end of a selection drag.
      if (matchMedia("(pointer: coarse)").matches) {
        window.clearTimeout(timer);
        timer = window.setTimeout(check, 450);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.shiftKey) onUp(e);
    };
    document.addEventListener("pointerup", onUp);
    document.addEventListener("keyup", onKeyUp);
    document.addEventListener("selectionchange", onSelChange);
    return () => {
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("keyup", onKeyUp);
      document.removeEventListener("selectionchange", onSelChange);
      window.clearTimeout(timer);
    };
  }, []);

  function onArticleClick(e: React.MouseEvent) {
    const target = e.target as HTMLElement;
    const fn = target.closest<HTMLAnchorElement>("a.fnref");
    if (fn) {
      e.preventDefault();
      const id = fn.dataset.fn!;
      const info = blockIndex.get(id);
      if (info) setFootnote({ block: info.block, rect: fn.getBoundingClientRect() });
      return;
    }
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    const mark = target.closest<HTMLElement>("mark[data-ann]");
    if (mark) {
      const a = annotations.find((x) => x.id === mark.dataset.ann);
      if (a) {
        const rects = Array.from(document.querySelectorAll<HTMLElement>(`mark[data-ann="${a.id}"]`)).map((m) => m.getBoundingClientRect());
        const r = rects.reduce((acc, x) => (x.top < acc.top ? x : acc), rects[0] ?? mark.getBoundingClientRect());
        setPop({ rect: r, mode: "edit", annotation: a });
      }
      return;
    }
    setFootnote(null);
    // Tapping the page on a phone toggles the toolbars, like turning attention to the text.
    if (matchMedia("(pointer: coarse)").matches && !pop) setChrome((c) => !c);
  }

  // Move focus into the footnote popup when it opens, and back to the reference when it closes.
  const footnoteOpen = !!footnote;
  useEffect(() => {
    if (!footnoteOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    document.getElementById("fn-pop")?.focus({ preventScroll: true });
    return () => previous?.focus?.({ preventScroll: true });
  }, [footnoteOpen]);

  const citation = useCallback(
    (text: string, page: number | null) => {
      const t = manifest?.book;
      const who = t?.author ? `${t.author}, ` : "";
      return `“${text}” (${who}${t?.title ?? ""}${page ? `, p. ${page}` : ""})`;
    },
    [manifest],
  );

  /* ----------------------------------------------------------- keyboard */

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return; // a panel, dialog or popover already handled it
      const t = e.target as HTMLElement;
      if (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
          e.preventDefault();
          setPanel("search");
        }
        return;
      }
      if (pop) return;
      if (e.key === "Escape" && footnote) {
        setFootnote(null);
        return;
      }
      if (!prefs.shortcuts && e.key !== "Escape") return;
      const k = e.key.toLowerCase();
      if (k === "t") setPanel((p) => (p === "toc" ? null : "toc"));
      else if (k === "/" || k === "s") {
        e.preventDefault();
        setPanel("search");
      } else if (k === "n") setPanel((p) => (p === "notes" ? null : "notes"));
      else if (k === "a") setPanel((p) => (p === "appearance" ? null : "appearance"));
      else if (k === "b") toggleBookmark();
      else if (k === "h" && pos) {
        // Keyboard-first highlighting: the paragraph at the top of the screen.
        const info = blockIndex.get(pos.blockId);
        const b = info?.block;
        if (b && b.text && ["paragraph", "list_item", "heading", "caption", "footnote"].includes(b.type)) {
          const len = cpLength(b.text);
          const already = (marksByBlock.get(b.id) ?? []).some((m) => m.start === 0 && m.end === len);
          if (!already) createHighlight([{ blockId: b.id, start: 0, end: len }], "yellow").then(() => toast(`Highlighted the passage on p. ${b.page}.`));
        }
      }
      else if (k === "escape") {
        if (panel) setPanel(null);
        else navigate("/");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  /* ----------------------------------------------------------- render */

  if (error) {
    return (
      <main className="center-message">
        <h1>Can't open this book</h1>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={() => navigate("/")}>
          Back to library
        </button>
      </main>
    );
  }
  if (!manifest || !win) {
    return (
      <div className="reader-loading" aria-busy="true">
        <div className="reader-skeleton">
          <div className="skeleton skeleton-line" style={{ width: "40%", height: 28 }} />
          {Array.from({ length: 9 }, (_, i) => (
            <div key={i} className="skeleton skeleton-line" style={{ width: `${88 - (i % 3) * 9}%` }} />
          ))}
        </div>
      </div>
    );
  }

  const prog = progressOf(pos);
  const book = manifest.book;
  const lastChapter = manifest.chapters[manifest.chapters.length - 1].idx;
  const visibleChapters: number[] = [];
  for (let c = win[0]; c <= win[1]; c++) if (chapters.has(c)) visibleChapters.push(c);
  const popAnnotation = pop?.annotation;

  let prevPage = -1;
  return (
    <div className={`reader ${chrome || panel ? "chrome-on" : "chrome-off"} ${panel ? `panel-open panel-${panel}` : ""}`}>
      <a className="skip-link" href="#reading">
        Skip to text
      </a>
      <header className="topbar" aria-label="Reader toolbar">
        <button className="icon-btn" onClick={() => navigate("/")} aria-label="Back to library" title="Library (Esc)">
          <IconBack />
        </button>
        <div className="topbar-title">
          <span className="tb-book">{book.title}</span>
        </div>
        <nav className="topbar-actions" aria-label="Reader tools">
          <button className="icon-btn" aria-expanded={panel === "toc"} onClick={() => setPanel(panel === "toc" ? null : "toc")} aria-label="Contents" title="Contents (T)">
            <IconContents />
          </button>
          <button className="icon-btn" aria-expanded={panel === "search"} onClick={() => setPanel(panel === "search" ? null : "search")} aria-label="Search" title="Search (/)">
            <IconSearch />
          </button>
          <button className="icon-btn" aria-expanded={panel === "notes"} onClick={() => setPanel(panel === "notes" ? null : "notes")} aria-label="Notes and highlights" title="Notes (N)">
            <IconNotes />
          </button>
          <button className="icon-btn" aria-expanded={panel === "appearance"} onClick={() => setPanel(panel === "appearance" ? null : "appearance")} aria-label="Appearance" title="Appearance (A)">
            <IconType />
          </button>
          <button
            className={`icon-btn bookmark-btn ${pos && bookmarks.has(pos.blockId) ? "is-on" : ""}`}
            aria-pressed={!!(pos && bookmarks.has(pos.blockId))}
            onClick={toggleBookmark}
            aria-label={pos && bookmarks.has(pos.blockId) ? "Remove bookmark here" : "Bookmark this place"}
            title="Bookmark (B)"
          >
            <IconBookmark filled={!!(pos && bookmarks.has(pos.blockId))} />
          </button>
        </nav>
      </header>

      <main id="reading" className="page" tabIndex={-1}>
        <h1 className="visually-hidden">{book.title}</h1>
        <div id="sentinel-top" className="sentinel" aria-hidden="true" />
        {win[0] > 0 && (
          <div className="chapter-gap" aria-hidden="true">
            <div className="spinner" />
          </div>
        )}
        <article ref={articleRef} className="article" onClick={onArticleClick}>
          {visibleChapters.map((ch) => (
            <section key={ch} className="chapter" data-chapter={ch} aria-label={`Part ${ch + 1}`}>
              {chapters.get(ch)!.map((b) => {
                const marker =
                  b.page !== prevPage ? (
                    <div key={`pg-${b.seq}`} className="pagemark" role="doc-pagebreak" aria-label={`Page ${b.page}`} data-page={b.page}>
                      <span>{b.page}</span>
                    </div>
                  ) : null;
                prevPage = b.page;
                return [
                  marker,
                  <BlockView
                    key={b.id}
                    block={b}
                    bookId={bookId}
                    marks={marksByBlock.get(b.id) ?? NO_MARKS}
                    bookmarked={bookmarks.has(b.id)}
                    ocrAvailable={session.ocrAvailable}
                  />,
                ];
              })}
            </section>
          ))}
        </article>
        {win[1] < lastChapter ? (
          <div className="chapter-gap" aria-hidden="true">
            <div className="spinner" />
          </div>
        ) : (
          <footer className="book-end">
            <p>End of the book</p>
            <button className="btn" onClick={() => navigate("/")}>
              Back to library
            </button>
          </footer>
        )}
        <div id="sentinel-bottom" className="sentinel" aria-hidden="true" />
      </main>

      <footer className="statusbar" aria-label="Reading progress">
        <div className="status-row">
          <span className="status-page">{pos ? `p. ${pos.page} of ${book.pageCount}` : ""}</span>
          <span className="status-time">
            {prog.minutesLeft > 0 ? `${prog.minutesLeft} min left in chapter` : pos ? "Last page of chapter" : ""}
          </span>
          <span className="status-pct">{Math.round(prog.book * 100)}%</span>
        </div>
        <div className="status-track" role="progressbar" aria-label="Book progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(prog.book * 100)}>
          <span style={{ transform: `scaleX(${prog.book})` }} />
        </div>
      </footer>

      {back && (
        <div className="back-chip">
          <button
            className="back-chip-go"
            onClick={() => {
              const b = back;
              setBack(null);
              jump({ blockId: b.blockId, seq: b.seq, chapter: b.chapter }, { remember: false });
            }}
          >
            <IconReturn width={16} height={16} />
            Back to p. {back.page}
          </button>
          <button className="back-chip-x" aria-label="Dismiss" onClick={() => setBack(null)}>
            ×
          </button>
        </div>
      )}

      {pop && (
        <HighlightPopover
          key={popAnnotation?.id ?? "new"}
          rect={pop.rect}
          mode={pop.mode}
          color={popAnnotation?.color}
          note={popAnnotation ? annotations.filter((a) => a.id === popAnnotation.id || (popAnnotation.groupId && a.groupId === popAnnotation.groupId)).map((a) => a.note).filter(Boolean).join("\n") : ""}
          startWithNote={pop.startWithNote}
          onColor={async (c) => {
            if (pop.mode === "new" && pop.ranges) {
              await createHighlight(pop.ranges, c);
              window.getSelection()?.removeAllRanges();
              setPop(null);
            } else if (popAnnotation) {
              await updateAnnotation(popAnnotation, { color: c });
              setPop(null);
            }
          }}
          onNote={async (note) => {
            if (pop.mode === "new" && pop.ranges) {
              await createHighlight(pop.ranges, "yellow", note);
              window.getSelection()?.removeAllRanges();
            } else if (popAnnotation) {
              const first = annotations.find((a) => (popAnnotation.groupId ? a.groupId === popAnnotation.groupId : a.id === popAnnotation.id)) ?? popAnnotation;
              await updateAnnotation(first, { note });
            }
            setPop(null);
          }}
          onCopy={async () => {
            let text = "";
            let page: number | null = null;
            if (pop.mode === "new") {
              text = window.getSelection()?.toString().trim() ?? "";
              const first = pop.ranges?.[0];
              page = first ? blockIndex.get(first.blockId)?.block.page ?? null : null;
            } else if (popAnnotation) {
              const parts = annotations.filter((a) => a.id === popAnnotation.id || (popAnnotation.groupId && a.groupId === popAnnotation.groupId));
              text = parts.map((p) => p.exact).join(" ");
              page = popAnnotation.page;
            }
            const ok = await copyText(citation(text.replace(/\s+/g, " "), page));
            toast(ok ? "Copied with page reference." : "Couldn't copy on this device.");
            setPop(null);
          }}
          onDelete={
            popAnnotation
              ? () => {
                  deleteAnnotation(popAnnotation);
                  setPop(null);
                }
              : undefined
          }
          onClose={() => setPop(null)}
        />
      )}

      {footnote && (
        <div
          className="fn-pop"
          role="dialog"
          aria-label="Footnote"
          tabIndex={-1}
          id="fn-pop"
          style={{ top: Math.min(footnote.rect.bottom + 10, window.innerHeight - 220), left: Math.max(12, Math.min(footnote.rect.left - 140, document.documentElement.clientWidth - 372)) }}
        >
          <p>{footnote.block.text}</p>
          <div className="fn-pop-actions">
            <button
              className="link-btn"
              onClick={() => {
                const b = footnote.block;
                setFootnote(null);
                jump({ blockId: b.id, seq: b.seq, chapter: chapterOfSeq(b.seq) }, { flash: true });
              }}
            >
              Go to note
            </button>
            <button className="link-btn" onClick={() => setFootnote(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {panel === "toc" && (
        <TocPanel manifest={manifest} currentChapter={pos?.chapter ?? win[0]} currentSeq={pos?.seq ?? -1} onJump={(t) => jump(t)} onClose={() => setPanel(null)} />
      )}
      {panel === "search" && (
        <SearchPanel bookId={bookId} initial={searchQuery} onQuery={setSearchQuery} onJump={(t) => jump(t, { flash: true })} onClose={() => setPanel(null)} />
      )}
      {panel === "notes" && (
        <NotesPanel
          bookId={bookId}
          annotations={annotations}
          chapterOfSeq={chapterOfSeq}
          onJump={(t) => jump(t, { flash: true })}
          onUpdate={updateAnnotation}
          onDelete={deleteAnnotation}
          onClose={() => setPanel(null)}
        />
      )}
      {panel === "appearance" && <AppearancePanel prefs={prefs} update={updatePrefs} onClose={() => setPanel(null)} />}
      {!local && <span className="visually-hidden">Reading over your home network.</span>}
    </div>
  );
}

const NO_MARKS: Mark[] = [];

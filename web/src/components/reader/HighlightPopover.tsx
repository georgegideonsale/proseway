import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { HighlightColor } from "../../types";
import { IconCopy, IconNote, IconTrash } from "../Icons";

export const COLORS: { id: HighlightColor; label: string }[] = [
  { id: "yellow", label: "Yellow" },
  { id: "green", label: "Green" },
  { id: "blue", label: "Blue" },
  { id: "pink", label: "Pink" },
  { id: "purple", label: "Purple" },
];

interface Props {
  rect: DOMRect;
  mode: "new" | "edit";
  color?: HighlightColor | null;
  note?: string;
  startWithNote?: boolean;
  onColor: (c: HighlightColor) => void;
  onNote: (note: string) => void;
  onCopy: () => void;
  onDelete?: () => void;
  onClose: () => void;
}

export function HighlightPopover(p: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(!!p.startWithNote);
  const [draft, setDraft] = useState(p.note ?? "");
  const [pos, setPos] = useState<{ top: number; left: number; below: boolean }>({ top: -999, left: 0, below: false });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = document.documentElement.clientWidth;
    const touch = matchMedia("(pointer: coarse)").matches;
    // On touch screens the system selection menu sits above the selection, so we go below.
    let below = touch || p.rect.top - h - 12 < 64;
    let top = below ? p.rect.bottom + 10 : p.rect.top - h - 10;
    if (below && top + h > window.innerHeight - 8) {
      below = false;
      top = Math.max(64, p.rect.top - h - 10);
    }
    const left = Math.min(Math.max(8, p.rect.left + p.rect.width / 2 - w / 2), vw - w - 8);
    setPos({ top, left, below });
  }, [p.rect, editing]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        p.onClose();
        return;
      }
      if (editing) return;
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      const n = Number(e.key);
      if (n >= 1 && n <= 5) {
        e.preventDefault();
        p.onColor(COLORS[n - 1].id);
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault();
        setEditing(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [editing, p]);

  const save = () => {
    p.onNote(draft.trim());
    setEditing(false);
  };

  return (
    <div
      ref={ref}
      className={`hl-pop ${pos.below ? "is-below" : ""} ${editing ? "is-editing" : ""}`}
      style={{ top: pos.top, left: pos.left }}
      role="toolbar"
      aria-label={p.mode === "new" ? "Highlight selection" : "Edit highlight"}
      onMouseDown={(e) => {
        // Keep the text selection alive while using the toolbar.
        if ((e.target as HTMLElement).tagName !== "TEXTAREA") e.preventDefault();
      }}
    >
      {!editing ? (
        <div className="hl-pop-row">
          <div className="swatches" role="group" aria-label="Highlight colour">
            {COLORS.map((c, i) => (
              <button
                key={c.id}
                className={`swatch sw-${c.id}`}
                aria-label={`${c.label} highlight`}
                aria-pressed={p.color === c.id}
                title={`${c.label} (${i + 1})`}
                onClick={() => p.onColor(c.id)}
              />
            ))}
          </div>
          <span className="hl-pop-sep" aria-hidden="true" />
          <button className="icon-btn" onClick={() => setEditing(true)} aria-label={p.note ? "Edit note" : "Add note"} title="Note (N)">
            <IconNote />
          </button>
          <button className="icon-btn" onClick={p.onCopy} aria-label="Copy with page reference" title="Copy">
            <IconCopy />
          </button>
          {p.onDelete && (
            <button className="icon-btn" onClick={p.onDelete} aria-label="Remove highlight" title="Remove">
              <IconTrash />
            </button>
          )}
        </div>
      ) : (
        <div className="hl-note-edit">
          <label htmlFor="hl-note" className="visually-hidden">
            Note
          </label>
          <textarea
            id="hl-note"
            autoFocus
            rows={4}
            placeholder="Write a note…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                save();
              }
            }}
          />
          <div className="hl-note-actions">
            <span className="hint">Ctrl+Enter to save</span>
            <button className="btn btn-quiet" onClick={() => setEditing(false)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={save}>
              Save note
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

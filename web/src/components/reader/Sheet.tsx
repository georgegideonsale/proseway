import { useEffect, useRef, type ReactNode } from "react";
import { IconClose } from "../Icons";

/** Side panel on wide screens, bottom sheet on phones. Non-modal on desktop. */
export function Sheet({ title, onClose, children, actions }: { title: string; onClose: () => void; children: ReactNode; actions?: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("[data-autofocus]") ?? ref.current?.querySelector<HTMLElement>("h2");
    first?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      // Escape inside a text field cancels the edit, not the whole panel.
      const t = e.target as HTMLElement;
      if (t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && (t as HTMLInputElement).type !== "search")) return;
      e.preventDefault();
      onClose();
    };
    const el = ref.current;
    el?.addEventListener("keydown", onKey);
    return () => {
      el?.removeEventListener("keydown", onKey);
      if (prev && document.contains(prev)) prev.focus({ preventScroll: true });
    };
  }, [onClose]);
  return (
    <>
      <div className="sheet-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="sheet" ref={ref} role="dialog" aria-label={title}>
        <div className="sheet-grip" aria-hidden="true" />
        <header className="sheet-head">
          <h2 tabIndex={-1}>{title}</h2>
          <div className="sheet-head-actions">
            {actions}
            <button className="icon-btn" onClick={onClose} aria-label={`Close ${title.toLowerCase()}`}>
              <IconClose />
            </button>
          </div>
        </header>
        <div className="sheet-body">{children}</div>
      </aside>
    </>
  );
}

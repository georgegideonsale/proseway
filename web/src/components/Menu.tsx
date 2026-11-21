import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface MenuItem {
  label: string;
  run: () => void;
  danger?: boolean;
}

/** Accessible menu button (ARIA menu pattern with arrow-key navigation). */
export function Menu({ label, trigger, items }: { label: string; trigger: ReactNode; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const first = list.current?.querySelector<HTMLElement>("[role=menuitem]");
    first?.focus();
    const onDown = (e: MouseEvent) => {
      if (!list.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function onKey(e: React.KeyboardEvent) {
    const nodes = Array.from(list.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = nodes.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      nodes[(i + 1) % nodes.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      nodes[(i - 1 + nodes.length) % nodes.length]?.focus();
    } else if (e.key === "Escape" || e.key === "Tab") {
      setOpen(false);
      btn.current?.focus();
    }
  }

  return (
    <div className="menu">
      <button
        ref={btn}
        className="icon-btn"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {trigger}
      </button>
      {open && (
        <ul className="menu-list" role="menu" id={id} ref={list} onKeyDown={onKey}>
          {items.map((it) => (
            <li key={it.label} role="none">
              <button
                role="menuitem"
                className={`menu-item ${it.danger ? "is-danger" : ""}`}
                onClick={() => {
                  setOpen(false);
                  it.run();
                }}
              >
                {it.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

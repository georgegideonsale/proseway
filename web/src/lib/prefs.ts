import { useCallback, useEffect, useState } from "react";

export type Theme = "auto" | "paper" | "sepia" | "dusk" | "night";
export type ReaderFont = "literata" | "source-serif" | "atkinson" | "dyslexic" | "system";
export type Measure = "narrow" | "medium" | "wide";

export interface Prefs {
  theme: Theme;
  font: ReaderFont;
  size: number; // px
  leading: number;
  measure: Measure;
  justify: boolean;
  shortcuts: boolean; // single-key shortcuts (WCAG 2.1.4: must be possible to turn off)
}

export const DEFAULT_PREFS: Prefs = {
  theme: "auto",
  font: "literata",
  size: 19,
  leading: 1.62,
  measure: "medium",
  justify: false,
  shortcuts: true,
};

const KEY = "proseway.prefs.v1";

export const FONT_LABELS: Record<ReaderFont, string> = {
  literata: "Literata",
  "source-serif": "Source Serif",
  atkinson: "Atkinson Hyperlegible",
  dyslexic: "OpenDyslexic",
  system: "Book serif",
};

export const FONT_VARS: Record<ReaderFont, string> = {
  literata: "var(--font-literata)",
  "source-serif": "var(--font-source-serif)",
  atkinson: "var(--font-atkinson)",
  dyslexic: "var(--font-dyslexic)",
  system: "var(--font-system)",
};

const MEASURES: Record<Measure, string> = { narrow: "28em", medium: "34em", wide: "42em" };

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_PREFS;
}

function resolvedTheme(theme: Theme): Exclude<Theme, "auto"> {
  if (theme !== "auto") return theme;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "night" : "paper";
}

export function applyPrefs(p: Prefs) {
  const root = document.documentElement;
  const theme = resolvedTheme(p.theme);
  root.dataset.theme = theme;
  root.style.setProperty("--reader-font", FONT_VARS[p.font]);
  // OpenDyslexic runs large; scale it down a touch so the size setting feels consistent.
  root.style.setProperty("--reader-size", `${p.font === "dyslexic" ? Math.round(p.size * 0.9) : p.size}px`);
  root.style.setProperty("--reader-leading", String(p.leading));
  root.style.setProperty("--reader-measure", MEASURES[p.measure]);
  root.style.setProperty("--reader-align", p.justify ? "justify" : "left");
  const meta = document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]');
  const bg = getComputedStyle(root).getPropertyValue("--bg").trim();
  meta.forEach((m) => {
    m.content = bg;
    m.removeAttribute("media");
  });
}

export function usePrefs(): [Prefs, (patch: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  useEffect(() => {
    applyPrefs(prefs);
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      /* ignore */
    }
  }, [prefs]);
  useEffect(() => {
    if (prefs.theme !== "auto") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyPrefs(prefs);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [prefs]);
  const update = useCallback((patch: Partial<Prefs>) => setPrefs((p) => ({ ...p, ...patch })), []);
  return [prefs, update];
}

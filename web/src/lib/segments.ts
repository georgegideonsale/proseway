import type { Span } from "../types";
import { cpToU16, cpToU16Map } from "./offsets";

export interface Mark {
  id: string;
  start: number;
  end: number;
  color: string;
  hasNote?: boolean;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  styles: Span[]; // inline styles covering this segment
  marks: Mark[]; // highlights covering this segment
}

/**
 * Split block text into segments at every span/highlight boundary, so each segment has a
 * single set of styles and highlights. Concatenating segment texts always gives back the
 * original text exactly, which keeps DOM offsets equal to text offsets.
 */
export function segment(text: string, spans: Span[] = [], marks: Mark[] = []): Segment[] {
  // Spans and marks arrive in code points (server offsets); work in UTF-16 from here on.
  const map = cpToU16Map(text);
  if (map) {
    spans = spans.map((s) => [cpToU16(text, s[0], map), cpToU16(text, s[1], map), s[2], s[3]] as Span);
    marks = marks.map((m) => ({ ...m, start: cpToU16(text, m.start, map), end: cpToU16(text, m.end, map) }));
  }
  const len = text.length;
  const cuts = new Set<number>([0, len]);
  const validSpans = spans.filter((s) => s[0] >= 0 && s[1] <= len && s[0] < s[1]);
  const validMarks = marks.filter((m) => m.start >= 0 && m.end <= len && m.start < m.end);
  for (const s of validSpans) {
    cuts.add(s[0]);
    cuts.add(s[1]);
  }
  for (const m of validMarks) {
    cuts.add(m.start);
    cuts.add(m.end);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const start = points[i];
    const end = points[i + 1];
    if (end <= start) continue;
    out.push({
      start,
      end,
      text: text.slice(start, end),
      styles: validSpans.filter((s) => s[0] <= start && s[1] >= end),
      marks: validMarks.filter((m) => m.start <= start && m.end >= end),
    });
  }
  return out;
}

/** Turn FTS snippet markers (\x02 ... \x03) into parts for safe rendering. */
export function snippetParts(snippet: string): { text: string; hit: boolean }[] {
  const parts: { text: string; hit: boolean }[] = [];
  let hit = false;
  let buf = "";
  for (const ch of snippet) {
    if (ch === "\u0002" || ch === "\u0003") {
      if (buf) parts.push({ text: buf, hit });
      buf = "";
      hit = ch === "\u0002";
    } else {
      buf += ch;
    }
  }
  if (buf) parts.push({ text: buf, hit });
  return parts;
}

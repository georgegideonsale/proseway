/**
 * The server stores text offsets in Unicode code points (Python string indices). The DOM
 * counts UTF-16 code units, where characters outside the Basic Multilingual Plane (such as
 * mathematical letters like 𝑥) take two units. Convert at the boundary so highlights,
 * italics and footnote links land on the right characters in every block.
 */

/** UTF-16 index for each code-point index (length = code points + 1). Null when all BMP. */
export function cpToU16Map(text: string): number[] | null {
  let astral = false;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      astral = true;
      break;
    }
  }
  if (!astral) return null;
  const map: number[] = [];
  let u = 0;
  for (const ch of text) {
    map.push(u);
    u += ch.length;
  }
  map.push(u);
  return map;
}

export function cpToU16(text: string, cp: number, map = cpToU16Map(text)): number {
  if (!map) return cp;
  return map[Math.max(0, Math.min(cp, map.length - 1))];
}

export function u16ToCp(text: string, u16: number): number {
  let cp = 0;
  let u = 0;
  for (const ch of text) {
    if (u >= u16) break;
    u += ch.length;
    cp++;
  }
  return cp;
}

/** Number of code points (what the server calls the text length). */
export function cpLength(text: string): number {
  let n = 0;
  for (const _ of text) n++;
  return n;
}

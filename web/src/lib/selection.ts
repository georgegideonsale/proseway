/**
 * Map a DOM selection onto (blockId, start, end) text offsets.
 *
 * Every block renders its text inside a single `.bt` element whose text content is exactly
 * the block text. Anything else in the block (page markers, buttons) lives outside `.bt`, so
 * counting characters inside `.bt` gives offsets that match the stored text.
 */
export interface BlockRange {
  blockId: string;
  start: number;
  end: number;
}

function blockOf(node: Node | null): HTMLElement | null {
  let el: Node | null = node;
  while (el && !(el instanceof HTMLElement && el.dataset.block)) el = el.parentNode;
  return el as HTMLElement | null;
}

function textOf(block: HTMLElement): HTMLElement | null {
  return block.querySelector<HTMLElement>(".bt");
}

function offsetIn(container: HTMLElement, node: Node, offset: number): number {
  const r = document.createRange();
  r.setStart(container, 0);
  try {
    r.setEnd(node, offset);
  } catch {
    return 0;
  }
  return r.toString().length;
}

export function rangesFromSelection(sel: Selection | null, root: HTMLElement): BlockRange[] {
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return [];
  const range = sel.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) return [];
  const startBlock = blockOf(range.startContainer);
  const endBlock = blockOf(range.endContainer);
  const blocks = Array.from(root.querySelectorAll<HTMLElement>("[data-block]")).filter((b) => textOf(b));
  let i0 = startBlock ? blocks.indexOf(startBlock) : -1;
  let i1 = endBlock ? blocks.indexOf(endBlock) : -1;
  // Selections that start or end between blocks: snap to the nearest block inside the range.
  if (i0 < 0) i0 = blocks.findIndex((b) => range.intersectsNode(b));
  if (i1 < 0) {
    for (let k = blocks.length - 1; k >= 0; k--) {
      if (range.intersectsNode(blocks[k])) {
        i1 = k;
        break;
      }
    }
  }
  if (i0 < 0 || i1 < 0 || i1 < i0) return [];
  const out: BlockRange[] = [];
  for (let k = i0; k <= i1; k++) {
    const b = blocks[k];
    const bt = textOf(b)!;
    const len = bt.textContent?.length ?? 0;
    let start = 0;
    let end = len;
    if (k === i0 && bt.contains(range.startContainer)) start = offsetIn(bt, range.startContainer, range.startOffset);
    if (k === i1 && bt.contains(range.endContainer)) end = offsetIn(bt, range.endContainer, range.endOffset);
    // Trim whitespace at the edges so highlights don't start or end on a space.
    const text = bt.textContent ?? "";
    while (start < end && /\s/.test(text[start])) start++;
    while (end > start && /\s/.test(text[end - 1])) end--;
    if (end > start) out.push({ blockId: b.dataset.block!, start, end });
  }
  return out;
}

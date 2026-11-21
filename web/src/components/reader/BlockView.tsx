import { memo, type ReactNode } from "react";
import { assetUrl } from "../../api";
import { segment, type Mark } from "../../lib/segments";
import type { Block } from "../../types";

interface Props {
  block: Block;
  bookId: string;
  marks: Mark[];
  bookmarked: boolean;
  ocrAvailable: boolean;
}

function renderSegments(block: Block, marks: Mark[]): ReactNode[] {
  return segment(block.text, block.data.spans, marks).map((seg, i) => {
    let node: ReactNode = seg.text;
    for (const s of seg.styles) {
      if (s[2] === "i") node = <i>{node}</i>;
      else if (s[2] === "sup") node = <sup>{node}</sup>;
      else if (s[2] === "fnref" && s[3])
        node = (
          <sup>
            <a className="fnref" href={`#b-${s[3]}`} data-fn={s[3]} aria-label={`Footnote ${seg.text.trim()}`}>
              {node}
            </a>
          </sup>
        );
    }
    // Overlapping highlights nest; the innermost (latest) colour wins visually.
    for (const m of seg.marks) {
      node = (
        <mark className={`hl hl-${m.color}${m.hasNote ? " has-note" : ""}`} data-ann={m.id}>
          {node}
        </mark>
      );
    }
    return <span key={i}>{node}</span>;
  });
}

function BlockViewInner({ block, bookId, marks, bookmarked, ocrAvailable }: Props) {
  const common = {
    id: `b-${block.id}`,
    "data-block": block.id,
    "data-seq": block.seq,
    "data-page": block.page,
  };
  const ribbon = bookmarked ? <span className="blk-ribbon" aria-label="Bookmarked" role="img" /> : null;
  const text = <span className="bt">{renderSegments(block, marks)}</span>;
  switch (block.type) {
    case "heading": {
      const level = Math.min(Math.max(block.level || 1, 1), 4);
      const Tag = (["h2", "h3", "h4", "h5"] as const)[level - 1];
      return (
        <Tag {...common} className={`blk blk-h blk-h${level}`}>
          {ribbon}
          {text}
        </Tag>
      );
    }
    case "footnote":
      return (
        <aside {...common} className="blk blk-footnote" role="note">
          {ribbon}
          {text}
        </aside>
      );
    case "list_item":
      return (
        <p {...common} className="blk blk-li">
          {ribbon}
          {text}
        </p>
      );
    case "caption":
      return (
        <p {...common} className="blk blk-caption">
          {ribbon}
          {text}
        </p>
      );
    case "code":
      return (
        <pre {...common} className="blk blk-code">
          {ribbon}
          <code className="bt">{block.text}</code>
        </pre>
      );
    case "equation":
      if (block.data.src)
        return (
          <div {...common} className="blk blk-eq">
            <img src={assetUrl(bookId, block.data.src)} alt={block.text} loading="lazy" decoding="async" />
          </div>
        );
      return (
        <p {...common} className="blk blk-eq-text">
          {text}
        </p>
      );
    case "figure":
    case "page_image": {
      if ((block.data as { failed?: boolean }).failed) {
        return (
          <div {...common} className="blk blk-failed" role="note">
            Page {block.page} couldn't be converted. It's in the original PDF; you can try converting the book again.
          </div>
        );
      }
      const w = block.data.w || 4;
      const h = block.data.h || 3;
      return (
        <figure {...common} className={`blk blk-fig ${block.type === "page_image" ? "is-scan" : ""}`}>
          {block.data.src && (
            <img
              src={assetUrl(bookId, block.data.src)}
              alt={block.type === "page_image" ? `Scanned page ${block.page}` : `Figure on page ${block.page}`}
              loading="lazy"
              decoding="async"
              style={{ aspectRatio: `${w} / ${h}`, maxWidth: `min(100%, ${Math.round(w * 1.6)}px)` }}
            />
          )}
          {block.type === "page_image" && (
            <figcaption className="scan-note">
              {ocrAvailable
                ? "This page is a scan, and text recognition couldn't read it."
                : "This page is a scan. Install the optional OCR add-on and convert the book again to turn it into text."}
            </figcaption>
          )}
        </figure>
      );
    }
    case "table":
      return (
        <div {...common} className="blk blk-table" tabIndex={0} role="region" aria-label={`Table on page ${block.page}`}>
          <table>
            <tbody>
              {(block.data.rows ?? []).map((r, i) => (
                <tr key={i}>
                  {r.map((c, j) => (i === 0 ? <th key={j}>{c}</th> : <td key={j}>{c}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      return (
        <p {...common} className="blk blk-p">
          {ribbon}
          {text}
        </p>
      );
  }
}

export const BlockView = memo(
  BlockViewInner,
  (a, b) =>
    a.block === b.block &&
    a.bookmarked === b.bookmarked &&
    a.ocrAvailable === b.ocrAvailable &&
    a.marks.length === b.marks.length &&
    a.marks.every((m, i) => {
      const o = b.marks[i];
      return o.id === m.id && o.color === m.color && o.start === m.start && o.end === m.end && o.hasNote === m.hasNote;
    }),
);

export type BookStatus = "queued" | "converting" | "paused" | "ready" | "error" | "cancelled";

export interface Book {
  id: string;
  title: string;
  author: string;
  fileName: string;
  fileSize: number;
  pageCount: number;
  pagesDone: number;
  status: BookStatus;
  error: { code: string; message: string } | null;
  wordCount: number;
  hasCover: boolean;
  createdAt: number;
  updatedAt: number;
  lastOpenedAt: number | null;
  progress?: number;
  highlights?: number;
}

export type Span = [number, number, "sup" | "i" | "fnref", string?];

export type BlockType =
  | "heading"
  | "paragraph"
  | "footnote"
  | "list_item"
  | "code"
  | "equation"
  | "figure"
  | "caption"
  | "table"
  | "page_image";

export interface Block {
  seq: number;
  id: string;
  type: BlockType;
  page: number;
  level: number;
  text: string;
  data: {
    spans?: Span[];
    src?: string;
    w?: number;
    h?: number;
    caption?: string;
    rows?: string[][];
    marker?: string;
  };
}

export interface TocEntry {
  title: string;
  level: number;
  block: string;
  page: number;
  chapter: number;
}

export interface ChapterInfo {
  idx: number;
  firstSeq: number;
  blocks: number;
  startPage: number;
  endPage: number;
  chars: number;
}

export interface Manifest {
  book: Book;
  toc: TocEntry[];
  chapters: ChapterInfo[];
  totalBlocks: number;
  totalChars: number;
  stats: { ocr_pages?: number; scanned_pages?: number; pages?: number };
}

export type HighlightColor = "yellow" | "green" | "blue" | "pink" | "purple";

export interface Annotation {
  id: string;
  kind: "highlight" | "bookmark";
  color: HighlightColor | null;
  groupId: string | null;
  blockId: string;
  start: number;
  end: number;
  exact: string;
  note: string;
  page: number | null;
  seq: number | null;
  orphaned: boolean;
  createdAt: number;
  updatedAt: number;
}

export interface SearchResult {
  blockId: string;
  seq: number;
  page: number;
  chapter: number;
  type: string;
  snippet: string;
}

export interface SharingState {
  enabled: boolean;
  address: string;
  port: number;
  url: string;
  scheme: string;
  /** Sharing is on over HTTPS with Proseway's own certificate. */
  secure: boolean;
  secureAvailable: boolean;
  /** Plain-HTTP page on the next port that serves only the certificate and phone steps. */
  setupUrl: string;
  ca: { fingerprint: string; name: string; expiresAt: number } | null;
  expiresAt: number | null;
  pairing: { code: string; expiresAt: number; url: string } | null;
  locked: boolean;
  addresses: { interface: string; address: string }[];
  devices: { id: string; name: string; createdAt: number; lastSeen: number | null }[];
}

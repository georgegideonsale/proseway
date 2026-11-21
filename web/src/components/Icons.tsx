// A small, consistent icon set drawn for Proseway: 24px grid, 1.75px strokes, round joins.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

export const IconBack = (p: P) => (
  <svg {...base} {...p}>
    <path d="M15 5l-7 7 7 7" />
  </svg>
);
export const IconContents = (p: P) => (
  <svg {...base} {...p}>
    <path d="M4 6h11M4 12h16M4 18h9" />
  </svg>
);
export const IconSearch = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </svg>
);
export const IconNotes = (p: P) => (
  <svg {...base} {...p}>
    <path d="M6 3.5h9l3.5 3.5v13.5H6z" />
    <path d="M9 11h6M9 15h4" />
  </svg>
);
export const IconType = (p: P) => (
  <svg {...base} {...p}>
    <path d="M4 18l4.5-12L13 18M5.6 14h5.8" />
    <path d="M15 18l2.7-7 2.8 7M15.9 15.8h3.6" />
  </svg>
);
export const IconBookmark = ({ filled, ...p }: P & { filled?: boolean }) => (
  <svg {...base} {...p}>
    <path d="M7 3.5h10v17l-5-4-5 4z" fill={filled ? "currentColor" : "none"} />
  </svg>
);
export const IconPlus = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
export const IconClose = (p: P) => (
  <svg {...base} {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
export const IconPhone = (p: P) => (
  <svg {...base} {...p}>
    <rect x="7" y="2.5" width="10" height="19" rx="2.2" />
    <path d="M11 18.5h2" />
  </svg>
);
export const IconMore = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="6" cy="12" r="1" fill="currentColor" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
    <circle cx="18" cy="12" r="1" fill="currentColor" />
  </svg>
);
export const IconNote = (p: P) => (
  <svg {...base} {...p}>
    <path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 013 3L8 19z" />
  </svg>
);
export const IconCopy = (p: P) => (
  <svg {...base} {...p}>
    <rect x="8.5" y="8.5" width="11" height="11" rx="2" />
    <path d="M15.5 8.5V6a1.5 1.5 0 00-1.5-1.5H6A1.5 1.5 0 004.5 6v8A1.5 1.5 0 006 15.5h2.5" />
  </svg>
);
export const IconTrash = (p: P) => (
  <svg {...base} {...p}>
    <path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13" />
  </svg>
);
export const IconSettings = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" />
  </svg>
);
export const IconUpload = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 16V4M7 9l5-5 5 5" />
    <path d="M4.5 15v3.5A1.5 1.5 0 006 20h12a1.5 1.5 0 001.5-1.5V15" />
  </svg>
);
export const IconReturn = (p: P) => (
  <svg {...base} {...p}>
    <path d="M9 14l-5-5 5-5" />
    <path d="M4 9h10.5a5.5 5.5 0 010 11H11" />
  </svg>
);

# 6. Design system: bookbinding materials, two typefaces, one accent

- Status: accepted
- Date: 2026-11-21

## Decision

- **Motif:** bookbinding.
  - **Paper:** a cool, uncoated-paper ground (`#f5f6f1`).
  - **Ink:** an ink-blue text colour (`#1e2433`).
  - **Binding-cloth green:** `#2f5d50`, for anything you can act on.
  - **Crimson ribbon:** `#9c2f3a`, used *only* for bookmarks and reading progress (wordmark, cover progress ribbon, progress bar, bookmark markers).
- **Typefaces**, all SIL OFL and self-hosted so nothing loads from the network:
  - Literata, designed for long reading on screens, is the reading default and the display face.
  - Atkinson Hyperlegible Next is the interface face.
  - Readers can switch to Source Serif 4, Atkinson, OpenDyslexic, or a system book serif.
- **Themes:** Paper, Sepia, Dusk and Night, plus "match system". Each defines the same tokens (`web/src/styles/tokens.css`). Highlight colours are pale in light themes and translucent in dark ones, so text stays readable over them.
- **Spacing and shape:** a 4 px spacing scale. Small radii on controls, larger ones on floating surfaces, none on book covers. One easing curve, `cubic-bezier(0.22, 1, 0.36, 1)`, and all motion is turned off under `prefers-reduced-motion`.
- **Reading measure:** 28, 34 or 42 em, about 60–80 characters. Line-height 1.45 to 1.85.

## Contrast (WCAG AA)

Computed with the WCAG 2.x relative-luminance formula from the token values in `tokens.css`.

| Text / background | Paper | Sepia | Dusk | Night |
|---|---:|---:|---:|---:|
| ink on bg | 14.27 | 11.03 | 11.49 | 11.55 |
| ink-soft on bg | 7.30 | 6.59 | 7.63 | 7.80 |
| ink-faint on bg (small labels) | 5.52 | 5.56 | 5.30 | 5.43 |
| ink-faint on sunken surfaces | 5.08 | 4.90 | 5.71 | 5.65 |
| accent text on bg (links) | 6.90 | 6.38 | 7.68 | 7.97 |
| button text on accent | 7.49 | 7.62 | 8.37 | 7.66 |

In the light themes, ink over every highlight colour is at least 8.3:1. The first pass had paper `ink-faint` at 4.49:1, so I darkened it.

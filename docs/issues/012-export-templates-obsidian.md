# Custom export templates and an Obsidian folder target

**Labels:** enhancement, annotations, export, v2

## Problem
v1 exports a fixed Markdown format. Readers want to control it: readest#1734 asks for a customizable highlight export with template placeholders (13 comments), and readest#991 asks the same for notes. Many readers send highlights to Obsidian (readest#7061, and the Readwise to Obsidian path). Zotero users complain that exported Markdown is over-escaped (zotero#2343).

## Proposed approach
- Templates use a small, logic-light syntax (Mustache or Liquid subset) with variables `{{title}}`, `{{author}}`, `{{chapter}}`, `{{text}}`, `{{note}}`, `{{color}}`, `{{tags}}`, `{{page}}` (source PDF page), `{{date}}` and `{{link}}` (a `http://<proseway-host>/b/<id>#<anchor>` deep link), with sections for per-book and per-annotation output.
- Ship 3 presets: the default, "Obsidian with YAML front matter" and "plain quotes".
- **Folder target:** choose a folder (for example an Obsidian vault subfolder). Export writes one file per book and updates it in place on later exports. A "user notes" region marked by comments is never overwritten.
- Optional auto-export on change, off by default.
- Other formats from the same data: JSON (stable schema, versioned), CSV, and plain text.

## Acceptance criteria
- [ ] A template preview updates live against a real book.
- [ ] Re-exporting to the same folder keeps text the user wrote inside the protected region.
- [ ] Markdown escaping touches only characters that would change rendering. Test with highlights that contain `*`, `_`, `#` and `[]`.
- [ ] The JSON export validates against a published schema, and a re-import round trip does not change it.

## Notes
- No plugins or network calls. Obsidian users just point Proseway at their vault folder.

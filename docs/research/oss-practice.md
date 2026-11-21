# Open-source practice: what respected projects do, and what Proseway should copy

Date: 2026-11-21. Sources were read through `gh api` and raw files on each repo's default branch.

| Project | License | Stars | Why it's a useful model |
|---|---|---|---|
| readest/readest | AGPL-3.0 | 26.5k | Closest peer: an open-source ebook reader. Best SECURITY.md in the set (threat model for parsing untrusted book files). Contributor Covenant 3.0. SHA-pinned actions. pnpm. |
| koreader/koreader | AGPL-3.0 | 31.2k | Reader app. Sharp bug form (device, regression yes/no, last working version). CODEOWNERS. |
| astral-sh/uv | Apache-2.0 (+MIT) | 92.5k | Same license as Proseway. Short PR template. Clear scope statement in SECURITY.md. Detailed CHANGELOG. Prefixed labels. AI policy. |
| fastapi/fastapi | MIT | 105k | Our backend framework. CI with `astral-sh/setup-uv` + cache. `permissions: {}`. `persist-credentials: false`. Issues gated through Discussions. |
| excalidraw/excalidraw | MIT | 136k | React/TS app. Semantic PR titles. Size-limit check. No issue templates (a counter-example). |
| immich-app/immich | AGPL-3.0 | 120k | Local-first, privacy-minded. Label-driven release notes (`.github/release.yml`). PR template with an LLM-use question. Detailed bug form. pnpm monorepo. |

---

## 1. File list for Proseway

```
README.md
LICENSE                         # Apache-2.0 full text
NOTICE                          # Apache-2.0 attribution notice (third-party credits)
CHANGELOG.md                    # Keep a Changelog 1.1.0
CONTRIBUTING.md
CODE_OF_CONDUCT.md              # Contributor Covenant 3.0
SECURITY.md
AGENTS.md                       # instructions for AI coding agents (uv, immich, excalidraw all have one); CLAUDE.md can point to it
.editorconfig
.gitattributes                  # * text=auto eol=lf ; *.pdf binary
.pre-commit-config.yaml         # ruff, prettier/eslint, typos (fastapi and uv use pre-commit)
.github/
  ISSUE_TEMPLATE/
    config.yml
    1_bug_report.yml
    2_conversion_problem.yml    # Proseway-specific: "this PDF converted badly"
    3_feature_request.yml
  PULL_REQUEST_TEMPLATE.md
  CODEOWNERS                    # optional until there are several maintainers
  release.yml                   # categories for auto-generated release notes
  dependabot.yml                # or renovate.json; with a cooldown
  workflows/
    ci.yml
    release.yml
    zizmor.yml                  # lints workflow security (uv, fastapi, immich run it)
docs/
```

Skip for now: FUNDING.yml, CITATION.cff, translations of the README, OpenSSF Scorecard. Add them when there is a reason.

---

## 2. README outline

What the peers do:
- **readest and koreader:** logo, one sentence, badges, a nav row, Features, Screenshots, Downloads, Building from source, Troubleshooting, License.
- **uv:** one sentence, "Highlights" bullets, Installation per OS, link to docs, Features, Contributing, FAQ, License.
- **excalidraw:** Features, Quick start, Contributing, Integrations.

Keep it under about two screens and push detail into `docs/`.

```markdown
# Proseway

Proseway turns book PDFs into reflowable reading editions you can read comfortably
on any screen. It runs entirely on your computer.

![Proseway: a PDF page on the left, the reflowed reading edition on the right](docs/assets/screenshot.png)

[CI badge] [latest release badge] [license badge]          <- three badges is plenty

## What it does
- 4–6 bullets in plain words: "Detects headings, paragraphs and footnotes", "Removes running
  headers and page numbers", "Exports EPUB and HTML", ...

## What it doesn't do (yet)
- Scanned PDFs without a text layer need OCR first. Complex tables and math may come out wrong.
  Be honest here; it saves you many duplicate issues.

## Privacy
- Proseway does not send your files or any data anywhere. No telemetry, no accounts,
  no analytics. The server listens on 127.0.0.1 only.
- Fonts and scripts are bundled; the app makes no network requests at runtime.
- The only network use is <list exactly, e.g. "the optional update check, off by default">.

## Install
### Windows / macOS / Linux (release builds)   <- once you ship them
### From source
    git clone ... && cd proseway
    uv sync                 # backend (Python, uses uv.lock)
    pnpm install            # frontend (uses pnpm-lock.yaml)
    pnpm dev                # or: uv run proseway

## Usage
Short walkthrough with one screenshot or GIF of the reader.

## Contributing
One paragraph + link to CONTRIBUTING.md. Mention good first issues.

## License
Apache-2.0. Third-party components and their licenses: see NOTICE.
```

Put the privacy statement in its own heading near the top. It's Proseway's main promise, and immich and readest show users look for it. Every claim in it must be testable. A CI job that runs the app with networking blocked (or checks the built bundle for external URLs) is a cheap way to keep it true.

License check before 1.0: list every runtime dependency and its license in NOTICE. Some PDF libraries are copyleft; PyMuPDF, for example, is AGPL-3.0 or commercial. Make sure what you ship is compatible with distributing Proseway under Apache-2.0.

---

## 3. CONTRIBUTING.md outline

Built from uv (setup, testing, formatting and linting commands, releases) and immich (small PRs, discuss first, AI policy, feature freezes).

```markdown
# Contributing to Proseway
## Ways to help            - bug reports with sample PDFs you are allowed to share, docs, testing on Windows/macOS
## Before you start        - for anything bigger than a bug fix, open an issue or Discussion first
                           - "good first issue" and "help wanted" labels
                           - we don't assign issues; comment that you're working on it
## Development setup       - prerequisites (uv, Node LTS + pnpm via corepack), clone, `uv sync`, `pnpm install`
## Running the app         - backend and frontend dev servers, ports
## Tests                   - `uv run pytest`, `pnpm test`, `pnpm test:e2e`; where test PDFs live and their licenses
## Style                   - `uv run ruff format && uv run ruff check`, `pnpm lint`, `pnpm typecheck`; pre-commit
## Pull requests           - one change per PR; tests for behaviour changes; update CHANGELOG.md "Unreleased"
                           - Conventional Commit style PR titles (optional, excalidraw and immich enforce it)
## Use of AI tools         - see below
## Sample files and copyright - never attach copyrighted books; use public-domain or self-made PDFs
## Releases                - how maintainers cut a release (link to docs/releasing.md)
```

AI policy. uv requires its org AI policy; immich asks PRs to state the degree of LLM use and closes undisclosed LLM PRs. A middle path that fits a project built with AI help:

> You may use AI tools. You are responsible for every line: you must understand it, have run it, and be able to explain it in review. Say in the PR how AI was used. Write issue and PR descriptions in your own words. Low-effort generated PRs will be closed.

---

## 4. CODE_OF_CONDUCT.md

Use **Contributor Covenant 3.0** (readest uses 3.0). Many projects still use 2.1, but 3.0 is the current version. Take the text unchanged from contributor-covenant.org/version/3/0/ and fill in:
- An enforcement contact. Use an email address you will actually read, not a personal phone number.
- Who handles reports. With one maintainer, say so, and give a fallback for reports about the maintainer, such as GitHub's report-abuse form.

---

## 5. SECURITY.md

Proseway parses untrusted files and runs a local web server. That is exactly readest's situation, so copy its structure. Also borrow uv's habit of saying up front what is *not* a vulnerability.

```markdown
# Security policy
## Supported versions          - only the latest minor release gets fixes (table)
## Reporting a vulnerability   - use GitHub private vulnerability reporting:
                                 https://github.com/<org>/proseway/security/advisories/new
                               - do not open a public issue
                               - we aim to acknowledge within 3 business days and to give a fix timeline within 14 days
## Scope / threat model
   - Malicious PDFs: parser crashes, memory exhaustion, decompression bombs, very large images
   - Output safety: text and links from the PDF ending up as live HTML/JS in the reading edition (XSS)
   - Local server: must bind to 127.0.0.1; DNS-rebinding and cross-site requests from other browser tabs
     (check Host/Origin, no permissive CORS)
   - File system: path traversal in output names, writing outside the chosen folder
   - Supply chain: dependencies, GitHub Actions, release artifacts
## Out of scope                - attacks that need someone already able to run code as the same user; bugs in a
                                 PDF that only make the output look wrong (file a normal issue)
## Disclosure                  - we publish a GitHub Security Advisory (and CVE when it applies) with the fix release
```

Turn on "Private vulnerability reporting" in the repo's Settings → Security. readest links straight to `/security/advisories/new`.

---

## 6. Issue forms (YAML)

What works:
- Required version and OS fields (all of them).
- A "searched existing issues" checkbox (immich, koreader).
- Regression yes/no plus "last working version" (koreader).
- A field for a reproduction file (readest).
- `blank_issues_enabled: false`, with questions sent to Discussions (fastapi, immich).

### `.github/ISSUE_TEMPLATE/config.yml`

```yaml
blank_issues_enabled: false
contact_links:
  - name: Question or idea
    url: https://github.com/<org>/proseway/discussions
    about: Ask questions and discuss ideas here first.
  - name: Security problem
    url: https://github.com/<org>/proseway/security/advisories/new
    about: Please report security issues privately, not as an issue.
```

### `.github/ISSUE_TEMPLATE/1_bug_report.yml`

```yaml
name: Bug report
description: The app crashes, errors, or does something it shouldn't.
labels: ["type: bug", "status: needs-triage"]
body:
  - type: checkboxes
    attributes:
      label: Before you file
      options:
        - label: I searched open and closed issues and this is not a duplicate.
          required: true
        - label: I am on the latest release (or main).
          required: false
  - type: textarea
    attributes:
      label: What happened?
      description: Include the full error message if there was one.
    validations: { required: true }
  - type: textarea
    attributes:
      label: Steps to reproduce
      placeholder: "1. Open ...\n2. Click ...\n3. See error"
    validations: { required: true }
  - type: textarea
    attributes:
      label: What did you expect?
    validations: { required: true }
  - type: dropdown
    attributes:
      label: Regression?
      options: ["No / don't know", "Yes, it worked in an earlier version"]
    validations: { required: true }
  - type: input
    attributes:
      label: Last version that worked (if a regression)
  - type: input
    attributes:
      label: Proseway version
      description: Shown in Settings → About, or `uv run proseway --version`.
      placeholder: "0.3.1"
    validations: { required: true }
  - type: dropdown
    attributes:
      label: How did you install it?
      options: ["Release download", "From source (main)", "From source (tag)", "Other"]
    validations: { required: true }
  - type: dropdown
    attributes:
      label: Operating system
      multiple: true
      options: ["Windows", "macOS", "Linux"]
    validations: { required: true }
  - type: input
    attributes:
      label: OS version and browser
      placeholder: "Windows 11 24H2, Firefox 140"
    validations: { required: true }
  - type: textarea
    attributes:
      label: Logs
      description: Paste the backend console output. Remove anything private.
      render: shell
```

### `.github/ISSUE_TEMPLATE/2_conversion_problem.yml` (Proseway-specific)

Most reports for a converter will be "this PDF came out wrong". A dedicated form gets you the details you need.

```yaml
name: Conversion problem
description: A PDF converted, but the reading edition is wrong (order, headings, missing text, footnotes...).
labels: ["type: conversion", "status: needs-triage"]
body:
  - type: markdown
    attributes:
      value: |
        Please only share PDFs you have the right to share (public domain, your own, or openly licensed).
        If you can't share the file, describe it and include screenshots of the affected page.
  - type: dropdown
    attributes:
      label: What went wrong?
      multiple: true
      options: ["Reading order", "Headings / chapters", "Paragraphs joined or split", "Hyphenation",
                "Footnotes / endnotes", "Headers, footers or page numbers left in", "Images", "Tables",
                "Math", "Missing text", "Wrong characters / encoding", "Other"]
    validations: { required: true }
  - type: input
    attributes:
      label: Link to the PDF (if shareable)
  - type: dropdown
    attributes:
      label: Kind of PDF
      options: ["Born-digital (text can be selected)", "Scanned with text layer (OCR)", "Scanned, no text layer", "Don't know"]
    validations: { required: true }
  - type: input
    attributes:
      label: Page number(s) affected
    validations: { required: true }
  - type: input
    attributes:
      label: Language(s) of the book
  - type: textarea
    attributes:
      label: Expected vs actual
      description: Screenshots of the original page and of the output side by side are ideal.
    validations: { required: true }
  - type: input
    attributes:
      label: Proseway version
    validations: { required: true }
```

### `.github/ISSUE_TEMPLATE/3_feature_request.yml`

Fields:
- Problem you're trying to solve (required)
- Proposed solution
- Alternatives you considered
- Would you help build it? (dropdown)

Like fastapi, ask people to describe the *problem* before the solution.

---

## 7. Pull request template

uv's is two headings and works well. immich adds a checklist and an LLM question. A middle ground:

```markdown
## Summary
<!-- What does this change and why? Link the issue: "Fixes #123" -->

## How it was tested
<!-- Commands you ran, platforms you tried, sample PDFs used -->

## Screenshots
<!-- For UI changes: before / after -->

## Checklist
- [ ] One focused change; no unrelated edits
- [ ] Tests added or updated for behaviour changes
- [ ] `CHANGELOG.md` "Unreleased" updated (or label `changelog: skip`)
- [ ] Docs updated if user-facing

## Use of AI
<!-- None / helped with parts / mostly generated. You must understand and have run all of it. -->
```

---

## 8. CI

Patterns used by fastapi, readest, uv and immich:
- `permissions: {}` at the top, then grant per job.
- `persist-credentials: false` on checkout.
- `timeout-minutes` on every job.
- `fail-fast: false` on matrices.
- Actions pinned by full commit SHA with the tag in a comment (readest).
- A `zizmor` workflow to lint the workflows themselves.
- `astral-sh/setup-uv` with `enable-cache` and a `cache-dependency-glob` on the lock file (fastapi).
- `pnpm/action-setup` + `actions/setup-node` with `cache: pnpm` and `pnpm install --frozen-lockfile` (readest).
- `paths-filter` to skip jobs when unrelated files change. Useful later, not needed on day one.

Sample `.github/workflows/ci.yml`. It assumes `backend/` (pyproject.toml, uv.lock) and `frontend/` (package.json with a `packageManager: "pnpm@x.y.z"` field, pnpm-lock.yaml, .nvmrc). Action SHAs are the current releases as of 2026-11-21. Let Dependabot or Renovate bump them.

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

permissions: {}

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    name: backend (${{ matrix.os }}, py${{ matrix.python }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.13"]
        include:
          - os: ubuntu-latest      # oldest supported Python, one OS only
            python: "3.12"
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
          python-version: ${{ matrix.python }}
      - run: uv sync --locked --all-extras --dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run mypy src            # or pyright
      - run: uv run pytest -q

  frontend:
    name: frontend (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115 # v6.1.1
        with:
          package_json_file: frontend/package.json   # reads the packageManager field
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: frontend/.nvmrc
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck               # tsc --noEmit
      - run: pnpm test -- --run           # vitest
      - run: pnpm build

  e2e:
    # Full stack in a real browser, one OS to keep it fast. Use @playwright/test with its webServer option
    # to start `uv run proseway` and `pnpm preview`.
    needs: [backend, frontend]
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - uses: pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115 # v6.1.1
        with:
          package_json_file: frontend/package.json
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: frontend/.nvmrc
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml
      - run: uv sync --locked
        working-directory: backend
      - run: pnpm install --frozen-lockfile && pnpm exec playwright install --with-deps chromium
        working-directory: frontend
      - run: pnpm test:e2e                 # includes axe accessibility checks via @axe-core/playwright
        working-directory: frontend
```

Notes:
- Check the `with:` inputs (`python-version`, `package_json_file`, `cache-dependency-path`) against each action's README for the pinned version before relying on them.
- Run Windows in CI from day one. Path handling, line endings and file locking are where a local-first Python + Node app breaks.
- Keep a small set of public-domain test PDFs in the repo (or Git LFS) and snapshot-test the converted output. uv uses snapshot tests heavily. The Python equivalent is `syrupy` or `inline-snapshot`.
- Add `zizmor.yml`, which runs `zizmor` on `.github/workflows/` for pushes and PRs. Also add `dependabot.yml` for `github-actions`, `uv` and `npm` (pnpm) with a weekly schedule and a cooldown of several days, so you don't pick up a freshly published bad release.

---

## 9. Releases and changelog

What the peers do:
- **Tags:** readest, immich and excalidraw use `v`-prefixed SemVer (`v0.12.20`, `v3.4.2`). uv and fastapi use bare versions (`0.13.9`). koreader uses date versions (`v2026.07`).
- **uv:** `CHANGELOG.md` with per-release headings and "Released on <date>". Sections like Preview features / Performance / Bug fixes / Other changes, every entry linking its PR.
- **immich:** `.github/release.yml` maps `changelog:*` labels to release-note sections, so GitHub's "Generate release notes" button groups PRs automatically.

Recommendation for Proseway:
1. **SemVer with a `v` prefix**: `v0.1.0`, `v0.2.0`. While on 0.x, a minor bump may break things; say so in the README.
2. **`CHANGELOG.md` in Keep a Changelog 1.1.0 format**: an `## [Unreleased]` section at the top, and the sections Added / Changed / Deprecated / Removed / Fixed / Security. Each entry is one user-facing line ending in `(#123)`. Contributors add their line in the PR. Comparison links at the bottom.
   ```markdown
   # Changelog
   All notable changes to this project are documented here.
   The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
   and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

   ## [Unreleased]
   ### Fixed
   - Footnote markers are no longer merged into the previous word. (#42)

   ## [0.1.0] - 2026-12-15
   ### Added
   - First public release: PDF to EPUB and HTML conversion, local web UI. (#1)

   [Unreleased]: https://github.com/<org>/proseway/compare/v0.1.0...HEAD
   [0.1.0]: https://github.com/<org>/proseway/releases/tag/v0.1.0
   ```
3. **Release steps** (put them in `docs/releasing.md`):
   1. Move Unreleased entries under a new version heading with the date.
   2. Bump the version in `pyproject.toml` and `package.json`.
   3. Open a PR, merge it, then tag `vX.Y.Z` on main.
   4. A `release.yml` workflow triggered by `push: tags: ['v*']` builds the artifacts on the three OSes, writes `SHA256SUMS`, optionally adds build provenance with `actions/attest-build-provenance`, and creates a GitHub Release whose body is that version's CHANGELOG section.
4. Optionally add immich-style `.github/release.yml` categories as a cross-check. CHANGELOG.md stays the source of truth, because it is reviewed in PRs and ships with the source.

---

## 10. Labels

Large projects grow 50–100 labels (uv, excalidraw, fastapi). Most of the value comes from a small, prefixed set. uv uses `area:`, `bot:`, `test:`, `internal:`; immich uses `changelog:`; readest has a `type:` label in its bug form. Start with about 20:

| Group | Labels |
|---|---|
| type | `type: bug`, `type: conversion`, `type: feature`, `type: docs`, `type: chore` |
| area | `area: backend`, `area: frontend`, `area: pdf-parsing`, `area: layout`, `area: export`, `area: packaging` |
| platform | `os: windows`, `os: macos`, `os: linux` |
| status | `status: needs-triage`, `status: needs-info`, `status: needs-repro`, `status: blocked`, `status: confirmed` |
| contributor | `good first issue`, `help wanted` (GitHub surfaces these two names specially, so keep them exact) |
| other | `accessibility`, `security`, `breaking`, `changelog: skip`, `duplicate`, `wontfix` |

Create them with a script, so they're reproducible:

```bash
gh label create "type: bug" --color d73a4a --description "Something is broken" --force
gh label create "type: conversion" --color e99695 --description "A PDF converted incorrectly" --force
gh label create "status: needs-repro" --color fbca04 --description "Need a file or steps to reproduce" --force
# ...one line per label; --force updates existing ones
```

Delete GitHub's default labels you don't use (`invalid`, `question`), so triage stays simple.

---

## 11. Smaller habits worth copying

- **Discussions on, blank issues off** (fastapi, immich). Questions don't clutter the tracker.
- **AGENTS.md** at the root (uv, excalidraw, immich). Proseway is built with AI help, so tell agents how to run tests, which commands are safe, and which files never to edit. Keep CLAUDE.md as a one-line pointer to AGENTS.md, or the reverse.
- **CODEOWNERS** (koreader, immich) once a second maintainer joins, so reviews are requested automatically.
- **Semantic PR titles** (excalidraw, and immich's conventional-commit check). Optional. Helps if you later generate changelogs from titles.
- **A bundle-size check** (excalidraw's `size-limit`). Cheap protection for a local web UI.
- **CodeQL** (readest, immich). Free for public repos. Covers both Python and TypeScript.

## Top recommendations, in order

1. Write **SECURITY.md** around the real risk: untrusted PDFs, a localhost server, and HTML output. Turn on private vulnerability reporting.
2. Add **YAML issue forms**: bug, conversion problem, feature. Turn blank issues off and send questions to Discussions.
3. Set up **CI on ubuntu, windows and macos** with `setup-uv` (cache on uv.lock) and pnpm (`cache: pnpm`, `--frozen-lockfile`). Use SHA-pinned actions, `permissions: {}`, and zizmor.
4. Keep **CHANGELOG.md in Keep a Changelog 1.1.0** format with an Unreleased section, and use `v`-prefixed SemVer tags. Releases are built from tags.
5. Give the **README** a plain, testable privacy statement, a screenshot, and install steps. Add **CONTRIBUTING** with a clear AI-use policy, and Contributor Covenant 3.0.

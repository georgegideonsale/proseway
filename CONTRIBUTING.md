# Contributing to Proseway

Thanks for helping. Proseway is small and opinionated: it should stay local-only, faithful to the source text, and calm to read in. Changes that keep those three things true are welcome.

## Ways to help

- **Conversion problems** are the most valuable reports. Open a "Conversion problem" issue with:
  - the page number;
  - what you expected;
  - what you got;
  - if you can, a link to the PDF. It must be public domain or openly licensed. Please don't attach books you can't share.
- **Reader bugs:** include your browser and device, and the steps to reproduce.
- **Ideas:** check [ROADMAP.md](ROADMAP.md) and `docs/issues/` first. Many are already drafted.

## Development setup

You need Python 3.10+ with [uv](https://docs.astral.sh/uv/), Node.js 20+, and [pnpm](https://pnpm.io/).

```sh
git clone https://github.com/georgegideonsale/proseway
cd proseway
uv sync                      # Python deps, including dev tools
pnpm --dir web install       # web app deps
pnpm --dir web build         # builds into src/proseway/static
uv run proseway --data-dir ./data/dev-library
```

For live reloading of the web app, run the backend with `uv run proseway --no-browser`, then run `pnpm --dir web dev` in a second terminal. Open http://localhost:5173. Vite proxies `/api` to the backend.

## Tests

```sh
uv run pytest                               # pipeline, anchoring, API, security
uv run ruff check .                         # lint
pnpm --dir web test                         # unit tests (vitest)
pnpm --dir web exec playwright install chromium
pnpm --dir web e2e                          # browser tests, desktop and phone sizes
```

To measure conversion accuracy on real books:

```sh
uv run python scripts/fetch_test_books.py   # downloads ~150 MB of public-domain PDFs into data/
uv run python scripts/benchmark.py          # writes bench-results/benchmark.md
```

If you change the pipeline, run the benchmark before and after and include both tables in your pull request.

## Guidelines

- **Faithful text first.** The pipeline may remove layout artefacts (headers, footers, page numbers, line-break hyphens). It must never rewrite, summarise or drop the author's words. Add a test in `tests/test_pipeline.py` that pins down the behaviour you're changing.
- **No network calls.** No analytics, CDNs, web fonts or update checks. Optional features that need a download (such as OCR models) must be explicit and opt-in.
- **Licences.** New dependencies must be compatible with Apache-2.0. Add them to `docs/research/licenses.md`. AGPL and GPL libraries, and models with non-commercial terms, can't be bundled.
- **Accessibility.** Everything needs to work with a keyboard and be labelled for screen readers. Keep text contrast at WCAG AA in all four themes.
- **Decisions.** Record significant decisions as a short ADR in `docs/decisions/`.
- **Commits.** Small and focused, with a message saying *why*.

## Using AI tools

You're welcome to use AI coding assistants. You're responsible for every line you submit. Read it, run the tests, and be ready to explain it.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind and assume good faith.

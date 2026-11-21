# Optional local AI through Ollama (off by default)

**Labels:** enhancement, ai, later

## Problem
Some readers want help with hard text: a context-aware assistant (readest#1741, 9+), Readwise's Ghostreader (define terms, simplify passages, ask questions), or Kindle-style X-Ray (who is this character?). Converter users also want Ollama support for LLM-assisted cleanup (marker#683). Proseway's promise is that nothing leaves the machine, so cloud LLMs are out.

## Proposed approach
- A Settings toggle, **off by default**, plus an Ollama endpoint field (default `http://127.0.0.1:11434`) and a model picker filled from `/api/tags`. Refuse non-loopback endpoints unless the user confirms a LAN address explicitly.
- Features, each with its own toggle:
  1. **Explain selection:** plain-language explanation of the selected passage, using the surrounding paragraph as context.
  2. **Define in context:** what this word or term means in this sentence.
  3. **Chapter summary:** on request, using text up to the reader's current position to avoid spoilers.
  4. **Who/what is this (X-Ray):** gathers earlier mentions of a name from the full-text index and summarizes them, limited to text already read.
  5. **Ask the book:** questions answered by retrieval over the book's FTS index or local embeddings, with citations that link to locations.
- Every answer shows the model name and links its sources. Answers are not saved unless the user saves them as a note.

## Acceptance criteria
- [ ] With the toggle off, there is no AI UI and no requests to any port.
- [ ] With Ollama absent, the UI explains how to install it and degrades gracefully.
- [ ] Spoiler-safe mode never sends text beyond the current position, as verified by logging the prompt.
- [ ] Each "ask the book" answer cites at least one location that opens correctly.
- [ ] Works with a 7–8B model on a laptop without a GPU, possibly slowly, with streaming output and a cancel button.

## Notes
- Never run AI during import by default. LLM cleanup of conversion output can invent text (see marker#1081), so if it is ever added it must be opt-in, applied per page, and shown as a diff.
- The prompt text is visible to the user in a "show prompt" disclosure.

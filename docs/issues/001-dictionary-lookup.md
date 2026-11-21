# Dictionary lookup (offline)

**Labels:** enhancement, reader, v2

## Problem
Readers want to look up a word without leaving the book, and they want to choose the dictionary. readest#170 (multiple dictionary providers, 14+, 21c), foliate#791 (custom dictionary), foliate#323 (GoldenDict). Kindle users see instant lookup as a basic feature. Proseway has no network dependency, so lookups have to work offline.

## Proposed approach
- Support **StarDict** (`.ifo/.idx/.dict[.dz]`) and **DICT/dictd** files that the user installs into a `dictionaries/` folder. Ship no dictionaries by default. Offer an optional download of a public-domain set (Wiktionary extracts, WordNet) only after the user asks for it.
- Index headwords in SQLite at install time. Look up with normalization: case folding, stripping punctuation, simple stemming or lemmatization per language, then falling back to the longest prefix match.
- UI: double-click on desktop or long-press on the phone opens a popover with the definition. Multiple dictionaries appear as tabs in a user-set order. Add a "copy" button and a "save to vocabulary" button (feeds issue 002).
- Choose the dictionary by book language from the conversion metadata, with a manual override.
- Optional: a "search the web" link that opens the user's browser. It is off by default and makes no automatic request.

## Acceptance criteria
- [ ] With a StarDict file installed, a lookup on a 1,000-page book returns in under 100 ms on a mid-range laptop and in under 300 ms on the phone over LAN.
- [ ] Works with the network unplugged.
- [ ] Inflected forms ("running", "ran") resolve to their headword for English.
- [ ] Opening the popover never turns the page or creates a highlight.
- [ ] Each looked-up word can be saved with its sentence and book location.
- [ ] Removing a dictionary folder removes it from the UI without a restart.

## Notes
- Look out for dictionary licenses. Do not bundle anything that cannot be redistributed.
- Lookups are not logged unless the user saves the word.

# Flashcards from highlights and saved words (spaced repetition)

**Labels:** enhancement, annotations, later

## Problem
Readers who study want to review what they marked instead of letting highlights sit unread. readest#789 asks for a vocabulary builder (15+). foliate#758 asks for an Anki export from a definition. KOReader's vocabulary builder, which reviews words with spaced repetition, is a frequently cited reason to use KOReader.

## Proposed approach
- A card source is either (a) a highlight with a note, where the highlight is the front and the note is the back, or the reverse, or (b) a saved dictionary word with its context sentence (from issue 001). Cloze cards come from a highlight with a selected span hidden.
- The user opts in per highlight ("make card"), per color (for example "all yellow highlights become cards"), or per book.
- Scheduling: **FSRS** (an open algorithm with open implementations), with SM-2 as a fallback setting. Review history is stored locally in SQLite.
- The review screen works on desktop and phone. Each card links back to its book location.
- Export to **Anki** as `.apkg` or a CSV that Anki can import, and to plain Markdown. Do not depend on AnkiConnect.

## Acceptance criteria
- [ ] Making a card from a highlight takes one tap or click.
- [ ] Editing or deleting the source highlight updates or retires the card, and the user is told about it.
- [ ] A daily review queue shows the due count and works offline on the phone.
- [ ] A test deck of 500 cards exports to `.apkg` and imports into Anki with scheduling reset.
- [ ] Review history is included in the JSON backup and restored by it.

## Notes
- No accounts and no sharing of decks.
- Keep this behind a "Study" section so casual readers never see it.

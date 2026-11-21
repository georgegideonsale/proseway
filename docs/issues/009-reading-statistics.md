# Reading statistics

**Labels:** enhancement, v2

## Problem
Readers like seeing how much and how fast they read. KOReader's statistics plugin is popular enough that third-party dashboards exist just to show its data (KoInsight). Requests: readest#589 (statistics sync, 12+), koreader#4865 (average words per minute, 8+), koreader#14466 (word counts). Reading speed also drives the v1 "time left in chapter" readout.

## Proposed approach
- Record reading sessions locally: book, start and end time, words or characters moved past, and device. Pause the timer after N minutes without interaction (default 2) or when the tab is hidden.
- Derived figures: time per day and week, time per book, words per minute (rolling median per book and overall), days read, books finished per year, and estimated time left.
- Views: a per-book panel (time spent, sessions, speed, completion date) and a stats page with a calendar heat map and weekly bars. No streaks or nagging by default.
- Export as CSV and JSON. Include it in the backup.

## Acceptance criteria
- [ ] A 30-minute session with ordinary page turns records within ±1 minute of wall-clock time, and idle time is excluded.
- [ ] Sessions from the phone (live or offline through issue 006) are attributed to the correct book and device.
- [ ] Statistics can be turned off entirely, and existing data can be deleted.
- [ ] The words-per-minute estimate is stable after 3 sessions, within 10% of a timed manual test.

## Notes
- Data stays on the machine, with no leaderboards or sharing.
- Keep the schema compatible enough to import KOReader's `statistics.sqlite3` later, if someone asks.

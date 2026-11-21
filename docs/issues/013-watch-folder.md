# Watch folder for automatic import

**Labels:** enhancement, library, import, v2

## Problem
Readers who keep their files in a folder (downloads, a Syncthing share, a calibre library) do not want to import each file by hand. foliate#1320 (watch folders, 14+), readest#1925 (read from a folder without importing, 7+, 15c) and readest#179 (recursive import, 10+). Proseway v1 ships bulk and recursive import. This issue adds watching.

## Proposed approach
- Add one or more watched folders in Settings, each with options for recursive scanning and automatic conversion or "list only".
- Use filesystem events (chokidar, watchdog or the platform equivalent) with a periodic rescan as a fallback. Wait until a file has stopped changing for N seconds before importing it.
- Find duplicates by content hash, so a file that already exists elsewhere is not imported twice. A file that was moved or renamed is matched to its existing book, keeping its annotations and position.
- A file deleted from the folder is **not** removed from the library automatically. Show a "source missing" badge instead.
- Conversion jobs from the watch folder join the normal queue with low priority and run one at a time, so the reader stays responsive.

## Acceptance criteria
- [ ] Dropping 50 PDFs into a watched folder queues all 50 with no duplicates.
- [ ] Renaming or moving a watched file keeps its annotations.
- [ ] A half-copied file is never imported. Test with a slow copy.
- [ ] CPU use stays under 5% while idle with a watched folder of 5,000 files.

## Notes
- Paths are stored relative to the watched root, so a library moved to another machine keeps working (see foliate#739).

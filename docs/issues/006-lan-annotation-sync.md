# Cross-device annotation sync over LAN (with offline phone reading)

**Labels:** enhancement, sync, v2

## Problem
In v1 the phone reads live from the desktop server, so it only works while both are on the same Wi-Fi. Readers want to keep reading on a train and merge their highlights later. Evidence: koreader#4587 (sync highlights across devices, 14+). readest#356 (35+), #192 (19+) and #2795 (9+) show people want sync they control, not a vendor cloud. readest#5033 shows the backlash when sync was put behind a paywall.

## Proposed approach
- **Offline copy on the phone:** "Download for offline" stores the converted book, its assets and its annotations in the phone browser (IndexedDB, with a service worker for the app shell). Installable as a PWA.
- **Change log, not a snapshot:** every annotation, bookmark and position change is an operation with a unique ID, a device ID, a Lamport or hybrid logical clock and a tombstone for deletes. When the phone sees the desktop again, it pushes and pulls operations.
- **Merge rules:** highlights and notes merge by ID. A note edited on both devices keeps both versions and flags the conflict. Reading position takes the furthest position with the newest timestamp, and asks when the two differ by more than a chapter.
- **Pairing:** keep the existing QR pairing. Sync runs only to paired devices on the LAN, authenticated with the pairing key, and the sync traffic is encrypted.
- Optional later step: desktop-to-desktop sync through a user-chosen folder (Syncthing, a USB stick), using the same operation log as files.

## Acceptance criteria
- [ ] Highlights made offline on the phone appear on the desktop within 5 s of reconnecting.
- [ ] Deleting a highlight on one device removes it on the other, and it does not reappear after a later sync.
- [ ] A note conflict keeps both texts. No data is lost.
- [ ] Sync works with no internet access, only the LAN.
- [ ] An unpaired device on the same network cannot read or write annotations.

## Notes
- Storage quotas in the phone browser vary. Show storage used per book, and handle eviction by asking the user to re-download. Never lose unsynced operations: keep those in a separate store that is not evicted.

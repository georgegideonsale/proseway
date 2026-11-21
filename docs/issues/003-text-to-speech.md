# Text-to-speech read-aloud

**Labels:** enhancement, reader, accessibility, v2

## Problem
TTS is among the most-discussed requests: readest#258 (custom TTS engine, 13+, 70 comments) and koreader#545 (8+, 41c). Users also report TTS bugs that lose their place (readest#4235: auto page turn fails and the reading position is lost).

## Proposed approach
- **Engine 1, no setup:** the platform voice through the Web Speech API (`speechSynthesis`) in the browser. This works on desktop and on the phone's browser. Some platform voices are cloud-backed, so the UI shows "may use online voices" when the voice is not marked `localService`.
- **Engine 2, fully local:** **Piper** on the desktop server, streamed to the client as audio. The user downloads voices explicitly.
- Reading moves sentence by sentence from the converted text: segment sentences, highlight the current sentence, scroll or turn the page automatically, and skip footnote markers, headers and figure captions (configurable).
- Controls: play/pause, speed, previous/next sentence, a sleep timer, and lock-screen controls on the phone where the browser allows (Media Session API).
- The reading position follows TTS and is saved continuously.

## Acceptance criteria
- [ ] Starting TTS from a selected sentence reads from that sentence.
- [ ] When TTS stops for any reason, the saved position is the last sentence spoken.
- [ ] Page turns during TTS never skip or repeat a sentence across a chapter boundary.
- [ ] With Piper selected, no audio or text leaves the machine. Verify by watching network traffic.
- [ ] TTS keeps playing with the phone screen off, where the platform allows it, and documents where it does not.

## Notes
- Handle math and tables: read the alt text or skip them with a short "table skipped" notice.
- Support pronunciation overrides per book (a small find-and-replace list).

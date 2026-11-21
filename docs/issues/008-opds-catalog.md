# OPDS catalog (serve and browse)

**Labels:** enhancement, library, later

## Problem
People with self-hosted libraries (calibre-web, Kavita, Komga) use OPDS to browse and download books. Requests: readest#2970 (OPDS-PS, 8+), koreader#10635 (download several books from OPDS, 11+), koreader#10551 (covers in OPDS, 7+), foliate#994. Proseway already runs a local server, so it could also be an OPDS source for e-ink readers on the LAN such as KOReader.

## Proposed approach
- **Serve:** an OPDS 1.2 Atom feed (with OPDS 2 JSON optional) of the Proseway library at `/opds`, protected by the pairing key or a separate read-only token. Offer the converted book as EPUB where an exporter exists, and the original PDF always.
- **Browse:** add an OPDS catalog by URL. List, search and download into the import queue. PDFs go through conversion, and EPUBs go to issue 007.
- Store credentials for authenticated catalogs in the OS keychain, never in plain-text settings.

## Acceptance criteria
- [ ] KOReader on the same LAN can browse and download a book from Proseway's feed.
- [ ] Adding a calibre-web catalog lists books with covers and supports search.
- [ ] Downloading 10 books queues them with progress and a cancel button.
- [ ] The feed is not reachable without the token. Verify with curl from another machine.

## Notes
- Do not advertise the feed on the network (no mDNS) unless the user turns that on.
- The local-only rule means catalogs are added only by URL, with no built-in public catalogs.

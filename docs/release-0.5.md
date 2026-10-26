# TRACTOR 0.5.0 — Browser Search

Tractor 0.5 adds the local recursive search service used by Orc and a public in-browser results page.

- DuckDuckGo provides general web result snippets. Destination websites are not crawled by the search adapter.
- Wikimedia Commons provides image results with thumbnails, file pages, creators, and license details.
- Search jobs use the existing recursive investigation engine and save progress to Tractor's local history.
- The service binds to loopback, uses a per-user local token, and shuts down after the Orc processes that started it close.
- Tractor's application icon is a flying saucer, including the Windows and macOS native application assets.

Provider availability, result ranking, and coverage can vary. The engine does not claim exhaustive web coverage.

Native bundles and checksums are built only after the platform checks complete.

# TRACTOR 0.5.1 — Browser Search

Tractor 0.5 adds the local recursive search service used by Orc and a public in-browser results page.

0.5.1 fixes a service startup race: when a previous instance's service still held the shared local port (a predecessor from another data directory cannot be joined, only outlived), a starting service failed instead of waiting for the port to free. Startup now retries binding and registering for up to 30 seconds, and the local token file's creation race is handled the same way. It also fixes a startup hang on machines whose hostname does not resolve (common on macOS): binding no longer reverse-resolves the hostname before the port opens.

- DuckDuckGo provides general web result snippets. Destination websites are not crawled by the search adapter.
- Wikimedia Commons provides image results with thumbnails, file pages, creators, and license details.
- Search jobs use the existing recursive investigation engine and save progress to Tractor's local history.
- The service binds to loopback, uses a per-user local token, and shuts down after the Orc processes that started it close.
- Tractor's application icon is a flying saucer, including the Windows and macOS native application assets.

Provider availability, result ranking, and coverage can vary. The engine does not claim exhaustive web coverage.

Native bundles and checksums are built only after the platform checks complete.

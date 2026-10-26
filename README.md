# TRACTOR

**Global Intelligence Search · v0.5**

A native desktop application for evidence-led research across independent public sources. Enter one subject. The engine builds a query plan, retrieves successive result pages, follows traceable multilingual candidates, groups duplicate records, and saves the evidence and unfinished work on your device.

The launch screen has one wordmark and one search field. Results, source coverage, and evidence appear as the investigation runs. A completed run describes the recorded search scope; it does not imply exhaustive coverage of the internet.

## Download and run

Get a versioned native bundle or source archive from [GitHub Releases](https://github.com/nightwarelabz/tractor/releases). Native bundles include Python and dependencies: extract the complete archive and open Tractor. See [platform instructions and verification limits](docs/releases.md).

For source installation, extract a release source archive and install **Python 3.11–3.13** (3.12 recommended). DuckDuckGo, Wikimedia Commons, the original public APIs, and Torch need no keys; premium search providers are optional.

**Linux and macOS:** open a terminal in the extracted folder and run:

```bash
sh run.sh
```

**Windows:** double-click `run.cmd`. Install Python with its `py` launcher enabled.

The launcher creates a private `.venv` and installs dependencies on the first run. Later launches reuse it; dependency changes trigger installation again. First-time setup requires internet access. The desktop application makes no network requests until you start a search.

On Fedora, install a supported interpreter with `sudo dnf install python3.12`. The launcher also accepts Python 3.11 and 3.13; Python 3.14 is not supported by the Qt version used here. Qt 6.8 is pinned for older desktop CPU compatibility. Linux requires desktop graphics libraries; minimal systems may need EGL, OpenGL, and Qt xcb dependencies. Wayland is also supported. CI checks Linux, Windows and macOS independently. Native bundles are unsigned and not notarized; see the release workflow results for verified platforms.

To clone or update the development source:

```bash
git clone https://github.com/nightwarelabz/tractor.git
cd tractor
sh run.sh
```

For an existing checkout on main, run `git pull --ff-only`, then `sh run.sh` again.

Manual installation is also supported:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tractor
```

On Windows, activate with `.venv\Scripts\Activate.ps1`.

## Use it

1. Enter a name, organization, or topic and press Enter. Every search uses the same iterative engine; there is no shallow-search mode.
2. Read results as sources respond. Cards show source category, provider, available date, language, relevance, and a link. Filtering and sorting work during retrieval. New arrivals retain existing cards and preserve the record you are reading.
3. Open **Evidence** to inspect the original text, discovery chain, ranking calculation, content hash, and provider metadata. **Related** shows observed identifiers and retained duplicates. **Copy link** copies the source address; **Open source** opens your external browser for ordinary websites. Onion links are shown for opening in Tor Browser; they are never sent to the ordinary browser automatically.
4. Open **Coverage** to inspect attempts, provider errors, request/cache counts, languages, discovery passes, limits, and the queue of remaining searches.
5. **Stop** cancels outstanding requests and saves collected evidence. **Continue** resumes the saved queue, including after closing and reopening the app. **Refresh** starts a separate investigation using fresh requests and preserves its predecessor in History.
6. Search **History** by subject or collected source text. Reopen an investigation to review or continue it. **Export** writes full JSON, Markdown, or spreadsheet-safe CSV.

Orc can launch Tractor's local browser search service as its default search engine. The service binds only to `127.0.0.1`, stores investigations in Tractor's local database, and returns recursive web and image results to its in-browser results page. Website pages open in Orc; Commons image results include attribution and license links. Search terms are sent to the enabled providers shown in Tractor coverage, including DuckDuckGo and Wikimedia Commons by default. Coverage depends on those providers and is not exhaustive.

Results can be filtered by text, category, provider, language, domain, publication date, source region, observed entity type, and relevance, or sorted by relevance/newest/oldest. Unknown dates sort last. Partial publication dates remain partial; date filters use their possible range. Provider-reported source country is not treated as the subject's location.

Shortcuts: **Ctrl+L** focuses the search, **Esc** stops retrieval, **Ctrl+E** exports, and **Ctrl+H** opens history when the engine is idle.

## Sources

| Provider | Coverage | Reference |
| --- | --- | --- |
| Brave, optional | Independent web search with API credentials | [Brave API](https://api-dashboard.search.brave.com/app/documentation/web-search) |
| Mojeek, optional | Independent web search; storage-eligible API plan required | [Mojeek API](https://www.mojeek.com/support/api/search/request_parameters.html) |
| Kagi, optional | Current v1 standard search, with account personalization | [Kagi API](https://kagi.com/api/docs/) |
| Marginalia, optional | Independent small-web search; public development or private key | [Marginalia API](https://about.marginalia-search.com/article/api/) |
| Common Crawl, optional | Known URL/domain capture metadata; no full-content downloads | [Common Crawl index](https://index.commoncrawl.org/) |
| Wikidata | Knowledge records and multilingual labels; not an official company registry | [Wikibase API](https://www.mediawiki.org/wiki/Wikibase/API) |
| Crossref | Publication metadata, available abstracts, DOI identifiers | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |
| Internet Archive | Archived item catalog metadata; not a Wayback-wide crawl | [Internet Archive developer portal](https://archive.org/developers/) |
| GitHub | Public repository names and descriptions; not authenticated code search | [Repository search](https://docs.github.com/en/rest/search/search#search-repositories) |
| Europe PMC | Life-sciences publication metadata, abstracts, DOI and PubMed identifiers | [Europe PMC services](https://europepmc.org/RestfulWebService) |
| GDELT News | Recent global news article metadata, over a three-month window | [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) |
| Torch | Public onion index queried through Tor; indexed titles and text snippets | [Source configuration reference](https://github.com/searxng/searxng/blob/master/searx/settings.yml) |
| Onion SearxNG, optional | Additional onion engines through your own onion-hosted server | [SearxNG search API](https://docs.searxng.org/dev/search_api.html) |
| SearxNG, optional | General web result snippets from your configured server | [SearxNG search API](https://docs.searxng.org/dev/search_api.html) |

Select providers in **Settings**. Desktop and command-line searches use the same saved selections. An unavailable or rate-limited source is reported as failed, while other providers keep running. Failure is never represented as zero matches. Tor is included in new default searches. Existing custom source selections are preserved; enable **Torch · Tor onion index** in Settings if it is unchecked. The six clearnet API services were previously verified with five responding and GDELT timing out. The v0.3 Tor check independently verified real onion results and a saved mixed-network investigation.

To enable general web search, enter a SearxNG server URL in Settings and select its checkbox. Use a server you operate or trust, with JSON output enabled. Many public instances disable JSON access. HTTPS is required except for a local loopback server such as `http://127.0.0.1:8080`. Queries also reach the upstream engines selected by that server. No public instance is selected automatically. Changing the configured server requires a fresh investigation for that source; saved cursors are not silently sent to a different server.

Web providers add search-index discovery; specialized APIs retain their narrower scopes. News metadata is not full article text; GDELT's seen time is retained as an observation time, not invented as a publication date. Third-party coverage, availability, and indexing vary.

## Coverage controls

Settings groups **Web search**, **Specialized sources** and **Tor**. API keys come from `TRACTOR_BRAVE_API_KEY`, `TRACTOR_MOJEEK_API_KEY`, `TRACTOR_KAGI_API_KEY` and optional `TRACTOR_MARGINALIA_API_KEY`; set them before launch. Keys are never saved in settings or SQLite. Mojeek additionally requires confirmation that your plan permits persistent storage.

Choose General, Academic, Historical, Code, News or Maximum coverage profiles, or keep a custom provider selection. Language, region, freshness and budgets are configurable. Maximum coverage increases bounded work; it cannot promise completeness and may use more paid requests. Unsupported API controls appear as Coverage warnings.

Coverage shows configuration, local health, independent discovery indexes, domains, languages, warnings and remaining pages. A shared page found by two engines remains one evidence item with both discovery paths. SearxNG partial responses retain useful records and retry the same page. Common Crawl requires a known URL/domain, records capture time separately from publication time, and never downloads archive content.

Read the [provider matrix and official API references](docs/providers.md), [benchmark scope](docs/benchmarks.md), [provider SDK](docs/provider-sdk.md), [changelog](CHANGELOG.md), and [explicitly deferred milestones](docs/roadmap.md).

## Search Tor

Onion results appear in the same investigation with an **ONION** badge. They participate in ranking, filtering, duplicate grouping, evidence trails, local history, exports, and **Continue**. The launch screen still has a single search field.

1. Keep **Torch · Tor onion index** enabled in Settings.
2. Start and connect [Tor Browser](https://www.torproject.org/download/) before searching, or install the Tor client so the `tor` executable is on your PATH. The app detects local SOCKS proxies on ports **9050** and **9150**. If neither is available, automatic startup launches an installed Tor client in its own local data directory, with an automatically assigned loopback port.
3. Search normally. A separate status line shows Tor connection progress. Clearnet sources continue while Tor connects. A missing proxy, failed bootstrap, unavailable index, or changed search page appears as an error in Coverage, with unfinished work retained for retry.
4. Use **Copy link** to open a destination in Tor Browser. Only search-index text is retrieved automatically; no result pages, scripts, advertisements, frames, images, or binaries are loaded.

Settings also accepts an explicit local proxy, such as `socks5h://127.0.0.1:9150`. This overrides automatic detection; an unreachable explicit proxy fails without selecting another route. You can disable automatic startup. An app-started Tor process stops when the run ends or is cancelled. Existing Tor and Tor Browser processes are left running. The app does not download Tor, alter system services, or modify Tor Browser configuration.

For more indexes, configure your own **onion-hosted SearxNG** server under **Additional onion indexes**. Enable its `onions` category and JSON search responses. Its host must be a valid v3 onion address. Pagination and saved continuation work for this source too; actual upstream coverage depends on your server configuration. No hosted metasearch server is chosen automatically.

**Scope and routing:** Tor has no complete public directory. These sources search publicly indexed onion pages; private sites, unindexed pages, and services behind authentication are outside this coverage. An index snippet does not prove a destination is currently online or trustworthy. Onion requests use a separate SOCKS connection with remote DNS, checksummed v3 addresses, registered hosts, and no direct fallback. Other enabled providers still use your normal internet connection and receive the same query; this is not a Tor-only anonymity environment. A configured local SOCKS proxy is trusted to provide Tor routing.

Torch's robots policy is checked through Tor before a search. Disallowed routes, unreadable policies, and policy retrieval failures stop that source; an explicitly missing policy (404 or 410) permits retrieval. Wildcard, query-string, crawl-delay, and request-rate rules are honored using [Protego](https://github.com/scrapy/protego). Search forms are parsed as data, and ordinary hidden search fields are submitted only to the registered search endpoint. Interactive challenges and unexpected pages are recorded as unavailable, never as zero matches. These boundaries follow the [robots exclusion standard](https://www.rfc-editor.org/rfc/rfc9309.html) and [v3 onion address format](https://spec.torproject.org/rend-spec/encoding-onion-addresses.html).

## Engine and evidence

**A persistent work queue.** Each unit records provider, query, discovery pass, page, and cursor. Successful pages are checkpointed into SQLite. Interrupted pages remain queued. Continuation retries unfinished work without repeating successful pages. A provider has at most one active search; other providers can run concurrently. Repeated pages and cursors stop with an explicit coverage note.

Default budgets permit up to 72 adapter searches, 3 pages per provider/query, 240 seconds, and 6 concurrent jobs. Investigations are bounded to 3 discovery passes, 12 query variants, and 3,000 retained records; each retrieval accepts up to 15 records. These are resource ceilings, not completeness claims. **Continue** renews the per-run page, query, and time budgets. The record cap remains investigation-wide. Provider-specific caps and unavailable pagination are disclosed. GitHub exposes at most 1,000 search hits; Crossref's offset retrieval is bounded at 10,000. Torch continuation is bounded at offset 10,000; its reported total is an index estimate. GDELT does not paginate in this implementation.

Requests are rate-limited per host (GitHub: at least 6.2 seconds apart), with bounded retries, backoff, response sizes, caching, and connection/read timeouts. Multiple application instances have separate rate limiters. Refresh bypasses the saved HTTP cache.

**Traceable candidates.** The seed is user-supplied. Legal-suffix spelling changes and mechanical transliterations are hypotheses. An exact textual match to a Wikidata label can produce foreign-language candidates, each linked to a source and marked **discovered**, not confirmed. Matching names do not establish that a record describes the intended subject. Multiple URLs alone never promote an alias to corroborated. Discovery depth and variant limits appear in coverage notes.

Language detection leaves short names undetermined. Provider-declared languages are retained, with common Europe PMC language codes normalized. Multilingual Wikidata labels are requested in 25 configured languages, independently of browser or OS locale. Original text is never overwritten. A tested `TranslationBackend` protocol is available for integrations; **no machine-translation service is enabled**.

**Duplicate grouping.** An index matches canonical URLs, stable identifiers such as DOI and PubMed IDs, exact substantial content hashes, and bounded near-text comparisons. Conflicting stable identifiers prevent text-only merging. Short or empty metadata does not collapse unrelated records. Duplicate copies and their discovery paths remain stored and exported. Near-text matches are marked as inferences. Semantic matching of translated copies is not implemented.

**Transparent ranking.** Relevance combines title token overlap (up to 35), body overlap (20), a whole-token title phrase (20), corpus-aware BM25 term rarity (15), provenance (5), and stable identifiers (5). A traceable candidate query can rank a foreign-language record; candidate lexical contributions receive a 15% discount. Evidence shows the actual query and components used. The score is not an identity assertion or truth probability. Evidence completeness separately measures the available URL, discovery chain, original text, and date.

**Conservative relationships.** Shared domains, DOI, PubMed and Wikidata IDs, repository names, and exact email identifiers create observation edges. Shared hosting does not establish shared ownership, and shared names do not establish person identity. The evidence graph remains inspectable without imposing a graph dashboard.

## Command line

The same engine runs without opening Qt windows:

```bash
tractor --search "OpenStreetMap" --export-json investigation.json
tractor --providers
tractor --test-provider common_crawl
tractor --benchmark
tractor --search "OpenStreetMap" --profile General --language fr --max-jobs 100
tractor --search example.org --sources common_crawl --export-markdown captures.md
tractor --coverage INVESTIGATION_ID
tractor --refresh INVESTIGATION_ID --export-csv refreshed.csv
tractor --history
tractor --history "cartography"
tractor --resume INVESTIGATION_ID --export-json continued.json
tractor --search "OpenStreetMap" --sources wikidata crossref europe_pmc
tractor --search "Tor Project" --sources torch
tractor --search "Tor Project" --sources torch --tor-proxy socks5h://127.0.0.1:9150
```

From a launcher installation, replace `tractor` with `.venv/bin/tractor` on Linux/macOS or `.venv\Scripts\tractor.exe` on Windows. Alternatively, pass the same options to `sh run.sh` or `run.cmd`. Use `--data-dir ./local-investigations` to select a different local store. `--sources` overrides the saved choices for that command. Ctrl+C checkpoints collected results and remaining work.

## Storage, exports, and privacy

SQLite stores atomic investigation snapshots, individual record projections, cached responses, and a local full-text history index. Existing v0.1–v0.3 history migrates automatically to database schema 3. Back up the data directory before upgrading; older application versions cannot open a newer database schema. Older investigations without saved cursors can be reopened and refreshed. A stopped application leaves unfinished investigations visibly marked as interrupted.

JSON preserves results, duplicates, source payloads, query states, entities, edges, attempts, budgets, source configuration, and remaining tasks. Markdown includes sources, coverage, trails, attempts, and limits. CSV includes every retained result, discovery/provider metadata and a duplicate reference and neutralizes spreadsheet formulas. Exports are atomically replaced only after a complete write.

No telemetry, advertising, history upload, stored API credentials, or background searching. Search terms and discovered variants go to enabled providers; direct providers can observe your IP and all providers apply their own policies. Onion providers receive searches through the separate Tor connection. Enabling onion search does not route the other providers through Tor. Investigations, cache, and exports are stored unencrypted. Default data location comes from `platformdirs` (`~/.local/share/TRACTOR` on typical Linux systems); Settings shows the exact location. Remove that directory while the app is closed to delete history, cache, and settings. Structured logs use query IDs rather than full queries or raw provider error bodies.

Read [SECURITY.md](SECURITY.md) for retrieval boundaries and reporting.

## Architecture and development

```text
tractor/
  app.py                 Desktop and headless entry points
  settings.py            Shared provider configuration
  ui/                    Qt widgets and cancellable background worker
  core/                  Queue, models, provenance, deduplication, ranking, filters
  sources/               Public APIs, onion indexes, and optional SearxNG adapters
  language/              Detection, transliteration, translation protocol
  analysis/              Observed identifier relationships
  network/               Pooling, Tor lifecycle, route isolation, retries, robots policy
  credentials.py         Environment and secure-store credential abstraction
  benchmark/             Versioned offline retrieval regression fixtures
  storage/               Local health, SQLite migrations, full-text history, cache, atomic file writes
  export/                JSON, CSV, and Markdown reports
scripts/launch.py         First-run environment setup
```

The GUI owns no networking logic. A QThread runs an asyncio engine and sends detached snapshots via Qt signals. Each thread has its own SQLite connection. Closing during retrieval cancels requests before the worker is destroyed.

To add a source, implement `search(QueryVariant, SearchContext) -> SearchBatch` and register the adapter. Return normalized `SourceResult` objects, optional evidence-backed query candidates, and a `next_cursor` for pagination. Official API hosts must be registered in the network policy. The scheduler requires no provider-specific branches. Add mocked contract and pagination tests.

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
QT_QPA_PLATFORM=offscreen pytest -q
python -m build
```

Deterministic tests block live HTTP and exercise provider contracts, pagination, continuation, cancellation, provenance, ranking, deduplication, network boundaries, migrations, exports, and real Qt widgets. CI targets Python 3.11, 3.12, and 3.13 on Ubuntu, Windows and macOS, with dependency auditing and native smoke builds. Live-service checks are explicitly opt-in and separate.

Version 0.5 adds the loopback browser search service, general web snippets, and image results. Claim/entity intelligence is planned for 0.6; full-document/PDF extraction, timelines, refresh diffs and large-scale persistence are planned for 0.7. Translation integration, additional government/forum sources and signed installers remain deferred. Current adapters retrieve API records and search-index snippets; they do not crawl arbitrary result pages. Future crawlers must enforce robots policies and bound document parsing resources.

License: [AGPL-3.0](LICENSE).

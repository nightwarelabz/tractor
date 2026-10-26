# Provider matrix and configuration

Capabilities describe what this application implements, not everything the provider sells. Search results are discovery records. A returned snippet is not a verified destination document.

| Provider / ID | Purpose | Credentials | Pagination | Language / region | Index and important limits |
| --- | --- | --- | --- | --- | --- |
| DuckDuckGo Web / `duckduckgo` | General web discovery | None | Bounded HTML result pages | English default in this integration | Public HTML search interface; snippets only; destination sites are not fetched |
| Wikimedia Commons Images / `commons_images` | Image discovery | None | API continuation | Query-language matching | Wikimedia Commons file results; image page, license and creator metadata are retained |
| Brave / `brave` | Web discovery | `TRACTOR_BRAVE_API_KEY` | Up to 10 provider pages; local chunks preserve smaller budgets | Language and country hints | Independent index; plan must permit storing results; provider defaults apply when language is unknown |
| Mojeek / `mojeek` | Web discovery | `TRACTOR_MOJEEK_API_KEY` | Absolute result offsets; conservative 10-result requests | Language and regional boosts | Independent index; enable storage eligibility only for a plan that permits persistent retention |
| Kagi / `kagi` | Web discovery | `TRACTOR_KAGI_API_KEY` | Current v1 pages and local chunks | Region filter; no language request field in the implemented API | Aggregate; account settings can personalize results; generated answers excluded |
| Marginalia / `marginalia` | Small/independent web | Optional `TRACTOR_MARGINALIA_API_KEY`; otherwise documented `public` development key | Pages; stable size across continuation | No implemented locale controls | Independent index; per-domain limit 1–100; returned license retained; shared key can be rate-limited |
| SearxNG / `searxng` | General or news metasearch | User-configured JSON-enabled HTTPS server | Pages and local chunks | Language; no implemented region control | Returned upstream engines retained; partial failures keep the page queued |
| Wikidata / `wikidata` | Labels and candidate aliases | None | Continuation token | 25 configured label languages plus `mul` | Knowledge records, not an official company registry; exact label matches permit unverified candidate pivots |
| Crossref / `crossref` | Publication metadata | None | Bounded offset | Original metadata | DOI records, not full paper extraction |
| Europe PMC / `europe_pmc` | Life-sciences publications | None | Cursor | Provider language metadata | Abstracts and publication metadata |
| Internet Archive / `internet_archive` | Item catalog | None | Pages | Original metadata | Not a Wayback-wide crawl |
| GitHub / `github` | Public repositories | None | Pages; API cap | Original metadata | Not private repositories or authenticated code search |
| GDELT / `gdelt` | Recent news metadata | None | Response cap disclosed | Source language/region metadata | Three-month query window; seen time is not publication time |
| Common Crawl / `common_crawl` | Capture metadata for known URL/domain | None | Collection + block + row cursor | No language/region controls | Not keyword search; no WARC/content download; default latest collection is fixed in continuation cursor |
| Torch / `torch` | Public onion index | Local Tor connection | Form cursor | Query text | Independent discovery index; robots rules, v3 validation; index snippets only |
| Onion SearxNG / `onion_searxng` | Onion metasearch | Configured onion server and Tor | Pages and local chunks | Language | Upstream metadata, partial failures and onion-only results; no automatic destination access |

## Credentials

Set environment variables **before** launching. Restart the app after changing environment credentials. Settings and `tractor --providers` show configuration states without revealing values. A missing key is explicit; enabling a missing-key provider produces a retryable configuration failure. Profiles automatically choose only configured providers, including Marginalia's shared development key. They retain excluded providers in the configuration inventory.

Environment values override the injectable secure-store interface. There is no OS keychain UI in 0.4. No plaintext key setting, credential file, or database field exists. Authenticated responses use a bounded in-memory cache, cleared when the network session closes. Secret echoes are removed before persistence, exports and application logs. Credential changes invalidate provider cursor identities. Authentication failures and rate limits never become successful empty searches.

Mojeek documents authentication as an HTTPS query parameter. Authenticated URLs are not logged or stored in the response cache, and authenticated requests never follow redirects. Other new APIs use documented headers. The user is responsible for having a suitable API plan and storage rights; particularly check Brave and Mojeek retention terms. Marginalia returns licensing information which remains in exports; a commercial use may require a commercial key.

## Routing controls

Settings → Search controls exposes language (`auto`, `all`, or a code), country/region, category, freshness, custom dates, collection and per-domain limits. These are **provider hints**, not claims about publisher or subject location. Browser and operating-system locale never supply query hints. A Latin-script name remains language `und` unless there is adequate language evidence.

- Brave: day/week/month/year or custom range. Unknown query language uses the provider's default and reports that fact.
- Mojeek: day/month/year or custom range; language and region are boosts, not strict filters. Its `before` date is exclusive. Modified and crawled dates remain metadata, not publication dates.
- Kagi: day/week/month or custom after/before filters; those dates can mean created **or updated**. Standard search results only: no answer, summary, or extraction workflows.
- SearxNG: day/month/year; general or news category. Onion SearxNG always uses `onions`.
- Unsupported requested filters are reported in attempt warnings. Post-retrieval publication-date filtering remains separate in Results.

Quoted mechanical query variants are issued only to adapters that declare the operator contract. Other adapters record a skipped attempt. Common Crawl skips keyword-only variants without a network request and explains why. Known URL/domain seeds work directly. Automatic official-domain and identifier expansion is deferred to the evidence milestone; speculative domains are not invented.

## Coverage and local health

Coverage separates attempts, successful/partial/skipped/failed responses, warnings, pending cursors, request counts, providers, known independent search indexes, exact host domains, source categories and languages. Kagi is not treated as an independent index. SearxNG only adds known index families when explicit upstream engine names support them; unknown upstreams remain unknown.

Duplicate results retain every discovery observation, query, provider rank, page and URL. The same webpage returned by multiple search engines is **one evidence item with multiple discovery paths**, not independent factual confirmation. Full source-independence analysis is deferred to 0.5.

Health stores the most recent 200 completed attempts per provider locally: success rate, median latency, error class, rate-limit responses, unique and duplicate yields, and last success time. It provides only a bounded ordering preference after the first discovery pass. It never permanently disables a provider. No health information is transmitted.

## Official contracts consulted for 0.5

- [Brave web search](https://api-dashboard.search.brave.com/app/documentation/web-search)
- [Mojeek request parameters](https://www.mojeek.com/support/api/search/request_parameters.html), [response format](https://www.mojeek.com/support/api/search/json_response.html), [plans and retention](https://www.mojeek.com/services/search/web-search-api/)
- [Kagi current OpenAPI schema](https://kagi.com/api/docs/_spec/openapi.yaml?download): POST `/api/v1/search`, bearer token, `workflow=search`; legacy GET examples are not used
- [Marginalia current API](https://about.marginalia-search.com/article/api/): `api2.marginalia-search.com`, `API-Key` header
- [SearxNG search API](https://docs.searxng.org/dev/search_api.html)
- [Common Crawl index](https://index.commoncrawl.org/), [CDX query API](https://github.com/webrecorder/pywb/wiki/CDX-Server-API)
- [DuckDuckGo HTML search](https://html.duckduckgo.com/html/), [MediaWiki API image search](https://www.mediawiki.org/wiki/API:Search), [Wikimedia Commons image information](https://www.mediawiki.org/wiki/API:Imageinfo)

Live verification on 2026-09-17: Common Crawl returned capture metadata and a saved continuation cursor. Marginalia's shared public key returned HTTP 429 and was reported as rate-limited. Brave, Mojeek and Kagi had no configured keys in the development environment: their request contracts, pagination, authentication and failures were tested with deterministic fixtures, not live paid accounts. SearxNG was fixture-tested; no user server was configured. Availability can change.

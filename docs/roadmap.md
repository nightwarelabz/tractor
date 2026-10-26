# Milestones and explicitly deferred work

The next-generation specification is delivered in coherent releases. Version 0.4 completes the Coverage milestone and 0.5 adds browser search through Tractor's local service. Evidence Intelligence and Temporal Research remain future work. Existing investigations and safety boundaries remain supported.

| Specification sections | 0.4 disposition |
| --- | --- |
| 1–2: strengths and architecture | Preserved; separate provider catalog, capability, credential, health, diversity and benchmark modules added. Full future architecture is not populated with placeholder classes. |
| 3–13: discovery providers, credentials, configuration, health, diversity | Implemented with documented per-API limits. OS keychain UI deferred; environment and injectable secure-store interface are usable. |
| 14–15: planning and multilingual search | Mechanical spelling, suffix, initials/acronym, handle, transliteration and quoted-query candidates; explicit script/origin/state; 25 label languages and provider routing. Source-backed aliases continue to work. Automatic official-site, historical-name and identifier expansion awaits 0.5/0.6. |
| 16: translation | Existing protocol and original-text preservation retained. External/offline translation integration deferred; no translation service is silently enabled. |
| 17–18: ranking and benchmark | Native ranks retained; versioned offline fixture benchmark added. Production ranking weights unchanged. RRF and semantic reranking deferred pending comparative evidence. |
| Browser integration and images | 0.5 adds a loopback search service, DuckDuckGo web snippets, and Wikimedia Commons image results with license attribution. The service reuses the recursive investigation engine and local history. It does not crawl arbitrary destination pages or claim exhaustive coverage. |
| 19–23: entities, claims, lineage, Wikidata properties, more specialized sources | Deferred to 0.6. Existing identifier observations and label candidates remain; no assertion-level Claim model or independence claim is fabricated. |
| 24–30: clearnet HTML/PDF, archive content, timelines and diffs | Deferred to 0.6. Common Crawl capture metadata is implemented; arbitrary destinations, WARC/PDF downloads and arbitrary onion fetching remain disabled. |
| 31–38: adaptation, convergence, persistence journal and graph/contradictions | Local health orders later-pass work without suppressing providers. Full marginal-yield scheduling, claim graph, contradiction candidates, incremental storage and event journal deferred. Existing bounded persistent queue and history remain. |
| 39–41: results, Coverage and provenance | Discovery observations, multi-index badges, grouped provider health/configuration, warnings, script/kind query plan and exports implemented. Claim-centric views wait for 0.6. |
| 42–48: pivots, deduplication, authority and evidence | Manual known URL/domain lookup, existing stable-ID/hash/near-text deduplication and conservative relevance preserved. Automatic domain/identifier pivots, stronger syndication/authority models and scale work deferred. No LLM dependency added. |
| 49–58: exports, CLI, profiles, budgets, freshness, planner, network/cache/ranks | Implemented for Coverage records. Claims, timelines, graph exchange formats and live benchmark corpus management remain deferred. Filter support is explicit per provider. |
| 59–60: 10,000-record performance and virtualization | Hard budget ceiling exposed but 10,000-record performance is not claimed validated. Existing 60-card incremental display preserved. Full scale profiling and model/view migration are deferred to 0.6. |
| 61–64: releases, CI, live checks, governance | Source/native build scripts, release workflow, nine OS/Python checks, three native smoke builds, dependency audit and opt-in live checks added. Signing/notarization and enforcing hosted branch rules require repository/account configuration. See releases documentation. |
| 65–71: security, privacy, tests, docs, provider matrix and SDK | Updated for implemented features. Future PDF/DNS/claim controls are explicitly described as prerequisites, not claimed existing features. No deprecated third-party provider is a required dependency. |
| 72–75: milestone quality and completion | 0.4 and 0.5 changes are exposed through GUI, CLI, local service, persisted history and exports. Live paid APIs and cross-platform builds are only claimed verified when actual evidence exists. |

## 0.5 — Browser Search

Expose the existing recursive investigation engine through a loopback-only HTTP service for Orc. Add a general web search adapter, image discovery through Wikimedia Commons, local in-browser result rendering, and release bundles. The results page reports provider limits and retains creator/license attribution for image records.

## 0.6 — Evidence Intelligence

Introduce immutable observations as the dependency for richer entities, assertion-level claims, publication/archive/syndication lineage, conservative source-independence groups, Wikidata property enrichment, and contradiction candidates. Build claim/evidence views and exports only after these contracts and migration tests exist. Shared URLs or matching names never prove a person/entity identity. Search index agreement remains discovery agreement.

## 0.7 — Temporal Research

Design a separate document-fetch context with public-IP/DNS validation on every redirect, credential-free requests, robots policies, decoded byte limits, content-type checks, process-isolated PDF parsing and deadline enforcement. Add archive content, first/last observation, timelines and refresh diffs. Move snapshot rewrites to incremental normalized records and an event journal; measure 10,000-record save, reopen, filter and render costs before choosing UI virtualization. Arbitrary onion destinations remain outside automatic retrieval.

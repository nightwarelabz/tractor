from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict

from tractor.analysis.relationships import correlate
from tractor.core.convergence import Budget
from tractor.core.deduplication import DuplicateIndex, normalize_result
from tractor.core.diversity import observation
from tractor.core.models import Attempt, Edge, Investigation, QueryVariant, RetrievalTask, new_id, now
from tractor.core.provenance import record_discovery
from tractor.core.query import add_variant, build_plan
from tractor.core.scoring import rank_results
from tractor.credentials import redact
from tractor.language.detect import detect_language
from tractor.network.client import NetworkContext, SourceUnavailable
from tractor.sources.base import SearchBatch, SearchContext, SourceAdapter
from tractor.sources.capabilities import capabilities
from tractor.storage.database import Database
from tractor.storage.health import provider_health, record_health, scheduling_score

logger = logging.getLogger("tractor.investigation")
EventHandler = Callable[[str, object], None]


class InvestigationEngine:
    """A resumable, provider-fair work queue. No provider-specific scheduling branches."""

    def __init__(
        self,
        adapters: list[SourceAdapter],
        client: NetworkContext,
        database: Database,
        budget: Budget | None = None,
        on_event: EventHandler | None = None,
        cancelled: threading.Event | None = None,
        network_contexts: dict[str, NetworkContext] | None = None,
        provider_configuration: dict | None = None,
        search_options: dict | None = None,
        profile: str = "Custom",
    ):
        if not adapters or len({a.id for a in adapters}) != len(adapters):
            raise ValueError("Enable at least one source, with unique source IDs.")
        self.adapters = {a.id: a for a in adapters}
        self.client = client
        self.network_contexts = {"clearnet": client, **(network_contexts or {})}
        self.database = database
        self.budget = budget or Budget()
        self.on_event = on_event or (lambda *_: None)
        self.cancelled = cancelled or threading.Event()
        self._duplicates = DuplicateIndex()
        self.provider_configuration = provider_configuration or {}
        self.search_options = search_options or {}
        self.profile = profile
        self.health = provider_health(database.connection)

    async def _search(
        self, task: RetrievalTask, query: QueryVariant, inv: Investigation
    ) -> tuple[Attempt, SearchBatch]:
        attempt = Attempt(
            task.provider,
            query.id,
            query.value,
            query.language,
            task.pass_number,
            task_id=task.id,
            page=task.page,
            cursor=task.cursor,
            run_number=inv.runs,
            network=getattr(self.adapters[task.provider], "network", "clearnet"),
            scheduling_score=scheduling_score(self.health.get(task.provider, {})),
        )
        context = SearchContext(
            self.client,
            self.budget.max_results_per_query,
            cursor=task.cursor,
            page=task.page,
            requested_language=self.search_options.get("language", "auto"),
        )
        inv.attempts.append(attempt)
        attempt.status = "running"
        started = time.monotonic()
        self.on_event(
            "activity", {"provider": task.provider, "page": task.page, "pass": task.pass_number}
        )
        try:
            adapter = self.adapters[task.provider]
            if query.source == "quoted_phrase" and not capabilities(adapter).quoted_queries:
                attempt.status = "skipped"
                attempt.warnings = ["This provider does not expose an exact-phrase query contract."]
                return attempt, SearchBatch(skipped_reason=attempt.warnings[0])
            if hasattr(adapter, "routing_notes"):
                attempt.warnings = adapter.routing_notes(query)
            else:
                caps = capabilities(adapter)
                for option, attribute, defaults in (
                    ("language", "languages", {"auto", "all"}),
                    ("region", "regions", {""}),
                    ("freshness", "freshness", {"any"}),
                ):
                    value = self.search_options.get(option)
                    if value is not None and value not in defaults and not getattr(caps, attribute):
                        attempt.warnings.append(
                            f"{task.provider}: {option} control unsupported; original query used."
                        )
            if attempt.network not in self.network_contexts:
                raise SourceUnavailable("This source requires a configured Tor network connection.")
            context.client = self.network_contexts[attempt.network]
            batch = await self.adapters[task.provider].search(query, context)
            attempt.status = (
                "skipped" if batch.skipped_reason else "partial" if batch.partial else "success"
            )
            attempt.warnings = redact(
                attempt.warnings
                + batch.warnings
                + ([batch.skipped_reason] if batch.skipped_reason else [])
            )
            if batch.partial:
                attempt.error_category = "upstream_partial"
            attempt.result_count = len(batch.results)
            attempt.truncated = batch.truncated
            if batch.results:
                attempt.page_fingerprint = hashlib.sha256(
                    "\n".join(sorted(r.url for r in batch.results)).encode()
                ).hexdigest()
            return attempt, batch
        except asyncio.CancelledError:
            attempt.status = "cancelled"
            raise
        except Exception as exc:
            attempt.status = "error"
            attempt.error = (
                redact(str(exc)) if isinstance(exc, SourceUnavailable) else type(exc).__name__
            )
            attempt.error_category = (
                exc.category if isinstance(exc, SourceUnavailable) else "contract"
            )
            return attempt, SearchBatch()
        finally:
            attempt.language = context.search_language or query.language
            attempt.duration_ms = int((time.monotonic() - started) * 1000)
            attempt.cached_requests = context.stats.cached
            attempt.network_requests = context.stats.network
            attempt.rate_limit_events = context.stats.rate_limits
            if attempt.error_category == "rate_limited" and not attempt.rate_limit_events:
                attempt.rate_limit_events = 1
            attempt.finished_at = now()
            logger.info(
                "source_attempt",
                extra={
                    "investigation_id": inv.id,
                    "adapter": task.provider,
                    "query_variant": query.id,
                    "duration_ms": attempt.duration_ms,
                    "result_count": attempt.result_count,
                    "error_category": attempt.error_category,
                    "status": attempt.status,
                },
            )

    def _accept(
        self, inv: Investigation, query: QueryVariant, batch: SearchBatch, attempt: Attempt
    ) -> list[QueryVariant]:
        accepted_ids: set[str] = set()
        capacity = min(
            self.budget.max_results_per_query, max(0, self.budget.max_results - len(inv.results))
        )
        for result in batch.results[:capacity]:
            try:
                normalize_result(result)
            except (ValueError, UnicodeError, TypeError):
                attempt.rejected_count += 1
                continue
            accepted_ids.add(result.id)
            record_discovery(inv, query, result)
            result.metadata["discovery_observations"] = [observation(result)]
            if result.original_language == "und":
                result.original_language = detect_language(result.original_text)
                result.metadata["language_basis"] = "automatic estimate"
            duplicate = self._duplicates.find(result)
            if duplicate:
                result.duplicate_of, reason = duplicate
                inv.edges.append(
                    Edge(
                        result.id,
                        result.duplicate_of,
                        "duplicate_of",
                        [result.id],
                        confidence=0.94 if reason == "near_duplicate_text" else 1.0,
                        state="inference" if reason == "near_duplicate_text" else "observation",
                        explanation=reason,
                    )
                )
                original = self._duplicates.records[result.duplicate_of]
                original.matched_queries = list(
                    dict.fromkeys(original.matched_queries + result.matched_queries)
                )
                original.metadata.setdefault(
                    "discovery_observations", [observation(original)]
                ).append(observation(result))
                attempt.duplicate_yield += 1
            else:
                attempt.unique_yield += 1
            inv.results.append(result)
            self._duplicates.add(result)
            correlate(inv, result)
        new_variants = []
        for variant in batch.variants:
            if variant.parent_result not in accepted_ids or not variant.evidence_urls:
                continue
            if len(inv.plan.variants) >= self.budget.max_variants and not any(
                v.value.casefold() == variant.value.casefold() for v in inv.plan.variants
            ):
                inv.limits.append("Some candidate queries exceeded the query-variant limit.")
            if add_variant(inv.plan, variant, self.budget.max_variants):
                new_variants.append(variant)
                inv.edges.append(
                    Edge(
                        variant.parent_result,
                        variant.id,
                        "candidate_alias",
                        [variant.parent_result],
                        confidence=0.5,
                        state="inference",
                        explanation=variant.reason,
                    )
                )
        return new_variants

    def _checkpoint(self, inv: Investigation) -> None:
        inv.provider_health = provider_health(self.database.connection)
        self.database.save(inv)
        self.on_event("snapshot", inv.to_dict())

    @staticmethod
    def _key(task: RetrievalTask) -> tuple[str, str, str | None]:
        return task.provider, task.query_id, task.cursor

    def _enqueue(self, inv: Investigation, task: RetrievalTask) -> None:
        keys = {self._key(t) for t in inv.pending_tasks}
        keys.update(
            (a.provider, a.query_id, a.cursor) for a in inv.attempts if a.status == "success"
        )
        if self._key(task) not in keys:
            inv.pending_tasks.append(task)

    def _complete(
        self,
        inv: Investigation,
        task: RetrievalTask,
        attempt: Attempt,
        batch: SearchBatch,
        blocked: set[str],
    ) -> None:
        if attempt.status == "error":
            # HTTP retries have already been exhausted. Stop spending this run on this provider.
            blocked.add(task.provider)
            record_health(self.database.connection, inv.id, attempt)
            return
        partial = attempt.status == "partial"
        if partial:
            blocked.add(task.provider)
        if len(inv.results) + len(batch.results) > self.budget.max_results:
            inv.limits.append("The record budget interrupted a page; its cursor is retained.")
        elif not partial:
            inv.pending_tasks = [t for t in inv.pending_tasks if t.id != task.id]
        before = len(inv.unique_results)
        query = next(v for v in inv.plan.variants if v.id == task.query_id)
        variants = self._accept(inv, query, batch, attempt)
        record_health(self.database.connection, inv.id, attempt)
        while len(inv.pass_yields) < task.pass_number:
            inv.pass_yields.append(0)
        inv.pass_yields[task.pass_number - 1] += len(inv.unique_results) - before
        for variant in variants:
            if task.pass_number >= self.budget.max_passes:
                inv.limits.append("Some candidate queries reached the discovery-depth limit.")
                continue
            for provider in inv.source_ids:
                self._enqueue(inv, RetrievalTask(provider, variant.id, task.pass_number + 1))
        repeated_page = bool(attempt.page_fingerprint) and any(
            a is not attempt
            and a.provider == attempt.provider
            and a.query_id == attempt.query_id
            and a.status == "success"
            and a.page_fingerprint == attempt.page_fingerprint
            and a.cursor != attempt.cursor
            for a in inv.attempts
        )
        if partial:
            # Warnings live on the attempt; the pending cursor communicates retryable work.
            # Do not leave an unresolved global limit after a later successful retry.
            pass
        elif repeated_page:
            inv.limits.append(f"{task.provider}: pagination returned a repeated page; stopped.")
        elif batch.next_cursor and len(batch.next_cursor) <= 8192:
            seen_cursor = any(
                a.provider == task.provider
                and a.query_id == query.id
                and a.cursor == batch.next_cursor
                and a.status == "success"
                for a in inv.attempts
            )
            if seen_cursor:
                inv.limits.append(
                    f"{task.provider}: pagination returned a previous cursor; stopped."
                )
            else:
                self._enqueue(
                    inv,
                    RetrievalTask(
                        task.provider, query.id, task.pass_number, task.page + 1, batch.next_cursor
                    ),
                )
        elif batch.truncated:
            inv.limits.append(f"{task.provider}: additional matches are outside the API response.")
        inv.limits = list(dict.fromkeys(inv.limits))
        rank_results(inv)

    async def run(
        self,
        value: str,
        *,
        resume: Investigation | None = None,
        previous_id: str | None = None,
        investigation_id: str | None = None,
    ) -> Investigation:
        if resume:
            inv = resume
            changed = {
                key
                for key, adapter in self.adapters.items()
                if key in inv.source_context
                and inv.source_context[key] != getattr(adapter, "identity", key)
            }
            if changed:
                inv.limits.append(
                    "Provider configuration changed: "
                    + ", ".join(sorted(changed))
                    + ". Refresh to query the current configuration."
                )
                self.adapters = {key: a for key, a in self.adapters.items() if key not in changed}
            for attempt in inv.attempts:
                if attempt.status in {"pending", "running"}:
                    attempt.status = "interrupted"
            inv.status = "running"
            inv.stop_reason = ""
            inv.runs += 1
            inv.budget = asdict(self.budget)
        else:
            plan = build_plan(value, self.budget.max_variants)
            inv = Investigation(
                plan.seed,
                plan,
                id=investigation_id or new_id(),
                budget=asdict(self.budget),
                source_ids=list(self.adapters),
                source_context={
                    key: getattr(a, "identity", key) for key, a in self.adapters.items()
                },
                previous_investigation=previous_id,
                provider_configuration=self.provider_configuration,
                search_options=self.search_options,
                profile=self.profile,
            )
            for variant in plan.variants:
                inv.edges.append(
                    Edge(inv.id, variant.id, "search_variant", explanation=variant.reason)
                )
                for provider in self.adapters:
                    self._enqueue(inv, RetrievalTask(provider, variant.id))
        self._duplicates = DuplicateIndex(inv.results)
        self._checkpoint(inv)
        started = time.monotonic()
        active: dict[asyncio.Task, RetrievalTask] = {}
        blocked: set[str] = set()
        scheduled = 0
        page_start: dict[tuple[str, str], int] = {}
        for task in inv.pending_tasks:
            pair = (task.provider, task.query_id)
            page_start[pair] = min(page_start.get(pair, task.page), task.page)
        try:
            while inv.pending_tasks or active:
                if self.cancelled.is_set():
                    inv.status = "cancelled"
                    inv.stop_reason = "Cancelled by user; collected evidence retained"
                    break
                if time.monotonic() - started >= self.budget.max_seconds:
                    inv.status = "partial"
                    inv.stop_reason = "Time budget reached; remaining searches saved"
                    break
                if len(inv.results) >= self.budget.max_results:
                    inv.stop_reason = "Record budget reached"
                    break
                occupied = {t.provider for t in active.values()}
                running_ids = {t.id for t in active.values()}
                for task in sorted(
                    inv.pending_tasks,
                    key=lambda t: (
                        t.pass_number,
                        t.page,
                        -scheduling_score(self.health.get(t.provider, {}))
                        if t.pass_number > 1
                        else 0,
                    ),
                ):
                    if len(active) >= self.budget.concurrency or scheduled >= self.budget.max_jobs:
                        break
                    pair = (task.provider, task.query_id)
                    start_page = page_start.setdefault(pair, task.page)
                    if (
                        task.id in running_ids
                        or task.provider in occupied | blocked
                        or task.provider not in self.adapters
                        or task.page >= start_page + self.budget.max_pages_per_query
                    ):
                        continue
                    query = next((v for v in inv.plan.variants if v.id == task.query_id), None)
                    if query is None or query.state == "rejected":
                        inv.pending_tasks = [t for t in inv.pending_tasks if t.id != task.id]
                        continue
                    inv.passes = max(inv.passes, task.pass_number)
                    future = asyncio.create_task(self._search(task, query, inv))
                    active[future] = task
                    occupied.add(task.provider)
                    scheduled += 1
                if not active:
                    if scheduled >= self.budget.max_jobs:
                        inv.stop_reason = "Query budget reached"
                    elif blocked:
                        inv.stop_reason = (
                            "Available sources finished; failed searches can be retried"
                        )
                    elif any(t.provider not in self.adapters for t in inv.pending_tasks):
                        inv.stop_reason = (
                            "Some saved searches require disabled or reconfigured providers"
                        )
                    elif inv.pending_tasks:
                        inv.stop_reason = "Page budget reached; additional searches saved"
                    break
                done, _ = await asyncio.wait(
                    active, timeout=0.15, return_when=asyncio.FIRST_COMPLETED
                )
                for future in done:
                    task = active.pop(future)
                    attempt, batch = future.result()
                    self._complete(inv, task, attempt, batch, blocked)
                    self._checkpoint(inv)
            if not inv.stop_reason:
                inv.stop_reason = "No unsearched, evidence-backed variants or pages remain"
        except asyncio.CancelledError:
            inv.status = "cancelled"
            inv.stop_reason = "Investigation interrupted; remaining searches saved"
            raise
        except Exception:
            inv.status = "failed"
            inv.stop_reason = "Unexpected investigation error; remaining searches saved"
            raise
        finally:
            # Keep completed responses; unfinished cursors stay queued for continuation.
            for future, task in list(active.items()):
                if future.done() and not future.cancelled():
                    attempt, batch = future.result()
                    self._complete(inv, task, attempt, batch, blocked)
                else:
                    future.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            if inv.status == "running":
                successful = any(
                    a.status in {"success", "partial", "skipped"} for a in inv.attempts
                )
                inv.status = (
                    "failed"
                    if not successful
                    else "partial"
                    if inv.pending_tasks or blocked or inv.limits
                    else "complete"
                )
            self._checkpoint(inv)
        self.on_event("status", inv.stop_reason)
        return inv

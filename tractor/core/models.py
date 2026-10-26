from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from tractor.credentials import redact


def new_id() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class SourceType(StrEnum):
    WEB = "WEB"
    IMAGE = "IMAGE"
    ARCHIVE = "ARCHIVE"
    NEWS = "NEWS"
    DOCUMENT = "DOCUMENT"
    FORUM = "FORUM"
    CODE = "CODE"
    REGISTRY = "REGISTRY"
    DATASET = "DATASET"
    ONION = "ONION"


class AliasState(StrEnum):
    SEED = "seed"
    DISCOVERED = "discovered"
    CORROBORATED = "corroborated"
    REJECTED = "rejected"


@dataclass
class QueryVariant:
    value: str
    source: str = "seed"
    language: str = "und"
    state: str = AliasState.DISCOVERED
    parent_result: str | None = None
    reason: str = ""
    evidence_urls: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    kind: str = "seed"
    origin: str = "user"
    script: str = "Zyyy"
    transliteration_of: str | None = None
    target_domain: str = ""


@dataclass
class QueryPlan:
    seed: str
    variants: list[QueryVariant] = field(default_factory=list)


@dataclass
class Entity:
    id: str
    kind: str
    value: str
    normalized: str
    evidence_results: list[str] = field(default_factory=list)


@dataclass
class Edge:
    source: str
    target: str
    kind: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 1.0
    state: str = "observation"
    explanation: str = ""


@dataclass
class SourceResult:
    title: str
    url: str
    source_type: str
    source_provider: str
    id: str = field(default_factory=new_id)
    discovered_at: str = field(default_factory=now)
    published_at: str | None = None
    original_language: str = "und"
    translated_language: str | None = None
    original_title: str = ""
    translated_title: str | None = None
    original_text: str = ""
    translated_text: str | None = None
    excerpt: str = ""
    translated_excerpt: str | None = None
    author: str | None = None
    organization: str | None = None
    matched_queries: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    content_hash: str = ""
    canonical_url: str = ""
    relevance_score: float = 0.0
    evidence_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    parent_result: str | None = None
    discovery_path: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Attempt:
    provider: str
    query_id: str
    query: str
    language: str
    pass_number: int
    status: str = "pending"
    result_count: int = 0
    duration_ms: int = 0
    error: str | None = None
    cached_requests: int = 0
    network_requests: int = 0
    truncated: bool = False
    task_id: str = ""
    page: int = 1
    cursor: str | None = None
    run_number: int = 1
    rejected_count: int = 0
    page_fingerprint: str = ""
    network: str = "clearnet"
    error_category: str | None = None
    rate_limit_events: int = 0
    warnings: list[str] = field(default_factory=list)
    unique_yield: int = 0
    duplicate_yield: int = 0
    finished_at: str = ""
    scheduling_score: float = 0.0


@dataclass
class RetrievalTask:
    provider: str
    query_id: str
    pass_number: int = 1
    page: int = 1
    cursor: str | None = None
    id: str = field(default_factory=new_id)


@dataclass
class Investigation:
    query: str
    plan: QueryPlan
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    status: str = "running"
    stop_reason: str = ""
    passes: int = 0
    results: list[SourceResult] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    pass_yields: list[int] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    pending_tasks: list[RetrievalTask] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    source_context: dict[str, str] = field(default_factory=dict)
    runs: int = 1
    limits: list[str] = field(default_factory=list)
    previous_investigation: str | None = None
    provider_configuration: dict[str, Any] = field(default_factory=dict)
    provider_health: dict[str, Any] = field(default_factory=dict)
    search_options: dict[str, Any] = field(default_factory=dict)
    profile: str = "Custom"

    @property
    def unique_results(self) -> list[SourceResult]:
        return sorted(
            (r for r in self.results if r.duplicate_of is None),
            key=lambda r: (-r.relevance_score, r.discovered_at, r.id),
        )

    @property
    def coverage(self) -> dict[str, Any]:
        from tractor.core.diversity import diversity

        attempted = {a.provider for a in self.attempts}
        successful = {a.provider for a in self.attempts if a.status == "success"}
        failed = {a.provider for a in self.attempts if a.status == "error"}
        return {
            "sources_attempted": len(attempted),
            "sources_successful": len(successful),
            "sources_unavailable": len(failed - successful),
            "sources_with_errors": len(failed),
            "partial_responses": sum(a.status == "partial" for a in self.attempts),
            "skipped_searches": sum(a.status == "skipped" for a in self.attempts),
            "rate_limit_events": sum(a.rate_limit_events for a in self.attempts),
            "provider_warnings": sorted({w for a in self.attempts for w in a.warnings}),
            **diversity(self.results),
            "queries_issued": len(self.attempts),
            "network_requests": sum(a.network_requests for a in self.attempts),
            "cached_requests": sum(a.cached_requests for a in self.attempts),
            "languages_searched": sorted({a.language for a in self.attempts} - {"und"}),
            "languages_represented": sorted({r.original_language for r in self.results} - {"und"}),
            "regions_represented": sorted(
                {str(r.metadata["region"]) for r in self.results if r.metadata.get("region")}
            ),
            "results_retrieved": len(self.results),
            "unique_results": len(self.unique_results),
            "duplicates_removed": sum(r.duplicate_of is not None for r in self.results),
            "secondary_pivots": len({a.query_id for a in self.attempts if a.pass_number > 1}),
            "investigation_passes": self.passes,
            "limited_responses": sum(a.truncated for a in self.attempts),
            "pages_retrieved": sum(a.status == "success" for a in self.attempts),
            "pending_searches": len(self.pending_tasks),
            "invalid_records_skipped": sum(a.rejected_count for a in self.attempts),
            "runs": self.runs,
            "onion_results": sum(r.source_type == SourceType.ONION for r in self.unique_results),
            "tor_sources_attempted": len({a.provider for a in self.attempts if a.network == "tor"}),
            "tor_sources_successful": len(
                {a.provider for a in self.attempts if a.network == "tor" and a.status == "success"}
            ),
            "tor_network_requests": sum(
                a.network_requests for a in self.attempts if a.network == "tor"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return redact({**asdict(self), "coverage": self.coverage, "schema_version": 3})

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Investigation:
        data = dict(value)
        data.pop("coverage", None)
        data.pop("schema_version", None)
        data["pending_tasks"] = [RetrievalTask(**v) for v in data.get("pending_tasks", [])]
        plan = data.pop("plan")
        data["plan"] = QueryPlan(plan["seed"], [QueryVariant(**v) for v in plan["variants"]])
        for name, model in (
            ("results", SourceResult),
            ("entities", Entity),
            ("edges", Edge),
            ("attempts", Attempt),
        ):
            data[name] = [model(**v) for v in data[name]]
        return cls(**data)

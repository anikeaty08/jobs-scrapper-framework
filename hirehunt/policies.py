"""Configurable framework policies for filtering, ranking, deduplication, and HTTP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Protocol

from hirehunt.models import Job

if TYPE_CHECKING:
    from hirehunt.query import JobQuery


@dataclass
class FilterOutcome:
    jobs: list[Job]
    dropped_by_reason: dict[str, int] = field(default_factory=dict)
    dropped_by_source: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class DedupeOutcome:
    jobs: list[Job]
    duplicates: int = 0
    duplicates_by_source: dict[str, int] = field(default_factory=dict)


class FilterPolicy(Protocol):
    def apply(self, jobs: list[Job], query: "JobQuery") -> FilterOutcome: ...


class RankPolicy(Protocol):
    def rank(self, jobs: list[Job], query: "JobQuery") -> list[Job]: ...


class DedupePolicy(Protocol):
    def apply(self, jobs: list[Job], query: "JobQuery") -> DedupeOutcome: ...


class CacheBackend(Protocol):
    def get(self, source: str, key: str) -> str | None: ...

    def set(self, source: str, key: str, content: str, status_code: int = 200) -> None: ...


@dataclass(frozen=True)
class RequestPolicy:
    retries: int = 3
    timeout: float = 20.0
    backoff_base: float = 2.0
    min_delay: float = 0.0
    max_delay: float = 0.0
    retry_statuses: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})
    sleep: Callable[[float], None] | None = None


class DefaultFilterPolicy:
    def apply(self, jobs: list[Job], query: "JobQuery") -> FilterOutcome:
        from hirehunt.filtering import filter_jobs_with_diagnostics

        return filter_jobs_with_diagnostics(jobs, query)


class DefaultRankPolicy:
    def rank(self, jobs: list[Job], query: "JobQuery") -> list[Job]:
        from hirehunt.ranking import rank_jobs

        return rank_jobs(jobs, query)


class DefaultDedupePolicy:
    def apply(self, jobs: list[Job], query: "JobQuery") -> DedupeOutcome:
        from hirehunt.utils.dedupe import deduplicate_jobs_with_diagnostics

        return deduplicate_jobs_with_diagnostics(jobs, mode=query.dedupe_mode)


@dataclass
class SearchPolicies:
    filtering: FilterPolicy = field(default_factory=DefaultFilterPolicy)
    ranking: RankPolicy = field(default_factory=DefaultRankPolicy)
    deduplication: DedupePolicy = field(default_factory=DefaultDedupePolicy)

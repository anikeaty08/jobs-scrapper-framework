"""Live source validation and fixture capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import time

from hirehunt.models import CompletionStatus
from hirehunt.query import JobQuery
from hirehunt.registry import default_registry


@dataclass
class SourceValidation:
    source: str
    url: str = ""
    status_code: int = 0
    backend: str = ""
    fetched: bool = False
    from_cache: bool = False
    parsed_count: int = 0
    sample_titles: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.fetched and self.status_code == 200 and self.parsed_count > 0 and not self.error


@dataclass
class SourceBenchmark:
    source: str
    duration_seconds: float = 0.0
    requests: int = 0
    parsed_count: int = 0
    completion: str = CompletionStatus.UNKNOWN
    completion_reason: str = ""
    error: str = ""

    @property
    def jobs_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.parsed_count / self.duration_seconds


@dataclass(frozen=True)
class HealthThresholds:
    min_parsed: int = 1
    max_failures: int = 0
    allowed_completions: frozenset[str] = frozenset(
        {
            CompletionStatus.EXHAUSTED,
            CompletionStatus.CAPPED,
            CompletionStatus.PARTIAL,
        }
    )
    required_fields: tuple[str, ...] = ("title", "company", "job_url")
    min_jobs_per_second: float = 0.0
    max_requests: int = 0


@dataclass
class HealthIssue:
    source: str
    code: str
    message: str


def validate_sources(query: JobQuery, sources: list[str] | None = None) -> list[SourceValidation]:
    registry = default_registry()
    selected = (
        registry.expand_sources(sources)
        or registry.expand_sources(query.source_list)
        or (registry.family_sources(query.source_family) if query.source_family else [])
        or registry.auto_sources(
            query.country,
            query.include_regional,
            query.normalized_term,
            query.job_kind,
        )
    )
    results: list[SourceValidation] = []

    for source in selected:
        item = SourceValidation(source=source)
        try:
            scraper = registry.create(
                source,
                proxies=query.proxies,
                fetch_backend=query.fetch_backend,
                cache_enabled=query.cache_enabled,
                cache_dir=query.cache_dir,
            )
            if source in {"indeed", "linkedin", "naukri", "shine", "unstop"}:
                jobs = scraper.search(query)
                item.url = scraper.build_url(query) if hasattr(scraper, "build_url") else ""
                item.status_code = getattr(scraper, "last_status_code", 200 if jobs else 0) or (200 if jobs else 0)
                item.backend = getattr(scraper, "last_backend", "requests")
                item.fetched = bool(jobs) or item.status_code == 200
                item.parsed_count = len(jobs)
                item.sample_titles = [job.title for job in jobs[:5]]
                results.append(item)
                continue
            url = scraper.build_url(query) if hasattr(scraper, "build_url") else ""
            item.url = url
            response = scraper.fetch(url) if url else None
            if response is None:
                item.error = "no response"
                results.append(item)
                continue
            item.status_code = response.status_code
            item.backend = response.backend
            item.fetched = bool(response.text)
            item.from_cache = response.from_cache
            jobs = scraper.limit(_parse_with_source(scraper, response.text, query), query)
            item.parsed_count = len(jobs)
            item.sample_titles = [job.title for job in jobs[:5]]
        except Exception as exc:
            item.error = str(exc)
        results.append(item)
    return results


def benchmark_sources(query: JobQuery, sources: list[str] | None = None) -> list[SourceBenchmark]:
    registry = default_registry()
    selected = (
        registry.expand_sources(sources)
        or registry.expand_sources(query.source_list)
        or (registry.family_sources(query.source_family) if query.source_family else [])
        or registry.auto_sources(
            query.country,
            query.include_regional,
            query.normalized_term,
            query.job_kind,
        )
    )
    results: list[SourceBenchmark] = []
    for source in selected:
        item = SourceBenchmark(source=source)
        started = time.perf_counter()
        try:
            scraper = registry.create(
                source,
                proxies=query.proxies,
                fetch_backend=query.fetch_backend,
                cache_enabled=query.cache_enabled,
                cache_dir=query.cache_dir,
                request_policy=query.request_policy,
                cache_backend=query.cache_backend,
            )
            jobs = scraper.search(query)
            item.parsed_count = len(jobs)
            item.requests = getattr(scraper, "request_count", 0)
            if query.results_wanted is not None and query.results_wanted > 0 and len(jobs) >= query.results_wanted:
                item.completion = CompletionStatus.CAPPED
                item.completion_reason = f"results_wanted={query.results_wanted}"
            elif scraper.capabilities.exhaustive_search:
                item.completion = CompletionStatus.EXHAUSTED
                item.completion_reason = "source returned no further results"
            else:
                item.completion = CompletionStatus.PARTIAL
                item.completion_reason = "source does not guarantee exhaustive search"
        except Exception as exc:
            item.error = str(exc)
            item.completion = CompletionStatus.FAILED
            item.completion_reason = str(exc)
        finally:
            item.duration_seconds = time.perf_counter() - started
        results.append(item)
    return results


def evaluate_validation_health(
    results: list[SourceValidation],
    thresholds: HealthThresholds | None = None,
) -> list[HealthIssue]:
    thresholds = thresholds or HealthThresholds()
    issues: list[HealthIssue] = []
    if not results:
        return [HealthIssue(source="*", code="no_sources_selected", message="validation selected no sources")]
    failures = sum(1 for item in results if not item.ok)
    if failures > thresholds.max_failures:
        issues.append(
            HealthIssue(
                source="*",
                code="too_many_failures",
                message=f"{failures} sources failed validation; allowed={thresholds.max_failures}",
            )
        )
    for item in results:
        if item.error:
            issues.append(
                HealthIssue(item.source, "fetch_error", item.error)
            )
        if item.parsed_count < thresholds.min_parsed:
            issues.append(
                HealthIssue(
                    item.source,
                    "parsed_below_minimum",
                    f"parsed_count={item.parsed_count} < min_parsed={thresholds.min_parsed}",
                )
            )
        if item.ok and not item.sample_titles:
            issues.append(
                HealthIssue(item.source, "missing_samples", "validation returned no sample titles")
            )
    return issues


def evaluate_benchmark_health(
    results: list[SourceBenchmark],
    thresholds: HealthThresholds | None = None,
) -> list[HealthIssue]:
    thresholds = thresholds or HealthThresholds()
    issues: list[HealthIssue] = []
    if not results:
        return [HealthIssue(source="*", code="no_sources_selected", message="benchmark selected no sources")]
    for item in results:
        if item.error:
            issues.append(HealthIssue(item.source, "benchmark_error", item.error))
        if item.completion not in thresholds.allowed_completions:
            issues.append(
                HealthIssue(
                    item.source,
                    "unexpected_completion",
                    f"completion={item.completion} allowed={sorted(thresholds.allowed_completions)}",
                )
            )
        if item.parsed_count < thresholds.min_parsed:
            issues.append(
                HealthIssue(
                    item.source,
                    "parsed_below_minimum",
                    f"parsed_count={item.parsed_count} < min_parsed={thresholds.min_parsed}",
                )
            )
        if thresholds.min_jobs_per_second > 0 and item.jobs_per_second < thresholds.min_jobs_per_second:
            issues.append(
                HealthIssue(
                    item.source,
                    "throughput_below_minimum",
                    f"jobs_per_second={item.jobs_per_second:.2f} < min_jobs_per_second={thresholds.min_jobs_per_second:.2f}",
                )
            )
        if thresholds.max_requests > 0 and item.requests > thresholds.max_requests:
            issues.append(
                HealthIssue(
                    item.source,
                    "requests_above_maximum",
                    f"requests={item.requests} > max_requests={thresholds.max_requests}",
                )
            )
    return issues


def _parse_with_source(scraper, html: str, query: JobQuery):
    source = scraper.source
    if source == "internshala":
        from hirehunt.scrapers.internshala import parse_internshala_jobs

        return parse_internshala_jobs(html, query)
    if source == "linkedin":
        from hirehunt.scrapers.linkedin import parse_linkedin_jobs

        return parse_linkedin_jobs(html, query)
    return scraper.search(query)


def write_validation_report(results: list[SourceValidation], path: str | Path) -> None:
    report = {
        "created_at": time.time(),
        "sources": [
            {
                "source": item.source,
                "ok": item.ok,
                "url": item.url,
                "status_code": item.status_code,
                "backend": item.backend,
                "fetched": item.fetched,
                "from_cache": item.from_cache,
                "parsed_count": item.parsed_count,
                "sample_titles": item.sample_titles,
                "error": item.error,
            }
            for item in results
        ],
    }
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_benchmark_report(results: list[SourceBenchmark], path: str | Path) -> None:
    report = {
        "created_at": time.time(),
        "sources": [
            {
                "source": item.source,
                "duration_seconds": item.duration_seconds,
                "requests": item.requests,
                "parsed_count": item.parsed_count,
                "jobs_per_second": item.jobs_per_second,
                "completion": item.completion,
                "completion_reason": item.completion_reason,
                "error": item.error,
            }
            for item in results
        ],
    }
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")

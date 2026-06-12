"""Search engine orchestration with source warnings."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import logging

from hirehunt.models import CompletionStatus, ScrapeResult, SourceStats
from hirehunt.policies import SearchPolicies
from hirehunt.query import JobQuery
from hirehunt.registry import ScraperRegistry, default_registry
from hirehunt.utils.normalization import KNOWN_CITIES

logger = logging.getLogger(__name__)


def _city_warnings(query: JobQuery) -> list[str]:
    warnings: list[str] = []
    if query.city and query.city.lower() not in KNOWN_CITIES:
        warnings.append(
            f"'{query.city}' is not a recognised Indian city. "
            "Results may be empty or incorrect. "
            "Try full city names like 'Bengaluru', 'Mumbai', 'Hyderabad'."
        )
    return warnings


class SearchEngine:
    def __init__(
        self,
        registry: ScraperRegistry | None = None,
        max_workers: int = 4,
        policies: SearchPolicies | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.max_workers = max_workers
        self.policies = policies or SearchPolicies()

    def search(self, query: JobQuery) -> ScrapeResult:
        sources = self._select_sources(query)
        result = ScrapeResult(
            stats={source: SourceStats() for source in sources},
            warnings=_city_warnings(query),
            selected_sources=list(sources),
        )
        all_jobs = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(sources)))) as executor:
            futures = {}
            for source in sources:
                scraper = self._create_scraper(source, query)
                futures[executor.submit(scraper.search, query)] = (source, scraper)

            for future in as_completed(futures):
                source, scraper = futures[future]
                try:
                    jobs = future.result()
                except Exception as exc:
                    logger.exception("source failed: %s", source)
                    result.errors[source] = str(exc)
                    result.stats[source].errors += 1
                    result.stats[source].completion = CompletionStatus.FAILED
                    result.stats[source].completion_reason = str(exc)
                    result.partial = True
                    result.warnings.append(f"{source}: failed to fetch ({exc.__class__.__name__})")
                    continue
                self._record_source_success(result.stats[source], jobs, query, scraper)
                if result.stats[source].completion == CompletionStatus.PARTIAL:
                    result.partial = True
                if len(jobs) == 0:
                    result.warnings.append(f"{source}: returned 0 results for '{query.normalized_term}'")
                all_jobs.extend(jobs)

        return self._finalize(result, all_jobs, sources, query)

    async def search_async(self, query: JobQuery) -> ScrapeResult:
        sources = self._select_sources(query)
        result = ScrapeResult(
            stats={source: SourceStats() for source in sources},
            warnings=_city_warnings(query),
            selected_sources=list(sources),
        )

        async def run_source(source: str):
            scraper = self._create_scraper(source, query)
            try:
                jobs = await asyncio.to_thread(scraper.search, query)
                return source, scraper, jobs, None
            except Exception as exc:
                return source, scraper, [], exc

        all_jobs = []
        for completed in asyncio.as_completed([run_source(source) for source in sources]):
            source, scraper, jobs, exc = await completed
            if exc is not None:
                logger.error("async source failed: %s error=%s", source, exc)
                result.errors[source] = str(exc)
                result.stats[source].errors += 1
                result.stats[source].completion = CompletionStatus.FAILED
                result.stats[source].completion_reason = str(exc)
                result.partial = True
                result.warnings.append(f"{source}: failed to fetch ({exc.__class__.__name__})")
                continue
            self._record_source_success(result.stats[source], jobs, query, scraper)
            if result.stats[source].completion == CompletionStatus.PARTIAL:
                result.partial = True
            if len(jobs) == 0:
                result.warnings.append(f"{source}: returned 0 results for '{query.normalized_term}'")
            all_jobs.extend(jobs)

        return self._finalize(result, all_jobs, sources, query)

    def _finalize(self, result: ScrapeResult, all_jobs: list, sources: list[str], query: JobQuery) -> ScrapeResult:
        filtered = self.policies.filtering.apply(all_jobs, query)
        for source, reasons in filtered.dropped_by_source.items():
            stats = result.stats.setdefault(source, SourceStats())
            stats.filter_reasons = dict(reasons)
            stats.filtered_out = sum(reasons.values())

        deduped = self.policies.deduplication.apply(filtered.jobs, query)
        for source, count in deduped.duplicates_by_source.items():
            result.stats.setdefault(source, SourceStats()).duplicates += count
        result.jobs = self.policies.ranking.rank(deduped.jobs, query)

        for job in deduped.jobs:
            result.stats.setdefault(job.source, SourceStats()).kept += 1
        if not result.jobs:
            result.warnings.append("No jobs found. Try: broader search term, different city, or more sources.")
        return result

    @staticmethod
    def _record_source_success(stats: SourceStats, jobs: list, query: JobQuery, scraper) -> None:
        count = len(jobs)
        stats.fetched = count
        stats.parsed = count
        stats.found = count
        stats.requests = getattr(scraper, "request_count", 0)
        limit = query.results_wanted
        if limit is not None and limit > 0 and count >= limit:
            stats.completion = CompletionStatus.CAPPED
            stats.completion_reason = f"results_wanted={limit}"
        elif not scraper.capabilities.exhaustive_search:
            stats.completion = CompletionStatus.PARTIAL
            stats.completion_reason = "source does not guarantee exhaustive search"
        else:
            stats.completion = CompletionStatus.EXHAUSTED
            stats.completion_reason = "source returned no further results"

    def _create_scraper(self, source: str, query: JobQuery):
        return self.registry.create(
            source,
            proxies=query.proxies,
            fetch_backend=query.fetch_backend,
            cache_enabled=query.cache_enabled,
            cache_dir=query.cache_dir,
            request_policy=query.request_policy,
            cache_backend=query.cache_backend,
        )

    def _select_sources(self, query: JobQuery) -> list[str]:
        if query.source_list:
            return self.registry.expand_sources(query.source_list)
        if query.source_family:
            return self.registry.family_sources(query.source_family)
        return self.registry.auto_sources(
            query.country,
            query.include_regional,
            query.normalized_term,
            query.job_kind,
        )


def search_jobs(**kwargs) -> ScrapeResult:
    query = JobQuery.from_kwargs(**kwargs)
    return SearchEngine().search(query)


def scrape_jobs(**kwargs) -> ScrapeResult:
    return search_jobs(**kwargs)


async def search_jobs_async(**kwargs) -> ScrapeResult:
    query = JobQuery.from_kwargs(**kwargs)
    return await SearchEngine().search_async(query)

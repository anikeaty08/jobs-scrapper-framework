"""Search engine orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import logging

from jobhunter.filtering import filter_jobs
from jobhunter.models import ScrapeResult, SourceStats
from jobhunter.query import JobQuery
from jobhunter.ranking import rank_jobs
from jobhunter.registry import ScraperRegistry, default_registry
from jobhunter.utils.dedupe import deduplicate_jobs

logger = logging.getLogger(__name__)


class SearchEngine:
    def __init__(self, registry: ScraperRegistry | None = None, max_workers: int = 4) -> None:
        self.registry = registry or default_registry()
        self.max_workers = max_workers

    def search(self, query: JobQuery) -> ScrapeResult:
        sources = query.source_list or self.registry.auto_sources(query.country, query.include_regional)
        result = ScrapeResult(stats={source: SourceStats() for source in sources})
        all_jobs = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(sources)))) as executor:
            futures = {}
            for source in sources:
                scraper = self._create_scraper(source, query)
                futures[executor.submit(scraper.search, query)] = source

            for future in as_completed(futures):
                source = futures[future]
                try:
                    jobs = future.result()
                except Exception as exc:  # scrapers should not crash the whole search
                    logger.exception("source failed: %s", source)
                    result.errors[source] = str(exc)
                    result.stats[source].errors += 1
                    continue
                result.stats[source].found = len(jobs)
                all_jobs.extend(jobs)

        filtered = filter_jobs(all_jobs, query)
        unique, duplicate_count = deduplicate_jobs(filtered)
        ranked = rank_jobs(unique, query)
        result.jobs = ranked

        total_found_by_source: dict[str, int] = {}
        for job in unique:
            total_found_by_source[job.source] = total_found_by_source.get(job.source, 0) + 1
        for source, kept in total_found_by_source.items():
            result.stats.setdefault(source, SourceStats()).kept = kept
        if sources:
            result.stats[sources[0]].duplicates = duplicate_count
        return result

    async def search_async(self, query: JobQuery) -> ScrapeResult:
        sources = query.source_list or self.registry.auto_sources(query.country, query.include_regional)
        result = ScrapeResult(stats={source: SourceStats() for source in sources})

        async def run_source(source: str):
            scraper = self._create_scraper(source, query)
            return source, await asyncio.to_thread(scraper.search, query)

        tasks = [run_source(source) for source in sources]
        all_jobs = []
        for completed in asyncio.as_completed(tasks):
            try:
                source, jobs = await completed
            except Exception as exc:
                source = "unknown"
                logger.exception("async source failed")
                result.errors[source] = str(exc)
                continue
            result.stats[source].found = len(jobs)
            all_jobs.extend(jobs)

        filtered = filter_jobs(all_jobs, query)
        unique, duplicate_count = deduplicate_jobs(filtered)
        result.jobs = rank_jobs(unique, query)
        for job in unique:
            result.stats.setdefault(job.source, SourceStats()).kept += 1
        if sources:
            result.stats[sources[0]].duplicates = duplicate_count
        return result

    def _create_scraper(self, source: str, query: JobQuery):
        return self.registry.create(
            source,
            proxies=query.proxies,
            fetch_backend=query.fetch_backend,
            cache_enabled=query.cache_enabled,
            cache_dir=query.cache_dir,
        )


def search_jobs(**kwargs) -> ScrapeResult:
    query = JobQuery.from_kwargs(**kwargs)
    return SearchEngine().search(query)


def scrape_jobs(**kwargs) -> ScrapeResult:
    return search_jobs(**kwargs)


async def search_jobs_async(**kwargs) -> ScrapeResult:
    query = JobQuery.from_kwargs(**kwargs)
    return await SearchEngine().search_async(query)

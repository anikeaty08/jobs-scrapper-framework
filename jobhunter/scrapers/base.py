"""Scraper base contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jobhunter.models import Job
from jobhunter.query import JobQuery
from jobhunter.utils.fetchers import CachedFetcher, FetchResponse


class BaseScraper(ABC):
    source: str = ""
    default_country: str = ""

    def __init__(
        self,
        proxies: list[str] | None = None,
        fetch_backend: str = "requests",
        cache_enabled: bool = False,
        cache_dir: str = ".jobhunter_cache",
    ):
        self.fetcher = CachedFetcher(
            self.source,
            backend=fetch_backend,
            proxies=proxies,
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
        )

    def fetch(self, url: str) -> FetchResponse | None:
        return self.fetcher.fetch(url)

    @abstractmethod
    def search(self, query: JobQuery) -> list[Job]:
        """Return normalized jobs for a query."""

    def limit(self, jobs: list[Job], query: JobQuery) -> list[Job]:
        return jobs[: max(0, query.results_wanted)]

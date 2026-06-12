"""Scraper base contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hirehunt.models import Job
from hirehunt.models import SourceCapabilities
from hirehunt.policies import CacheBackend, RequestPolicy
from hirehunt.query import JobQuery
from hirehunt.utils.fetchers import CachedFetcher, FetchResponse


class BaseScraper(ABC):
    source: str = ""
    default_country: str = ""
    capabilities = SourceCapabilities()

    def __init__(
        self,
        proxies: list[str] | None = None,
        fetch_backend: str = "requests",
        cache_enabled: bool = False,
        cache_dir: str = ".jobhunter_cache",
        request_policy: RequestPolicy | None = None,
        cache_backend: CacheBackend | None = None,
    ):
        self.request_count = 0
        self.request_policy = request_policy
        self.fetcher = CachedFetcher(
            self.source,
            backend=fetch_backend,
            proxies=proxies,
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
            request_policy=request_policy,
            cache_backend=cache_backend,
        )

    def fetch(self, url: str) -> FetchResponse | None:
        self.request_count += 1
        return self.fetcher.fetch(url)

    def get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> FetchResponse | None:
        self.request_count += 1
        return self.fetcher.get_json(url, params=params, headers=headers)

    def post_json(self, url: str, *, headers: dict[str, str] | None = None, payload: dict | None = None) -> FetchResponse | None:
        self.request_count += 1
        return self.fetcher.post_json(url, headers=headers, payload=payload)

    @abstractmethod
    def search(self, query: JobQuery) -> list[Job]:
        """Return normalized jobs for a query."""

    def wants_more(self, jobs: list[Job], query: JobQuery) -> bool:
        return query.results_wanted is None or query.results_wanted <= 0 or len(jobs) < query.results_wanted

    def limit(self, jobs: list[Job], query: JobQuery) -> list[Job]:
        if query.results_wanted is None or query.results_wanted <= 0:
            return jobs
        return jobs[:query.results_wanted]

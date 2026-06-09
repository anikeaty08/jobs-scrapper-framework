"""Fetch backends for source scrapers."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from jobhunter.utils.cache import PageCache
from jobhunter.utils.http import build_session, safe_get

logger = logging.getLogger(__name__)


@dataclass
class FetchResponse:
    url: str
    text: str
    status_code: int
    backend: str
    from_cache: bool = False


class RequestsFetcher:
    backend = "requests"

    def __init__(self, proxies: list[str] | None = None) -> None:
        self.session = build_session(proxies=proxies)

    def fetch(self, url: str) -> FetchResponse | None:
        response = safe_get(self.session, url)
        if response is None:
            return None
        return FetchResponse(url=response.url, text=response.text, status_code=response.status_code, backend=self.backend)


class CachedFetcher:
    def __init__(
        self,
        source: str,
        backend: str = "requests",
        proxies: list[str] | None = None,
        cache_enabled: bool = False,
        cache_dir: str = ".jobhunter_cache",
    ) -> None:
        self.source = source
        self.cache_enabled = cache_enabled
        self.cache = PageCache(cache_dir)
        if backend != "requests":
            raise ValueError("only the requests fetch backend is enabled in this build")
        self.primary = RequestsFetcher(proxies=proxies)

    def fetch(self, url: str) -> FetchResponse | None:
        if self.cache_enabled:
            cached = self.cache.get(self.source, url)
            if cached is not None:
                return FetchResponse(url=url, text=cached, status_code=200, backend="cache", from_cache=True)

        response = self.primary.fetch(url)
        if response and response.status_code == 200 and response.text.strip():
            if self.cache_enabled:
                self.cache.set(self.source, response.url or url, response.text, response.status_code)
            return response

        return response

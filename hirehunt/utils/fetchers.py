"""Fetch backends for source scrapers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import random
import time

from hirehunt.policies import CacheBackend, RequestPolicy
from hirehunt.utils.cache import PageCache
from hirehunt.utils.http import build_session, safe_get

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

    def __init__(self, proxies: list[str] | None = None, request_policy: RequestPolicy | None = None) -> None:
        self.session = build_session(proxies=proxies)
        self.request_policy = request_policy or RequestPolicy()

    def fetch(self, url: str) -> FetchResponse | None:
        response = safe_get(self.session, url, policy=self.request_policy)
        if response is None:
            return None
        return FetchResponse(url=response.url, text=response.text, status_code=response.status_code, backend=self.backend)

    def post_json(self, url: str, *, headers: dict[str, str] | None = None, payload: dict | None = None) -> FetchResponse | None:
        response = self._request("post", url, headers=headers, json=payload or {})
        if response is None:
            return None
        return FetchResponse(url=response.url, text=response.text, status_code=response.status_code, backend=self.backend)

    def get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> FetchResponse | None:
        """GET request with optional query params and custom headers (e.g. XHR endpoints)."""
        merged = dict(self.session.headers)
        if headers:
            merged.update(headers)
        response = self._request("get", url, params=params, headers=merged)
        if response is None:
            return None
        return FetchResponse(url=str(response.url), text=response.text, status_code=response.status_code, backend=self.backend)

    def _request(self, method: str, url: str, **kwargs):
        policy = self.request_policy
        sleep = policy.sleep or time.sleep
        for attempt in range(max(1, policy.retries)):
            if policy.max_delay > 0:
                sleep(random.uniform(policy.min_delay, policy.max_delay))
            try:
                response = self.session.request(method, url, timeout=policy.timeout, **kwargs)
            except Exception:
                logger.exception("%s failed: %s", method.upper(), url)
                if attempt + 1 >= policy.retries:
                    return None
                sleep(policy.backoff_base**attempt)
                continue
            if response.status_code in policy.retry_statuses and attempt + 1 < policy.retries:
                sleep(policy.backoff_base**attempt)
                continue
            return response
        return None


class CachedFetcher:
    def __init__(
        self,
        source: str,
        backend: str = "requests",
        proxies: list[str] | None = None,
        cache_enabled: bool = False,
        cache_dir: str = ".jobhunter_cache",
        request_policy: RequestPolicy | None = None,
        cache_backend: CacheBackend | None = None,
    ) -> None:
        self.source = source
        self.cache_enabled = cache_enabled
        self.cache = cache_backend or PageCache(cache_dir)
        if backend != "requests":
            raise ValueError("only the requests fetch backend is enabled in this build")
        self.primary = RequestsFetcher(proxies=proxies, request_policy=request_policy)

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

    def post_json(self, url: str, *, headers: dict[str, str] | None = None, payload: dict | None = None) -> FetchResponse | None:
        cache_key = url + "::" + json.dumps(payload or {}, sort_keys=True)
        if self.cache_enabled:
            cached = self.cache.get(self.source, cache_key)
            if cached is not None:
                return FetchResponse(url=url, text=cached, status_code=200, backend="cache", from_cache=True)

        response = self.primary.post_json(url, headers=headers, payload=payload)
        if response and response.status_code == 200 and response.text.strip() and self.cache_enabled:
            self.cache.set(self.source, cache_key, response.text, response.status_code)
        return response

    def get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> FetchResponse | None:
        """GET with params + optional headers; caches on 200."""
        cache_key = url + "::" + json.dumps(params or {}, sort_keys=True)
        if self.cache_enabled:
            cached = self.cache.get(self.source, cache_key)
            if cached is not None:
                return FetchResponse(url=url, text=cached, status_code=200, backend="cache", from_cache=True)

        response = self.primary.get_json(url, params=params, headers=headers)
        if response and response.status_code == 200 and response.text.strip() and self.cache_enabled:
            self.cache.set(self.source, cache_key, response.text, response.status_code)
        return response

"""HTTP utilities shared by scrapers."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import requests

from hirehunt.policies import RequestPolicy

logger = logging.getLogger(__name__)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
]


@dataclass(frozen=True)
class HttpConfig:
    retries: int = 3
    timeout: int = 20
    min_delay: float = 0.5
    max_delay: float = 1.5


def build_session(proxies: list[str] | None = None, user_agent: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
    )
    if proxies:
        proxy = random.choice(proxies)
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def safe_get(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    config: HttpConfig | None = None,
    policy: RequestPolicy | None = None,
):
    cfg = config or HttpConfig()
    retries = policy.retries if policy else cfg.retries
    timeout = policy.timeout if policy else cfg.timeout
    retry_statuses = policy.retry_statuses if policy else frozenset({408, 429, 500, 502, 503, 504})
    sleep = (policy.sleep or time.sleep) if policy else time.sleep
    for attempt in range(max(1, retries)):
        if policy and policy.max_delay > 0:
            sleep(random.uniform(policy.min_delay, policy.max_delay))
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            if response.status_code in {403, 406}:
                logger.warning("source blocked request: %s status=%s", url, response.status_code)
                return response
            if response.status_code in retry_statuses and attempt + 1 < retries:
                delay = (policy.backoff_base**attempt) if policy else (2**attempt)
                sleep(delay)
                continue
            logger.warning("request failed: %s status=%s", url, response.status_code)
            return response
        except requests.RequestException as exc:
            logger.warning("request error: %s attempt=%s error=%s", url, attempt + 1, exc)
            delay = (policy.backoff_base**attempt) if policy else (2**attempt) + random.uniform(cfg.min_delay, cfg.max_delay)
            sleep(delay)
    return None


def polite_delay(min_seconds: float = 0.5, max_seconds: float = 1.5) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))

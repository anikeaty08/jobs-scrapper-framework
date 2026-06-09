"""Scraper base contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jobhunter.models import Job
from jobhunter.query import JobQuery
from jobhunter.utils.http import build_session


class BaseScraper(ABC):
    source: str = ""
    default_country: str = ""

    def __init__(self, proxies: list[str] | None = None):
        self.session = build_session(proxies=proxies)

    @abstractmethod
    def search(self, query: JobQuery) -> list[Job]:
        """Return normalized jobs for a query."""

    def limit(self, jobs: list[Job], query: JobQuery) -> list[Job]:
        return jobs[: max(0, query.results_wanted)]

"""Scraper registry."""

from __future__ import annotations

import re

from hirehunt.exceptions import UnknownSourceError
from hirehunt.models import SourceCapabilities
from hirehunt.scrapers.base import BaseScraper


class ScraperRegistry:
    def __init__(self) -> None:
        self._scrapers: dict[str, type[BaseScraper]] = {}

    def register(self, scraper_cls: type[BaseScraper]) -> None:
        if not scraper_cls.source:
            raise ValueError("scraper source cannot be empty")
        self._scrapers[scraper_cls.source] = scraper_cls

    def create(self, source: str, **kwargs) -> BaseScraper:
        try:
            scraper_cls = self._scrapers[source]
        except KeyError as exc:
            raise UnknownSourceError(f"unknown source: {source}") from exc
        return scraper_cls(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._scrapers)

    def capabilities(self, source: str | None = None) -> SourceCapabilities | dict[str, SourceCapabilities]:
        if source is not None:
            try:
                return self._scrapers[source].capabilities
            except KeyError as exc:
                raise UnknownSourceError(f"unknown source: {source}") from exc
        return {name: scraper.capabilities for name, scraper in sorted(self._scrapers.items())}

    def auto_sources(
        self,
        query_country: str = "",
        include_regional: bool = True,
        search_term: str = "",
        job_kind: list[str] | str | None = None,
    ) -> list[str]:
        names = ["indeed", "linkedin"]
        if include_regional and query_country.lower() in {"", "india", "in"}:
            names.extend(["internshala", "naukri", "shine"])
            kind_text = " ".join(job_kind) if isinstance(job_kind, list) else str(job_kind or "")
            opportunity_text = f"{search_term} {kind_text}".lower()
            if re.search(r"\b(hackathon|competition|challenge|contest|fellowship)s?\b", opportunity_text):
                names.append("unstop")
        return [name for name in names if name in self._scrapers]

    def faang_sources(self) -> list[str]:
        """Return all FAANG/Big-Tech source names."""
        candidates = ["google_careers", "amazon", "meta", "apple", "netflix", "microsoft"]
        return [name for name in candidates if name in self._scrapers]


def default_registry() -> ScraperRegistry:
    from hirehunt.scrapers import BUILTIN_SCRAPERS

    registry = ScraperRegistry()
    for scraper_cls in BUILTIN_SCRAPERS:
        registry.register(scraper_cls)
    return registry

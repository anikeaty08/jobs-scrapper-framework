"""Scraper registry."""

from __future__ import annotations

from jobhunter.exceptions import UnknownSourceError
from jobhunter.scrapers.base import BaseScraper


class ScraperRegistry:
    def __init__(self) -> None:
        self._scrapers: dict[str, type[BaseScraper]] = {}

    def register(self, scraper_cls: type[BaseScraper]) -> None:
        if not scraper_cls.source:
            raise ValueError("scraper source cannot be empty")
        self._scrapers[scraper_cls.source] = scraper_cls

    def create(self, source: str, *, proxies: list[str] | None = None) -> BaseScraper:
        try:
            scraper_cls = self._scrapers[source]
        except KeyError as exc:
            raise UnknownSourceError(f"unknown source: {source}") from exc
        return scraper_cls(proxies=proxies)

    def names(self) -> list[str]:
        return sorted(self._scrapers)

    def auto_sources(self, query_country: str = "", include_regional: bool = True) -> list[str]:
        names = ["indeed", "linkedin"]
        if include_regional and query_country.lower() in {"", "india", "in"}:
            names.extend(["internshala", "unstop"])
        return [name for name in names if name in self._scrapers]


def default_registry() -> ScraperRegistry:
    from jobhunter.scrapers import BUILTIN_SCRAPERS

    registry = ScraperRegistry()
    for scraper_cls in BUILTIN_SCRAPERS:
        registry.register(scraper_cls)
    return registry

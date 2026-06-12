"""Scraper registry."""

from __future__ import annotations

import re

from hirehunt.exceptions import UnknownSourceError
from hirehunt.models import SourceCapabilities, SourceDefinition
from hirehunt.scrapers.base import BaseScraper


class ScraperRegistry:
    def __init__(self) -> None:
        self._scrapers: dict[str, type[BaseScraper]] = {}
        self._definitions: dict[str, SourceDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, scraper_cls: type[BaseScraper]) -> None:
        if not scraper_cls.source:
            raise ValueError("scraper source cannot be empty")
        self._scrapers[scraper_cls.source] = scraper_cls
        definition = SourceDefinition(
            name=scraper_cls.source,
            family=getattr(scraper_cls, "source_family", "custom") or "custom",
            adapter=getattr(scraper_cls, "source_adapter", "") or scraper_cls.__name__,
            aliases=tuple(dict.fromkeys(getattr(scraper_cls, "source_aliases", ()) or ())),
            tags=tuple(dict.fromkeys(getattr(scraper_cls, "source_tags", ()) or ())),
            config=dict(getattr(scraper_cls, "source_config", {}) or {}),
            capabilities=scraper_cls.capabilities,
        )
        self._definitions[scraper_cls.source] = definition
        self._aliases[scraper_cls.source.lower()] = scraper_cls.source
        self._aliases[definition.family.lower()] = definition.family.lower()
        for alias in definition.aliases:
            self._aliases[alias.lower()] = scraper_cls.source

    def register_configured_source(
        self,
        scraper_cls: type[BaseScraper],
        *,
        source: str,
        family: str,
        aliases: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        config: dict[str, object] | None = None,
    ) -> None:
        configured_cls = type(
            f"{scraper_cls.__name__}_{source}",
            (scraper_cls,),
            {
                "source": source,
                "source_family": family,
                "source_aliases": aliases,
                "source_tags": tags,
                "source_config": dict(config or {}),
            },
        )
        self.register(configured_cls)

    def create(self, source: str, **kwargs) -> BaseScraper:
        source = self.resolve(source)
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
                return self._scrapers[self.resolve(source)].capabilities
            except KeyError as exc:
                raise UnknownSourceError(f"unknown source: {source}") from exc
        return {name: scraper.capabilities for name, scraper in sorted(self._scrapers.items())}

    def definition(self, source: str) -> SourceDefinition:
        resolved = self.resolve(source)
        if resolved in self._definitions:
            return self._definitions[resolved]
        raise UnknownSourceError(f"unknown source: {source}")

    def definitions(self, family: str | None = None) -> dict[str, SourceDefinition]:
        if family is None:
            return dict(sorted(self._definitions.items()))
        selected = {
            name: definition
            for name, definition in sorted(self._definitions.items())
            if definition.family.lower() == family.lower()
        }
        if not selected:
            raise UnknownSourceError(f"unknown source family: {family}")
        return selected

    def families(self) -> list[str]:
        return sorted({definition.family for definition in self._definitions.values()})

    def family_sources(self, family: str) -> list[str]:
        return list(self.definitions(family).keys())

    def resolve(self, source: str) -> str:
        key = (source or "").strip().lower()
        resolved = self._aliases.get(key, source)
        if resolved in self._scrapers:
            return resolved
        raise UnknownSourceError(f"unknown source: {source}")

    def expand_sources(self, sources: list[str] | str | None) -> list[str]:
        if not sources or sources == "auto":
            return []
        items = [sources] if isinstance(sources, str) else list(sources)
        expanded: list[str] = []
        for item in items:
            key = (item or "").strip()
            if not key:
                continue
            lowered = key.lower()
            if lowered in {family.lower() for family in self.families()}:
                expanded.extend(self.family_sources(key))
                continue
            expanded.append(self.resolve(key))
        return list(dict.fromkeys(expanded))

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

"""Live source validation and fixture capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import time

from hirehunt.query import JobQuery
from hirehunt.registry import default_registry


@dataclass
class SourceValidation:
    source: str
    url: str = ""
    status_code: int = 0
    backend: str = ""
    fetched: bool = False
    from_cache: bool = False
    parsed_count: int = 0
    sample_titles: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.fetched and self.status_code == 200 and self.parsed_count > 0 and not self.error


def validate_sources(query: JobQuery, sources: list[str] | None = None) -> list[SourceValidation]:
    registry = default_registry()
    selected = sources or query.source_list or registry.auto_sources(
        query.country,
        query.include_regional,
        query.normalized_term,
        query.job_kind,
    )
    results: list[SourceValidation] = []

    for source in selected:
        item = SourceValidation(source=source)
        try:
            scraper = registry.create(
                source,
                proxies=query.proxies,
                fetch_backend=query.fetch_backend,
                cache_enabled=query.cache_enabled,
                cache_dir=query.cache_dir,
            )
            if source in {"indeed", "linkedin", "naukri", "shine", "unstop"}:
                jobs = scraper.search(query)
                item.url = scraper.build_url(query) if hasattr(scraper, "build_url") else ""
                item.status_code = getattr(scraper, "last_status_code", 200 if jobs else 0) or (200 if jobs else 0)
                item.backend = getattr(scraper, "last_backend", "requests")
                item.fetched = bool(jobs) or item.status_code == 200
                item.parsed_count = len(jobs)
                item.sample_titles = [job.title for job in jobs[:5]]
                results.append(item)
                continue
            url = scraper.build_url(query) if hasattr(scraper, "build_url") else ""
            item.url = url
            response = scraper.fetch(url) if url else None
            if response is None:
                item.error = "no response"
                results.append(item)
                continue
            item.status_code = response.status_code
            item.backend = response.backend
            item.fetched = bool(response.text)
            item.from_cache = response.from_cache
            jobs = scraper.limit(_parse_with_source(scraper, response.text, query), query)
            item.parsed_count = len(jobs)
            item.sample_titles = [job.title for job in jobs[:5]]
        except Exception as exc:
            item.error = str(exc)
        results.append(item)
    return results


def _parse_with_source(scraper, html: str, query: JobQuery):
    source = scraper.source
    if source == "internshala":
        from hirehunt.scrapers.internshala import parse_internshala_jobs

        return parse_internshala_jobs(html, query)
    if source == "linkedin":
        from hirehunt.scrapers.linkedin import parse_linkedin_jobs

        return parse_linkedin_jobs(html, query)
    return scraper.search(query)


def write_validation_report(results: list[SourceValidation], path: str | Path) -> None:
    report = {
        "created_at": time.time(),
        "sources": [
            {
                "source": item.source,
                "ok": item.ok,
                "url": item.url,
                "status_code": item.status_code,
                "backend": item.backend,
                "fetched": item.fetched,
                "from_cache": item.from_cache,
                "parsed_count": item.parsed_count,
                "sample_titles": item.sample_titles,
                "error": item.error,
            }
            for item in results
        ],
    }
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")

"""Duplicate detection for cross-source job results."""

from __future__ import annotations

from hashlib import sha256
import re

from hirehunt.models import Job
from hirehunt.policies import DedupeOutcome
from hirehunt.utils.normalization import normalize_url


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def job_identity(job: Job, mode: str = "strict") -> str:
    url = normalize_url(job.job_url or job.apply_url)
    if mode == "strict" and url:
        return f"url:{url}"
    if job.source_job_id:
        if mode == "strict":
            return f"id:{job.source}:{job.source_job_id}"
    parts = [_slug(job.title), _slug(job.company), _slug(job.city or job.location), _slug(job.country)]
    raw = "|".join(parts)
    return "hash:" + sha256(raw.encode("utf-8")).hexdigest()


def deduplicate_jobs_with_diagnostics(jobs: list[Job], mode: str = "strict") -> DedupeOutcome:
    if mode not in {"strict", "heuristic", "none"}:
        raise ValueError("dedupe mode must be 'strict', 'heuristic', or 'none'")
    if mode == "none":
        return DedupeOutcome(list(jobs))

    seen: set[str] = set()
    unique: list[Job] = []
    duplicates = 0
    duplicates_by_source: dict[str, int] = {}
    for job in jobs:
        identity = job_identity(job, mode=mode)
        if identity in seen:
            duplicates += 1
            duplicates_by_source[job.source] = duplicates_by_source.get(job.source, 0) + 1
            continue
        seen.add(identity)
        unique.append(job)
    return DedupeOutcome(unique, duplicates, duplicates_by_source)


def deduplicate_jobs(jobs: list[Job], mode: str = "strict") -> tuple[list[Job], int]:
    outcome = deduplicate_jobs_with_diagnostics(jobs, mode=mode)
    return outcome.jobs, outcome.duplicates

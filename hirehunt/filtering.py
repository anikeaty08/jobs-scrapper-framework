"""Post-scrape filtering."""

from __future__ import annotations

from datetime import date, timedelta
import re

from hirehunt.models import Job, JobKind, WorkMode
from hirehunt.policies import FilterOutcome
from hirehunt.query import JobQuery
from hirehunt.utils.normalization import CITY_ALIASES, normalize_city, normalize_country


def _contains_any(value: str, needles: list[str]) -> bool:
    lowered = value.lower()
    return any(needle.lower() in lowered for needle in needles if needle)


def _company_matches(job: Job, companies: list[str]) -> bool:
    if not companies:
        return True
    company = job.company.lower()
    return any(term.lower() in company for term in companies if term)


def _matches_city(job: Job, city: str) -> bool:
    wanted = normalize_city(city).lower()
    primary = normalize_city(job.city).lower()
    if primary and (wanted in primary or primary in wanted):
        return True

    location = " ".join([job.city, job.location]).lower()
    aliases = {
        alias
        for alias, canonical in CITY_ALIASES.items()
        if canonical.lower() == wanted
    }
    aliases.update({wanted, city.lower()})
    return any(
        re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", location)
        for alias in aliases
        if alias
    )


def _filter_reason(job: Job, query: JobQuery, today: date) -> str | None:
    excludes = [item.lower() for item in query.exclude]
    searchable = " ".join([job.title, job.company, job.description, " ".join(job.skills)]).lower()

    if excludes and any(excluded in searchable for excluded in excludes):
        return "excluded_term"

    if query.company_terms and job.company and not _company_matches(job, query.company_terms):
        return "company_mismatch"

    if query.city and (job.city or job.location) and not _matches_city(job, query.city):
        return "city_mismatch"

    if query.cities and (job.city or job.location):
        if not any(_matches_city(job, city) for city in query.cities):
            return "city_mismatch"

    if (
        query.country
        and job.country
        and normalize_country(query.country) != normalize_country(job.country)
    ):
        return "country_mismatch"

    if query.remote is True and job.work_mode != WorkMode.REMOTE:
        return "work_mode_mismatch"
    if query.remote is False and job.work_mode == WorkMode.REMOTE:
        return "work_mode_mismatch"
    if query.work_mode and str(job.work_mode) != str(query.work_mode).lower():
        return "work_mode_mismatch"

    if query.fresher is True and job.experience_min and job.experience_min > 1:
        return "experience_mismatch"
    if query.experience_max is not None and job.experience_min and job.experience_min > query.experience_max:
        return "experience_mismatch"

    if query.skills:
        skill_terms = [skill.lower() for skill in query.skills]
        structured_skills = set(job.skills)
        skill_in_text = any(skill in searchable for skill in skill_terms)
        if structured_skills and not structured_skills.intersection(skill_terms) and not skill_in_text:
            return "skills_mismatch"

    if query.salary_min is not None:
        amount = job.salary.max_amount or job.salary.min_amount
        if amount is not None and amount < query.salary_min:
            return "salary_below_minimum"

    if query.stipend_min is not None:
        amount = job.stipend.max_amount or job.stipend.min_amount
        if amount is not None and amount < query.stipend_min:
            return "stipend_below_minimum"

    if query.posted_within_days is not None:
        if not job.date_posted:
            return "posting_date_missing"
        try:
            posted = date.fromisoformat(job.date_posted)
        except ValueError:
            return "posting_date_invalid"
        if posted < today - timedelta(days=query.posted_within_days):
            return "posting_too_old"

    if query.job_kind:
        wanted = {query.job_kind} if isinstance(query.job_kind, str) else set(query.job_kind)
        if str(job.job_kind) not in wanted and job.job_kind not in wanted:
            return "job_kind_mismatch"

    if query.normalized_term and not _contains_any(searchable, [query.normalized_term]):
        terms = [part for part in query.normalized_term.split() if len(part) > 2]
        if terms and not _contains_any(searchable, terms):
            return "keyword_mismatch"

    return None


def filter_jobs_with_diagnostics(jobs: list[Job], query: JobQuery) -> FilterOutcome:
    filtered: list[Job] = []
    dropped: dict[str, int] = {}
    dropped_by_source: dict[str, dict[str, int]] = {}
    today = date.today()

    for job in jobs:
        reason = _filter_reason(job, query, today)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            source_reasons = dropped_by_source.setdefault(job.source, {})
            source_reasons[reason] = source_reasons.get(reason, 0) + 1
            continue
        if job.job_kind == JobKind.UNKNOWN and "intern" in query.normalized_term.lower():
            job.job_kind = JobKind.INTERNSHIP

        filtered.append(job)

    return FilterOutcome(filtered, dropped, dropped_by_source)


def filter_jobs(jobs: list[Job], query: JobQuery) -> list[Job]:
    return filter_jobs_with_diagnostics(jobs, query).jobs

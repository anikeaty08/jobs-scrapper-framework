"""Post-scrape filtering."""

from __future__ import annotations

from datetime import date, timedelta

from jobhunter.models import Job, JobKind, WorkMode
from jobhunter.query import JobQuery


def _contains_any(value: str, needles: list[str]) -> bool:
    lowered = value.lower()
    return any(needle.lower() in lowered for needle in needles if needle)


def filter_jobs(jobs: list[Job], query: JobQuery) -> list[Job]:
    filtered: list[Job] = []
    excludes = [item.lower() for item in query.exclude]
    today = date.today()

    for job in jobs:
        searchable = " ".join([job.title, job.company, job.description, " ".join(job.skills)]).lower()
        if excludes and any(excluded in searchable for excluded in excludes):
            continue
        if query.city and job.city and query.city.lower() not in job.city.lower():
            continue
        if query.cities and job.city:
            if not any(city.lower() in job.city.lower() for city in query.cities):
                continue
        if query.country and job.country and query.country.lower() not in job.country.lower():
            continue
        if query.remote is True and job.work_mode not in {WorkMode.REMOTE, WorkMode.UNKNOWN}:
            continue
        if query.remote is False and job.work_mode == WorkMode.REMOTE:
            continue
        if query.fresher is True and job.experience_min and job.experience_min > 1:
            continue
        if query.experience_max is not None and job.experience_min and job.experience_min > query.experience_max:
            continue
        if query.skills:
            skill_terms = [skill.lower() for skill in query.skills]
            structured_skills = set(job.skills)
            if not structured_skills.intersection(skill_terms) and not any(skill in searchable for skill in skill_terms):
                continue
        if query.salary_min is not None:
            amount = job.salary.max_amount or job.salary.min_amount
            if amount is not None and amount < query.salary_min:
                continue
        if query.stipend_min is not None:
            amount = job.stipend.max_amount or job.stipend.min_amount
            if amount is not None and amount < query.stipend_min:
                continue
        if query.posted_within_days is not None:
            if not job.date_posted:
                continue
            try:
                posted = date.fromisoformat(job.date_posted)
            except ValueError:
                continue
            if posted < today - timedelta(days=query.posted_within_days):
                continue
        if query.job_kind:
            wanted = {query.job_kind} if isinstance(query.job_kind, str) else set(query.job_kind)
            if str(job.job_kind) not in wanted and job.job_kind not in wanted:
                continue
        if query.normalized_term and not _contains_any(searchable, [query.normalized_term]):
            terms = [part for part in query.normalized_term.split() if len(part) > 2]
            if terms and not _contains_any(searchable, terms):
                continue
        if job.job_kind == JobKind.UNKNOWN and "intern" in query.normalized_term.lower():
            job.job_kind = JobKind.INTERNSHIP
        filtered.append(job)
    return filtered

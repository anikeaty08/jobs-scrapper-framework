"""Result scoring and explainability."""

from __future__ import annotations

from hirehunt.models import Job, WorkMode
from hirehunt.query import JobProfile, JobQuery


def rank_jobs(jobs: list[Job], query: JobQuery) -> list[Job]:
    terms = [term.lower() for term in query.normalized_term.split() if len(term) > 2]
    skills = [skill.lower() for skill in query.skills]

    for job in jobs:
        score = 0.0
        reasons: list[str] = []
        warnings: list[str] = []
        title = job.title.lower()
        description = job.description.lower()

        title_hits = [term for term in terms if term in title]
        if title_hits:
            score += min(35, 12 * len(title_hits))
            reasons.append("title matches search intent")

        skill_hits = sorted(set(skills).intersection(job.skills))
        text_skill_hits = [skill for skill in skills if skill in title or skill in description]
        combined_skill_hits = sorted(set(skill_hits + text_skill_hits))
        if combined_skill_hits:
            score += min(30, 8 * len(combined_skill_hits))
            reasons.append("skills match: " + ", ".join(combined_skill_hits[:5]))
        elif skills:
            warnings.append("no requested skills found")

        if query.company_terms and any(term.lower() in job.company.lower() for term in query.company_terms):
            score += 12
            reasons.append("company matches")

        if query.remote is True and job.work_mode == WorkMode.REMOTE:
            score += 10
            reasons.append("remote role")
        if query.work_mode and str(job.work_mode) == str(query.work_mode).lower():
            score += 8
            reasons.append("work mode matches")
        if query.city and job.city and query.city.lower() in job.city.lower():
            score += 8
            reasons.append("city matches")
        if query.cities and job.city and any(city.lower() in job.city.lower() for city in query.cities):
            score += 8
            reasons.append("preferred city matches")
        if query.fresher and (job.experience_min is None or job.experience_min <= 1):
            score += 10
            reasons.append("fresher friendly")
        if query.salary_min and (job.salary.max_amount or 0) >= query.salary_min:
            score += 8
            reasons.append("salary target met")
        if query.stipend_min and (job.stipend.max_amount or 0) >= query.stipend_min:
            score += 8
            reasons.append("stipend target met")
        if job.date_posted:
            score += 5
            reasons.append("has posting date")
        profile_score, profile_reasons, profile_warnings = score_for_profile(job, query.profile)
        score += profile_score
        reasons.extend(profile_reasons)
        warnings.extend(profile_warnings)

        if not job.description:
            warnings.append("description unavailable")
        if "senior" in title and query.fresher:
            warnings.append("senior title may not fit fresher profile")
            score -= 15
        if terms and not title_hits and not any(term in description for term in terms):
            score -= 10

        job.match_score = max(0.0, min(100.0, score))
        job.reasons = reasons
        job.warnings = warnings

    return sorted(jobs, key=lambda item: (item.match_score, item.date_posted or ""), reverse=True)


def score_for_profile(job: Job, profile: JobProfile | None) -> tuple[float, list[str], list[str]]:
    if profile is None:
        return 0.0, [], []

    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    title = job.title.lower()
    company = job.company.lower()

    title_hits = [wanted for wanted in profile.preferred_titles if wanted.lower() in title]
    if title_hits:
        score += min(18, 6 * len(title_hits))
        reasons.append("profile title preference matched")

    skill_hits = sorted(set(skill.lower() for skill in profile.skills).intersection(job.skills))
    if skill_hits:
        score += min(24, 6 * len(skill_hits))
        reasons.append("profile skills matched: " + ", ".join(skill_hits[:5]))

    if profile.preferred_companies and any(name.lower() in company for name in profile.preferred_companies):
        score += 10
        reasons.append("preferred company matched")

    if profile.excluded_companies and any(name.lower() in company for name in profile.excluded_companies):
        score -= 40
        warnings.append("excluded company matched")

    if profile.preferred_cities and job.city:
        if any(city.lower() in job.city.lower() for city in profile.preferred_cities):
            score += 8
            reasons.append("profile city preference matched")

    if profile.remote_preferred and job.work_mode == WorkMode.REMOTE:
        score += 8
        reasons.append("profile remote preference matched")

    if profile.fresher and (job.experience_min is None or job.experience_min <= 1):
        score += 8
        reasons.append("profile fresher fit")

    if profile.experience_years is not None:
        if job.experience_min is not None and job.experience_min > profile.experience_years:
            score -= 12
            warnings.append("experience requirement may be high")
        elif job.experience_max is None or job.experience_max >= profile.experience_years:
            score += 6
            reasons.append("experience range fits profile")

    if profile.min_salary is not None and (job.salary.max_amount or 0) >= profile.min_salary:
        score += 6
        reasons.append("profile salary target met")

    if profile.min_stipend is not None and (job.stipend.max_amount or 0) >= profile.min_stipend:
        score += 6
        reasons.append("profile stipend target met")

    return score, reasons, warnings

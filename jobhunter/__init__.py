"""JobHunter public API."""

from jobhunter.engine import SearchEngine, scrape_jobs, search_jobs, search_jobs_async
from jobhunter.models import Job, JobKind, Money, SalaryPeriod, ScrapeResult, WorkMode
from jobhunter.query import JobProfile, JobQuery

__all__ = [
    "Job",
    "JobKind",
    "JobQuery",
    "JobProfile",
    "Money",
    "SalaryPeriod",
    "ScrapeResult",
    "SearchEngine",
    "WorkMode",
    "scrape_jobs",
    "search_jobs",
    "search_jobs_async",
]

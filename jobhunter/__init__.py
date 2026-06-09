"""JobHunter public API."""

from jobhunter.engine import SearchEngine, scrape_jobs, search_jobs
from jobhunter.models import Job, JobKind, Money, SalaryPeriod, ScrapeResult, WorkMode
from jobhunter.query import JobQuery

__all__ = [
    "Job",
    "JobKind",
    "JobQuery",
    "Money",
    "SalaryPeriod",
    "ScrapeResult",
    "SearchEngine",
    "WorkMode",
    "scrape_jobs",
    "search_jobs",
]

"""JobHunter public API."""

from hirehunt.engine import SearchEngine, scrape_jobs, search_jobs, search_jobs_async
from hirehunt.models import (
    CompletionStatus,
    JOB_SCHEMA_VERSION,
    Job,
    JobKind,
    Money,
    SalaryPeriod,
    ScrapeResult,
    SourceCapabilities,
    SourceStats,
    WorkMode,
)
from hirehunt.policies import CacheBackend, RequestPolicy, SearchPolicies
from hirehunt.query import JobProfile, JobQuery

__all__ = [
    "Job",
    "CompletionStatus",
    "JOB_SCHEMA_VERSION",
    "JobKind",
    "JobQuery",
    "JobProfile",
    "Money",
    "SalaryPeriod",
    "ScrapeResult",
    "SourceCapabilities",
    "SourceStats",
    "RequestPolicy",
    "CacheBackend",
    "SearchPolicies",
    "SearchEngine",
    "WorkMode",
    "scrape_jobs",
    "search_jobs",
    "search_jobs_async",
]

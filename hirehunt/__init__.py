"""JobHunter public API."""

from importlib.metadata import PackageNotFoundError, version

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
    SourceDefinition,
    SourceStats,
    WorkMode,
)
from hirehunt.policies import CacheBackend, RequestPolicy, SearchPolicies
from hirehunt.query import JobProfile, JobQuery

try:
    __version__ = version("hirehunt")
except PackageNotFoundError:
    __version__ = "0.4.0"

__all__ = [
    "__version__",
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
    "SourceDefinition",
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

"""Core data models for normalized job search results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import json


class JobKind(StrEnum):
    JOB = "job"
    INTERNSHIP = "internship"
    HACKATHON = "hackathon"
    COMPETITION = "competition"
    FELLOWSHIP = "fellowship"
    UNKNOWN = "unknown"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class SalaryPeriod(StrEnum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    PROJECT = "project"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Money:
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "INR"
    period: SalaryPeriod = SalaryPeriod.UNKNOWN
    raw_text: str = ""

    @property
    def has_value(self) -> bool:
        return self.min_amount is not None or self.max_amount is not None


@dataclass
class Job:
    title: str
    company: str
    source: str
    job_url: str

    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN

    job_kind: JobKind = JobKind.UNKNOWN
    employment_type: str = ""
    experience_min: float | None = None
    experience_max: float | None = None
    experience_text: str = ""

    salary: Money = field(default_factory=Money)
    stipend: Money = field(default_factory=Money)

    skills: list[str] = field(default_factory=list)
    description: str = ""
    date_posted: str | None = None
    deadline: str | None = None

    company_url: str = ""
    company_rating: str = ""
    company_industry: str = ""

    source_job_id: str = ""
    apply_url: str = ""
    easy_apply: bool = False

    match_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["job_kind"] = str(self.job_kind)
        data["work_mode"] = str(self.work_mode)
        data["salary"]["period"] = str(self.salary.period)
        data["stipend"]["period"] = str(self.stipend.period)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def __str__(self) -> str:
        place = self.city or self.location or self.country or "unknown location"
        return f"{self.title} @ {self.company} | {place} | {self.source}"


@dataclass
class SourceStats:
    found: int = 0
    kept: int = 0
    duplicates: int = 0
    errors: int = 0


@dataclass
class ScrapeResult:
    jobs: list[Job] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    stats: dict[str, SourceStats] = field(default_factory=dict)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.jobs]

    def top(self, count: int = 20) -> list[Job]:
        return self.jobs[:count]

    def to_dataframe(self):
        from jobhunter.exporters.dataframe import to_dataframe

        return to_dataframe(self.jobs)

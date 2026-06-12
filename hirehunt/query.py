"""User-facing query model."""

from __future__ import annotations

from dataclasses import dataclass, field

from hirehunt.policies import CacheBackend, RequestPolicy


@dataclass
class JobProfile:
    skills: list[str] = field(default_factory=list)
    experience_years: float | None = None
    preferred_titles: list[str] = field(default_factory=list)
    preferred_companies: list[str] = field(default_factory=list)
    excluded_companies: list[str] = field(default_factory=list)
    preferred_cities: list[str] = field(default_factory=list)
    min_salary: float | None = None
    min_stipend: float | None = None
    remote_preferred: bool = False
    fresher: bool = False


@dataclass
class JobQuery:
    role: str = ""
    search_term: str = ""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    cities: list[str] = field(default_factory=list)

    skills: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    sources: list[str] | str = "auto"

    job_type: list[str] | str | None = None
    job_kind: list[str] | str | None = None
    remote: bool | None = None
    work_mode: str | None = None
    fresher: bool | None = None
    experience_min: float | None = None
    experience_max: float | None = None

    salary_min: float | None = None
    stipend_min: float | None = None
    currency: str = "INR"

    posted_within_days: int | None = None
    results_wanted: int | None = 50
    dedupe_mode: str = "strict"
    fetch_descriptions: bool = False
    fetch_backend: str = "requests"
    cache_enabled: bool = False
    cache_dir: str = ".jobhunter_cache"
    cache_backend: CacheBackend | None = None
    include_regional: bool = True
    proxies: list[str] = field(default_factory=list)
    request_policy: RequestPolicy | None = None
    profile: JobProfile | None = None

    def __post_init__(self) -> None:
        # Normalize city at entry — blr→Bengaluru, calcutta→Kolkata, mum→Mumbai etc.
        if self.city:
            from hirehunt.utils.normalization import normalize_city
            self.city = normalize_city(self.city)
        if self.city and not self.cities:
            self.cities = [self.city]
        if not self.search_term and self.role:
            self.search_term = self.role
        if isinstance(self.profile, dict):
            self.profile = JobProfile(**self.profile)
        if isinstance(self.request_policy, dict):
            self.request_policy = RequestPolicy(**self.request_policy)
        if self.dedupe_mode not in {"strict", "heuristic", "none"}:
            raise ValueError("dedupe_mode must be 'strict', 'heuristic', or 'none'")

    @classmethod
    def from_kwargs(cls, **kwargs) -> "JobQuery":
        if "search_term" not in kwargs and "role" in kwargs:
            kwargs["search_term"] = kwargs["role"]
        if "city" in kwargs and kwargs["city"] and "cities" not in kwargs:
            kwargs["cities"] = [kwargs["city"]]
        return cls(**kwargs)

    @property
    def normalized_term(self) -> str:
        return (self.search_term or self.role).strip()

    @property
    def source_list(self) -> list[str]:
        if self.sources == "auto":
            return []
        if isinstance(self.sources, str):
            return [self.sources]
        return list(self.sources)

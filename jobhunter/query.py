"""User-facing query model."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    results_wanted: int = 50
    fetch_descriptions: bool = False
    include_regional: bool = True
    proxies: list[str] = field(default_factory=list)

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

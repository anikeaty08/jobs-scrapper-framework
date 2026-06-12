"""Indeed GraphQL scraper."""

from __future__ import annotations

from datetime import datetime, timezone
import os

from hirehunt.models import Job, JobKind, Money, SalaryPeriod, SourceCapabilities, WorkMode
from hirehunt.query import JobQuery
from hirehunt.scrapers.base import BaseScraper
from hirehunt.utils.normalization import clean_text, normalize_city, parse_experience, parse_job_kind


INDEED_GRAPHQL_URL = "https://apis.indeed.com/graphql"
DEFAULT_INDEED_API_KEY = "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"

INDEED_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "accept": "application/json",
    "indeed-locale": "en-US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1",
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

INDEED_COUNTRY_CODES = {
    "india": "IN",
    "in": "IN",
    "usa": "US",
    "us": "US",
    "uk": "GB",
    "gb": "GB",
    "canada": "CA",
    "ca": "CA",
    "australia": "AU",
    "au": "AU",
}

INDEED_DOMAINS = {
    "IN": "in.indeed.com",
    "US": "www.indeed.com",
    "GB": "uk.indeed.com",
    "CA": "ca.indeed.com",
    "AU": "au.indeed.com",
}


class IndeedScraper(BaseScraper):
    source = "indeed"
    source_family = "aggregator"
    source_adapter = "indeed_graphql"
    source_tags = ("global", "jobs", "internships")
    capabilities = SourceCapabilities(
        countries=("global",),
        job_kinds=(JobKind.JOB, JobKind.INTERNSHIP),
        supported_filters=frozenset({"country", "city", "job_type", "remote", "posted_within_days"}),
        pagination=True,
        exhaustive_search=True,
        description="Indeed GraphQL job search",
    )
    jobs_per_page = 100
    last_status_code = 0
    last_backend = ""

    def build_url(self, query: JobQuery, start: int = 0) -> str:
        return INDEED_GRAPHQL_URL

    def search(self, query: JobQuery) -> list[Job]:
        jobs: list[Job] = []
        cursor = None
        while self.wants_more(jobs, query):
            response = self.post_json(
                INDEED_GRAPHQL_URL,
                headers=build_indeed_headers(query),
                payload={"query": build_indeed_query(query, cursor=cursor)},
            )
            self.last_status_code = response.status_code if response else 0
            self.last_backend = response.backend if response else ""
            if response is None or response.status_code != 200:
                return jobs
            parsed_jobs, cursor = parse_indeed_graphql_response(response.text, query)
            if not parsed_jobs:
                break
            jobs.extend(parsed_jobs)
            if not cursor:
                break
        return self.limit(jobs, query)


def build_indeed_headers(query: JobQuery) -> dict[str, str]:
    headers = INDEED_HEADERS.copy()
    headers["indeed-api-key"] = os.getenv("INDEED_API_KEY", DEFAULT_INDEED_API_KEY)
    headers["indeed-co"] = indeed_country_code(query)
    return headers


def indeed_country_code(query: JobQuery) -> str:
    country = (query.country or "").strip().lower()
    return INDEED_COUNTRY_CODES.get(country, "US")


def indeed_base_url(query: JobQuery) -> str:
    code = indeed_country_code(query)
    return "https://" + INDEED_DOMAINS.get(code, "www.indeed.com")


def build_indeed_query(query: JobQuery, cursor: str | None = None) -> str:
    keywords = " ".join([*query.company_terms, query.normalized_term]).strip()
    what = _graphql_arg("what", keywords)
    location = ""
    where = query.city or query.location or query.country
    if where:
        location = f'location: {{where: "{_escape_graphql(where)}", radius: 50, radiusUnit: MILES}}'
    cursor_arg = _graphql_arg("cursor", cursor) if cursor else ""
    filters = build_indeed_filters(query)
    return f"""
    query GetJobData {{
      jobSearch(
        {what}
        {location}
        limit: 100
        {cursor_arg}
        sort: RELEVANCE
        {filters}
      ) {{
        pageInfo {{
          nextCursor
        }}
        results {{
          trackingKey
          job {{
            source {{ name }}
            key
            title
            datePublished
            dateOnIndeed
            description {{ html }}
            location {{
              countryName
              countryCode
              admin1Code
              city
              postalCode
              streetAddress
              formatted {{ short long }}
            }}
            compensation {{
              estimated {{
                currencyCode
                baseSalary {{
                  unitOfWork
                  range {{ ... on Range {{ min max }} }}
                }}
              }}
              baseSalary {{
                unitOfWork
                range {{ ... on Range {{ min max }} }}
              }}
              currencyCode
            }}
            attributes {{ key label }}
            employer {{
              relativeCompanyPageUrl
              name
              dossier {{
                employerDetails {{
                  addresses
                  industry
                  employeesLocalizedLabel
                  revenueLocalizedLabel
                  briefDescription
                }}
                images {{ squareLogoUrl }}
                links {{ corporateWebsite }}
              }}
            }}
            recruit {{ viewJobUrl detailedSalary workSchedule }}
          }}
        }}
      }}
    }}
    """


def build_indeed_filters(query: JobQuery) -> str:
    if query.posted_within_days:
        return f"""
        filters: {{
          date: {{
            field: "dateOnIndeed"
            start: "{query.posted_within_days * 24}h"
          }}
        }}
        """

    attribute_keys: list[str] = []
    job_type = query.job_type[0] if isinstance(query.job_type, list) and query.job_type else query.job_type
    job_type_map = {
        "fulltime": "CF3CP",
        "full_time": "CF3CP",
        "parttime": "75GKK",
        "part_time": "75GKK",
        "contract": "NJXCK",
        "internship": "VDTG7",
    }
    if job_type:
        key = job_type_map.get(str(job_type).lower())
        if key:
            attribute_keys.append(key)
    if query.remote:
        attribute_keys.append("DSQF7")
    if not attribute_keys:
        return ""
    keys = '", "'.join(attribute_keys)
    return f"""
    filters: {{
      composite: {{
        filters: [{{
          keyword: {{
            field: "attributes"
            keys: ["{keys}"]
          }}
        }}]
      }}
    }}
    """


def parse_indeed_graphql_response(text: str, query: JobQuery) -> tuple[list[Job], str | None]:
    import json

    payload = json.loads(text)
    search = payload.get("data", {}).get("jobSearch", {})
    results = search.get("results", [])
    cursor = search.get("pageInfo", {}).get("nextCursor")
    return [job for item in results if (job := parse_indeed_job(item.get("job", {}), query))], cursor


def parse_indeed_job(job: dict, query: JobQuery) -> Job | None:
    key = job.get("key")
    title = clean_text(job.get("title", ""))
    if not key or not title:
        return None

    location = job.get("location") or {}
    employer = job.get("employer") or {}
    dossier = employer.get("dossier") or {}
    details = dossier.get("employerDetails") or {}
    description_html = job.get("description", {}).get("html", "")
    description = clean_text(description_html)
    attributes = job.get("attributes") or []
    attribute_text = " ".join(clean_text(attr.get("label", "")) for attr in attributes)
    exp_min, exp_max, exp_text = parse_experience(description + " " + attribute_text)
    company_rel = employer.get("relativeCompanyPageUrl") or ""
    base_url = indeed_base_url(query)

    return Job(
        title=title,
        company=clean_text(employer.get("name", "")),
        source="indeed",
        job_url=f"{base_url}/viewjob?jk={key}",
        location=clean_text(location.get("formatted", {}).get("long") or location.get("formatted", {}).get("short") or ""),
        city=normalize_city(location.get("city") or query.city),
        state=clean_text(location.get("admin1Code", "")),
        country=clean_text(location.get("countryCode") or query.country),
        work_mode=parse_indeed_work_mode(location, attribute_text, description),
        job_kind=parse_job_kind(title + " " + attribute_text),
        employment_type=", ".join(parse_indeed_job_types(attributes)),
        salary=parse_indeed_money(job.get("compensation") or {}),
        experience_min=exp_min,
        experience_max=exp_max,
        experience_text=exp_text,
        description=description,
        date_posted=parse_indeed_timestamp(job.get("datePublished")),
        company_url=f"{base_url}{company_rel}" if company_rel else "",
        company_industry=clean_text((details.get("industry") or "").replace("Iv1", "").replace("_", " ").title()),
        source_job_id=key,
        apply_url=(job.get("recruit") or {}).get("viewJobUrl") or "",
        raw={"source_card": "indeed_graphql"},
    )


def parse_indeed_money(compensation: dict) -> Money:
    comp = compensation.get("baseSalary") or (compensation.get("estimated") or {}).get("baseSalary")
    if not comp:
        return Money()
    amount_range = comp.get("range") or {}
    return Money(
        min_amount=amount_range.get("min"),
        max_amount=amount_range.get("max"),
        currency=(compensation.get("currencyCode") or (compensation.get("estimated") or {}).get("currencyCode") or "INR"),
        period=parse_salary_period(comp.get("unitOfWork")),
        raw_text="",
    )


def parse_salary_period(unit: str | None) -> SalaryPeriod:
    mapping = {
        "HOUR": SalaryPeriod.HOUR,
        "DAY": SalaryPeriod.DAY,
        "WEEK": SalaryPeriod.WEEK,
        "MONTH": SalaryPeriod.MONTH,
        "YEAR": SalaryPeriod.YEAR,
    }
    return mapping.get((unit or "").upper(), SalaryPeriod.UNKNOWN)


def parse_indeed_timestamp(value) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def parse_indeed_work_mode(location: dict, attribute_text: str, description: str) -> WorkMode:
    haystack = " ".join(
        [
            location.get("formatted", {}).get("long", ""),
            location.get("formatted", {}).get("short", ""),
            attribute_text,
            description,
        ]
    ).lower()
    if any(term in haystack for term in ("remote", "work from home", "wfh")):
        return WorkMode.REMOTE
    if "hybrid" in haystack:
        return WorkMode.HYBRID
    return WorkMode.UNKNOWN


def parse_indeed_job_types(attributes: list[dict]) -> list[str]:
    labels = []
    for attr in attributes:
        label = clean_text(attr.get("label", ""))
        lowered = label.lower().replace("-", "").replace(" ", "")
        if lowered in {"fulltime", "parttime", "contract", "internship"}:
            labels.append(label.lower())
    return labels


def _graphql_arg(name: str, value: str | None) -> str:
    if not value:
        return ""
    return f'{name}: "{_escape_graphql(value)}"'


def _escape_graphql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

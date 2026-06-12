"""FAANG/Big-Tech scrapers.

Strategy after reverse engineering (2026):
  - Amazon    → amazon.jobs/en/search.json  ✅ confirmed public REST API
  - Google    → No public API → use LinkedIn company filter
  - Meta      → No public API → use LinkedIn company filter
  - Apple     → No public API → use LinkedIn company filter
  - Netflix   → No public API → use LinkedIn company filter
  - Microsoft → No public API → use LinkedIn company filter

LinkedIn's guest API (already used by LinkedInScraper) supports
filtering by company name, so we subclass it here to hard-code
the company filter for each FAANG company.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlencode

from hirehunt.models import Job, JobKind, Money, SalaryPeriod, SourceCapabilities, WorkMode
from hirehunt.query import JobQuery
from hirehunt.scrapers.base import BaseScraper
from hirehunt.scrapers.linkedin import LinkedInScraper
from hirehunt.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_skills,
    parse_work_mode,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# LinkedIn company IDs — confirmed working with the guest API
# Note: f_C filter only works for some company IDs on the guest endpoint.
# For companies where f_C returns 0, we fall back to keyword+company search.
_LINKEDIN_COMPANY_IDS = {
    "google":    "1441",    # ✅ confirmed working
    "meta":      "10667",   # ✅ confirmed working
    "apple":     "",        # f_C=162479 returns 0 on guest API — use keyword fallback
    "netflix":   "165158",  # ✅ confirmed working
    "microsoft": "1035",    # ✅ confirmed working
}

# Company name override — added to keywords when f_C is empty
_COMPANY_KEYWORD_OVERRIDE = {
    "apple": "Apple",
}


# ══════════════════════════════════════════════════════════════════════════════
# Base company-pinned LinkedIn scraper
# ══════════════════════════════════════════════════════════════════════════════

class _CompanyLinkedInScraper(LinkedInScraper):
    """LinkedIn scraper pinned to a specific company via f_C filter."""
    _company_name: str = ""
    _company_id:   str = ""
    capabilities = SourceCapabilities(
        countries=("global",),
        job_kinds=(JobKind.JOB, JobKind.INTERNSHIP),
        supported_filters=frozenset({"country", "city", "remote"}),
        pagination=False,
        exhaustive_search=False,
        description="Company-filtered LinkedIn guest search",
    )

    def build_url(self, query: JobQuery) -> str:  # type: ignore[override]
        """Build LinkedIn guest API URL with company filter or keyword fallback."""
        from urllib.parse import urlencode
        # If company ID is known-working, use f_C filter
        # Otherwise, inject company name into keywords
        keyword_override = _COMPANY_KEYWORD_OVERRIDE.get(self._company_name.lower(), "")
        keywords = (
            f"{self._company_name} {query.normalized_term}"
            if keyword_override
            else query.normalized_term
        )
        params: dict = {
            "keywords": keywords,
            "location": query.city or query.location or query.country or "",
            "start":    0,
        }
        if self._company_id:
            params["f_C"] = self._company_id
        if query.remote:
            params["f_WT"] = "2"
        return (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
            + urlencode({k: v for k, v in params.items() if str(v) != ""})
        )

    def search(self, query: JobQuery) -> list[Job]:
        from hirehunt.scrapers.linkedin import parse_linkedin_jobs
        resp = self.fetch(self.build_url(query))
        if not resp or resp.status_code != 200:
            return []
        jobs = parse_linkedin_jobs(resp.text, query)
        # Re-tag source and company
        for job in jobs:
            job.source  = self.source
            job.company = job.company or self._company_name
        return self.limit(jobs, query)


# ══════════════════════════════════════════════════════════════════════════════
# Individual FAANG scrapers (LinkedIn-backed, company-pinned)
# ══════════════════════════════════════════════════════════════════════════════

class GoogleCareersScraper(_CompanyLinkedInScraper):
    source         = "google_careers"
    _company_name  = "Google"
    _company_id    = _LINKEDIN_COMPANY_IDS["google"]


class MetaCareersScraper(_CompanyLinkedInScraper):
    source         = "meta"
    _company_name  = "Meta"
    _company_id    = _LINKEDIN_COMPANY_IDS["meta"]


class AppleJobsScraper(_CompanyLinkedInScraper):
    source         = "apple"
    _company_name  = "Apple"
    _company_id    = _LINKEDIN_COMPANY_IDS["apple"]


class NetflixJobsScraper(_CompanyLinkedInScraper):
    source         = "netflix"
    _company_name  = "Netflix"
    _company_id    = _LINKEDIN_COMPANY_IDS["netflix"]


class MicrosoftCareersScraper(_CompanyLinkedInScraper):
    source         = "microsoft"
    _company_name  = "Microsoft"
    _company_id    = _LINKEDIN_COMPANY_IDS["microsoft"]


# ══════════════════════════════════════════════════════════════════════════════
# Amazon Jobs — confirmed working REST JSON API
# ══════════════════════════════════════════════════════════════════════════════

class AmazonJobsScraper(BaseScraper):
    """Amazon Jobs — confirmed REST JSON API at amazon.jobs/en/search.json.

    Response structure:
      { "jobs": [ { "title", "location", "job_path", "posted_date",
                    "description_short", "basic_qualifications",
                    "job_category", "is_intern", "team": {dict}, ... } ] }
    """
    source = "amazon"
    default_country = ""
    capabilities = SourceCapabilities(
        countries=("global",),
        job_kinds=(JobKind.JOB, JobKind.INTERNSHIP),
        supported_filters=frozenset({"country", "city", "job_kind"}),
        pagination=True,
        exhaustive_search=True,
        description="Amazon Jobs public API",
    )
    _ENDPOINT = "https://www.amazon.jobs/en/search.json"

    def search(self, query: JobQuery) -> list[Job]:
        jobs: list[Job] = []
        offset    = 0
        page_size = 10

        location = query.city or query.location or query.country or ""

        while self.wants_more(jobs, query):
            params: dict = {
                "base_query":   query.normalized_term,
                "result_limit": page_size,
                "offset":       offset,
                "sort":         "relevant",
            }
            if location:
                params["loc_query"] = location
            if query.job_kind and "intern" in str(query.job_kind).lower():
                params["category[]"] = "internships"

            resp = self.get_json(
                self._ENDPOINT,
                params=params,
                headers={
                    "User-Agent": _UA,
                    "Accept":     "application/json",
                    "Referer":    "https://www.amazon.jobs/en/jobs/",
                },
            )
            if not resp or resp.status_code != 200:
                break

            try:
                data = json.loads(resp.text)
            except Exception:
                break

            items = data.get("jobs", [])
            if not items:
                break

            for item in items:
                job = _parse_amazon_job(item, query)
                if job:
                    jobs.append(job)

            if len(items) < page_size:
                break

            offset += page_size
            time.sleep(0.3)

        return self.limit(jobs, query)


def _parse_amazon_job(item: dict, query: JobQuery) -> Job | None:
    title = clean_text(item.get("title") or "")
    if not title:
        return None

    job_id   = str(item.get("id") or item.get("id_icims") or "")
    url_path = item.get("job_path") or ""
    job_url  = f"https://www.amazon.jobs{url_path}" if url_path else f"https://www.amazon.jobs/en/jobs/{job_id}"

    # location is a plain string like "US, CA, Cupertino"
    location = clean_text(item.get("location") or item.get("normalized_location") or "")
    city_raw = item.get("city") or location.split(",")[-1].strip()
    city     = normalize_city(city_raw)

    # team is a dict — extract label safely
    team_raw = item.get("team") or {}
    team = (
        clean_text(team_raw.get("label") or team_raw.get("name") or "")
        if isinstance(team_raw, dict)
        else clean_text(str(team_raw))
    )

    category = clean_text(item.get("job_category") or item.get("job_family") or "")
    is_intern = bool(item.get("is_intern") or item.get("university_job"))

    job_kind = (
        JobKind.INTERNSHIP
        if (is_intern or "intern" in title.lower())
        else JobKind.JOB
    )

    posted_raw  = item.get("posted_date") or item.get("updated_time") or ""
    date_posted = posted_raw[:10] if posted_raw else None

    desc = clean_text(
        item.get("description_short") or
        item.get("basic_qualifications") or
        item.get("description") or ""
    )

    emp_type = clean_text(item.get("job_schedule_type") or "")

    return Job(
        title           = title,
        company         = "Amazon",
        source          = "amazon",
        job_url         = job_url,
        location        = location,
        city            = city,
        country         = item.get("country_code") or query.country or "",
        work_mode       = parse_work_mode(location + " " + desc),
        job_kind        = job_kind,
        employment_type = emp_type,
        description     = desc,
        date_posted     = date_posted,
        source_job_id   = job_id,
        company_industry= category or team,
        raw             = {"source_card": "amazon_jobs", "team": team},
    )

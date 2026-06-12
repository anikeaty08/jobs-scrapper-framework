"""Shine.com scraper — uses __NEXT_DATA__ JSON embedded in HTML pages.

Reverse engineering findings:
  - Data is in: __NEXT_DATA__ → props.pageProps.initialState.jsrp.searchresult.data.results
  - 20 results per page, 897 pages (17,927 total for broad searches)
  - Pagination: append -N to the search slug, e.g. ...-jobs-in-bangalore-2
  - Field mapping (abbreviated keys):
      jJT    → job title
      jCName → company name
      jSal   → salary text (e.g. 'Rs 4.0 - 6 Lakh/Yr')
      jLoc   → location list
      jKwd   → skills/keywords (comma-separated)
      jPDate → posted date (ISO format)
      jSlug  → URL slug (contains company slug + job id)
      jExp   → experience text
      jWM    → work mode (0=onsite, 1=wfh/remote)
      id     → numeric job ID
      jRUrl  → relative URL for job detail (if present)
  - URL: https://www.shine.com/jobs/{jSlug}
  - No external API found — all data is SSR-embedded
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from bs4 import BeautifulSoup

from hirehunt.models import Job, JobKind, Money, SalaryPeriod, SourceCapabilities, WorkMode
from hirehunt.query import JobQuery
from hirehunt.scrapers.base import BaseScraper
from hirehunt.utils.normalization import (
    city_for_scraper,
    clean_text,
    normalize_city,
    normalize_skills,
    parse_date,
    parse_work_mode,
)

_BASE = "https://www.shine.com"
_JOBS_PER_PAGE = 20


def _make_search_url(query: JobQuery, page: int = 1) -> str:
    """Build Shine.com search URL with optional city filter."""
    term = query.normalized_term.lower().strip()
    term_slug = re.sub(r"[^a-z0-9]+", "-", term).strip("-")

    requested_city = query.city or query.location or ""
    city = city_for_scraper(requested_city, "shine") if requested_city else ""
    city_slug = re.sub(r"[^a-z0-9]+", "-", city).strip("-") if city else ""

    if city_slug:
        path = f"/job-search/{term_slug}-jobs-in-{city_slug}"
    else:
        path = f"/job-search/{term_slug}-jobs"

    url = f"{_BASE}{path}"
    if page > 1:
        url += f"-{page}"
    return url


class ShineScraper(BaseScraper):
    source = "shine"
    source_family = "regional"
    source_adapter = "shine_ssr"
    source_tags = ("india", "jobs", "internships")
    default_country = "India"
    capabilities = SourceCapabilities(
        countries=("India",),
        job_kinds=(JobKind.JOB, JobKind.INTERNSHIP),
        supported_filters=frozenset({"city"}),
        pagination=True,
        exhaustive_search=True,
        description="Shine SSR job search",
    )

    def build_url(self, query: JobQuery, page: int = 1) -> str:
        return _make_search_url(query, page)

    def search(self, query: JobQuery) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str | tuple[str, str, str]] = set()
        page = 1

        while self.wants_more(jobs, query):
            url = self.build_url(query, page)
            resp = self.fetch(url)

            if resp is None or resp.status_code != 200:
                break

            batch, total_pages = _parse_shine_page(resp.text, query)
            if not batch:
                break

            new_jobs: list[Job] = []
            for job in batch:
                identity: str | tuple[str, str, str] = job.source_job_id or (
                    job.title.lower(),
                    job.company.lower(),
                    job.location.lower(),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                new_jobs.append(job)

            if not new_jobs:
                break

            jobs.extend(new_jobs)

            if page >= total_pages:
                break

            page += 1
            time.sleep(0.4)

        return self.limit(jobs, query)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_shine_page(html: str, query: JobQuery) -> tuple[list[Job], int]:
    soup = BeautifulSoup(html, "html.parser")
    nd = soup.find("script", id="__NEXT_DATA__")
    if not nd:
        return [], 1

    try:
        data = json.loads(nd.get_text())
    except (json.JSONDecodeError, Exception):
        return [], 1

    sr_data = (
        data.get("props", {})
            .get("pageProps", {})
            .get("initialState", {})
            .get("jsrp", {})
            .get("searchresult", {})
            .get("data", {})
    )
    results    = sr_data.get("results", [])
    total_pages = sr_data.get("num_pages", 1) or 1

    jobs = []
    for item in results:
        job = _parse_shine_item(item, query)
        if job:
            jobs.append(job)

    return jobs, int(total_pages)


def _parse_shine_item(item: dict, query: JobQuery) -> Job | None:
    # Title
    title = clean_text(item.get("jJT") or "")
    if not title:
        return None

    # Company
    company = clean_text(item.get("jCName") or "")

    # URL — jSlug contains 'slug/company-slug/id'
    job_slug = item.get("jSlug", "")
    job_id   = str(item.get("id", ""))
    job_url  = f"{_BASE}/jobs/{job_slug}" if job_slug else ""
    if not job_url and job_id:
        job_url = f"{_BASE}/jobs/{job_id}"
    if not job_url:
        return None

    # Location — jLoc is a list of city strings
    locs = item.get("jLoc") or []
    if isinstance(locs, str):
        locs = [locs]
    raw_location = ", ".join(locs)
    city = normalize_city(locs[0] if locs else query.city)

    # Salary
    sal_text = clean_text(item.get("jSal") or "")
    salary = _parse_shine_salary(sal_text)

    # Skills
    raw_skills = item.get("jKwd") or ""
    if isinstance(raw_skills, str):
        skills = normalize_skills(raw_skills.split(","))
    else:
        skills = normalize_skills(raw_skills)

    # Date posted
    date_raw = item.get("jPDate") or ""
    date_posted = date_raw[:10] if date_raw else None  # ISO datetime → just date part

    # Experience
    exp_text = clean_text(item.get("jExp") or "")

    # Work mode — jWM: 0=onsite, 1=wfh/remote
    wm_val = item.get("jWM", 0)
    if wm_val == 1:
        work_mode = WorkMode.REMOTE
    elif wm_val == 2:
        work_mode = WorkMode.HYBRID
    else:
        work_mode = WorkMode.ONSITE

    # Job kind
    emp_type = str(item.get("jEType") or item.get("jJobType") or "")
    if "intern" in title.lower() or "intern" in emp_type.lower():
        job_kind = JobKind.INTERNSHIP
    else:
        job_kind = JobKind.JOB

    return Job(
        title           = title,
        company         = company,
        source          = "shine",
        job_url         = job_url,
        location        = raw_location,
        city            = city,
        country         = "India",
        work_mode       = work_mode,
        job_kind        = job_kind,
        salary          = salary,
        experience_text = exp_text,
        skills          = skills,
        date_posted     = date_posted,
        source_job_id   = job_id,
        raw             = {"source_card": "shine_nextdata"},
    )


def _parse_shine_salary(text: str) -> Money:
    """Parse salary strings like 'Rs 4.0 - 6 Lakh/Yr' or 'Rs 30,000/Mo'."""
    if not text or "hidden" in text.lower():
        return Money()
    text_lower = text.lower()

    # Detect period
    if "/yr" in text_lower or "lakh" in text_lower or "annual" in text_lower:
        period = SalaryPeriod.YEAR
        multiplier = 100_000
    elif "/mo" in text_lower or "month" in text_lower:
        period = SalaryPeriod.MONTH
        multiplier = 1
    else:
        period = SalaryPeriod.UNKNOWN
        multiplier = 1

    # Extract numbers
    nums = re.findall(r"[\d,]+\.?\d*", text.replace(",", ""))
    floats = []
    for n in nums:
        try:
            floats.append(float(n))
        except ValueError:
            pass

    if not floats:
        return Money(raw_text=text)

    min_amt = floats[0] * multiplier if floats else None
    max_amt = floats[1] * multiplier if len(floats) > 1 else None

    return Money(
        min_amount = min_amt,
        max_amount = max_amt,
        currency   = "INR",
        period     = period,
        raw_text   = text,
    )

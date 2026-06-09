"""Indeed scraper."""

from __future__ import annotations

from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobhunter.models import Job, JobKind
from jobhunter.query import JobQuery
from jobhunter.scrapers.base import BaseScraper
from jobhunter.utils.http import safe_get
from jobhunter.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_url,
    parse_date,
    parse_experience,
    parse_job_kind,
    parse_money,
    parse_work_mode,
)


class IndeedScraper(BaseScraper):
    source = "indeed"

    def build_url(self, query: JobQuery, start: int = 0) -> str:
        params = {
            "q": query.normalized_term,
            "l": query.city or query.location or query.country,
            "start": start,
        }
        if query.remote:
            params["remotejob"] = "1"
        if query.posted_within_days:
            params["fromage"] = str(query.posted_within_days)
        host = "in.indeed.com" if (query.country or "").lower() in {"india", "in"} else "www.indeed.com"
        return f"https://{host}/jobs?{urlencode({k: v for k, v in params.items() if v})}"

    def search(self, query: JobQuery) -> list[Job]:
        response = safe_get(self.session, self.build_url(query))
        if response is None or response.status_code != 200:
            return []
        return self.limit(parse_indeed_jobs(response.text, query), query)


def parse_indeed_jobs(html: str, query: JobQuery) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("[data-jk], .job_seen_beacon, .jobsearch-SerpJobCard")
    jobs: list[Job] = []
    for card in cards:
        title_el = card.select_one("h2 a, a.jcs-JobTitle, .jobTitle a, .jobTitle")
        company_el = card.select_one("[data-testid='company-name'], .companyName, span.company")
        location_el = card.select_one("[data-testid='text-location'], .companyLocation, .location")
        if not title_el or not company_el:
            continue
        href = title_el.get("href", "")
        job_url = href if href.startswith("http") else f"https://www.indeed.com{href}"
        title = clean_text(title_el.get_text(" "))
        company = clean_text(company_el.get_text(" "))
        location = clean_text(location_el.get_text(" ")) if location_el else query.location
        salary_el = card.select_one("[data-testid='attribute_snippet_testid'], .salary-snippet-container, .salaryText")
        date_el = card.select_one("[data-testid='myJobsStateDate'], .date")
        snippet = clean_text(card.get_text(" "))
        exp_min, exp_max, exp_text = parse_experience(snippet)
        jobs.append(
            Job(
                title=title,
                company=company,
                source="indeed",
                job_url=normalize_url(job_url),
                location=location,
                city=normalize_city(query.city or location.split(",")[0]),
                country=query.country or ("India" if "in.indeed" in job_url else ""),
                work_mode=parse_work_mode(location + " " + snippet),
                job_kind=parse_job_kind(title + " " + snippet) if "intern" in query.normalized_term.lower() else JobKind.JOB,
                salary=parse_money(salary_el.get_text(" ") if salary_el else ""),
                experience_min=exp_min,
                experience_max=exp_max,
                experience_text=exp_text,
                date_posted=parse_date(date_el.get_text(" ") if date_el else ""),
                description=snippet,
                source_job_id=card.get("data-jk", ""),
                raw={"source_card": "indeed"},
            )
        )
    return jobs

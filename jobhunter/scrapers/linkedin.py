"""LinkedIn public jobs scraper."""

from __future__ import annotations

from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobhunter.models import Job, JobKind
from jobhunter.query import JobQuery
from jobhunter.scrapers.base import BaseScraper
from jobhunter.utils.normalization import clean_text, normalize_city, normalize_url, parse_date, parse_job_kind, parse_work_mode


class LinkedInScraper(BaseScraper):
    source = "linkedin"

    def build_url(self, query: JobQuery) -> str:
        params = {
            "keywords": query.normalized_term,
            "location": query.city or query.location or query.country,
        }
        if query.remote:
            params["f_WT"] = "2"
        return "https://www.linkedin.com/jobs/search?" + urlencode({k: v for k, v in params.items() if v})

    def search(self, query: JobQuery) -> list[Job]:
        response = self.fetch(self.build_url(query))
        if response is None or response.status_code != 200:
            return []
        return self.limit(parse_linkedin_jobs(response.text, query), query)


def parse_linkedin_jobs(html: str, query: JobQuery) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".base-card")
    if not cards:
        cards = soup.select(".jobs-search__results-list li")
    jobs: list[Job] = []
    for card in cards:
        title_el = card.select_one(".base-search-card__title, h3")
        company_el = card.select_one(".base-search-card__subtitle, h4")
        location_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not title_el or not company_el:
            continue
        href = link_el.get("href", "") if link_el else ""
        location = clean_text(location_el.get_text(" ")) if location_el else query.location
        posted_el = card.select_one("time")
        source_job_id = ""
        if "/jobs/view/" in href:
            source_job_id = href.split("/jobs/view/", 1)[1].split("?", 1)[0].strip("/")
        jobs.append(
            Job(
                title=clean_text(title_el.get_text(" ")),
                company=clean_text(company_el.get_text(" ")),
                source="linkedin",
                job_url=normalize_url(href),
                location=location,
                city=normalize_city(query.city or location.split(",")[0]),
                country=query.country,
                work_mode=parse_work_mode(location),
                job_kind=parse_job_kind(clean_text(title_el.get_text(" "))) if "intern" in query.normalized_term.lower() else JobKind.JOB,
                date_posted=parse_date(posted_el.get("datetime") or posted_el.get_text(" ") if posted_el else ""),
                source_job_id=source_job_id,
                raw={"source_card": "linkedin"},
            )
        )
    return jobs

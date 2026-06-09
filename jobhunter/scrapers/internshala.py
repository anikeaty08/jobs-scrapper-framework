"""Internshala scraper for India-specific internships and fresher jobs."""

from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from jobhunter.models import Job, JobKind, SalaryPeriod
from jobhunter.query import JobQuery
from jobhunter.scrapers.base import BaseScraper
from jobhunter.utils.http import safe_get
from jobhunter.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_skills,
    normalize_url,
    parse_date,
    parse_money,
    parse_work_mode,
)


class InternshalaScraper(BaseScraper):
    source = "internshala"
    default_country = "India"

    def build_url(self, query: JobQuery) -> str:
        term = quote_plus(query.normalized_term.replace(" ", "-"))
        kind = "internships" if "intern" in query.normalized_term.lower() else "jobs"
        city = quote_plus((query.city or query.location).replace(" ", "-").lower())
        if city:
            return f"https://internshala.com/{kind}/{term}-in-{city}/"
        return f"https://internshala.com/{kind}/{term}/"

    def search(self, query: JobQuery) -> list[Job]:
        response = safe_get(self.session, self.build_url(query))
        if response is None or response.status_code != 200:
            return []
        return self.limit(parse_internshala_jobs(response.text, query), query)


def parse_internshala_jobs(html: str, query: JobQuery) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".individual_internship, .internship_meta")
    jobs: list[Job] = []
    for card in cards:
        title_el = card.select_one(".job-title-href, .profile, h3 a, h3")
        company_el = card.select_one(".company-name, .company_and_premium .company_name, .heading_6")
        if not title_el or not company_el:
            continue
        href = title_el.get("href", "")
        job_url = href if href.startswith("http") else f"https://internshala.com{href}"
        location_el = card.select_one(".locations, .location_link, .row-1-item.locations")
        stipend_el = card.select_one(".stipend, .salary")
        date_el = card.select_one(".status-success, .posted_by_container, .posted_by")
        skills = [item.get_text(" ") for item in card.select(".round_tabs_container span, .skill")]
        duration_el = card.select_one(".item_body.desktop-text, .duration")
        title = clean_text(title_el.get_text(" "))
        location = clean_text(location_el.get_text(" ")) if location_el else query.location
        stipend = parse_money(stipend_el.get_text(" ") if stipend_el else "")
        if stipend.has_value and stipend.period == SalaryPeriod.UNKNOWN:
            stipend = type(stipend)(stipend.min_amount, stipend.max_amount, stipend.currency, SalaryPeriod.MONTH, stipend.raw_text)
        jobs.append(
            Job(
                title=title,
                company=clean_text(company_el.get_text(" ")),
                source="internshala",
                job_url=normalize_url(job_url),
                location=location,
                city=normalize_city(query.city or location.split(",")[0]),
                country="India",
                work_mode=parse_work_mode(location),
                job_kind=JobKind.INTERNSHIP if "intern" in title.lower() or "intern" in query.normalized_term.lower() else JobKind.JOB,
                stipend=stipend,
                skills=normalize_skills(skills),
                date_posted=parse_date(date_el.get_text(" ") if date_el else ""),
                description=clean_text(card.get_text(" ")),
                raw={"duration": clean_text(duration_el.get_text(" ")) if duration_el else ""},
            )
        )
    return jobs

"""Unstop scraper for India-specific jobs, internships, and challenges."""

from __future__ import annotations

from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobhunter.models import Job
from jobhunter.query import JobQuery
from jobhunter.scrapers.base import BaseScraper
from jobhunter.utils.http import safe_get
from jobhunter.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_skills,
    normalize_url,
    parse_date,
    parse_job_kind,
    parse_money,
    parse_work_mode,
)


class UnstopScraper(BaseScraper):
    source = "unstop"
    default_country = "India"

    def build_url(self, query: JobQuery) -> str:
        params = {"searchTerm": query.normalized_term}
        return "https://unstop.com/jobs?" + urlencode({k: v for k, v in params.items() if v})

    def search(self, query: JobQuery) -> list[Job]:
        response = safe_get(self.session, self.build_url(query))
        if response is None or response.status_code != 200:
            return []
        return self.limit(parse_unstop_jobs(response.text, query), query)


def parse_unstop_jobs(html: str, query: JobQuery) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a[href*='/jobs/'], a[href*='/internships/'], a[href*='/competitions/'], .single_profile, .opportunity-card")
    jobs: list[Job] = []
    seen_urls: set[str] = set()
    for card in cards:
        link_el = card if card.name == "a" else card.select_one("a[href]")
        href = link_el.get("href", "") if link_el else ""
        if not href:
            continue
        job_url = href if href.startswith("http") else f"https://unstop.com{href}"
        job_url = normalize_url(job_url)
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)
        salary_el = card.select_one(".salary, .stipend, .prize")
        salary_text = clean_text(salary_el.get_text(" ")) if salary_el else ""
        text = clean_text(card.get_text(" "))
        if salary_text:
            text = clean_text(text.replace(salary_text, ""))
        if not text:
            continue
        parts = [part.strip() for part in text.split("|") if part.strip()]
        title = parts[0] if parts else text[:120]
        company = parts[1] if len(parts) > 1 else ""
        if not company:
            company_el = card.select_one(".company-name, .organisation, .org-name")
            company = clean_text(company_el.get_text(" ")) if company_el else "Unknown"
        location_el = card.select_one(".location, .seperate_box")
        deadline_el = card.select_one(".deadline, .date")
        jobs.append(
            Job(
                title=title,
                company=company,
                source="unstop",
                job_url=job_url,
                location=clean_text(location_el.get_text(" ")) if location_el else query.location,
                city=normalize_city(query.city),
                country="India",
                work_mode=parse_work_mode(text),
                job_kind=parse_job_kind(job_url + " " + title + " " + text),
                salary=parse_money(salary_text),
                stipend=parse_money(salary_text),
                skills=normalize_skills(query.skills),
                deadline=parse_date(deadline_el.get_text(" ") if deadline_el else ""),
                description=text,
                raw={"source_card": "unstop"},
            )
        )
    return jobs

"""Internshala scraper — SEO-route filtering + ?page=N pagination + fixed selectors.

Based on reverse engineering findings:
  - Job routes require "-jobs", e.g. /jobs/python-developer-jobs-in-bangalore/
  - Internship routes require "-internship", e.g. /internships/python-internship-in-mumbai/
  - Pagination works via the ?page=N query parameter
  - /internships_ajax/ JSON endpoint ignores page_no and location_list[] params
  - Skills live in .job_skill elements (not .round_tabs_container)
  - Date lives in .status-success or .posted_by_container
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from hirehunt.models import Job, JobKind, Money, SalaryPeriod, SourceCapabilities
from hirehunt.query import JobQuery
from hirehunt.scrapers.base import BaseScraper
from hirehunt.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_skills,
    normalize_url,
    parse_date,
    parse_money,
    parse_work_mode,
)

BASE_URL = "https://internshala.com"
MAX_PAGES = 100


def _slug(text: str) -> str:
    """Convert search text to Internshala URL slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")


def _search_slug(term: str, internship: bool) -> str:
    """Build the search segment used by Internshala's current SEO routes."""
    if internship:
        term = re.sub(r"\bintern(?:ship)?s?\b", " ", term, flags=re.I)
        suffix = "internship"
    else:
        term = re.sub(r"\bjobs?\b", " ", term, flags=re.I)
        suffix = "jobs"

    normalized = _slug(term)
    return f"{normalized}-{suffix}" if normalized else suffix


# Internshala uses different city names in URLs than common usage
_CITY_SLUG_ALIAS: dict[str, str] = {
    "bengaluru": "bangalore",
    "bengaluru urban": "bangalore",
    "new delhi": "delhi",
    "gurugram": "gurgaon",
    "mysuru": "mysore",
    "thiruvananthapuram": "trivandrum",
    "kochi": "cochin",
    "kolkata": "kolkata",
}

class InternshalaScraper(BaseScraper):
    source = "internshala"
    source_family = "regional"
    source_adapter = "internshala_html"
    source_tags = ("india", "jobs", "internships")
    default_country = "India"
    capabilities = SourceCapabilities(
        countries=("India",),
        job_kinds=(JobKind.JOB, JobKind.INTERNSHIP),
        supported_filters=frozenset({"city", "job_kind"}),
        pagination=True,
        exhaustive_search=True,
        description="Internshala jobs and internships",
    )

    def _is_internship_search(self, query: JobQuery) -> bool:
        term = query.normalized_term.lower()
        kind = query.job_kind or ""
        if isinstance(kind, (list, tuple)):
            kind = " ".join(kind)
        return bool(
            re.search(r"\bintern(?:ship)?s?\b", term)
            or re.search(r"\bintern(?:ship)?s?\b", str(kind).lower())
        )

    def build_url(self, query: JobQuery, page: int = 1) -> str:
        """Build paginated URL with city slug using centralized per-scraper city map."""
        from hirehunt.utils.normalization import city_for_scraper

        internship = self._is_internship_search(query)
        kind = "internships" if internship else "jobs"
        search_slug = _search_slug(query.normalized_term, internship)
        if query.city:
            city_slug = city_for_scraper(query.city, "internshala")
            base = f"{BASE_URL}/{kind}/{search_slug}-in-{city_slug}/"
        elif query.normalized_term:
            base = f"{BASE_URL}/{kind}/{search_slug}/"
        else:
            base = f"{BASE_URL}/{kind}/"
        return base if page == 1 else f"{base}?page={page}"

    def search(self, query: JobQuery) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str | tuple[str, str, str]] = set()
        page = 1

        while self.wants_more(jobs, query) and page <= MAX_PAGES:
            url = self.build_url(query, page)
            response = self.fetch(url)

            if response is None or response.status_code != 200:
                break

            batch = parse_internshala_jobs(response.text, query)
            if not batch:
                break

            new_jobs: list[Job] = []
            for job in batch:
                identity: str | tuple[str, str, str] = job.job_url or (
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
            page += 1

        return self.limit(jobs, query)


# ─────────────────────────────────────────────────────────────────────────────
# Parser — handles both full HTML pages and AJAX HTML fragments
# ─────────────────────────────────────────────────────────────────────────────

_MODE_RE = re.compile(r"\s*\((hybrid|remote|onsite|wfh|work\s*from\s*home)\)\s*$", re.I)


def _split_location(raw: str) -> tuple[str, str]:
    """Strip work-mode suffix from location string.
    Returns (clean_location, mode_hint)
    e.g. 'Gurgaon (Hybrid)' → ('Gurgaon', 'hybrid')
    """
    raw = clean_text(raw)
    m = _MODE_RE.search(raw)
    if m:
        return raw[: m.start()].strip(", "), m.group(1).lower()
    return raw, ""


def parse_internshala_jobs(html: str, query: JobQuery) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")

    # Primary: full page or AJAX fragment — both use this selector
    cards = soup.select("div[id^='individual_internship_'][internshipid]")
    if not cards:
        # Fallback for jobs endpoint variant
        cards = soup.select("div.individual_internship[data-href]")

    return [job for card in cards if (job := _parse_card(card, query)) is not None]


def _parse_card(card, query: JobQuery) -> Job | None:
    # ── Title ──────────────────────────────────────────────────────────────
    title_el = card.select_one("a.job-title-href")
    if not title_el:
        return None
    title = clean_text(title_el.get_text(" "))
    if not title:
        return None

    # ── Company (strip "Actively hiring" badge) ────────────────────────────
    company_el = card.select_one("p.company-name")
    company = clean_text(company_el.get_text(" ")) if company_el else ""
    company = re.sub(r"\s*Actively\s+hiring\s*$", "", company, flags=re.I).strip()

    # ── URL ────────────────────────────────────────────────────────────────
    href = title_el.get("href", "") or card.get("data-href", "")
    job_url = href if href.startswith("http") else f"{BASE_URL}{href}"
    job_url = normalize_url(job_url)

    # ── Location / City ────────────────────────────────────────────────────
    loc_el = card.select_one(".row-1-item.locations, .locations, .location_link")
    raw_location = clean_text(loc_el.get_text(" ")) if loc_el else ""
    clean_loc, mode_hint = _split_location(raw_location)

    # Extract city from location text (first part before comma)
    # WFH jobs: leave city empty so city-specific queries still see them
    wfh = any(w in clean_loc.lower() for w in ("work from home", "wfh", "remote"))
    city_text = "" if wfh else clean_loc.split(",")[0].strip()
    city = normalize_city(city_text) if city_text else ""

    # ── Work mode ──────────────────────────────────────────────────────────
    work_mode = parse_work_mode(raw_location)

    # ── Stipend / Salary ───────────────────────────────────────────────────
    stipend_el = card.select_one(".stipend, .salary, span.stipend")
    stipend = parse_money(stipend_el.get_text(" ") if stipend_el else "")
    if stipend.has_value and stipend.period == SalaryPeriod.UNKNOWN:
        stipend = Money(
            stipend.min_amount, stipend.max_amount,
            stipend.currency, SalaryPeriod.MONTH, stipend.raw_text,
        )

    # ── Skills (.job_skill confirmed from live page — 5 skills/card avg) ──
    skill_els = card.select(".job_skill")
    skills = normalize_skills([el.get_text(" ") for el in skill_els])

    # ── Date posted ────────────────────────────────────────────────────────
    date_el = card.select_one(".status-success, .posted_by_container, [class*='posted']")
    date_posted = parse_date(date_el.get_text(" ") if date_el else "")

    # ── Job kind ───────────────────────────────────────────────────────────
    if "intern" in title.lower() or "intern" in query.normalized_term.lower():
        job_kind = JobKind.INTERNSHIP
    elif "hackathon" in title.lower():
        job_kind = JobKind.HACKATHON
    elif "fellowship" in title.lower():
        job_kind = JobKind.FELLOWSHIP
    else:
        job_kind = JobKind.JOB

    # ── Duration ───────────────────────────────────────────────────────────
    duration_el = card.select_one(".item_body.desktop-text, .duration")
    duration = clean_text(duration_el.get_text(" ")) if duration_el else ""

    # ── Description ────────────────────────────────────────────────────────
    desc_el = card.select_one(".about_job .text, .about_job")
    description = clean_text(desc_el.get_text(" ")) if desc_el else clean_text(card.get_text(" "))

    return Job(
        title=title,
        company=company,
        source="internshala",
        job_url=job_url,
        location=raw_location,
        city=city,
        country="India",
        work_mode=work_mode,
        job_kind=job_kind,
        stipend=stipend,
        skills=skills,
        date_posted=date_posted,
        description=description,
        raw={"duration": duration},
    )

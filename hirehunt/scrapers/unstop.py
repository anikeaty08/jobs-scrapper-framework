"""Unstop scraper — uses confirmed API endpoint for hackathons & competitions.

Reverse engineering findings:
  - Endpoint: GET https://unstop.com/api/public/opportunity/search-result
  - NOTE: The API ALWAYS returns hackathons/competitions regardless of type params.
    This is by design — Unstop's public API is competition-focused.
    We embrace this and use it specifically for hackathons/competitions/challenges.
  - Pagination: page= + size= params, up to 1000 pages (10,000+ total)
  - Rich fields: id, title, organisation, required_skills, locations, end_date,
                 type, subtype, region, tags, prizes
  - URL: https://unstop.com/{public_url}
"""

from __future__ import annotations

import time

from hirehunt.models import Job, JobKind, Money, SourceCapabilities, WorkMode
from hirehunt.query import JobQuery
from hirehunt.scrapers.base import BaseScraper
from hirehunt.utils.normalization import (
    clean_text,
    normalize_city,
    normalize_skills,
    normalize_url,
    parse_date,
    parse_money,
)

_API = "https://unstop.com/api/public/opportunity/search-result"
_BASE = "https://unstop.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class UnstopScraper(BaseScraper):
    """Unstop — returns hackathons, competitions, and coding challenges via API."""
    source = "unstop"
    default_country = "India"
    capabilities = SourceCapabilities(
        countries=("India",),
        job_kinds=(JobKind.HACKATHON, JobKind.COMPETITION, JobKind.FELLOWSHIP),
        supported_filters=frozenset({"job_kind"}),
        pagination=True,
        exhaustive_search=True,
        description="Unstop opportunities API",
    )

    def build_url(self, query: JobQuery) -> str:
        return _BASE + "/hackathons"

    def search(self, query: JobQuery) -> list[Job]:
        jobs: list[Job] = []
        page = 1
        page_size = 20

        while self.wants_more(jobs, query):
            params: dict = {
                "page":    page,
                "size":    page_size,
            }
            # Add keyword search if term specified
            term = query.normalized_term.strip()
            if term:
                params["keyword"] = term

            resp = self.get_json(
                _API,
                params=params,
                headers={
                    "User-Agent": _UA,
                    "Accept":     "application/json",
                    "Referer":    "https://unstop.com/hackathons",
                },
            )
            if not resp or resp.status_code != 200:
                break

            try:
                import json
                data = json.loads(resp.text)
            except Exception:
                break

            wrapper = data.get("data") or {}
            items   = wrapper.get("data") or []
            last_page = wrapper.get("last_page", 1)

            if not items:
                break

            for item in items:
                job = _parse_unstop_item(item, query)
                if job:
                    jobs.append(job)

            if page >= last_page:
                break

            page += 1
            time.sleep(0.3)

        return self.limit(jobs, query)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_unstop_item(item: dict, query: JobQuery) -> Job | None:
    title = clean_text(item.get("title") or "")
    if not title:
        return None

    # Organisation
    org = item.get("organisation") or {}
    if isinstance(org, dict):
        company = clean_text(org.get("name") or org.get("org_name") or "Unstop")
    else:
        company = clean_text(str(org)) or "Unstop"

    # URL
    public_url = item.get("public_url") or item.get("seo_url") or ""
    job_url    = f"{_BASE}/{public_url}" if public_url else _BASE
    job_url    = normalize_url(job_url)

    # Location
    locs = item.get("locations") or []
    region = item.get("region") or ""
    if locs and isinstance(locs, list):
        loc_names = []
        for l in locs:
            if isinstance(l, dict):
                loc_names.append(l.get("city") or l.get("name") or l.get("country") or "")
            elif isinstance(l, str):
                loc_names.append(l)
        raw_location = ", ".join(filter(None, loc_names))
    elif region and region.lower() == "online":
        raw_location = "Online"
    else:
        raw_location = region or query.location or ""

    city = normalize_city(raw_location.split(",")[0] if raw_location else query.city)

    # Work mode
    is_online = region == "online" or "online" in raw_location.lower()
    work_mode = WorkMode.REMOTE if is_online else WorkMode.UNKNOWN

    # Skills
    skills_raw = item.get("required_skills") or []
    if isinstance(skills_raw, list):
        skill_names = [
            s.get("name") or s.get("skill") or str(s)
            for s in skills_raw if s
        ]
    elif isinstance(skills_raw, str):
        skill_names = [skills_raw]
    else:
        skill_names = []
    skills = normalize_skills(skill_names)

    # Prize money (treat as salary for hackathons)
    prizes = item.get("prizes") or []
    prize_text = ""
    if isinstance(prizes, list) and prizes:
        first = prizes[0]
        if isinstance(first, dict):
            prize_text = str(first.get("amount") or first.get("prize") or "")
    salary = parse_money(prize_text) if prize_text else Money()

    # Deadline / date
    end_date    = parse_date(item.get("end_date") or "")
    posted_date = parse_date(item.get("approved_date") or item.get("updated_at") or "")

    # Job kind from type/subtype
    item_type    = (item.get("type") or "").lower()
    item_subtype = (item.get("subtype") or "").lower()
    if "hackathon" in item_type or "coding" in item_subtype:
        job_kind = JobKind.HACKATHON
    elif "competition" in item_type or "competition" in item_subtype:
        job_kind = JobKind.COMPETITION
    elif "fellowship" in item_type or "fellowship" in item_subtype:
        job_kind = JobKind.FELLOWSHIP
    else:
        job_kind = JobKind.COMPETITION

    # Tags → extra context
    tags = item.get("tags") or []
    tag_names = [t.get("name") or t if isinstance(t, (str, dict)) else "" for t in tags]
    description = f"Type: {item_type} | Tags: {', '.join(str(t) for t in tag_names[:5])}"

    return Job(
        title        = title,
        company      = company,
        source       = "unstop",
        job_url      = job_url,
        location     = raw_location,
        city         = city,
        country      = "India",
        work_mode    = work_mode,
        job_kind     = job_kind,
        salary       = salary,
        stipend      = salary,
        skills       = skills,
        deadline     = end_date,
        date_posted  = posted_date,
        description  = description,
        source_job_id= str(item.get("id") or ""),
        raw          = {"type": item_type, "subtype": item_subtype},
    )


def parse_unstop_item(item: dict, query: JobQuery) -> Job | None:
    """Public parser helper used by tests and fixture validation."""
    return _parse_unstop_item(item, query)

"""Normalization helpers for job search data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import parse_qs, urlparse, urlunparse
import re

from dateutil import parser as dateparser

from jobhunter.models import JobKind, Money, SalaryPeriod, WorkMode


CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
}


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_city(city: str | None) -> str:
    value = clean_text(city).strip(", ")
    if not value:
        return ""
    lowered = value.lower()
    return CITY_ALIASES.get(lowered, value.title() if value.islower() else value)


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    kept_query = []
    for key in sorted(query):
        if key.lower().startswith("utm_") or key.lower() in {"ref", "trk"}:
            continue
        for value in query[key]:
            kept_query.append(f"{key}={value}")
    normalized = parsed._replace(
        scheme=parsed.scheme.lower() or "https",
        netloc=parsed.netloc.lower(),
        query="&".join(kept_query),
        fragment="",
    )
    return urlunparse(normalized).rstrip("/")


def parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    text = clean_text(date_str).lower()
    now = datetime.now(timezone.utc)
    if text in {"today", "just now"} or "just posted" in text:
        return now.date().isoformat()
    if "yesterday" in text:
        return (now - timedelta(days=1)).date().isoformat()
    match = re.search(r"(\d+)\s*(hour|day|week|month|year)s?\s+ago", text)
    if match:
        count = int(match.group(1))
        unit = match.group(2)
        days = {"hour": 0, "day": count, "week": count * 7, "month": count * 30, "year": count * 365}[unit]
        return (now - timedelta(days=days)).date().isoformat()
    try:
        parsed = dateparser.parse(date_str, fuzzy=True)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.date().isoformat() if parsed else None


def parse_experience(text: str | None) -> tuple[float | None, float | None, str]:
    raw = clean_text(text)
    if not raw:
        return None, None, ""
    lowered = raw.lower()
    if any(marker in lowered for marker in ("fresher", "entry level", "no experience", "0 year")):
        return 0, 1, raw
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:year|yr)", lowered)
    if match:
        return float(match.group(1)), float(match.group(2)), raw
    match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:year|yr)", lowered)
    if match:
        start = float(match.group(1))
        return start, None, raw
    return None, None, raw


def parse_work_mode(text: str | None) -> WorkMode:
    lowered = clean_text(text).lower()
    if any(marker in lowered for marker in ("work from home", "remote")):
        return WorkMode.REMOTE
    if "hybrid" in lowered:
        return WorkMode.HYBRID
    if any(marker in lowered for marker in ("onsite", "on-site", "office")):
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def parse_job_kind(text: str | None) -> JobKind:
    lowered = clean_text(text).lower()
    if "intern" in lowered:
        return JobKind.INTERNSHIP
    if "hackathon" in lowered:
        return JobKind.HACKATHON
    if "competition" in lowered or "challenge" in lowered:
        return JobKind.COMPETITION
    if "fellowship" in lowered:
        return JobKind.FELLOWSHIP
    if lowered:
        return JobKind.JOB
    return JobKind.UNKNOWN


def parse_money(text: str | None, default_currency: str = "INR") -> Money:
    raw = clean_text(text)
    if not raw:
        return Money(currency=default_currency)
    lowered = raw.lower()
    currency = default_currency
    if "$" in raw or "usd" in lowered:
        currency = "USD"
    elif "€" in raw or "eur" in lowered:
        currency = "EUR"
    elif "£" in raw or "gbp" in lowered:
        currency = "GBP"
    elif "₹" in raw or "inr" in lowered or "lpa" in lowered or "lac" in lowered:
        currency = "INR"

    period = SalaryPeriod.UNKNOWN
    if any(marker in lowered for marker in ("per month", "/month", "monthly", "pm")):
        period = SalaryPeriod.MONTH
    elif any(marker in lowered for marker in ("per annum", "per year", "/year", "yearly", "lpa", "pa")):
        period = SalaryPeriod.YEAR
    elif any(marker in lowered for marker in ("per hour", "/hour", "hourly")):
        period = SalaryPeriod.HOUR

    numbers = re.findall(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(lpa|lac|lakh|k)?", lowered)
    shared_lakh_suffix = any(marker in lowered for marker in ("lpa", "lac", "lakh"))
    amounts: list[float] = []
    for value, suffix in numbers:
        amount = float(value.replace(",", ""))
        if suffix == "k":
            amount *= 1000
        elif suffix in {"lpa", "lac", "lakh"} or shared_lakh_suffix:
            amount *= 100000
            period = SalaryPeriod.YEAR
            currency = "INR"
        amounts.append(amount)
    if not amounts:
        return Money(currency=currency, period=period, raw_text=raw)
    if len(amounts) == 1:
        return Money(min_amount=amounts[0], max_amount=amounts[0], currency=currency, period=period, raw_text=raw)
    return Money(min_amount=min(amounts), max_amount=max(amounts), currency=currency, period=period, raw_text=raw)


def normalize_skills(skills: list[str] | str | None) -> list[str]:
    if not skills:
        return []
    if isinstance(skills, str):
        parts = re.split(r"[,;/|]", skills)
    else:
        parts = skills
    seen = set()
    normalized = []
    for skill in parts:
        value = clean_text(skill).lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized

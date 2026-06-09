# 🎯 HireHunt

**A programmable job-scraping framework for India & global markets.**  
Aggregate jobs from **12 sources** — Naukri, Internshala, Shine, LinkedIn, Indeed, and FAANG companies — into a unified, filterable, ranked dataset.

---

## ✨ Sources

| Source | Region | Type | Method |
|---|---|---|---|
| `naukri` | 🇮🇳 India | Jobs | REST API — 15,000+ listings |
| `shine` | 🇮🇳 India | Jobs | SSR JSON — 17,000+ listings |
| `internshala` | 🇮🇳 India | Internships / Jobs | HTML scraping |
| `unstop` | 🇮🇳 India | Hackathons / Competitions | REST API |
| `linkedin` | 🌍 Global | Jobs | Guest HTML API |
| `indeed` | 🌍 Global | Jobs | GraphQL API |
| `google_careers` | 🌍 FAANG | Jobs | LinkedIn (company-filtered) |
| `amazon` | 🌍 FAANG | Jobs | REST API |
| `meta` | 🌍 FAANG | Jobs | LinkedIn (company-filtered) |
| `apple` | 🌍 FAANG | Jobs | LinkedIn (keyword search) |
| `netflix` | 🌍 FAANG | Jobs | LinkedIn (company-filtered) |
| `microsoft` | 🌍 FAANG | Jobs | LinkedIn (company-filtered) |

---

## 📦 Installation

```bash
pip install hirehunt
```

> **Note:** The PyPI package is `hirehunt`. The import name is `jobhunter`.
> ```python
> import jobhunter   # ← this is correct after pip install hirehunt
> ```

**Requirements:** Python 3.10+

---

## ⚡ Quick Start

### Python API

```python
from jobhunter import scrape_jobs

# Search across India's top job boards
jobs = scrape_jobs(
    search_term="python developer",
    sources=["naukri", "shine", "internshala"],
    city="Bengaluru",
    results_wanted=50,
)

for job in jobs:
    print(job)
# Python Developer @ TCS | Bengaluru | naukri
# Python Developer @ Infosys | Bengaluru | shine
```

### CLI

```bash
# India job search
jobhunter search "data scientist" --city Mumbai --sources naukri,shine

# Hackathons & competitions
jobhunter search "hackathon" --sources unstop

# FAANG company jobs
jobhunter search "software engineer" --sources google_careers,amazon,netflix

# Export to CSV
jobhunter search "backend developer" --sources naukri,linkedin --output jobs.csv

# Top 20 ranked results
jobhunter search "machine learning" --sources naukri,shine,linkedin --top 20
```

---

## 🔧 Python API Reference

### `scrape_jobs()`

```python
from jobhunter import scrape_jobs

jobs = scrape_jobs(
    search_term="python developer",   # What to search
    sources=["naukri", "shine"],      # Which sources (list or "auto")
    city="Bengaluru",                 # City filter (optional)
    location="India",                 # Broader location (optional)
    country="India",                  # Country (optional)
    results_wanted=50,                # Max results per source
    job_kind="job",                   # "job", "internship", "hackathon"
    remote=None,                      # True = remote only
    salary_min=500000,                # Min salary in INR (optional)
    posted_within_days=30,            # Only jobs from last N days
    skills=["python", "django"],      # Skill filter (optional)
    experience_min=0,                 # Min years experience (optional)
    experience_max=5,                 # Max years experience (optional)
)
```

### `Job` Object

Every source returns the same normalized `Job` dataclass:

```python
@dataclass
class Job:
    title: str
    company: str
    source: str
    job_url: str

    location: str
    city: str
    country: str
    work_mode: WorkMode         # "remote" | "hybrid" | "onsite" | "unknown"
    job_kind: JobKind           # "job" | "internship" | "hackathon" | "competition"

    salary: Money               # min_amount, max_amount, currency, period
    stipend: Money

    skills: list[str]
    experience_min: float | None
    experience_max: float | None
    description: str
    date_posted: str | None
    deadline: str | None        # for competitions/hackathons

    match_score: float          # 0.0–1.0 after ranking
```

### Export

```python
from jobhunter import scrape_jobs
from jobhunter.exporters import to_csv, to_json, to_dataframe

jobs = scrape_jobs("python developer", sources=["naukri", "shine"])

to_csv(jobs, "jobs.csv")
to_json(jobs, "jobs.json")
df = to_dataframe(jobs)   # pandas DataFrame
```

---

## 🏗️ Project Structure

```
jobhunter/
├── __init__.py          # scrape_jobs() entry point
├── models.py            # Job, Money, WorkMode, JobKind dataclasses
├── query.py             # JobQuery — unified search parameters
├── engine.py            # Orchestrates parallel scraping + dedup
├── registry.py          # Scraper registry + auto-source selection
├── filtering.py         # Soft filtering (salary, city, skills, date)
├── ranking.py           # Relevance scoring / match_score
├── validation.py        # Input validation
├── exceptions.py        # Custom exceptions
├── cli.py               # `jobhunter` CLI entry point
│
├── scrapers/
│   ├── base.py          # BaseScraper ABC
│   ├── naukri.py        # 🇮🇳 Naukri — /jobapi/v2/search REST API
│   ├── shine.py         # 🇮🇳 Shine — __NEXT_DATA__ SSR JSON
│   ├── internshala.py   # 🇮🇳 Internshala — HTML + pagination
│   ├── unstop.py        # 🇮🇳 Unstop — hackathons REST API
│   ├── linkedin.py      # 🌍 LinkedIn — guest HTML API
│   ├── indeed.py        # 🌍 Indeed — GraphQL API
│   └── faang.py         # 🌍 Google, Amazon, Meta, Apple, Netflix, Microsoft
│
├── exporters/
│   ├── csv_exporter.py
│   ├── json_exporter.py
│   └── dataframe.py
│
└── utils/
    ├── fetchers.py      # CachedFetcher with proxy + backend support
    └── normalization.py # clean_text, parse_money, normalize_city, ...

tests/
```

---

## 🔍 Source Details

### 🇮🇳 Naukri
- **Endpoint:** `GET https://www.naukri.com/jobapi/v2/search`
- **Auth:** Session cookies from page warm-up (automatic)
- **Fields:** Title, company, salary (LPA), location, skills, experience, date
- **Pagination:** `pageNo=N`, 20 results/page, 3,000+ pages available

### 🇮🇳 Shine
- **Endpoint:** `__NEXT_DATA__` SSR JSON embedded in HTML
- **Fields:** `jJT` (title), `jCName` (company), `jSal` (salary), `jLoc` (location), `jKwd` (skills), `jPDate` (date), `jSlug` (URL)
- **Pagination:** `?page=N`, 20 results/page, 900+ pages

### 🇮🇳 Internshala
- **Endpoint:** HTML scraping — `div[id^='individual_internship_'][internshipid]`
- **Pagination:** `?page=N`, 40+ cards/page
- **City filter:** URL slug e.g. `/internships/python-intern-in-bengaluru/`

### 🇮🇳 Unstop
- **Endpoint:** `GET https://unstop.com/api/public/opportunity/search-result`
- **Note:** Returns hackathons, coding competitions, and challenges only
- **Fields:** Title, organisation, skills, location, deadline, prize

### 🌍 Indeed
- **Endpoint:** `POST https://apis.indeed.com/graphql`
- **Auth:** Public API key (included)
- **Pagination:** Cursor-based

### 🌍 LinkedIn
- **Endpoint:** `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`
- **Auth:** None — guest API
- **FAANG filter:** `f_C` company ID parameter

### 🌍 Amazon
- **Endpoint:** `GET https://www.amazon.jobs/en/search.json`
- **Auth:** None — public REST API

---

## ⚙️ Filtering

Filters are **soft by default** — jobs missing a field pass through rather than being dropped:

```python
jobs = scrape_jobs(
    "python developer",
    sources=["naukri", "shine"],
    salary_min=600_000,        # Only applied if salary data exists
    city="Bengaluru",          # Only applied if location data exists
    skills=["python", "sql"],  # Only applied if skills data exists
    posted_within_days=14,     # Only applied if date data exists
)
```

---

## 🚀 Advanced Usage

### FAANG-only search

```python
from jobhunter import scrape_jobs
from jobhunter.registry import default_registry

registry = default_registry()
faang = registry.faang_sources()  # ['google_careers', 'amazon', 'meta', 'apple', 'netflix', 'microsoft']

jobs = scrape_jobs(
    search_term="software engineer",
    sources=faang,
    results_wanted=20,
)
```

### Parallel scraping with custom config

```python
jobs = scrape_jobs(
    search_term="backend developer",
    sources=["naukri", "shine", "linkedin"],
    city="Hyderabad",
    results_wanted=100,
    posted_within_days=7,
    cache_enabled=True,        # Cache responses locally
    proxies=["http://..."],    # Optional proxy list
)
```

### Auto-source selection

```python
# Automatically picks India sources when country="India"
jobs = scrape_jobs(
    search_term="python developer",
    country="India",
    sources="auto",  # → [indeed, linkedin, internshala, naukri, shine, unstop]
)
```

---

## 🧪 Running Tests

```bash
pip install -e .
pytest tests/
```

---

## 📄 License

MIT

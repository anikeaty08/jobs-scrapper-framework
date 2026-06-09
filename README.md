# JobHunter

JobHunter is a programmable job search framework. It is not a JobSpy clone: scraping is only the collection layer. The framework also normalizes, filters, deduplicates, ranks, explains, and exports jobs.

The design goal is global coverage with regional intelligence. The first built-in sources are LinkedIn, Indeed, Internshala, and Unstop. The model treats `city` as a first-class field and keeps jobs unique by canonical URL, source job ID, or normalized title/company/city fallback.

## Install

```powershell
pip install -e .
```

or install dependencies directly:

```powershell
pip install -r requirements.txt
```

## Python Usage

```python
from jobhunter import search_jobs

result = search_jobs(
    role="software engineer intern",
    country="India",
    city="Bengaluru",
    skills=["python", "react"],
    exclude=["sales", "marketing"],
    remote=True,
    fresher=True,
    sources=["internshala", "unstop", "indeed", "linkedin"],
    results_wanted=50,
)

for job in result.top(10):
    print(job.match_score, job.title, job.company, job.city, job.job_url)
```

## CLI Usage

```powershell
jobhunter search "backend engineer intern" --country India --city Bengaluru --skill python --skill fastapi --remote --fresher --csv jobs.csv
```

Validate live source fetch + parser behavior with request-based fetching:

```powershell
python -m jobhunter.cli validate "python intern" --country India --city Bengaluru --source internshala --source unstop --source indeed --source linkedin --limit 5 --cache --report live-validation.json
```

## Framework Layers

- Source layer: one scraper module per source.
- Query layer: one user-facing `JobQuery` translated by each source.
- Normalization layer: city aliases, salary/stipend parsing, work mode, job kind, skills, dates.
- Filter layer: city, country, skills, remote, fresher, salary, stipend, date, exclusions.
- Uniqueness layer: canonical URL, source IDs, and normalized fallback identity.
- Ranking layer: match score, reasons, warnings.
- Cache layer: saves fetched HTML for repeatable parser debugging.
- Export layer: DataFrame, CSV, JSON.

## Built-In Sources

| Source | Scope | Notes |
| --- | --- | --- |
| LinkedIn | Global | Public job search pages; detail fetch is intentionally not aggressive. |
| Indeed | Global/India | Uses Indeed host selection for India vs global searches. |
| Internshala | India | Internships and fresher jobs with stipend support. |
| Unstop | India | Jobs, internships, competitions, hackathons, and challenges. |

## Architecture

```text
jobhunter/
  engine.py              # orchestration
  query.py               # user-facing query model
  models.py              # normalized jobs and results
  registry.py            # pluggable source registry
  filtering.py           # post-scrape filters
  ranking.py             # score + explainability
  scrapers/
    base.py
    indeed.py
    linkedin.py
    internshala.py
    unstop.py
  utils/
    normalization.py
    dedupe.py
    http.py
    cache.py
    fetchers.py
  exporters/
    csv.py
    json.py
    dataframe.py
```

## Adding A Source

Create a scraper that implements the base contract:

```python
from jobhunter.scrapers.base import BaseScraper

class MyBoardScraper(BaseScraper):
    source = "myboard"

    def search(self, query):
        return []
```

Then register it:

```python
from jobhunter.registry import ScraperRegistry

registry = ScraperRegistry()
registry.register(MyBoardScraper)
```

## Testing

The unit tests use parser fixtures and mocked scrapers, so they do not depend on live websites:

```powershell
python -m unittest discover -s tests
```

Live websites change often and may block automated requests. The framework is structured so parser fixes are isolated to individual source modules.

Current v0.2 tests cover normalization, parser fixtures, dedupe, city/remote/skill/exclude/salary/stipend/fresher/date filters, async search, cache round trips, and profile-aware ranking.

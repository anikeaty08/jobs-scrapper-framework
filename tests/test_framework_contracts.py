import json
import unittest
from pathlib import Path

from hirehunt import JOB_SCHEMA_VERSION
from hirehunt.engine import SearchEngine
from hirehunt.models import CompletionStatus, Job, SourceDefinition
from hirehunt.models import ScrapeResult, SourceStats
from hirehunt.policies import DedupeOutcome, FilterOutcome, RequestPolicy, SearchPolicies
from hirehunt.query import JobQuery
from hirehunt.registry import ScraperRegistry, default_registry
from hirehunt.scrapers.base import BaseScraper
from hirehunt.scrapers.indeed import parse_indeed_job
from hirehunt.scrapers.internshala import parse_internshala_jobs
from hirehunt.scrapers.linkedin import parse_linkedin_jobs
from hirehunt.scrapers.naukri import _parse_naukri_job
from hirehunt.scrapers.shine import _parse_shine_item
from hirehunt.scrapers.unstop import parse_unstop_item
from hirehunt.utils.http import safe_get
from hirehunt.validation import (
    HealthThresholds,
    SourceBenchmark,
    SourceValidation,
    evaluate_benchmark_health,
    evaluate_validation_health,
)


FIXTURES = Path(__file__).parent / "fixtures"


class TwoJobScraper(BaseScraper):
    source = "two"
    source_family = "fixture"

    def search(self, query):
        return [
            Job("Python Developer", "Acme", self.source, "https://example.com/1", city="Bengaluru"),
            Job("Sales Manager", "Beta", self.source, "https://example.com/2", city="Mumbai"),
        ]


class FailingScraper(BaseScraper):
    source = "failing"

    def search(self, query):
        raise RuntimeError("fixture failure")


class KeepAllFilter:
    def apply(self, jobs, query):
        return FilterOutcome(list(jobs))


class NoDedupe:
    def apply(self, jobs, query):
        return DedupeOutcome(list(jobs))


class ReverseRank:
    def rank(self, jobs, query):
        return list(reversed(jobs))


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, source, key):
        return self.values.get((source, key))

    def set(self, source, key, content, status_code=200):
        self.values[(source, key)] = content


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class RetrySession:
    def __init__(self):
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return FakeResponse(503 if self.calls == 1 else 200)


class FrameworkContractTests(unittest.TestCase):
    def test_all_builtin_sources_declare_capabilities(self):
        capabilities = default_registry().capabilities()
        self.assertEqual(set(capabilities), set(default_registry().names()))
        for capability in capabilities.values():
            self.assertTrue(capability.description)
            self.assertIsInstance(capability.supported_filters, frozenset)

    def test_all_builtin_sources_declare_source_definitions(self):
        definitions = default_registry().definitions()
        self.assertEqual(set(definitions), set(default_registry().names()))
        for definition in definitions.values():
            self.assertIsInstance(definition, SourceDefinition)
            self.assertTrue(definition.family)
            self.assertTrue(definition.adapter)
            self.assertTrue(definition.capabilities.description)

    def test_registry_expands_source_families(self):
        registry = default_registry()
        self.assertIn("linkedin", registry.expand_sources(["aggregator"]))
        self.assertIn("indeed", registry.expand_sources(["aggregator"]))
        self.assertIn("amazon", registry.expand_sources(["company"]))

    def test_registry_can_register_configured_sources(self):
        registry = ScraperRegistry()
        registry.register_configured_source(
            TwoJobScraper,
            source="tenant_one",
            family="workday",
            aliases=("tenant-1",),
            config={"tenant": "tenant-one"},
        )

        definition = registry.definition("tenant-1")
        self.assertEqual(definition.family, "workday")
        self.assertEqual(definition.config["tenant"], "tenant-one")
        self.assertEqual(registry.family_sources("workday"), ["tenant_one"])

    def test_result_diagnostics_and_partial_failure(self):
        registry = ScraperRegistry()
        registry.register(TwoJobScraper)
        registry.register(FailingScraper)
        with self.assertLogs("hirehunt.engine", level="ERROR"):
            result = SearchEngine(registry=registry).search(
                JobQuery(
                    search_term="python",
                    city="Bengaluru",
                    sources=["two", "failing"],
                    results_wanted=10,
                )
            )

        self.assertTrue(result.partial)
        self.assertEqual(result.stats["failing"].completion, CompletionStatus.FAILED)
        self.assertEqual(result.stats["two"].filter_reasons["city_mismatch"], 1)
        self.assertEqual(result.stats["two"].kept, 1)

    def test_custom_cache_backend_is_supported(self):
        cache = MemoryCache()
        url = "https://example.com/cached"
        cache.set("two", url, "<html>fixture</html>")
        scraper = TwoJobScraper(cache_enabled=True, cache_backend=cache)

        response = scraper.fetch(url)

        self.assertTrue(response.from_cache)
        self.assertEqual(response.text, "<html>fixture</html>")

    def test_custom_search_policies_are_injected(self):
        registry = ScraperRegistry()
        registry.register(TwoJobScraper)
        policies = SearchPolicies(
            filtering=KeepAllFilter(),
            deduplication=NoDedupe(),
            ranking=ReverseRank(),
        )
        result = SearchEngine(registry=registry, policies=policies).search(
            JobQuery(search_term="python", sources=["two"])
        )
        self.assertEqual([job.company for job in result.jobs], ["Beta", "Acme"])

    def test_schema_version_is_exported(self):
        job = Job("Developer", "Acme", "mock", "https://example.com")
        self.assertEqual(job.to_dict()["schema_version"], JOB_SCHEMA_VERSION)

    def test_job_string_includes_url(self):
        job = Job("Developer", "Acme", "mock", "https://example.com/job", city="Bengaluru")
        self.assertEqual(
            str(job),
            "Developer @ Acme | Bengaluru | mock | https://example.com/job",
        )

    def test_existing_positional_model_construction_remains_valid(self):
        stats = SourceStats(2, 1, 0, 0)
        result = ScrapeResult([], {}, {"mock": stats}, [])
        self.assertEqual(result.stats["mock"].found, 2)
        self.assertEqual(result.stats["mock"].kept, 1)

    def test_request_policy_retries_configured_statuses(self):
        session = RetrySession()
        sleeps = []
        response = safe_get(
            session,
            "https://example.com",
            policy=RequestPolicy(retries=2, sleep=sleeps.append),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.calls, 2)
        self.assertEqual(len(sleeps), 1)

    def test_query_company_and_family_select_sources(self):
        registry = ScraperRegistry()
        registry.register(TwoJobScraper)

        result = SearchEngine(registry=registry).search(
            JobQuery(search_term="python", company="Acme", source_family="fixture")
        )

        self.assertEqual([job.company for job in result.jobs], ["Acme"])
        self.assertEqual(result.selected_sources, ["two"])

    def test_fixture_parsers_follow_job_contract(self):
        query = JobQuery(search_term="backend developer", city="Bengaluru", country="India")
        items = json.loads((FIXTURES / "source_items.json").read_text(encoding="utf-8"))
        jobs = [
            parse_internshala_jobs(
                (FIXTURES / "internshala_search.html").read_text(encoding="utf-8"),
                JobQuery(search_term="python intern", city="Bengaluru"),
            )[0],
            parse_linkedin_jobs(
                (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8"),
                query,
            )[0],
            _parse_naukri_job(items["naukri"], query),
            _parse_shine_item(items["shine"], query),
            parse_unstop_item(items["unstop"], query),
            parse_indeed_job(items["indeed"], query),
        ]

        for job in jobs:
            self.assertIsNotNone(job)
            self.assertTrue(job.title)
            self.assertTrue(job.source)
            self.assertTrue(job.job_url)

    def test_validation_health_flags_empty_sources(self):
        results = [SourceValidation(source="linkedin", status_code=200, fetched=True, parsed_count=0)]
        issues = evaluate_validation_health(results, HealthThresholds(min_parsed=1, max_failures=0))
        self.assertTrue(any(issue.code == "parsed_below_minimum" for issue in issues))

    def test_benchmark_health_flags_unexpected_completion(self):
        results = [
            SourceBenchmark(
                source="linkedin",
                parsed_count=0,
                completion=CompletionStatus.FAILED,
                completion_reason="blocked",
                error="blocked",
            )
        ]
        issues = evaluate_benchmark_health(results, HealthThresholds(min_parsed=1))
        self.assertTrue(any(issue.code == "unexpected_completion" for issue in issues))


if __name__ == "__main__":
    unittest.main()

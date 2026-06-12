import asyncio
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import hirehunt
from hirehunt.cli import main
from hirehunt.engine import SearchEngine
from hirehunt.models import Job, WorkMode
from hirehunt.query import JobProfile, JobQuery
from hirehunt.ranking import rank_jobs
from hirehunt.registry import ScraperRegistry
from hirehunt.registry import default_registry
from hirehunt.scrapers.base import BaseScraper
from hirehunt.utils.cache import PageCache


class MockScraper(BaseScraper):
    source = "mock"

    def search(self, query):
        return [
            Job(
                "Python Backend Intern",
                "Acme",
                "mock",
                "https://example.com/1",
                city=query.city,
                country=query.country,
                skills=["python", "fastapi"],
                work_mode=WorkMode.REMOTE,
                experience_min=0,
            )
        ]


class V02FeatureTests(unittest.TestCase):
    def test_public_version_is_exposed(self):
        self.assertTrue(hirehunt.__version__)

    def test_cli_validate_strict_exits_on_health_failure(self):
        buffer = io.StringIO()
        with patch("hirehunt.cli.validate_sources") as validate_sources:
            validate_sources.return_value = []
            with redirect_stdout(buffer):
                code = main(["validate", "python developer", "--strict"])
        self.assertEqual(code, 1)
        self.assertIn("Health issues:", buffer.getvalue())

    def test_auto_sources_only_include_unstop_for_opportunity_searches(self):
        registry = default_registry()
        job_sources = registry.auto_sources("India", search_term="software developer")
        opportunity_sources = registry.auto_sources("India", search_term="coding hackathon")

        self.assertNotIn("unstop", job_sources)
        self.assertIn("unstop", opportunity_sources)

    def test_page_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = PageCache(tmp)
            cache.set("mock", "https://example.com/jobs", "<html>ok</html>")
            self.assertEqual(cache.get("mock", "https://example.com/jobs"), "<html>ok</html>")

    def test_zero_or_none_result_limit_is_uncapped(self):
        scraper = MockScraper()
        jobs = [
            Job("One", "Acme", "mock", "https://example.com/1"),
            Job("Two", "Acme", "mock", "https://example.com/2"),
        ]

        self.assertTrue(scraper.wants_more(jobs, JobQuery(results_wanted=0)))
        self.assertTrue(scraper.wants_more(jobs, JobQuery(results_wanted=None)))
        self.assertEqual(scraper.limit(jobs, JobQuery(results_wanted=0)), jobs)
        self.assertEqual(scraper.limit(jobs, JobQuery(results_wanted=None)), jobs)

    def test_async_search_path(self):
        registry = ScraperRegistry()
        registry.register(MockScraper)
        result = asyncio.run(
            SearchEngine(registry=registry).search_async(
                JobQuery(role="python intern", city="Bengaluru", country="India", sources=["mock"])
            )
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].city, "Bengaluru")

    def test_profile_ranking_adds_reasons(self):
        query = JobQuery(
            role="backend intern",
            city="Bengaluru",
            profile=JobProfile(
                skills=["python", "fastapi"],
                preferred_titles=["backend"],
                preferred_cities=["Bengaluru"],
                remote_preferred=True,
                fresher=True,
            ),
        )
        jobs = [
            Job(
                "Python Backend Intern",
                "Acme",
                "mock",
                "https://example.com/1",
                city="Bengaluru",
                skills=["python", "fastapi"],
                work_mode=WorkMode.REMOTE,
                experience_min=0,
            )
        ]
        ranked = rank_jobs(jobs, query)
        self.assertGreater(ranked[0].match_score, 50)
        self.assertTrue(any("profile" in reason for reason in ranked[0].reasons))


if __name__ == "__main__":
    unittest.main()

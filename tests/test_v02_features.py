import asyncio
import tempfile
import unittest

from jobhunter.engine import SearchEngine
from jobhunter.models import Job, WorkMode
from jobhunter.query import JobProfile, JobQuery
from jobhunter.ranking import rank_jobs
from jobhunter.registry import ScraperRegistry
from jobhunter.scrapers.base import BaseScraper
from jobhunter.utils.cache import PageCache


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
    def test_page_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = PageCache(tmp)
            cache.set("mock", "https://example.com/jobs", "<html>ok</html>")
            self.assertEqual(cache.get("mock", "https://example.com/jobs"), "<html>ok</html>")

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

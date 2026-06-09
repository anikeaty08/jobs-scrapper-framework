import unittest

from jobhunter.filtering import filter_jobs
from jobhunter.models import Job, WorkMode
from jobhunter.query import JobQuery
from jobhunter.ranking import rank_jobs
from jobhunter.utils.dedupe import deduplicate_jobs


class DedupeFilterRankTests(unittest.TestCase):
    def test_duplicate_urls_are_removed(self):
        jobs = [
            Job("Backend Intern", "Acme", "indeed", "https://example.com/job?utm_source=x", city="Bengaluru"),
            Job("Backend Intern", "Acme", "linkedin", "https://example.com/job", city="Bengaluru"),
        ]
        unique, duplicates = deduplicate_jobs(jobs)
        self.assertEqual(len(unique), 1)
        self.assertEqual(duplicates, 1)

    def test_city_filter_and_rank(self):
        query = JobQuery(role="backend intern", search_term="backend intern", city="Bengaluru", skills=["python"], fresher=True)
        jobs = [
            Job("Backend Intern", "Acme", "internshala", "https://a.example", city="Bengaluru", skills=["python"], work_mode=WorkMode.REMOTE),
            Job("Sales Intern", "Beta", "internshala", "https://b.example", city="Mumbai", skills=["sales"]),
        ]
        filtered = filter_jobs(jobs, query)
        ranked = rank_jobs(filtered, query)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].company, "Acme")
        self.assertGreater(ranked[0].match_score, 0)
        self.assertTrue(ranked[0].reasons)

    def test_ranker_counts_skill_in_title(self):
        query = JobQuery(role="python developer", search_term="python developer", skills=["python"])
        ranked = rank_jobs([Job("Python Developer", "Acme", "linkedin", "https://example.com/1")], query)
        self.assertTrue(any("skills match" in reason for reason in ranked[0].reasons))
        self.assertFalse(any("no requested skills" in warning for warning in ranked[0].warnings))


if __name__ == "__main__":
    unittest.main()

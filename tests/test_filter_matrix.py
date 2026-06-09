import unittest

from jobhunter.filtering import filter_jobs
from jobhunter.models import Job, JobKind, Money, SalaryPeriod, WorkMode
from jobhunter.query import JobQuery


def sample_jobs():
    return [
        Job(
            "Python Backend Intern",
            "Acme",
            "internshala",
            "https://example.com/a",
            city="Bengaluru",
            country="India",
            work_mode=WorkMode.REMOTE,
            job_kind=JobKind.INTERNSHIP,
            skills=["python", "fastapi"],
            stipend=Money(20000, 30000, "INR", SalaryPeriod.MONTH),
            experience_min=0,
            date_posted="2026-06-08",
        ),
        Job(
            "Senior Java Engineer",
            "Beta",
            "indeed",
            "https://example.com/b",
            city="Mumbai",
            country="India",
            work_mode=WorkMode.ONSITE,
            job_kind=JobKind.JOB,
            skills=["java"],
            salary=Money(1800000, 2400000, "INR", SalaryPeriod.YEAR),
            experience_min=5,
            date_posted="2026-06-01",
        ),
        Job(
            "Marketing Intern",
            "SalesCo",
            "unstop",
            "https://example.com/c",
            city="Bengaluru",
            country="India",
            work_mode=WorkMode.HYBRID,
            job_kind=JobKind.INTERNSHIP,
            skills=["marketing"],
            stipend=Money(5000, 8000, "INR", SalaryPeriod.MONTH),
            experience_min=0,
        ),
    ]


class FilterMatrixTests(unittest.TestCase):
    def test_city_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="intern", city="Bengaluru"))
        self.assertEqual({job.company for job in jobs}, {"Acme", "SalesCo"})

    def test_remote_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="intern", remote=True))
        self.assertEqual([job.company for job in jobs], ["Acme"])

    def test_skill_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="engineer", skills=["java"]))
        self.assertEqual([job.company for job in jobs], ["Beta"])

    def test_skill_filter_checks_title_and_description(self):
        jobs = [
            Job(
                "Python Developer",
                "Acme",
                "linkedin",
                "https://example.com/python",
                city="Bengaluru",
                description="Entry level role",
            )
        ]
        filtered = filter_jobs(jobs, JobQuery(role="python", skills=["python"]))
        self.assertEqual([job.company for job in filtered], ["Acme"])

    def test_exclude_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="intern", exclude=["marketing"]))
        self.assertEqual([job.company for job in jobs], ["Acme"])

    def test_salary_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="engineer", salary_min=2000000))
        self.assertEqual([job.company for job in jobs], ["Beta"])

    def test_stipend_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="intern", stipend_min=15000))
        self.assertEqual([job.company for job in jobs], ["Acme"])

    def test_fresher_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="engineer", fresher=True))
        self.assertNotIn("Beta", {job.company for job in jobs})

    def test_posted_within_filter(self):
        jobs = filter_jobs(sample_jobs(), JobQuery(role="intern", posted_within_days=2))
        self.assertEqual([job.company for job in jobs], ["Acme"])


if __name__ == "__main__":
    unittest.main()

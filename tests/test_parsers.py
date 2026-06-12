import json
import unittest

from hirehunt.query import JobQuery
from hirehunt.scrapers.indeed import parse_indeed_graphql_response
from hirehunt.scrapers.internshala import InternshalaScraper, parse_internshala_jobs
from hirehunt.scrapers.linkedin import LinkedInScraper, parse_linkedin_jobs
from hirehunt.scrapers.naukri import _parse_naukri_locations
from hirehunt.scrapers.shine import _make_search_url
from hirehunt.scrapers.unstop import parse_unstop_item
from hirehunt.utils.fetchers import FetchResponse


class ParserTests(unittest.TestCase):
    def test_internshala_parser(self):
        html = """
        <div class="individual_internship" id="individual_internship_1" internshipid="1" data-href="/internship/detail/python-intern">
          <a class="job-title-href" href="/internship/detail/python-intern">Python Intern</a>
          <div class="company-name">Acme Labs</div>
          <span class="location_link">Bangalore</span>
          <span class="stipend">15000 /month</span>
          <div class="round_tabs_container"><span>Python</span><span>Django</span></div>
        </div>
        """
        jobs = parse_internshala_jobs(html, JobQuery(role="python intern", search_term="python intern", city="Bangalore"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].city, "Bengaluru")
        self.assertEqual(jobs[0].stipend.min_amount, 15000)

    def test_internshala_builds_supported_search_routes(self):
        scraper = InternshalaScraper()

        jobs_url = scraper.build_url(
            JobQuery(search_term="software developer", city="Bengaluru")
        )
        internship_url = scraper.build_url(
            JobQuery(search_term="python intern", city="Mumbai")
        )
        internal_url = scraper.build_url(
            JobQuery(search_term="internal auditor", city="Delhi")
        )

        self.assertEqual(
            jobs_url,
            "https://internshala.com/jobs/software-developer-jobs-in-bangalore/",
        )
        self.assertEqual(
            internship_url,
            "https://internshala.com/internships/python-internship-in-mumbai/",
        )
        self.assertEqual(
            internal_url,
            "https://internshala.com/jobs/internal-auditor-jobs-in-delhi/",
        )

    def test_internshala_paginates_after_a_short_page(self):
        scraper = InternshalaScraper()
        query = JobQuery(search_term="python intern", results_wanted=3)

        def page(*identifiers):
            return "".join(
                f"""
                <div class="individual_internship" id="individual_internship_{job_id}"
                     internshipid="{job_id}" data-href="/internship/detail/{job_id}">
                  <a class="job-title-href" href="/internship/detail/{job_id}">{title}</a>
                  <p class="company-name">{company}</p>
                </div>
                """
                for job_id, title, company in identifiers
            )

        pages = {
            1: page(("1", "Python Intern", "Acme"), ("2", "Backend Intern", "Beta")),
            2: page(("3", "Django Intern", "Gamma")),
        }

        def fetch(url):
            page_number = 2 if "page=2" in url else 1
            return FetchResponse(url, pages[page_number], 200, "test")

        scraper.fetch = fetch
        jobs = scraper.search(query)

        self.assertEqual([job.company for job in jobs], ["Acme", "Beta", "Gamma"])

    def test_indeed_parser(self):
        payload = {
            "data": {
                "jobSearch": {
                    "pageInfo": {"nextCursor": "next"},
                    "results": [
                        {
                            "job": {
                                "key": "abc123",
                                "title": "Backend Engineer Intern",
                                "datePublished": 1780963200000,
                                "description": {"html": "<p>Python internship</p>"},
                                "location": {
                                    "countryCode": "IN",
                                    "admin1Code": "KA",
                                    "city": "Bangalore",
                                    "formatted": {"short": "Bangalore, KA", "long": "Bangalore, KA, IN"},
                                },
                                "compensation": {
                                    "baseSalary": {"unitOfWork": "MONTH", "range": {"min": 15000, "max": 25000}},
                                    "estimated": None,
                                    "currencyCode": "INR",
                                },
                                "attributes": [{"key": "VDTG7", "label": "Internship"}],
                                "employer": {"name": "Acme", "relativeCompanyPageUrl": "/cmp/acme", "dossier": {}},
                                "recruit": {"viewJobUrl": "https://example.com/apply"},
                            }
                        }
                    ],
                }
            }
        }
        jobs, cursor = parse_indeed_graphql_response(
            json.dumps(payload),
            JobQuery(role="backend engineer", search_term="backend engineer", city="Bengaluru", country="India"),
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(cursor, "next")
        self.assertEqual(jobs[0].source_job_id, "abc123")
        self.assertEqual(jobs[0].job_url, "https://in.indeed.com/viewjob?jk=abc123")
        self.assertEqual(jobs[0].city, "Bengaluru")
        self.assertEqual(jobs[0].salary.min_amount, 15000)

    def test_linkedin_parser(self):
        html = """
        <li class="base-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/12345"></a>
          <h3 class="base-search-card__title">Software Engineer Intern</h3>
          <h4 class="base-search-card__subtitle">Acme</h4>
          <span class="job-search-card__location">Remote</span>
        </li>
        """
        jobs = parse_linkedin_jobs(html, JobQuery(role="software engineer intern", search_term="software engineer intern"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_job_id, "12345")

    def test_linkedin_search_paginates(self):
        scraper = LinkedInScraper()
        query = JobQuery(role="software engineer", results_wanted=3)

        def page(*job_ids):
            return "".join(
                f"""
                <li class="base-card">
                  <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{job_id}"></a>
                  <h3 class="base-search-card__title">Software Engineer {job_id}</h3>
                  <h4 class="base-search-card__subtitle">Acme</h4>
                </li>
                """
                for job_id in job_ids
            )

        pages = {0: page("1", "2"), 2: page("3")}

        def fetch(url):
            start = 2 if "start=2" in url else 0
            return FetchResponse(url, pages[start], 200, "test")

        scraper.fetch = fetch
        jobs = scraper.search(query)
        self.assertEqual([job.source_job_id for job in jobs], ["1", "2", "3"])

    def test_shine_uses_supported_bangalore_slug(self):
        first_page = _make_search_url(
            JobQuery(search_term="software developer", city="Bengaluru")
        )
        second_page = _make_search_url(
            JobQuery(search_term="software developer", city="Bengaluru"),
            page=2,
        )
        self.assertEqual(
            first_page,
            "https://www.shine.com/job-search/software-developer-jobs-in-bangalore",
        )
        self.assertEqual(
            second_page,
            "https://www.shine.com/job-search/software-developer-jobs-in-bangalore-2",
        )

    def test_naukri_extracts_locations_from_cityfield(self):
        locations = _parse_naukri_locations(
            "telangana - hyderabad, karnataka bengaluru Metropolitan Cities"
        )
        self.assertEqual(locations, "Hyderabad, Bengaluru")

    def test_unstop_parser(self):
        item = {
            "id": 123,
            "title": "Backend Hackathon",
            "organisation": {"name": "Acme"},
            "public_url": "hackathons/backend-hackathon-123",
            "region": "online",
            "type": "hackathon",
            "required_skills": [{"name": "Python"}],
        }
        job = parse_unstop_item(item, JobQuery(role="backend", search_term="backend", city="Bengaluru"))
        self.assertIsNotNone(job)
        self.assertEqual(job.company, "Acme")
        self.assertEqual(job.source_job_id, "123")

    def test_linkedin_parser_accepts_blocked_empty_page(self):
        jobs = parse_linkedin_jobs("<html><title>authwall</title></html>", JobQuery(role="software engineer"))
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()

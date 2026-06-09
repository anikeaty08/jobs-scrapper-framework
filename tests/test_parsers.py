import unittest

from jobhunter.query import JobQuery
from jobhunter.scrapers.indeed import parse_indeed_jobs
from jobhunter.scrapers.internshala import parse_internshala_jobs
from jobhunter.scrapers.linkedin import parse_linkedin_jobs
from jobhunter.scrapers.unstop import parse_unstop_jobs


class ParserTests(unittest.TestCase):
    def test_internshala_parser(self):
        html = """
        <div class="individual_internship">
          <a class="job-title-href" href="/internship/detail/python-intern">Python Intern</a>
          <div class="company-name">Acme Labs</div>
          <span class="location_link">Bangalore</span>
          <span class="stipend">₹15,000 /month</span>
          <div class="round_tabs_container"><span>Python</span><span>Django</span></div>
        </div>
        """
        jobs = parse_internshala_jobs(html, JobQuery(role="python intern", search_term="python intern", city="Bangalore"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].city, "Bengaluru")
        self.assertEqual(jobs[0].stipend.min_amount, 15000)

    def test_indeed_parser(self):
        html = """
        <div data-jk="abc123">
          <h2><a href="/viewjob?jk=abc123">Backend Engineer</a></h2>
          <span class="companyName">Acme</span>
          <div class="companyLocation">Bengaluru, Karnataka</div>
          <span class="salary-snippet-container">5 - 8 LPA</span>
        </div>
        """
        jobs = parse_indeed_jobs(html, JobQuery(role="backend engineer", search_term="backend engineer", city="Bengaluru", country="India"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_job_id, "abc123")

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

    def test_unstop_parser(self):
        html = """
        <div class="opportunity-card">
          <a href="/jobs/backend-intern-acme-123">Backend Intern | Acme</a>
          <span class="salary">₹25,000 per month</span>
        </div>
        """
        jobs = parse_unstop_jobs(html, JobQuery(role="backend intern", search_term="backend intern", city="Bengaluru"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Acme")


if __name__ == "__main__":
    unittest.main()

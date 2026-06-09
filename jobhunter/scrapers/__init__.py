"""Built-in source scrapers."""

from jobhunter.scrapers.indeed import IndeedScraper
from jobhunter.scrapers.internshala import InternshalaScraper
from jobhunter.scrapers.linkedin import LinkedInScraper
from jobhunter.scrapers.unstop import UnstopScraper

BUILTIN_SCRAPERS = [
    IndeedScraper,
    InternshalaScraper,
    LinkedInScraper,
    UnstopScraper,
]

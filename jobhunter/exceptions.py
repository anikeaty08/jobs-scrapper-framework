"""Framework-specific exceptions."""


class JobHunterError(Exception):
    """Base exception for JobHunter."""


class ScraperError(JobHunterError):
    """Raised when a scraper cannot complete normally."""


class ScraperBlockedError(ScraperError):
    """Raised when a source blocks or rate-limits requests."""


class UnknownSourceError(JobHunterError):
    """Raised when a requested source is not registered."""


class QueryValidationError(JobHunterError):
    """Raised when a search query cannot be used safely."""

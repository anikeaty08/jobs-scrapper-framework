"""Command line interface."""

from __future__ import annotations

import argparse

from jobhunter.engine import search_jobs
from jobhunter.exporters.csv import to_csv
from jobhunter.exporters.json import to_json
from jobhunter.query import JobQuery
from jobhunter.validation import validate_sources, write_validation_report


class SimpleConsole:
    def print(self, value) -> None:
        print(value)


class SimpleTable:
    def __init__(self, title: str = "") -> None:
        self.title = title
        self.columns: list[str] = []
        self.rows: list[list[str]] = []

    def add_column(self, name: str, **_: object) -> None:
        self.columns.append(name)

    def add_row(self, *values: str) -> None:
        self.rows.append([str(value) for value in values])

    def __str__(self) -> str:
        lines = [self.title] if self.title else []
        if self.columns:
            lines.append(" | ".join(self.columns))
            lines.append("-" * len(lines[-1]))
        lines.extend(" | ".join(row) for row in self.rows)
        return "\n".join(lines)


try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    Console = SimpleConsole
    Table = SimpleTable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobhunter", description="Search jobs across global and regional sources.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search jobs")
    search.add_argument("role", help="Role or search term")
    search.add_argument("--source", "--site", dest="sources", action="append", help="Source to search. Can be repeated.")
    search.add_argument("--city", default="", help="Preferred city")
    search.add_argument("--country", default="", help="Country")
    search.add_argument("--location", default="", help="Free-form location")
    search.add_argument("--skill", dest="skills", action="append", default=[], help="Required/preferred skill. Can be repeated.")
    search.add_argument("--exclude", action="append", default=[], help="Term to exclude. Can be repeated.")
    search.add_argument("--remote", action="store_true", help="Prefer remote jobs")
    search.add_argument("--fresher", action="store_true", help="Prefer fresher-friendly roles")
    search.add_argument("--limit", type=int, default=50, help="Results wanted per source")
    search.add_argument("--cache", action="store_true", help="Use cached source pages when available and save fetched pages")
    search.add_argument("--cache-dir", default=".jobhunter_cache", help="Cache directory")
    search.add_argument("--csv", default="", help="Write CSV output")
    search.add_argument("--json", default="", help="Write JSON output")

    validate = subparsers.add_parser("validate", help="Validate live source fetching and parsing")
    validate.add_argument("role", help="Role or search term")
    validate.add_argument("--source", "--site", dest="sources", action="append", help="Source to validate. Can be repeated.")
    validate.add_argument("--city", default="", help="Preferred city")
    validate.add_argument("--country", default="", help="Country")
    validate.add_argument("--location", default="", help="Free-form location")
    validate.add_argument("--limit", type=int, default=10, help="Results wanted per source")
    validate.add_argument("--backend", default="requests", choices=["requests"], help="Fetch backend")
    validate.add_argument("--cache", action="store_true", help="Cache fetched pages")
    validate.add_argument("--cache-dir", default=".jobhunter_cache", help="Cache directory")
    validate.add_argument("--report", default="", help="Write JSON validation report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if args.command == "search":
        result = search_jobs(
            role=args.role,
            sources=args.sources or "auto",
            city=args.city,
            country=args.country,
            location=args.location,
            skills=args.skills,
            exclude=args.exclude,
            remote=args.remote or None,
            fresher=args.fresher or None,
            results_wanted=args.limit,
            cache_enabled=args.cache,
            cache_dir=args.cache_dir,
        )
        if args.csv:
            to_csv(result.jobs, args.csv)
        if args.json:
            to_json(result.jobs, args.json)

        table = Table(title=f"JobHunter results: {len(result.jobs)} unique jobs")
        table.add_column("Score", justify="right")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("City")
        table.add_column("Source")
        table.add_column("URL")
        for job in result.jobs[:25]:
            table.add_row(f"{job.match_score:.0f}", job.title, job.company, job.city, job.source, job.job_url)
        console.print(table)
    elif args.command == "validate":
        query = JobQuery(
            role=args.role,
            city=args.city,
            country=args.country,
            location=args.location,
            sources=args.sources or "auto",
            results_wanted=args.limit,
            fetch_backend=args.backend,
            cache_enabled=args.cache,
            cache_dir=args.cache_dir,
        )
        results = validate_sources(query, args.sources)
        table = Table(title="JobHunter live validation")
        table.add_column("Source")
        table.add_column("OK")
        table.add_column("Status")
        table.add_column("Backend")
        table.add_column("Parsed", justify="right")
        table.add_column("Sample")
        table.add_column("Error")
        for item in results:
            table.add_row(
                item.source,
                "yes" if item.ok else "no",
                str(item.status_code),
                item.backend,
                str(item.parsed_count),
                "; ".join(item.sample_titles[:2]),
                item.error,
            )
        console.print(table)
        if args.report:
            write_validation_report(results, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

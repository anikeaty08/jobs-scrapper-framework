"""Command line interface."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from jobhunter.engine import search_jobs
from jobhunter.exporters.csv import to_csv
from jobhunter.exporters.json import to_json


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
    search.add_argument("--csv", default="", help="Write CSV output")
    search.add_argument("--json", default="", help="Write JSON output")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

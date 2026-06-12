"""Command line interface for HireHunt."""

from __future__ import annotations

import argparse

from hirehunt.engine import search_jobs
from hirehunt.exporters.csv import to_csv
from hirehunt.exporters.json import to_json
from hirehunt.query import JobQuery
from hirehunt.validation import validate_sources, write_validation_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hirehunt",
        description="Search and validate jobs across India and global sources.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search jobs across sources")
    _add_query_args(search)
    search.add_argument("--skill", dest="skills", action="append", default=[], help="Required skill. Repeat to add more.")
    search.add_argument("--exclude", action="append", default=[], help="Term to exclude from results.")
    search.add_argument("--remote", action="store_true", help="Remote/WFH jobs only")
    search.add_argument("--fresher", action="store_true", help="Fresher-friendly roles only")
    search.add_argument("--csv", default="", metavar="FILE", help="Export to CSV")
    search.add_argument("--json", default="", metavar="FILE", help="Export to JSON")
    search.add_argument("--top", type=int, default=25, help="Max rows to display")

    validate = subparsers.add_parser("validate", help="Validate live source fetching and parsing")
    _add_query_args(validate)
    validate.add_argument("--report", default="", metavar="FILE", help="Write JSON validation report")

    return parser


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("role", help="Role or search term")
    parser.add_argument(
        "--source",
        "--site",
        dest="sources",
        action="append",
        metavar="SOURCE",
        help="Source to use. Repeat to add more.",
    )
    parser.add_argument("--city", default="", metavar="CITY", help="City to filter by")
    parser.add_argument("--country", default="", help="Country")
    parser.add_argument("--location", default="", help="Free-form location")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max results per source; use 0 to fetch until the source is exhausted",
    )
    parser.add_argument(
        "--dedupe-mode",
        choices=["strict", "heuristic", "none"],
        default="strict",
        help="Cross-source deduplication policy",
    )
    parser.add_argument("--cache", action="store_true", help="Use and update response cache")
    parser.add_argument("--cache-dir", default=".jobhunter_cache", help="Cache directory")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "search":
        result = search_jobs(
            search_term=args.role,
            sources=args.sources or "auto",
            city=args.city,
            country=args.country,
            location=args.location,
            skills=args.skills,
            exclude=args.exclude,
            remote=args.remote or None,
            fresher=args.fresher or None,
            results_wanted=args.limit,
            dedupe_mode=args.dedupe_mode,
            cache_enabled=args.cache,
            cache_dir=args.cache_dir,
        )
        if args.csv:
            to_csv(result.jobs, args.csv)
        if args.json:
            to_json(result.jobs, args.json)
        _print_search(result, args.role, args.top)
        return 0

    if args.command == "validate":
        query = JobQuery(
            search_term=args.role,
            sources=args.sources or "auto",
            city=args.city,
            country=args.country,
            location=args.location,
            results_wanted=args.limit,
            dedupe_mode=args.dedupe_mode,
            cache_enabled=args.cache,
            cache_dir=args.cache_dir,
        )
        results = validate_sources(query, args.sources)
        _print_validation(results)
        if args.report:
            write_validation_report(results, args.report)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _print_search(result, role: str, top: int) -> None:
    print(f"HireHunt results for '{role}': {len(result.jobs)} unique jobs")
    for warning in result.warnings:
        print(f"NOTICE: {warning}")
    print("score | source | title | company | city | url")
    print("-" * 90)
    for job in result.jobs[:top]:
        print(
            f"{job.match_score:5.0f} | {job.source} | {job.title} | "
            f"{job.company} | {job.city or '-'} | {job.job_url}"
        )
    if result.errors:
        print("Errors:")
        for source, error in result.errors.items():
            print(f"{source}: {error}")
    print("Source diagnostics:")
    for source, stats in result.stats.items():
        reasons = ", ".join(f"{key}={value}" for key, value in sorted(stats.filter_reasons.items()))
        print(
            f"{source}: parsed={stats.parsed} kept={stats.kept} "
            f"duplicates={stats.duplicates} completion={stats.completion}"
            + (f" filtered[{reasons}]" if reasons else "")
        )


def _print_validation(results) -> None:
    print("HireHunt live validation")
    print("source | ok | status | backend | parsed | samples | error")
    print("-" * 90)
    for item in results:
        samples = "; ".join(item.sample_titles[:2])
        ok = "yes" if item.ok else "no"
        print(
            f"{item.source} | {ok} | {item.status_code} | {item.backend or '-'} | "
            f"{item.parsed_count} | {samples} | {item.error}"
        )


if __name__ == "__main__":
    raise SystemExit(main())

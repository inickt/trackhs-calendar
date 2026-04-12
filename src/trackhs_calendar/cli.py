from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_app_config
from .fetch import export_reservations_csv
from .ops import (
    maybe_notify,
    ping_healthchecks_fail,
    ping_healthchecks_start,
    ping_healthchecks_success,
)
from .trackhs import BookingLoadResult, load_booking_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trackhs-calendar",
        description="Parse TrackHS booking CSV exports into normalized guest bookings.",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("download.csv"),
        help="Path to the TrackHS CSV export.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to the optional behavior config file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    preview_parser = subparsers.add_parser(
        "preview",
        help="Print normalized bookings that qualify for calendar sync.",
    )
    add_config_flag(preview_parser)
    preview_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output.",
    )
    preview_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Log into the TrackHS owner portal and export the reservations CSV.",
    )
    add_config_flag(fetch_parser)
    add_output_flags(fetch_parser)
    fetch_parser.add_argument(
        "--output",
        type=Path,
        default=Path("download.csv"),
        help="Where to write the downloaded CSV.",
    )
    fetch_parser.add_argument(
        "--start-date",
        default="",
        help="Optional export filter in YYYY-MM-DD format.",
    )
    fetch_parser.add_argument(
        "--end-date",
        default="",
        help="Optional export filter in YYYY-MM-DD format.",
    )
    fetch_parser.add_argument(
        "--unit",
        default="",
        help="Optional TrackHS unit ID filter.",
    )
    fetch_parser.add_argument(
        "--search",
        default="",
        help="Optional keyword search filter.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Fetch the TrackHS CSV, then sync it into Google Calendar.",
    )
    add_config_flag(run_parser)
    add_output_flags(run_parser)
    run_parser.add_argument(
        "--output",
        type=Path,
        default=Path("download.csv"),
        help="Where to write the downloaded CSV.",
    )
    run_parser.add_argument(
        "--start-date",
        default="",
        help="Optional export filter in YYYY-MM-DD format.",
    )
    run_parser.add_argument(
        "--end-date",
        default="",
        help="Optional export filter in YYYY-MM-DD format.",
    )
    run_parser.add_argument(
        "--unit",
        default="",
        help="Optional TrackHS unit ID filter.",
    )
    run_parser.add_argument(
        "--search",
        default="",
        help="Optional keyword search filter.",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Fetch the CSV, then print the planned Google changes without writing them.")

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync normalized guest bookings into Google Calendar.",
    )
    add_config_flag(sync_parser)
    add_output_flags(sync_parser)
    sync_parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("download.csv"),
        help="Path to the TrackHS CSV export to sync.",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned creates, updates, and deletes without calling Google.",
    )

    return parser


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-row and per-event details in text output.",
    )


def add_config_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to the optional behavior config file.",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        command = args.command or "preview"
        app_config = load_app_config(args.config)

        if command == "preview":
            report = load_booking_report(args.csv_path, app_config.filters)
            indent = 2 if args.pretty or getattr(args, "json", False) else None
            print(json.dumps(report.to_dict(), indent=indent))
            return

        if command == "fetch":
            export_reservations_csv(
                output_path=args.output,
                start_date=args.start_date,
                end_date=args.end_date,
                unit=args.unit,
                search=args.search,
            )
            report = load_booking_report(args.output, app_config.filters)
            result = {
                "csv_path": str(args.output),
                "rows_read": report.total_rows,
                "bookings_considered": len(report.bookings),
                "ignored_counts": report.ignored_counts,
                "ignored_samples": [sample.to_dict() for sample in report.ignored_samples],
            }
            emit_result("fetch", result, args.verbose, args.json)
            return

        if command == "run":
            from .google_sync import sync_google_calendar

            ping_healthchecks_start()
            export_reservations_csv(
                output_path=args.output,
                start_date=args.start_date,
                end_date=args.end_date,
                unit=args.unit,
                search=args.search,
            )
            booking_report = load_booking_report(args.output, app_config.filters)
            result = sync_google_calendar(
                csv_path=args.output,
                dry_run=args.dry_run,
                app_config=app_config,
            )
            if not args.dry_run:
                maybe_notify(result, booking_report, app_config)
            ping_healthchecks_success()
            emit_result(
                "run",
                {
                    "config_path": str(args.config),
                    "csv_path": str(args.output),
                    "sync": result,
                },
                args.verbose,
                args.json,
            )
            return

        if command == "sync":
            from .google_sync import sync_google_calendar

            result = sync_google_calendar(
                csv_path=args.csv_path,
                dry_run=args.dry_run,
                app_config=app_config,
            )
            emit_result("sync", result, args.verbose, args.json)
            return

        parser.error(f"Unsupported command: {command}")
    except RuntimeError as exc:
        if command == "run":
            ping_healthchecks_fail(str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def format_ignored_samples(samples: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for sample in samples:
        reservation_id = sample.get("reservation_id") or "unknown"
        source_type = sample.get("source_type") or "--"
        status = sample.get("status") or "--"
        lines.append(
            f"ignored {reservation_id} | reason={sample['reason']} | type={source_type} | status={status}"
        )
    return lines


def format_action_lines(actions: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for action in actions:
        guest = action.get("guest") or "--"
        source_type = action.get("source_type") or "--"
        status = action.get("status") or "--"
        lines.append(
            f"{action['action']} {action['reservation_id']} | {guest} | "
            f"type={source_type} | status={status} | "
            f"{action['check_in']} -> {action['checkout']} | {action['summary']}"
        )
    return lines


def emit_result(command: str, result: dict, verbose: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return

    if command == "fetch":
        print("Fetch:")
        print(f"- wrote {result['csv_path']}")
        print(f"- rows read: {result['rows_read']}")
        print(f"- included bookings: {result['bookings_considered']}")
        for reason, count in sorted(result["ignored_counts"].items()):
            print(f"- {reason}: {count}")
        if verbose:
            for line in format_ignored_samples(result["ignored_samples"]):
                print(f"- {line}")
        return

    if command == "sync":
        print("Sync:")
        print(f"- calendar: {result['calendar_id']}")
        print(f"- dry run: {str(result['dry_run']).lower()}")
        print(f"- rows read: {result['rows_read']}")
        print(f"- included bookings: {result['bookings_considered']}")
        for reason, count in sorted(result["ignored_counts"].items()):
            print(f"- {reason}: {count}")
        print(f"- creates: {len(result['creates'])}")
        print(f"- updates: {len(result['updates'])}")
        print(f"- deletes: {len(result['deletes'])}")
        if verbose:
            for line in format_ignored_samples(result["ignored_samples"]):
                print(f"- {line}")
            for section in ("creates", "updates", "deletes"):
                for line in format_action_lines(result[section]):
                    print(f"- {line}")
        return

    if command == "run":
        sync = result["sync"]
        print("Run:")
        print(f"- config: {result['config_path']}")
        print(f"- csv: {result['csv_path']}")
        print(f"- calendar: {sync['calendar_id']}")
        print(f"- dry run: {str(sync['dry_run']).lower()}")
        print(f"- rows read: {sync['rows_read']}")
        print(f"- included bookings: {sync['bookings_considered']}")
        for reason, count in sorted(sync["ignored_counts"].items()):
            print(f"- {reason}: {count}")
        print(f"- creates: {len(sync['creates'])}")
        print(f"- updates: {len(sync['updates'])}")
        print(f"- deletes: {len(sync['deletes'])}")
        if verbose:
            for line in format_ignored_samples(sync["ignored_samples"]):
                print(f"- {line}")
            for section in ("creates", "updates", "deletes"):
                for line in format_action_lines(sync[section]):
                    print(f"- {line}")

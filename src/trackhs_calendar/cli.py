from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fetch import export_reservations_csv
from .trackhs import load_bookings


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

    subparsers = parser.add_subparsers(dest="command", required=False)

    preview_parser = subparsers.add_parser(
        "preview",
        help="Print normalized bookings that qualify for calendar sync.",
    )
    preview_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output.",
    )

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Log into the TrackHS owner portal and export the reservations CSV.",
    )
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
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch the CSV, then print the planned Google changes without writing them.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync normalized guest bookings into Google Calendar.",
    )
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        command = args.command or "preview"

        if command == "preview":
            bookings = load_bookings(args.csv_path)
            indent = 2 if args.pretty else None
            print(json.dumps([booking.to_dict() for booking in bookings], indent=indent))
            return

        if command == "fetch":
            export_reservations_csv(
                output_path=args.output,
                start_date=args.start_date,
                end_date=args.end_date,
                unit=args.unit,
                search=args.search,
            )
            print(args.output)
            return

        if command == "run":
            from .google_sync import sync_google_calendar

            export_reservations_csv(
                output_path=args.output,
                start_date=args.start_date,
                end_date=args.end_date,
                unit=args.unit,
                search=args.search,
            )
            result = sync_google_calendar(csv_path=args.output, dry_run=args.dry_run)
            print(
                json.dumps(
                    {
                        "csv_path": str(args.output),
                        "sync": result,
                    },
                    indent=2,
                )
            )
            return

        if command == "sync":
            from .google_sync import sync_google_calendar

            result = sync_google_calendar(csv_path=args.csv_path, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return

        parser.error(f"Unsupported command: {command}")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

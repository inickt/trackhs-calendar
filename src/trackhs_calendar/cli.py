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

        parser.error(f"Unsupported command: {command}")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

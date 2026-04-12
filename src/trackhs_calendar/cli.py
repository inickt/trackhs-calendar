from __future__ import annotations

import argparse
import json
from pathlib import Path

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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    command = args.command or "preview"
    bookings = load_bookings(args.csv_path)

    if command == "preview":
        indent = 2 if args.pretty else None
        print(json.dumps([booking.to_dict() for booking in bookings], indent=indent))
        return

    parser.error(f"Unsupported command: {command}")

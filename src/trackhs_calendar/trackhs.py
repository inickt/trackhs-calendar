from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import FilterConfig


@dataclass(frozen=True)
class Booking:
    reservation_id: str
    source_type: str
    status: str
    unit: str
    guest: str
    booked_date: date
    check_in: date
    checkout: date

    def to_dict(self) -> dict[str, str]:
        return {
            "reservation_id": self.reservation_id,
            "source_type": self.source_type,
            "status": self.status,
            "unit": self.unit,
            "guest": self.guest,
            "booked_date": self.booked_date.isoformat(),
            "check_in": self.check_in.isoformat(),
            "checkout": self.checkout.isoformat(),
        }


@dataclass(frozen=True)
class IgnoredRow:
    reason: str
    reservation_id: str
    source_type: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "reason": self.reason,
            "reservation_id": self.reservation_id,
            "source_type": self.source_type,
            "status": self.status,
        }


@dataclass(frozen=True)
class BookingLoadResult:
    bookings: list[Booking]
    total_rows: int
    ignored_counts: dict[str, int]
    ignored_samples: list[IgnoredRow]

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "included_bookings": len(self.bookings),
            "ignored_counts": self.ignored_counts,
            "ignored_samples": [sample.to_dict() for sample in self.ignored_samples],
            "bookings": [booking.to_dict() for booking in self.bookings],
        }


def parse_date(raw_value: str, field_name: str, row_number: int) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"Row {row_number}: invalid {field_name!r} date {raw_value!r}"
        ) from exc


def should_include_value(value: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    if include and value not in include:
        return False
    if value in exclude:
        return False
    return True


def load_booking_report(csv_path: Path, filters: FilterConfig) -> BookingLoadResult:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        bookings: list[Booking] = []
        ignored_counter: Counter[str] = Counter()
        ignored_samples: list[IgnoredRow] = []
        total_rows = 0

        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            reservation_id = (row.get("Reservation Id") or "").strip()
            source_type = (row.get("Type") or "").strip()
            status = (row.get("Status") or "").strip()

            if not should_include_value(
                source_type,
                filters.include_types,
                filters.exclude_types,
            ):
                ignored_counter["excluded_type"] += 1
                if len(ignored_samples) < 10:
                    ignored_samples.append(
                        IgnoredRow(
                            reason="excluded_type",
                            reservation_id=reservation_id,
                            source_type=source_type,
                            status=status,
                        )
                    )
                continue

            if not should_include_value(
                status,
                filters.include_statuses,
                filters.exclude_statuses,
            ):
                ignored_counter["excluded_status"] += 1
                if len(ignored_samples) < 10:
                    ignored_samples.append(
                        IgnoredRow(
                            reason="excluded_status",
                            reservation_id=reservation_id,
                            source_type=source_type,
                            status=status,
                        )
                    )
                continue

            check_in = parse_date((row.get("Check-In") or "").strip(), "Check-In", row_number)
            checkout = parse_date((row.get("Checkout") or "").strip(), "Checkout", row_number)

            if check_in >= checkout:
                raise ValueError(
                    f"Row {row_number}: expected Check-In before Checkout, got "
                    f"{check_in.isoformat()} >= {checkout.isoformat()}"
                )

            bookings.append(
                Booking(
                    reservation_id=reservation_id,
                    source_type=source_type,
                    status=status,
                    unit=(row.get("Unit") or "").strip(),
                    guest=(row.get("Guest") or "").strip(),
                    booked_date=parse_date(
                        (row.get("Booked Date") or "").strip(),
                        "Booked Date",
                        row_number,
                    ),
                    check_in=check_in,
                    checkout=checkout,
                )
            )

    bookings.sort(key=lambda booking: (booking.check_in, booking.reservation_id))
    return BookingLoadResult(
        bookings=bookings,
        total_rows=total_rows,
        ignored_counts=dict(ignored_counter),
        ignored_samples=ignored_samples,
    )


def load_bookings(csv_path: Path, filters: FilterConfig) -> list[Booking]:
    return load_booking_report(csv_path, filters).bookings

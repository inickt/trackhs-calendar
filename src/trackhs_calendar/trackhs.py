from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ALLOWED_TYPES = {"Website", "Airbnb", "VRBO", "Phone Guest"}
ALLOWED_STATUSES = {"Confirmed", "Checked In"}


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


def parse_date(raw_value: str, field_name: str, row_number: int) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"Row {row_number}: invalid {field_name!r} date {raw_value!r}"
        ) from exc


def load_bookings(csv_path: Path) -> list[Booking]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        bookings: list[Booking] = []

        for row_number, row in enumerate(reader, start=2):
            source_type = (row.get("Type") or "").strip()
            status = (row.get("Status") or "").strip()

            if source_type not in ALLOWED_TYPES or status not in ALLOWED_STATUSES:
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
                    reservation_id=(row.get("Reservation Id") or "").strip(),
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
    return bookings

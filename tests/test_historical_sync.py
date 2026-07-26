from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from trackhs_calendar.config import (
    AppConfig,
    EventConfig,
    FilterConfig,
    NotifyConfig,
    SyncBehaviorConfig,
)
from trackhs_calendar.google_sync import (
    GoogleConfig,
    calendar_sync_filters,
    event_has_ended,
    sync_google_calendar,
)


def app_config() -> AppConfig:
    return AppConfig(
        filters=FilterConfig(
            include_statuses=(),
            exclude_statuses=("Checked Out",),
            include_types=(),
            exclude_types=(),
        ),
        events=EventConfig(
            summary="Booked",
            description="Reservation {reservation_id}: {status}",
        ),
        sync=SyncBehaviorConfig(
            managed_by="trackhs-calendar",
            past_years=1,
            future_years=5,
            historical_statuses=("Checked Out",),
        ),
        notify=NotifyConfig(
            known_statuses=(),
            known_types=(),
            notify_on_actions=False,
            notify_on_unknown_values=False,
            notify_on_zero_bookings=False,
        ),
    )


class FakeRequest:
    def __init__(self, result=None):
        self.result = result or {}

    def execute(self):
        return self.result


class FakeEvents:
    def __init__(self):
        self.inserts: list[dict] = []
        self.deletes: list[dict] = []

    def insert(self, **kwargs):
        self.inserts.append(kwargs)
        return FakeRequest()

    def delete(self, **kwargs):
        self.deletes.append(kwargs)
        return FakeRequest()


class FakeService:
    def __init__(self):
        self.events_api = FakeEvents()

    def events(self):
        return self.events_api


class HistoricalSyncTests(unittest.TestCase):
    def test_checked_out_status_overrides_active_filter_for_sync(self):
        filters = calendar_sync_filters(app_config())

        self.assertEqual(filters.exclude_statuses, ())

    def test_event_with_past_checkout_is_historical(self):
        event = {"end": {"date": "2026-07-25"}}

        self.assertTrue(event_has_ended(event, today=date(2026, 7, 26)))

    def test_next_sync_recreates_previously_deleted_checked_out_event(self):
        service = FakeService()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bookings.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "Reservation Id",
                        "Type",
                        "Status",
                        "Unit",
                        "Guest",
                        "Booked Date",
                        "Check-In",
                        "Checkout",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Reservation Id": "history-1",
                        "Type": "Website",
                        "Status": "Checked Out",
                        "Unit": "Lakehouse",
                        "Guest": "Historical Guest",
                        "Booked Date": "2026-01-01",
                        "Check-In": "2026-07-20",
                        "Checkout": "2026-07-25",
                    }
                )

            with (
                patch(
                    "trackhs_calendar.google_sync.load_google_config",
                    return_value=GoogleConfig(
                        calendar_id="calendar",
                        auth_mode="service_account",
                        credentials_file=None,
                        token_file=None,
                        service_account_file=None,
                    ),
                ),
                patch(
                    "trackhs_calendar.google_sync.build_service",
                    return_value=service,
                ),
                patch(
                    "trackhs_calendar.google_sync.iter_managed_events",
                    return_value=[],
                ),
            ):
                result = sync_google_calendar(
                    csv_path=csv_path,
                    dry_run=False,
                    app_config=app_config(),
                )

        self.assertEqual(
            [action["reservation_id"] for action in result["creates"]],
            ["history-1"],
        )
        self.assertEqual(len(service.events_api.inserts), 1)

    def test_missing_historical_event_is_not_deleted(self):
        service = FakeService()
        historical_event = {
            "id": "google-event-1",
            "summary": "Booked",
            "start": {"date": "2000-07-20"},
            "end": {"date": "2000-07-25"},
            "extendedProperties": {
                "private": {
                    "managedBy": "trackhs-calendar",
                    "reservationId": "history-1",
                    "sourceType": "Website",
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bookings.csv"
            csv_path.write_text(
                "Reservation Id,Type,Status,Unit,Guest,Booked Date,Check-In,Checkout\n",
                encoding="utf-8",
            )

            with (
                patch(
                    "trackhs_calendar.google_sync.load_google_config",
                    return_value=GoogleConfig(
                        calendar_id="calendar",
                        auth_mode="service_account",
                        credentials_file=None,
                        token_file=None,
                        service_account_file=None,
                    ),
                ),
                patch(
                    "trackhs_calendar.google_sync.build_service",
                    return_value=service,
                ),
                patch(
                    "trackhs_calendar.google_sync.iter_managed_events",
                    return_value=[historical_event],
                ),
            ):
                result = sync_google_calendar(
                    csv_path=csv_path,
                    dry_run=False,
                    app_config=app_config(),
                )

        self.assertEqual(result["deletes"], [])
        self.assertEqual(service.events_api.deletes, [])

    def test_missing_future_event_is_still_deleted(self):
        service = FakeService()
        future_event = {
            "id": "google-event-2",
            "summary": "Booked",
            "start": {"date": "2999-07-20"},
            "end": {"date": "2999-07-25"},
            "extendedProperties": {
                "private": {
                    "managedBy": "trackhs-calendar",
                    "reservationId": "cancelled-1",
                    "sourceType": "Website",
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bookings.csv"
            csv_path.write_text(
                "Reservation Id,Type,Status,Unit,Guest,Booked Date,Check-In,Checkout\n",
                encoding="utf-8",
            )

            with (
                patch(
                    "trackhs_calendar.google_sync.load_google_config",
                    return_value=GoogleConfig(
                        calendar_id="calendar",
                        auth_mode="service_account",
                        credentials_file=None,
                        token_file=None,
                        service_account_file=None,
                    ),
                ),
                patch(
                    "trackhs_calendar.google_sync.build_service",
                    return_value=service,
                ),
                patch(
                    "trackhs_calendar.google_sync.iter_managed_events",
                    return_value=[future_event],
                ),
            ):
                result = sync_google_calendar(
                    csv_path=csv_path,
                    dry_run=False,
                    app_config=app_config(),
                )

        self.assertEqual(
            [action["reservation_id"] for action in result["deletes"]],
            ["cancelled-1"],
        )
        self.assertEqual(len(service.events_api.deletes), 1)


if __name__ == "__main__":
    unittest.main()

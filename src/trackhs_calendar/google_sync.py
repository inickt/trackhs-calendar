from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import AppConfig
from .render import render_event_description, render_event_summary
from .trackhs import Booking, load_bookings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass(frozen=True)
class GoogleConfig:
    calendar_id: str
    credentials_file: Path
    token_file: Path


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_google_config() -> GoogleConfig:
    return GoogleConfig(
        calendar_id=get_env("GOOGLE_CALENDAR_ID"),
        credentials_file=Path(get_env("GOOGLE_CREDENTIALS_FILE")),
        token_file=Path(get_env("GOOGLE_TOKEN_FILE")),
    )


def get_google_credentials(config: GoogleConfig) -> Credentials:
    creds: Credentials | None = None

    if config.token_file.exists():
        creds = Credentials.from_authorized_user_file(str(config.token_file), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not config.credentials_file.exists():
            raise RuntimeError(
                f"Google OAuth client file not found: {config.credentials_file}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_file),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

    config.token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_service(config: GoogleConfig):
    credentials = get_google_credentials(config)
    return build("calendar", "v3", credentials=credentials)


def sync_window(app_config: AppConfig) -> tuple[str, str]:
    today = date.today()
    time_min = datetime(today.year - app_config.sync.past_years, 1, 1, tzinfo=timezone.utc)
    time_max = datetime(
        today.year + app_config.sync.future_years,
        12,
        31,
        23,
        59,
        59,
        tzinfo=timezone.utc,
    )
    return time_min.isoformat(), time_max.isoformat()


def event_payload(booking: Booking, app_config: AppConfig) -> dict[str, Any]:
    return {
        "summary": render_event_summary(booking, app_config.events),
        "description": render_event_description(booking, app_config.events),
        "start": {"date": booking.check_in.isoformat()},
        "end": {"date": booking.checkout.isoformat()},
        "extendedProperties": {
            "private": {
                "managedBy": app_config.sync.managed_by,
                "reservationId": booking.reservation_id,
                "sourceType": booking.source_type,
            }
        },
    }


def iter_managed_events(service, calendar_id: str, app_config: AppConfig) -> list[dict[str, Any]]:
    time_min, time_max = sync_window(app_config)
    events: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                privateExtendedProperty=f"managedBy={app_config.sync.managed_by}",
                singleEvents=True,
                showDeleted=False,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events


def reservation_id_for_event(event: dict[str, Any]) -> str | None:
    return (
        event.get("extendedProperties", {})
        .get("private", {})
        .get("reservationId")
    )


def events_equal(event: dict[str, Any], desired: dict[str, Any]) -> bool:
    current_private = event.get("extendedProperties", {}).get("private", {})
    desired_private = desired.get("extendedProperties", {}).get("private", {})
    return (
        event.get("summary") == desired.get("summary")
        and event.get("description") == desired.get("description")
        and event.get("start", {}).get("date") == desired.get("start", {}).get("date")
        and event.get("end", {}).get("date") == desired.get("end", {}).get("date")
        and current_private == desired_private
    )


def sync_google_calendar(csv_path: Path, dry_run: bool, app_config: AppConfig) -> dict[str, Any]:
    google_config = load_google_config()
    bookings = load_bookings(csv_path, app_config.filters)
    desired_by_reservation = {
        booking.reservation_id: event_payload(booking, app_config) for booking in bookings
    }

    service = build_service(google_config)
    existing_events = iter_managed_events(service, google_config.calendar_id, app_config)
    existing_by_reservation = {
        reservation_id: event
        for event in existing_events
        if (reservation_id := reservation_id_for_event(event))
    }

    creates: list[str] = []
    updates: list[str] = []
    deletes: list[str] = []

    for reservation_id, payload in desired_by_reservation.items():
        existing = existing_by_reservation.get(reservation_id)
        if existing is None:
            creates.append(reservation_id)
            if not dry_run:
                service.events().insert(
                    calendarId=google_config.calendar_id,
                    body=payload,
                ).execute()
            continue

        if not events_equal(existing, payload):
            updates.append(reservation_id)
            if not dry_run:
                service.events().patch(
                    calendarId=google_config.calendar_id,
                    eventId=existing["id"],
                    body=payload,
                ).execute()

    for reservation_id, event in existing_by_reservation.items():
        if reservation_id in desired_by_reservation:
            continue
        deletes.append(reservation_id)
        if not dry_run:
            service.events().delete(
                calendarId=google_config.calendar_id,
                eventId=event["id"],
            ).execute()

    return {
        "dry_run": dry_run,
        "calendar_id": google_config.calendar_id,
        "bookings_considered": len(bookings),
        "creates": creates,
        "updates": updates,
        "deletes": deletes,
    }

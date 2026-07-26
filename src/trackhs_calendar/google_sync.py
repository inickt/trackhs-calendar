from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import AppConfig, FilterConfig
from .render import render_event_description, render_event_summary
from .trackhs import Booking, BookingLoadResult, load_booking_report

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass(frozen=True)
class GoogleConfig:
    calendar_id: str
    auth_mode: str
    credentials_file: Path | None
    token_file: Path | None
    service_account_file: Path | None


@dataclass(frozen=True)
class SyncAction:
    action: str
    reservation_id: str
    summary: str
    guest: str
    unit: str
    source_type: str
    status: str
    check_in: str
    checkout: str

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "reservation_id": self.reservation_id,
            "summary": self.summary,
            "guest": self.guest,
            "unit": self.unit,
            "source_type": self.source_type,
            "status": self.status,
            "check_in": self.check_in,
            "checkout": self.checkout,
        }


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_google_config() -> GoogleConfig:
    auth_mode = os.environ.get("GOOGLE_AUTH_MODE", "oauth").strip().lower()
    if auth_mode not in {"oauth", "service_account"}:
        raise RuntimeError(
            "GOOGLE_AUTH_MODE must be either 'oauth' or 'service_account'."
        )

    credentials_file = os.environ.get("GOOGLE_CREDENTIALS_FILE")
    token_file = os.environ.get("GOOGLE_TOKEN_FILE")
    service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    return GoogleConfig(
        calendar_id=get_env("GOOGLE_CALENDAR_ID"),
        auth_mode=auth_mode,
        credentials_file=Path(credentials_file) if credentials_file else None,
        token_file=Path(token_file) if token_file else None,
        service_account_file=(
            Path(service_account_file) if service_account_file else None
        ),
    )


def get_oauth_credentials(config: GoogleConfig) -> Credentials:
    if not config.credentials_file:
        raise RuntimeError(
            "Missing required environment variable: GOOGLE_CREDENTIALS_FILE"
        )
    if not config.token_file:
        raise RuntimeError("Missing required environment variable: GOOGLE_TOKEN_FILE")

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


def get_service_account_credentials(
    config: GoogleConfig,
) -> ServiceAccountCredentials:
    if not config.service_account_file:
        raise RuntimeError(
            "Missing required environment variable: GOOGLE_SERVICE_ACCOUNT_FILE"
        )
    if not config.service_account_file.exists():
        raise RuntimeError(
            f"Google service account file not found: {config.service_account_file}"
        )
    return ServiceAccountCredentials.from_service_account_file(
        str(config.service_account_file),
        scopes=SCOPES,
    )


def build_service(config: GoogleConfig):
    if config.auth_mode == "service_account":
        credentials = get_service_account_credentials(config)
    else:
        credentials = get_oauth_credentials(config)
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


def calendar_sync_filters(app_config: AppConfig) -> FilterConfig:
    """Keep terminal booking statuses eligible for historical calendar sync."""
    filters = app_config.filters
    historical_statuses = app_config.sync.historical_statuses

    if filters.include_statuses:
        include_statuses = tuple(
            dict.fromkeys((*filters.include_statuses, *historical_statuses))
        )
    else:
        include_statuses = ()

    historical_status_set = set(historical_statuses)
    exclude_statuses = tuple(
        status
        for status in filters.exclude_statuses
        if status not in historical_status_set
    )
    return FilterConfig(
        include_statuses=include_statuses,
        exclude_statuses=exclude_statuses,
        include_types=filters.include_types,
        exclude_types=filters.exclude_types,
    )


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


def action_from_booking(action: str, booking: Booking, app_config: AppConfig) -> SyncAction:
    return SyncAction(
        action=action,
        reservation_id=booking.reservation_id,
        summary=render_event_summary(booking, app_config.events),
        guest=booking.guest,
        unit=booking.unit,
        source_type=booking.source_type,
        status=booking.status,
        check_in=booking.check_in.isoformat(),
        checkout=booking.checkout.isoformat(),
    )


def action_from_event(action: str, reservation_id: str, event: dict[str, Any]) -> SyncAction:
    private = event.get("extendedProperties", {}).get("private", {})
    return SyncAction(
        action=action,
        reservation_id=reservation_id,
        summary=event.get("summary", ""),
        guest="",
        unit="",
        source_type=private.get("sourceType", ""),
        status="",
        check_in=event.get("start", {}).get("date", ""),
        checkout=event.get("end", {}).get("date", ""),
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


def event_has_ended(event: dict[str, Any], today: date | None = None) -> bool:
    """Return whether an event is historical, accounting for all-day end exclusivity."""
    end = event.get("end", {})
    raw_end = end.get("date")
    if raw_end:
        try:
            end_date = date.fromisoformat(raw_end)
        except ValueError:
            return False
    else:
        raw_end = end.get("dateTime")
        if not raw_end:
            return False
        try:
            end_date = datetime.fromisoformat(raw_end.replace("Z", "+00:00")).date()
        except ValueError:
            return False

    return end_date <= (today or date.today())


def sync_google_calendar(csv_path: Path, dry_run: bool, app_config: AppConfig) -> dict[str, Any]:
    google_config = load_google_config()
    booking_report = load_booking_report(csv_path, calendar_sync_filters(app_config))
    bookings = booking_report.bookings
    desired_by_reservation = {
        booking.reservation_id: event_payload(booking, app_config) for booking in bookings
    }
    booking_by_reservation = {booking.reservation_id: booking for booking in bookings}

    service = build_service(google_config)
    existing_events = iter_managed_events(service, google_config.calendar_id, app_config)
    existing_by_reservation = {
        reservation_id: event
        for event in existing_events
        if (reservation_id := reservation_id_for_event(event))
    }

    creates: list[SyncAction] = []
    updates: list[SyncAction] = []
    deletes: list[SyncAction] = []

    for reservation_id, payload in desired_by_reservation.items():
        existing = existing_by_reservation.get(reservation_id)
        if existing is None:
            creates.append(
                action_from_booking(
                    "create",
                    booking_by_reservation[reservation_id],
                    app_config,
                )
            )
            if not dry_run:
                service.events().insert(
                    calendarId=google_config.calendar_id,
                    body=payload,
                ).execute()
            continue

        if not events_equal(existing, payload):
            updates.append(
                action_from_booking(
                    "update",
                    booking_by_reservation[reservation_id],
                    app_config,
                )
            )
            if not dry_run:
                service.events().patch(
                    calendarId=google_config.calendar_id,
                    eventId=existing["id"],
                    body=payload,
                ).execute()

    for reservation_id, event in existing_by_reservation.items():
        if reservation_id in desired_by_reservation:
            continue
        if event_has_ended(event):
            continue
        deletes.append(action_from_event("delete", reservation_id, event))
        if not dry_run:
            service.events().delete(
                calendarId=google_config.calendar_id,
                eventId=event["id"],
            ).execute()

    return {
        "dry_run": dry_run,
        "calendar_id": google_config.calendar_id,
        "auth_mode": google_config.auth_mode,
        "rows_read": booking_report.total_rows,
        "bookings_considered": len(bookings),
        "ignored_counts": booking_report.ignored_counts,
        "ignored_samples": [sample.to_dict() for sample in booking_report.ignored_samples],
        "creates": [action.to_dict() for action in creates],
        "updates": [action.to_dict() for action in updates],
        "deletes": [action.to_dict() for action in deletes],
    }

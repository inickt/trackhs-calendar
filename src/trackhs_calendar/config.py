from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class FilterConfig:
    include_statuses: tuple[str, ...]
    exclude_statuses: tuple[str, ...]
    include_types: tuple[str, ...]
    exclude_types: tuple[str, ...]


@dataclass(frozen=True)
class EventConfig:
    summary: str
    description: str


@dataclass(frozen=True)
class SyncBehaviorConfig:
    managed_by: str
    past_years: int
    future_years: int


@dataclass(frozen=True)
class NotifyConfig:
    known_statuses: tuple[str, ...]
    known_types: tuple[str, ...]
    notify_on_actions: bool
    notify_on_unknown_values: bool
    notify_on_zero_bookings: bool


@dataclass(frozen=True)
class AppConfig:
    filters: FilterConfig
    events: EventConfig
    sync: SyncBehaviorConfig
    notify: NotifyConfig


DEFAULT_CONFIG = AppConfig(
    filters=FilterConfig(
        include_statuses=("Confirmed", "Checked In"),
        exclude_statuses=(),
        include_types=("Website", "Airbnb", "VRBO", "Phone Guest"),
        exclude_types=(),
    ),
    events=EventConfig(
        summary="Booked: {source_type}",
        description=(
            "Managed by trackhs-calendar.\n"
            "Reservation ID: {reservation_id}\n"
            "Status: {status}\n"
            "Type: {source_type}\n"
            "Unit: {unit}\n"
            "Booked Date: {booked_date}"
        ),
    ),
    sync=SyncBehaviorConfig(
        managed_by="trackhs-calendar",
        past_years=1,
        future_years=5,
    ),
    notify=NotifyConfig(
        known_statuses=("Confirmed", "Checked In", "Checked Out"),
        known_types=(
            "Website",
            "Airbnb",
            "VRBO",
            "Phone Guest",
            "Owner",
            "Owner Stay - Clean After",
            "Owner Stay - No Clean",
            "Owner Guest",
            "Owner Referral",
            "Long Term",
            "Home2Go",
            "Comp Stay",
            "Wedding",
            "Maintenance Block",
            "Housekeeping Block",
            "Wander",
        ),
        notify_on_actions=True,
        notify_on_unknown_values=True,
        notify_on_zero_bookings=True,
    ),
)


def _read_section(data: dict, section: str) -> dict:
    value = data.get(section, {})
    if not isinstance(value, dict):
        raise RuntimeError(f"Config section [{section}] must be a table.")
    return value


def _read_string_list(section: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = section.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Config key must be a string list: {key}")
    return tuple(item.strip() for item in value if item.strip())


def _read_string(section: dict, key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Config key must be a non-empty string: {key}")
    return value


def _read_int(section: dict, key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int):
        raise RuntimeError(f"Config key must be an integer: {key}")
    return value


def load_app_config(config_path: Path) -> AppConfig:
    if config_path.exists():
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    else:
        data = {}

    filters = _read_section(data, "filters")
    events = _read_section(data, "events")
    sync = _read_section(data, "sync")
    notify = _read_section(data, "notify")

    return AppConfig(
        filters=FilterConfig(
            include_statuses=_read_string_list(
                filters, "include_statuses", DEFAULT_CONFIG.filters.include_statuses
            ),
            exclude_statuses=_read_string_list(
                filters, "exclude_statuses", DEFAULT_CONFIG.filters.exclude_statuses
            ),
            include_types=_read_string_list(
                filters, "include_types", DEFAULT_CONFIG.filters.include_types
            ),
            exclude_types=_read_string_list(
                filters, "exclude_types", DEFAULT_CONFIG.filters.exclude_types
            ),
        ),
        events=EventConfig(
            summary=_read_string(events, "summary", DEFAULT_CONFIG.events.summary),
            description=_read_string(
                events, "description", DEFAULT_CONFIG.events.description
            ),
        ),
        sync=SyncBehaviorConfig(
            managed_by=_read_string(
                sync, "managed_by", DEFAULT_CONFIG.sync.managed_by
            ),
            past_years=_read_int(sync, "past_years", DEFAULT_CONFIG.sync.past_years),
            future_years=_read_int(
                sync, "future_years", DEFAULT_CONFIG.sync.future_years
            ),
        ),
        notify=NotifyConfig(
            known_statuses=_read_string_list(
                notify, "known_statuses", DEFAULT_CONFIG.notify.known_statuses
            ),
            known_types=_read_string_list(
                notify, "known_types", DEFAULT_CONFIG.notify.known_types
            ),
            notify_on_actions=bool(
                notify.get("notify_on_actions", DEFAULT_CONFIG.notify.notify_on_actions)
            ),
            notify_on_unknown_values=bool(
                notify.get(
                    "notify_on_unknown_values",
                    DEFAULT_CONFIG.notify.notify_on_unknown_values,
                )
            ),
            notify_on_zero_bookings=bool(
                notify.get(
                    "notify_on_zero_bookings",
                    DEFAULT_CONFIG.notify.notify_on_zero_bookings,
                )
            ),
        ),
    )

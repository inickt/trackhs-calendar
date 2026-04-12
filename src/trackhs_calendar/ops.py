from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import AppConfig
from .trackhs import BookingLoadResult


def get_optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def post_json(url: str, payload: dict) -> None:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15):
        pass


def ping_url(url: str) -> None:
    with urlopen(url, timeout=15):
        pass


def ping_healthchecks_start() -> None:
    base = get_optional_env("HEALTHCHECKS_PING_URL")
    if not base:
        return
    ping_url(f"{base.rstrip('/')}/start")


def ping_healthchecks_success() -> None:
    base = get_optional_env("HEALTHCHECKS_PING_URL")
    if not base:
        return
    ping_url(base)


def ping_healthchecks_fail(message: str) -> None:
    base = get_optional_env("HEALTHCHECKS_PING_URL")
    if not base:
        return
    ping_url(f"{base.rstrip('/')}/fail")
    log_url = f"{base.rstrip('/')}/log"
    payload = Request(
        log_url,
        data=message.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    with urlopen(payload, timeout=15):
        pass


def send_telegram_message(text: str) -> None:
    token = get_optional_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_optional_env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
        },
    )


@dataclass(frozen=True)
class AnomalyReport:
    unknown_statuses: tuple[str, ...]
    unknown_types: tuple[str, ...]
    zero_bookings: bool

    def has_any(self) -> bool:
        return bool(self.unknown_statuses or self.unknown_types or self.zero_bookings)


def detect_anomalies(report: BookingLoadResult, app_config: AppConfig) -> AnomalyReport:
    statuses = sorted({booking.status for booking in report.bookings})
    types = sorted({booking.source_type for booking in report.bookings})
    unknown_statuses = tuple(
        status for status in statuses if status not in app_config.notify.known_statuses
    )
    unknown_types = tuple(
        source_type for source_type in types if source_type not in app_config.notify.known_types
    )
    return AnomalyReport(
        unknown_statuses=unknown_statuses,
        unknown_types=unknown_types,
        zero_bookings=len(report.bookings) == 0,
    )


def build_action_summary_lines(sync_result: dict) -> list[str]:
    lines: list[str] = []
    for key in ("creates", "updates", "deletes"):
        actions = sync_result.get(key, [])
        if not actions:
            continue
        lines.append(f"{key}: {len(actions)}")
        for action in actions[:5]:
            guest = action.get("guest") or "--"
            source_type = action.get("source_type") or "--"
            status = action.get("status") or "--"
            lines.append(
                f"- {action['action']} {action['reservation_id']} | {guest} | "
                f"type={source_type} | status={status} | "
                f"{action['check_in']} -> {action['checkout']}"
            )
    return lines


def maybe_notify(sync_result: dict, booking_report: BookingLoadResult, app_config: AppConfig) -> None:
    anomaly_report = detect_anomalies(booking_report, app_config)
    sections: list[str] = []

    if app_config.notify.notify_on_unknown_values and anomaly_report.has_any():
        if anomaly_report.unknown_types:
            sections.append(
                "Unexpected types: " + ", ".join(anomaly_report.unknown_types)
            )
        if anomaly_report.unknown_statuses:
            sections.append(
                "Unexpected statuses: " + ", ".join(anomaly_report.unknown_statuses)
            )
        if anomaly_report.zero_bookings and app_config.notify.notify_on_zero_bookings:
            sections.append("Zero bookings matched the current filters.")

    if app_config.notify.notify_on_actions:
        action_lines = build_action_summary_lines(sync_result)
        if action_lines:
            sections.append("\n".join(action_lines))

    if not sections:
        return

    message = "\n\n".join(
        [
            "trackhs-calendar alert",
            f"rows read: {sync_result['rows_read']}",
            f"included bookings: {sync_result['bookings_considered']}",
            *sections,
        ]
    )
    send_telegram_message(message)

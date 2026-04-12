from __future__ import annotations

from .config import EventConfig
from .trackhs import Booking


class BookingFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise RuntimeError(f"Unknown booking template field: {key}")


def booking_template_context(booking: Booking) -> BookingFormatDict:
    return BookingFormatDict(booking.to_dict())


def render_event_summary(booking: Booking, config: EventConfig) -> str:
    return config.summary.format_map(booking_template_context(booking))


def render_event_description(booking: Booking, config: EventConfig) -> str:
    return config.description.format_map(booking_template_context(booking))

from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


class SecurityTokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.security_token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return

        attr_map = dict(attrs)
        if attr_map.get("name") == "security":
            self.security_token = attr_map.get("value")


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_request(url: str, data: dict[str, str] | None = None) -> Request:
    headers = {
        "User-Agent": "trackhs-calendar/0.1.0",
    }
    encoded = None
    if data is not None:
        encoded = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    return Request(url, data=encoded, headers=headers)


def read_text(opener, request: Request) -> str:
    with opener.open(request) as response:
        return response.read().decode("utf-8", errors="replace")


def login(opener, base_url: str, username: str, password: str) -> None:
    login_url = urljoin(base_url, "/owner")
    login_page = read_text(opener, build_request(login_url))

    parser = SecurityTokenParser()
    parser.feed(login_page)
    if not parser.security_token:
        raise RuntimeError("Could not find the TrackHS login security token.")

    request = build_request(
        login_url,
        data={
            "username": username,
            "password": password,
            "security": parser.security_token,
        },
    )
    response_body = read_text(opener, request)
    if "Owner Connect Login" in response_body:
        raise RuntimeError("TrackHS login failed. Check the supplied credentials.")


def export_reservations_csv(
    output_path: Path,
    start_date: str,
    end_date: str,
    unit: str,
    search: str,
) -> None:
    username = get_env("TRACKHS_USERNAME")
    password = get_env("TRACKHS_PASSWORD")
    base_url = get_env("TRACKHS_BASE_URL").rstrip("/")

    opener = build_opener(HTTPCookieProcessor())

    try:
        login(opener, base_url, username, password)

        export_url = urljoin(base_url, "/owner/reservations/generate-csv/")
        request = build_request(
            export_url,
            data={
                "startDate": start_date,
                "endDate": end_date,
                "unit": unit,
                "search": search,
            },
        )

        with opener.open(request) as response:
            content_type = response.headers.get("Content-Type", "")
            payload = response.read()

        if "text/csv" not in content_type:
            raise RuntimeError(
                f"Expected a CSV export from TrackHS, got Content-Type {content_type!r}."
            )

        output_path.write_bytes(payload)
    except HTTPError as exc:
        raise RuntimeError(
            f"TrackHS request failed with HTTP {exc.code} for {exc.url}."
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"TrackHS request failed: {exc.reason}") from exc

## TrackHS Calendar

Small `uv`-managed Python CLI for turning TrackHS owner CSV exports into normalized guest bookings, with Google Calendar sync to be added next.

This project targets Python 3.13 and relies on `pyproject.toml` for uv's Python selection instead of `.python-version`.

Current behavior:
- logs into the TrackHS owner portal and exports the reservations CSV
- parses `download.csv` exports
- keeps only guest bookings from `Website`, `Airbnb`, `VRBO`, and `Phone Guest`
- keeps only `Confirmed` and `Checked In` reservations
- syncs managed booking events into Google Calendar
- prints normalized booking records as JSON

Usage:

```sh
uv run --env-file .env trackhs-calendar fetch
```

```sh
uv run trackhs-calendar preview --pretty
```

```sh
uv run --env-file .env trackhs-calendar sync --dry-run
```

```sh
uv run --env-file .env trackhs-calendar run
```

Optional fetch filters:

```sh
uv run --env-file .env trackhs-calendar fetch \
  --start-date 2026-01-01 \
  --end-date 2026-12-31
```

Environment variables:
- `TRACKHS_USERNAME`: owner portal username
- `TRACKHS_PASSWORD`: owner portal password
- `TRACKHS_BASE_URL`: owner portal base URL, for example `https://example.trackhs.com`
- `GOOGLE_CALENDAR_ID`: target Google Calendar ID
- `GOOGLE_CREDENTIALS_FILE`: OAuth client JSON path from Google Cloud
- `GOOGLE_TOKEN_FILE`: local token cache path written after first auth

Local env setup:
- `.env` is ignored by git and intended for local secrets
- `.env.example` is checked in as the template
- `uv run --env-file .env ...` loads the file explicitly
- `credentials.json` and `token.json` are ignored by git

Google Calendar sync:
- create a dedicated Google Calendar for the rental
- create a Google Cloud desktop OAuth client and place its JSON at `credentials.json`
- first `sync` run will open a browser for consent and write `token.json`
- synced events are marked with private extended properties so only managed events are touched

Recommended scheduled entrypoint:
- use `uv run --env-file .env trackhs-calendar run`
- add `--dry-run` if you want fetch plus reconciliation preview without writing to Google

The local export file `download.csv` is intentionally ignored by git.

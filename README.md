## TrackHS Calendar

Small `uv`-managed Python CLI for turning TrackHS owner CSV exports into normalized guest bookings, with Google Calendar sync to be added next.

This project targets Python 3.13 and relies on `pyproject.toml` for uv's Python selection instead of `.python-version`.

Current behavior:
- logs into the TrackHS owner portal and exports the reservations CSV
- parses `download.csv` exports
- applies built-in defaults, optionally overridden by `config.toml`
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

```sh
uv run --env-file .env trackhs-calendar run --dry-run --verbose
```

```sh
uv run --env-file .env trackhs-calendar run --dry-run --json
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
- `GOOGLE_AUTH_MODE`: `oauth` or `service_account`
- `GOOGLE_CREDENTIALS_FILE`: OAuth client JSON path from Google Cloud
- `GOOGLE_TOKEN_FILE`: local token cache path written after first OAuth auth
- `GOOGLE_SERVICE_ACCOUNT_FILE`: service account JSON path for headless auth
- `TELEGRAM_BOT_TOKEN`: optional Telegram bot token for alerts
- `TELEGRAM_CHAT_ID`: optional Telegram chat ID for alerts
- `HEALTHCHECKS_PING_URL`: optional Healthchecks ping URL for liveness monitoring

Local env setup:
- `.env` is ignored by git and intended for local secrets
- `.env.example` is checked in as the template
- `uv run --env-file .env ...` loads the file explicitly
- `credentials.json`, `token.json`, and `service-account.json` are ignored by git

Behavior config:
- the app runs without a config file by using built-in defaults
- `config.toml.example` is checked in as a starting point for local overrides
- `config.toml` is ignored by git and can override filtering, event templates, and sync policy
- template fields available in event strings:
  `reservation_id`, `status`, `source_type`, `unit`, `guest`, `booked_date`, `check_in`, `checkout`
- pass `--config path/to/config.toml` to use a different behavior profile

Google Calendar sync:
- create a dedicated Google Calendar for the rental
- for `oauth` mode, create a Google Cloud desktop OAuth client and place its JSON at `credentials.json`
- first OAuth `sync` run will open a browser for consent and write `token.json`
- for `service_account` mode, create a service account JSON key at `service-account.json` and share the target calendar with that service account email
- synced events are marked with private extended properties so only managed events are touched

Recommended scheduled entrypoint:
- use `uv run --env-file .env trackhs-calendar run`
- add `--dry-run` if you want fetch plus reconciliation preview without writing to Google

Output modes:
- default `fetch`, `sync`, and `run` output is human-readable text
- add `--verbose` to include ignored-row samples and per-event action details
- add `--json` for machine-readable output

Long-term monitoring:
- `run` sends Healthchecks start/success/fail pings when `HEALTHCHECKS_PING_URL` is set
- `run` can send Telegram alerts for unexpected types/statuses, zero-booking results, and CRUD actions
- these alerts are optional and only activate when the relevant environment variables are set

The local export file `download.csv` is intentionally ignored by git.

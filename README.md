## TrackHS Calendar

Small `uv`-managed Python CLI for turning TrackHS owner CSV exports into normalized guest bookings, with Google Calendar sync to be added next.

Current behavior:
- logs into the TrackHS owner portal and exports the reservations CSV
- parses `download.csv` exports
- keeps only guest bookings from `Website`, `Airbnb`, `VRBO`, and `Phone Guest`
- keeps only `Confirmed` and `Checked In` reservations
- prints normalized booking records as JSON

Usage:

```sh
uv run --env-file .env trackhs-calendar fetch
```

```sh
uv run trackhs-calendar preview --pretty
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

Local env setup:
- `.env` is ignored by git and intended for local secrets
- `.env.example` is checked in as the template
- `uv run --env-file .env ...` loads the file explicitly

The local export file `download.csv` is intentionally ignored by git.

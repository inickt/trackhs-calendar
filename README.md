## TrackHS Calendar

Small `uv`-managed Python CLI for turning TrackHS owner CSV exports into normalized guest bookings, with Google Calendar sync to be added next.

Current behavior:
- parses `download.csv` exports
- keeps only guest bookings from `Website`, `Airbnb`, `VRBO`, and `Phone Guest`
- keeps only `Confirmed` and `Checked In` reservations
- prints normalized booking records as JSON

Usage:

```sh
uv run trackhs-calendar preview --pretty
```

The local export file `download.csv` is intentionally ignored by git.

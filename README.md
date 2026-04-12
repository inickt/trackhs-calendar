# TrackHS Calendar

`trackhs-calendar` is a small Python CLI for syncing vacation-rental bookings from a TrackHS owner portal into Google Calendar.

The intended use case is a rental property calendar that family members or co-owners can subscribe to, so everyone can see when the property is booked.

At a high level, the tool:
- logs into a TrackHS owner portal
- exports the reservations CSV
- filters and normalizes reservation rows
- creates, updates, and deletes managed events in Google Calendar
- optionally sends monitoring alerts

The project uses `uv` and targets Python `3.13`.

**How It Works**
The sync is one-way:

1. Fetch the latest reservation export from TrackHS.
2. Apply booking filters from built-in defaults or `config.toml`.
3. Render calendar event titles and descriptions from templates.
4. Reconcile Google Calendar so managed events match the latest CSV.

The Google sync is idempotent. Each managed event stores its `reservationId` in private extended properties, so rerunning the tool updates only events owned by this integration.

**Project Layout**
- `.env`: local secrets and runtime configuration, ignored by git
- `.env.example`: checked-in environment template
- `config.toml`: optional local behavior override, ignored by git
- `config.toml.example`: checked-in behavior example
- `download.csv`: local export file, ignored by git

**Environment Setup**
Copy `.env.example` to `.env` and fill in the values you need.

TrackHS:
- `TRACKHS_BASE_URL`: owner portal base URL, for example `https://example.trackhs.com`
- `TRACKHS_USERNAME`: owner portal username
- `TRACKHS_PASSWORD`: owner portal password

Google:
- `GOOGLE_CALENDAR_ID`: target Google Calendar ID
- `GOOGLE_AUTH_MODE`: `oauth` or `service_account`
- `GOOGLE_CREDENTIALS_FILE`: OAuth client JSON path
- `GOOGLE_TOKEN_FILE`: OAuth token cache path
- `GOOGLE_SERVICE_ACCOUNT_FILE`: service account JSON path

Optional monitoring:
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `TELEGRAM_CHAT_ID`: Telegram chat or group ID
- `HEALTHCHECKS_PING_URL`: Healthchecks ping URL

Git ignores local secret and auth files by default, including `.env`, `credentials.json`, `token.json`, `service-account.json`, and `download.csv`.

**Behavior Configuration**
The app works without a config file by using built-in defaults.

If you want local behavior overrides, create `config.toml` from `config.toml.example`. Typical settings are:
- which reservation `types` and `statuses` to include
- how event `summary` and `description` are rendered
- sync window and managed event marker
- notification policy for unknown values and zero-booking runs

Template fields available in event strings:
- `reservation_id`
- `status`
- `source_type`
- `unit`
- `guest`
- `booked_date`
- `check_in`
- `checkout`

You can also point at a different config file with `--config path/to/config.toml`.

**Google Authentication**
Two auth modes are supported.

`oauth`:
- use a Google Cloud desktop OAuth client JSON
- first sync opens a browser for consent
- token refresh state is stored in `GOOGLE_TOKEN_FILE`
- best for local development and self-hosted runs

`service_account`:
- use a service account JSON key
- share the target Google Calendar with the service account email
- no browser flow and no token cache
- better for headless deployment such as GitHub Actions

Using a dedicated Google Calendar for the rental is strongly recommended.

**Commands**
Fetch the latest CSV:

```sh
uv run --env-file .env trackhs-calendar fetch
```

Preview normalized bookings:

```sh
uv run trackhs-calendar preview --pretty
```

Dry-run a Google Calendar sync:

```sh
uv run --env-file .env trackhs-calendar sync --dry-run
```

Run the full fetch + sync flow:

```sh
uv run --env-file .env trackhs-calendar run
```

Verbose dry-run:

```sh
uv run --env-file .env trackhs-calendar run --dry-run --verbose
```

Machine-readable JSON output:

```sh
uv run --env-file .env trackhs-calendar run --dry-run --json
```

Optional date range for TrackHS fetch:

```sh
uv run --env-file .env trackhs-calendar fetch \
  --start-date 2026-01-01 \
  --end-date 2026-12-31
```

**Output**
Default output from `fetch`, `sync`, and `run` is human-readable text.

Use:
- `--verbose` for ignored-row samples and per-event action details
- `--json` for machine-readable output

Dry-runs do not write to Google Calendar and do not send Healthchecks or Telegram notifications.

**Monitoring**
If configured, `run` can:
- send Healthchecks start, success, and failure pings
- send Telegram alerts for creates, updates, deletes, unexpected types or statuses, and zero-booking runs

This is useful for long-running scheduled deployments where you want to know:
- the script stopped running
- the script failed
- reservation data changed
- TrackHS started returning unexpected values

**Deployment**
The recommended scheduled entrypoint is:

```sh
uv run --env-file .env trackhs-calendar run
```

This works well for:
- a local server with `cron`, `systemd`, or `launchd`
- GitHub Actions
- other headless schedulers

For GitHub Actions or other ephemeral runners, `service_account` mode is usually the simpler Google auth option.

**GitHub Actions**
The repository includes one workflow:
- `.github/workflows/trackhs-calendar-sync.yml`: daily sync plus manual `workflow_dispatch`

The sync workflow expects these repository secrets:
- `TRACKHS_BASE_URL`
- `TRACKHS_USERNAME`
- `TRACKHS_PASSWORD`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `HEALTHCHECKS_PING_URL`
- `TRACKHS_CALENDAR_CONFIG_TOML`

Only the first five are required. `TRACKHS_CALENDAR_CONFIG_TOML` is optional and can contain the contents of a local `config.toml` if you want GitHub Actions to use a custom filter or event template.

The workflow passes secrets as environment variables at runtime. It only writes `service-account.json` and optional `config.toml` to disk inside the runner.

The workflow runs the default text output, not `--verbose` or `--json`, to reduce the chance of printing guest-level details into Actions logs.

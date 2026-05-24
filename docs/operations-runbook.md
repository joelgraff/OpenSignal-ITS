# OpenSignal ITS Operations Runbook

This runbook records operational requirements that must be preserved across releases and handoffs.

## Safety-Critical Runtime Controls

1. Commands are denied unless an operator is authenticated.
2. Write mode is denied unless explicitly unlocked.
3. Write commands require per-command confirmation token entry.
4. Probe mode is the default-safe control mode.
5. Sensitive maintenance operations require admin role.

## Required Environment Variables

Production-like modes are defined as `OPENSIGNAL_ENV` in: `prod`, `production`, `staging`, `pilot`.

### Required in production-like modes

- `OPENSIGNAL_OPERATOR_PASSWORD`: Operator login password.
- `OPENSIGNAL_OPERATOR_KEY`: Write-mode unlock key.

### Optional with defaults

- `OPENSIGNAL_OPERATOR_USERNAME`: Defaults to `operator`.
- `OPENSIGNAL_ADMIN_USERNAME`: Defaults to `admin`.
- `OPENSIGNAL_COMMAND_RETENTION_DAYS`: Defaults to `90`.
- `OPENSIGNAL_SNAPSHOT_RETENTION_DAYS`: Defaults to `30`.
- `OPENSIGNAL_APPLY_RETENTION_ON_START`: Defaults to `true`.
- `OPENSIGNAL_DB_PATH`: Defaults to `traffic.db`.
- `OPENSIGNAL_AUDIT_EXPORT_PATH`: Defaults to `runtime_reports/latest_runtime_report.json`.
- `OPENSIGNAL_MAX_LOGIN_ATTEMPTS`: Defaults to `5`.
- `OPENSIGNAL_LOGIN_LOCKOUT_SECONDS`: Defaults to `300`.
- `OPENSIGNAL_ENABLE_RETENTION_SCHEDULER`: Defaults to `false`.
- `OPENSIGNAL_RETENTION_SCHEDULE_SECONDS`: Defaults to `3600` (minimum `300`).
- `OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK`: Defaults to `3`.
- `OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK`: Defaults to `3`.

### Secret and credential options

Credentials and unlock/recovery keys support plaintext, single hash, or rotating hash sets:

- Operator password: `OPENSIGNAL_OPERATOR_PASSWORD`, `OPENSIGNAL_OPERATOR_PASSWORD_HASH`, `OPENSIGNAL_OPERATOR_PASSWORD_HASHES`
- Operator unlock key: `OPENSIGNAL_OPERATOR_KEY`, `OPENSIGNAL_OPERATOR_KEY_HASH`, `OPENSIGNAL_OPERATOR_KEY_HASHES`
- Admin password: `OPENSIGNAL_ADMIN_PASSWORD`, `OPENSIGNAL_ADMIN_PASSWORD_HASH`, `OPENSIGNAL_ADMIN_PASSWORD_HASHES`
- Admin recovery key: `OPENSIGNAL_ADMIN_RECOVERY_KEY`, `OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH`, `OPENSIGNAL_ADMIN_RECOVERY_KEY_HASHES`

Hash format is `sha256:<hex>`.

## Startup Preflight Behavior

At application startup, preflight checks validate runtime configuration.

1. In production-like mode, required secrets must be present.
2. Retention window variables must be positive integers.
3. If plaintext secrets are used in production-like mode, each value must be at least 12 characters.
4. If enabled, retention cleanup is executed on startup.
5. In production-like mode, ops API must be token-protected when enabled unless `OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED=true` is explicitly set.

If preflight fails, startup is blocked.

## Command Audit and Snapshot Logging

Audit data is persisted in SQLite (`traffic.db` by default):

- `command_audit` table: command attempt/result records.
- `status_snapshots` table: periodic and command-result snapshots.

Both tables support correlation via `correlation_id`.

## Retention Operations

Retention can be applied in two ways:

1. Automatically at startup (`OPENSIGNAL_APPLY_RETENTION_ON_START=true`).
2. Manually from the dashboard maintenance action.
3. Periodically with optional scheduler (`OPENSIGNAL_ENABLE_RETENTION_SCHEDULER=true`).

Manual cleanup and audit export operations require an authenticated admin session.

Retention windows:

- Commands: `OPENSIGNAL_COMMAND_RETENTION_DAYS`
- Snapshots: `OPENSIGNAL_SNAPSHOT_RETENTION_DAYS`
- Alarm events: `OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS`

Each retention run also removes expired alarm silences from the `alarm_silences` table.
Retention status now reports deleted alarm event counts.

### Runtime Health Panel

Use the dashboard maintenance panel to validate runtime retention state:

1. Click **Refresh Runtime Health** to pull live scheduler + cleanup status.
2. Confirm scheduler enabled/running state and configured interval.
3. Verify the latest retention cleanup timestamp and outcome message.
4. Use **Export Audit Report** to write recent command/snapshot activity plus runtime metadata to disk.

## Operational API Endpoints

The app exposes read-only operational JSON endpoints for automation and NOC tooling:

1. `GET /api/ops/health`
2. `GET /api/ops/alarms`
: Query params: `window_minutes`, `command_limit`, `snapshot_limit`
3. `GET /api/ops/alarm-history`
: Query params: `limit`, `action_filter`, `actor_contains`, `key_contains`
4. `GET /api/ops/audit-export`
: Query params: `file_path`, `command_limit`, `snapshot_limit`

All responses include a `generated_at` timestamp.
Audit export returns the resolved report `file_path` and writes command/snapshot activity JSON to disk.
Health payload includes storage table row counts under `storage.table_row_counts`.
Health payload includes growth warnings under `storage.warnings`.
Warnings include severity levels (`warn`, `critical`) and persistence-based alerts under `storage.persistent_alerts`.

Optional webhook dispatch for persistent alerts can be enabled with:

- `OPENSIGNAL_ALERT_WEBHOOK_ENABLED`
- `OPENSIGNAL_ALERT_WEBHOOK_URL`
- `OPENSIGNAL_ALERT_WEBHOOK_DEDUP_SECONDS`
- `OPENSIGNAL_ALERT_WEBHOOK_TIMEOUT_SECONDS`
- `OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES`

Dispatch status is exposed in ops health payload under `storage.alert_dispatch`.

Persistent alert dispatch uses durable SQLite tables:

- `alert_webhook_queue` for pending retries
- `alert_webhook_deadletter` for exhausted retry attempts

Dead-letter volume is visible through storage table row counts in ops health.

Storage warning threshold environment variables:

- `OPENSIGNAL_DB_WARN_COMMAND_AUDIT_ROWS`
- `OPENSIGNAL_DB_WARN_STATUS_SNAPSHOTS_ROWS`
- `OPENSIGNAL_DB_WARN_ALARM_ACK_ROWS`
- `OPENSIGNAL_DB_WARN_ALARM_SILENCES_ROWS`
- `OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS`
- `OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_QUEUE_ROWS`
- `OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_DEADLETTER_ROWS`
- `OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS`

For deterministic unit/integration tests, endpoint handlers are also exposed in app module map `OPS_API_ENDPOINTS`.

Access controls:

- `OPENSIGNAL_OPS_API_ENABLED` (`true`/`false`) to enable or disable route registration.
- Required token controls by default:
	- `OPENSIGNAL_OPS_API_TOKEN`
	- `OPENSIGNAL_OPS_API_TOKEN_HASH`
	- `OPENSIGNAL_OPS_API_TOKEN_HASHES`
- Local-only override (not recommended outside isolated dev):
	- `OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED`

Provide auth using `Authorization: Bearer <token>` (preferred). Legacy `api_token` query param remains supported for compatibility.

Audit export writes are restricted to `OPENSIGNAL_AUDIT_EXPORT_DIR` (default `runtime_reports`).

### Managed Polling Runtime Controls

Use site polling controls to manage long-lived controller polling tasks:

1. Select a target site profile (`selected_device_id`).
2. Set managed polling interval seconds.
3. Start or stop managed polling for the selected site.
4. Refresh active poll sessions to verify running polling loops.
5. Use site-wide controls to start/stop polling across all configured profiles (admin-authenticated sessions only).

### Event Timeline and Alarms

The dashboard can compute event timeline and alarms from persisted command/snapshot activity:

1. Use **Refresh Timeline** to rebuild timeline rows from recent command and snapshot history.
2. Use the window controls (**15m**, **1h**, **24h**, **All**) to focus on current incidents or review longer history.
3. Offline streak alarm triggers when a device has N consecutive offline snapshots.
4. Command failure streak alarm triggers when a device has N consecutive failed commands.
5. Admin users can acknowledge alarms with a note and later clear acknowledgements.
6. Alarm list is severity-prioritized (critical before high).
7. Admin users can silence individual alarms for a bounded number of minutes; silenced alarms are hidden from active alarms until expiry or manual clear.
8. Use **Use Policy** to auto-fill silence duration from policy defaults.
9. Review **Alarm History** to verify acknowledge/silence/clear activity with actor and timestamp.
10. Use history filters to focus by action type, actor fragment, alarm key fragment, and row limit.

Silence policy environment variables:

- `OPENSIGNAL_ALARM_SILENCE_DEFAULT_MINUTES` (fallback for unknown alarms)
- `OPENSIGNAL_ALARM_SILENCE_CRITICAL_MINUTES`
- `OPENSIGNAL_ALARM_SILENCE_HIGH_MINUTES`
- `OPENSIGNAL_ALARM_SILENCE_OFFLINE_STREAK_MINUTES`
- `OPENSIGNAL_ALARM_SILENCE_COMMAND_FAILURE_STREAK_MINUTES`

## Operator Workflow (Write Commands)

1. Login as operator.
2. Unlock write mode with valid operator key.
3. Initiate command.
4. Enter generated confirmation token before expiry.
5. Confirm and execute.

If any step fails, command execution is denied and denial is audited.

## Login Lockout Policy

1. Failed operator logins are counted.
2. After `OPENSIGNAL_MAX_LOGIN_ATTEMPTS`, login is temporarily locked.
3. Lockout duration is `OPENSIGNAL_LOGIN_LOCKOUT_SECONDS`.
4. Successful login resets failure counters and lockout state.

## Admin Recovery Workflow

1. Enter admin recovery key in the dashboard.
2. Run **Reset Login Lockout**.
3. Re-attempt operator/admin login.

## Regression Test Baseline

Run:

```bash
.venv/bin/python -m unittest discover -s opensignal_its/tests -p 'test_*.py'
```

Current baseline includes:

1. Operator authentication service tests.
2. Command safety policy tests.
3. Audit persistence and retention tests.
4. Startup preflight tests.
5. Dry Reflex compile smoke coverage via `python -m reflex compile --dry --no-rich`.

## Known Operational Constraints

1. Authentication is single-operator credential based (no multi-role RBAC yet).
2. Audit retention uses simple day-based cleanup in SQLite.
3. Command OIDs remain controller/vendor dependent and must be validated before production writes.

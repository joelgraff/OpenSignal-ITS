"""SQLite-backed audit persistence for command and telemetry events."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CommandAuditRecord:
    timestamp: str
    correlation_id: str
    device_ip: str
    command_type: str
    command_value: Any
    probe_only: bool
    allowed: bool
    success: bool
    error: str
    actor: str


class AuditStore:
    """Simple thread-safe SQLite writer for command and status records."""

    def __init__(self, db_path: str | None = None):
        self._lock = Lock()
        configured = db_path or os.getenv("OPENSIGNAL_DB_PATH", "traffic.db")
        self._db_path = str(Path(configured))
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS command_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        correlation_id TEXT,
                        device_ip TEXT NOT NULL,
                        command_type TEXT NOT NULL,
                        command_value_json TEXT,
                        probe_only INTEGER NOT NULL,
                        allowed INTEGER NOT NULL,
                        success INTEGER NOT NULL,
                        error TEXT,
                        actor TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS status_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        correlation_id TEXT,
                        source TEXT NOT NULL,
                        device_ip TEXT NOT NULL,
                        is_online INTEGER NOT NULL,
                        status_text TEXT,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_command_audit_timestamp ON command_audit(timestamp)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_status_snapshots_timestamp ON status_snapshots(timestamp)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alarm_acknowledgements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alarm_key TEXT NOT NULL UNIQUE,
                        acknowledged_at TEXT NOT NULL,
                        acknowledged_by TEXT NOT NULL,
                        note TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alarm_silences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alarm_key TEXT NOT NULL UNIQUE,
                        silenced_at TEXT NOT NULL,
                        silenced_until TEXT NOT NULL,
                        silenced_by TEXT NOT NULL,
                        note TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alarm_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        alarm_key TEXT NOT NULL,
                        action TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        note TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_alarm_events_timestamp ON alarm_events(timestamp)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_webhook_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        alert_key TEXT NOT NULL UNIQUE,
                        payload_json TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_webhook_deadletter (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        failed_at TEXT NOT NULL,
                        alert_key TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        attempts INTEGER NOT NULL,
                        last_error TEXT
                    )
                    """
                )
                self._ensure_legacy_columns(conn)

    @staticmethod
    def _ensure_legacy_columns(conn: sqlite3.Connection) -> None:
        command_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(command_audit)")
        }
        if "correlation_id" not in command_columns:
            conn.execute("ALTER TABLE command_audit ADD COLUMN correlation_id TEXT")

        snapshot_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(status_snapshots)")
        }
        if "correlation_id" not in snapshot_columns:
            conn.execute("ALTER TABLE status_snapshots ADD COLUMN correlation_id TEXT")
        if "source" not in snapshot_columns:
            conn.execute("ALTER TABLE status_snapshots ADD COLUMN source TEXT NOT NULL DEFAULT 'poll'")

    def log_command(self, record: CommandAuditRecord) -> None:
        value_json = json.dumps(record.command_value)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO command_audit (
                        timestamp, correlation_id, device_ip, command_type, command_value_json,
                        probe_only, allowed, success, error, actor
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.timestamp,
                        record.correlation_id,
                        record.device_ip,
                        record.command_type,
                        value_json,
                        int(record.probe_only),
                        int(record.allowed),
                        int(record.success),
                        record.error,
                        record.actor,
                    ),
                )

    def log_status_snapshot(
        self,
        device_ip: str,
        payload: dict[str, Any],
        correlation_id: str = "",
        source: str = "poll",
    ) -> None:
        timestamp = str(payload.get("timestamp") or _utc_now_iso())
        is_online = bool(payload.get("is_online", False))
        status_text = str(payload.get("status_text", ""))
        payload_json = json.dumps(payload)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO status_snapshots (
                        timestamp, correlation_id, source, device_ip, is_online, status_text, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        correlation_id,
                        source,
                        device_ip,
                        int(is_online),
                        status_text,
                        payload_json,
                    ),
                )

    def fetch_recent_activity(
        self,
        command_limit: int = 100,
        snapshot_limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        command_limit = max(1, command_limit)
        snapshot_limit = max(1, snapshot_limit)
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                command_rows = conn.execute(
                    """
                    SELECT timestamp, correlation_id, device_ip, command_type, command_value_json,
                           probe_only, allowed, success, error, actor
                    FROM command_audit
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (command_limit,),
                ).fetchall()
                snapshot_rows = conn.execute(
                    """
                    SELECT timestamp, correlation_id, source, device_ip, is_online, status_text
                    FROM status_snapshots
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (snapshot_limit,),
                ).fetchall()

        commands: list[dict[str, Any]] = []
        for row in command_rows:
            command_value = row["command_value_json"]
            try:
                parsed_value: Any = json.loads(command_value) if command_value else None
            except json.JSONDecodeError:
                parsed_value = command_value
            commands.append(
                {
                    "timestamp": row["timestamp"],
                    "correlation_id": row["correlation_id"],
                    "device_ip": row["device_ip"],
                    "command_type": row["command_type"],
                    "command_value": parsed_value,
                    "probe_only": bool(row["probe_only"]),
                    "allowed": bool(row["allowed"]),
                    "success": bool(row["success"]),
                    "error": row["error"],
                    "actor": row["actor"],
                }
            )

        snapshots: list[dict[str, Any]] = []
        for row in snapshot_rows:
            snapshots.append(
                {
                    "timestamp": row["timestamp"],
                    "correlation_id": row["correlation_id"],
                    "source": row["source"],
                    "device_ip": row["device_ip"],
                    "is_online": bool(row["is_online"]),
                    "status_text": row["status_text"],
                }
            )

        return {
            "commands": commands,
            "snapshots": snapshots,
        }

    def acknowledge_alarm(self, alarm_key: str, acknowledged_by: str, note: str = "") -> None:
        key = alarm_key.strip()
        if not key:
            raise ValueError("alarm_key is required")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO alarm_acknowledgements (alarm_key, acknowledged_at, acknowledged_by, note)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(alarm_key)
                    DO UPDATE SET
                        acknowledged_at = excluded.acknowledged_at,
                        acknowledged_by = excluded.acknowledged_by,
                        note = excluded.note
                    """,
                    (key, _utc_now_iso(), acknowledged_by.strip() or "unknown", note.strip()),
                )
        self.log_alarm_event(
            alarm_key=key,
            action="acknowledge",
            actor=acknowledged_by,
            note=note,
        )

    def clear_alarm_acknowledgement(self, alarm_key: str) -> None:
        key = alarm_key.strip()
        if not key:
            raise ValueError("alarm_key is required")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM alarm_acknowledgements WHERE alarm_key = ?",
                    (key,),
                )

    def clear_alarm_acknowledgement_with_actor(
        self,
        alarm_key: str,
        actor: str,
        note: str = "",
    ) -> None:
        self.clear_alarm_acknowledgement(alarm_key)
        self.log_alarm_event(
            alarm_key=alarm_key,
            action="clear_acknowledgement",
            actor=actor,
            note=note,
        )

    def list_alarm_acknowledgements(self) -> dict[str, dict[str, str]]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT alarm_key, acknowledged_at, acknowledged_by, COALESCE(note, '') AS note
                    FROM alarm_acknowledgements
                    ORDER BY acknowledged_at DESC
                    """
                ).fetchall()
        result: dict[str, dict[str, str]] = {}
        for row in rows:
            result[str(row["alarm_key"])] = {
                "acknowledged_at": str(row["acknowledged_at"]),
                "acknowledged_by": str(row["acknowledged_by"]),
                "note": str(row["note"]),
            }
        return result

    def silence_alarm(self, alarm_key: str, silenced_by: str, silence_minutes: int, note: str = "") -> None:
        key = alarm_key.strip()
        if not key:
            raise ValueError("alarm_key is required")
        minutes = max(1, int(silence_minutes))
        now = datetime.now(timezone.utc)
        silenced_until = (now + timedelta(minutes=minutes)).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO alarm_silences (
                        alarm_key, silenced_at, silenced_until, silenced_by, note
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(alarm_key)
                    DO UPDATE SET
                        silenced_at = excluded.silenced_at,
                        silenced_until = excluded.silenced_until,
                        silenced_by = excluded.silenced_by,
                        note = excluded.note
                    """,
                    (
                        key,
                        now.isoformat(),
                        silenced_until,
                        silenced_by.strip() or "unknown",
                        note.strip(),
                    ),
                )
        self.log_alarm_event(
            alarm_key=key,
            action="silence",
            actor=silenced_by,
            note=f"duration_minutes={minutes}; {note.strip()}".strip(),
        )

    def clear_alarm_silence(self, alarm_key: str) -> None:
        key = alarm_key.strip()
        if not key:
            raise ValueError("alarm_key is required")
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM alarm_silences WHERE alarm_key = ?", (key,))

    def clear_alarm_silence_with_actor(
        self,
        alarm_key: str,
        actor: str,
        note: str = "",
    ) -> None:
        self.clear_alarm_silence(alarm_key)
        self.log_alarm_event(
            alarm_key=alarm_key,
            action="clear_silence",
            actor=actor,
            note=note,
        )

    def list_alarm_silences(self, include_expired: bool = False) -> dict[str, dict[str, str]]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT alarm_key, silenced_at, silenced_until, silenced_by, COALESCE(note, '') AS note
                    FROM alarm_silences
                    ORDER BY silenced_until DESC
                    """
                ).fetchall()

        now = datetime.now(timezone.utc)
        result: dict[str, dict[str, str]] = {}
        for row in rows:
            until_raw = str(row["silenced_until"])
            try:
                until_dt = datetime.fromisoformat(until_raw.replace("Z", "+00:00"))
                if until_dt.tzinfo is None:
                    until_dt = until_dt.replace(tzinfo=timezone.utc)
                until_dt = until_dt.astimezone(timezone.utc)
            except ValueError:
                continue

            is_expired = until_dt <= now
            if (not include_expired) and is_expired:
                continue

            result[str(row["alarm_key"])] = {
                "silenced_at": str(row["silenced_at"]),
                "silenced_until": until_raw,
                "silenced_by": str(row["silenced_by"]),
                "note": str(row["note"]),
            }
        return result

    def purge_expired_alarm_silences(self) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM alarm_silences WHERE silenced_until <= ?",
                    (now_iso,),
                )
                return int(cur.rowcount or 0)

    def purge_old_alarm_events(self, retention_days: int) -> int:
        if retention_days <= 0:
            raise ValueError("retention_days must be > 0")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM alarm_events WHERE timestamp < ?",
                    (cutoff,),
                )
                return int(cur.rowcount or 0)

    def table_row_counts(self) -> dict[str, int]:
        tables = [
            "command_audit",
            "status_snapshots",
            "alarm_acknowledgements",
            "alarm_silences",
            "alarm_events",
            "alert_webhook_queue",
            "alert_webhook_deadletter",
        ]
        counts: dict[str, int] = {}
        with self._lock:
            with self._connect() as conn:
                for table in tables:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    row = cur.fetchone()
                    counts[table] = int(row[0] if row else 0)
        return counts

    def enqueue_alert_webhook(self, alert_key: str, payload: dict[str, Any]) -> bool:
        key = alert_key.strip()
        if not key:
            raise ValueError("alert_key is required")
        payload_json = json.dumps(payload)
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO alert_webhook_queue (created_at, alert_key, payload_json)
                    VALUES (?, ?, ?)
                    """,
                    (_utc_now_iso(), key, payload_json),
                )
                return int(cur.rowcount or 0) > 0

    def list_alert_webhook_queue(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit)))
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT id, created_at, alert_key, payload_json, attempts, COALESCE(last_error, '') AS last_error
                    FROM alert_webhook_queue
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload_raw = str(row["payload_json"])
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {"raw": payload_raw}
            items.append(
                {
                    "id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "alert_key": str(row["alert_key"]),
                    "payload": payload,
                    "attempts": int(row["attempts"]),
                    "last_error": str(row["last_error"]),
                }
            )
        return items

    def mark_alert_webhook_sent(self, queue_id: int) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM alert_webhook_queue WHERE id = ?",
                    (int(queue_id),),
                )

    def record_alert_webhook_failure(
        self,
        queue_id: int,
        max_attempts: int,
        error: str = "",
    ) -> bool:
        qid = int(queue_id)
        safe_max = max(1, int(max_attempts))
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT id, alert_key, payload_json, attempts
                    FROM alert_webhook_queue
                    WHERE id = ?
                    """,
                    (qid,),
                ).fetchone()
                if row is None:
                    return False

                attempts = int(row["attempts"]) + 1
                if attempts >= safe_max:
                    conn.execute(
                        """
                        INSERT INTO alert_webhook_deadletter (
                            failed_at, alert_key, payload_json, attempts, last_error
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            _utc_now_iso(),
                            str(row["alert_key"]),
                            str(row["payload_json"]),
                            attempts,
                            error.strip(),
                        ),
                    )
                    conn.execute(
                        "DELETE FROM alert_webhook_queue WHERE id = ?",
                        (qid,),
                    )
                    return True

                conn.execute(
                    """
                    UPDATE alert_webhook_queue
                    SET attempts = ?, last_error = ?
                    WHERE id = ?
                    """,
                    (attempts, error.strip(), qid),
                )
                return False

    def list_alert_webhook_deadletter(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit)))
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT failed_at, alert_key, payload_json, attempts, COALESCE(last_error, '') AS last_error
                    FROM alert_webhook_deadletter
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload_raw = str(row["payload_json"])
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {"raw": payload_raw}
            items.append(
                {
                    "failed_at": str(row["failed_at"]),
                    "alert_key": str(row["alert_key"]),
                    "payload": payload,
                    "attempts": int(row["attempts"]),
                    "last_error": str(row["last_error"]),
                }
            )
        return items

    def log_alarm_event(
        self,
        alarm_key: str,
        action: str,
        actor: str,
        note: str = "",
    ) -> None:
        key = alarm_key.strip()
        act = action.strip().lower()
        if not key:
            raise ValueError("alarm_key is required")
        if not act:
            raise ValueError("action is required")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO alarm_events (timestamp, alarm_key, action, actor, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (_utc_now_iso(), key, act, actor.strip() or "unknown", note.strip()),
                )

    def list_alarm_events(self, limit: int = 100) -> list[dict[str, str]]:
        safe_limit = max(1, min(500, int(limit)))
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT timestamp, alarm_key, action, actor, COALESCE(note, '') AS note
                    FROM alarm_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        events: list[dict[str, str]] = []
        for row in rows:
            events.append(
                {
                    "timestamp": str(row["timestamp"]),
                    "alarm_key": str(row["alarm_key"]),
                    "action": str(row["action"]),
                    "actor": str(row["actor"]),
                    "note": str(row["note"]),
                }
            )
        return events

    def export_activity_report(
        self,
        file_path: str,
        command_limit: int = 100,
        snapshot_limit: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        report_path = Path(file_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        activity = self.fetch_recent_activity(command_limit=command_limit, snapshot_limit=snapshot_limit)
        payload = {
            "generated_at": _utc_now_iso(),
            "metadata": metadata or {},
            "commands": activity["commands"],
            "snapshots": activity["snapshots"],
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(report_path)

    def purge_old_records(
        self,
        command_retention_days: int,
        snapshot_retention_days: int,
    ) -> tuple[int, int]:
        """Delete old command/snapshot records and return deleted row counts."""
        now = datetime.now(timezone.utc)
        command_cutoff = (now - timedelta(days=command_retention_days)).isoformat()
        snapshot_cutoff = (now - timedelta(days=snapshot_retention_days)).isoformat()

        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM command_audit WHERE timestamp < ?",
                    (command_cutoff,),
                )
                command_deleted = int(cur.rowcount or 0)
                cur = conn.execute(
                    "DELETE FROM status_snapshots WHERE timestamp < ?",
                    (snapshot_cutoff,),
                )
                snapshot_deleted = int(cur.rowcount or 0)

        return command_deleted, snapshot_deleted

    def apply_retention_from_env(self) -> tuple[int, int]:
        """Apply cleanup using retention windows defined in environment variables."""
        command_days = int(os.getenv("OPENSIGNAL_COMMAND_RETENTION_DAYS", "90"))
        snapshot_days = int(os.getenv("OPENSIGNAL_SNAPSHOT_RETENTION_DAYS", "30"))
        if command_days <= 0 or snapshot_days <= 0:
            raise ValueError("Retention days must be > 0")
        return self.purge_old_records(command_days, snapshot_days)

    def apply_alarm_event_retention_from_env(self) -> int:
        days = int(os.getenv("OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS", "30"))
        if days <= 0:
            raise ValueError("OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS must be > 0")
        return self.purge_old_alarm_events(days)


STORE = AuditStore()

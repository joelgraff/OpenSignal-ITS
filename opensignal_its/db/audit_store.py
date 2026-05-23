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


STORE = AuditStore()

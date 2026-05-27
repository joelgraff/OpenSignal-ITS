"""Shared observability helpers for polling timing and overlap baselines."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from time import perf_counter
from typing import Any, AsyncIterator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ScopeMetrics:
    count: int = 0
    total_duration_seconds: float = 0.0
    last_duration_seconds: float = 0.0
    max_duration_seconds: float = 0.0
    last_started_at: str = ""
    last_finished_at: str = ""
    last_in_flight_before_start: int = 0
    last_overlap_detected: bool = False
    overlap_count: int = 0

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["average_duration_seconds"] = (
            self.total_duration_seconds / self.count if self.count else 0.0
        )
        return payload


@dataclass
class _RuntimeMetrics:
    active_refresh_count: int = 0
    last_updated_at: str = ""
    scopes: dict[str, _ScopeMetrics] = field(default_factory=dict)

    def snapshot(self, runtime_key: str) -> dict[str, Any]:
        return {
            "runtime_key": runtime_key,
            "active_refresh_count": self.active_refresh_count,
            "last_updated_at": self.last_updated_at,
            "scopes": {scope: metrics.snapshot() for scope, metrics in self.scopes.items()},
        }


class PollingTelemetryStore:
    """In-memory store for polling cycle timing and overlap observations."""

    def __init__(self):
        self._lock = RLock()
        self._entries: dict[str, _RuntimeMetrics] = {}

    def reset(self) -> None:
        with self._lock:
            self._entries = {}

    def _entry(self, runtime_key: str) -> _RuntimeMetrics:
        entry = self._entries.get(runtime_key)
        if entry is None:
            entry = _RuntimeMetrics()
            self._entries[runtime_key] = entry
        return entry

    @asynccontextmanager
    async def observe(
        self,
        runtime_key: str,
        scope: str,
        *,
        track_overlap: bool = False,
    ) -> AsyncIterator[None]:
        started_at = perf_counter()
        started_wall_clock = _utc_now_iso()
        with self._lock:
            entry = self._entry(runtime_key)
            scope_metrics = entry.scopes.setdefault(scope, _ScopeMetrics())
            in_flight_before_start = entry.active_refresh_count
            overlap_detected = bool(track_overlap and in_flight_before_start > 0)
            scope_metrics.count += 1
            scope_metrics.last_started_at = started_wall_clock
            scope_metrics.last_in_flight_before_start = in_flight_before_start
            scope_metrics.last_overlap_detected = overlap_detected
            if overlap_detected:
                scope_metrics.overlap_count += 1
            if track_overlap:
                entry.active_refresh_count += 1
            entry.last_updated_at = started_wall_clock

        try:
            yield
        finally:
            elapsed = perf_counter() - started_at
            finished_wall_clock = _utc_now_iso()
            with self._lock:
                entry = self._entry(runtime_key)
                scope_metrics = entry.scopes.setdefault(scope, _ScopeMetrics())
                scope_metrics.last_duration_seconds = elapsed
                scope_metrics.total_duration_seconds += elapsed
                scope_metrics.max_duration_seconds = max(
                    scope_metrics.max_duration_seconds,
                    elapsed,
                )
                scope_metrics.last_finished_at = finished_wall_clock
                entry.last_updated_at = finished_wall_clock
                if track_overlap:
                    entry.active_refresh_count = max(0, entry.active_refresh_count - 1)

    def snapshot(self, runtime_key: str | None = None) -> dict[str, Any]:
        with self._lock:
            if runtime_key is not None:
                entry = self._entries.get(runtime_key)
                if entry is None:
                    return {
                        "runtime_key": runtime_key,
                        "active_refresh_count": 0,
                        "last_updated_at": "",
                        "scopes": {},
                    }
                return deepcopy(entry.snapshot(runtime_key))

            return {
                "runtime_keys": {
                    key: deepcopy(entry.snapshot(key))
                    for key, entry in self._entries.items()
                }
            }


POLLING_TELEMETRY = PollingTelemetryStore()
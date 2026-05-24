"""Shared timestamp parsing and expiration helpers for state mixins."""

from __future__ import annotations

from datetime import UTC, datetime


class TimeStateMixin:
    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _parse_timestamp(self, ts: str) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _poll_delta_seconds(self, previous_ts: str, current_ts: str) -> int:
        prev = self._parse_timestamp(previous_ts)
        curr = self._parse_timestamp(current_ts)
        if prev is None or curr is None:
            return 0
        delta = int((curr - prev).total_seconds())
        return max(0, delta)

    def _has_expired(self, ts: str) -> bool:
        parsed = self._parse_timestamp(ts)
        if parsed is None:
            return True
        # _parse_timestamp may return timezone-aware dt if offset is included.
        if parsed.tzinfo is not None:
            return datetime.now(UTC).astimezone(parsed.tzinfo) >= parsed
        return datetime.now(UTC).replace(tzinfo=None) >= parsed
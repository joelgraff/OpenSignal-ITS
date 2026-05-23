"""Webhook dispatch for persistent operational alerts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib import request

from ..db import STORE


_last_sent_by_alert: dict[str, str] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AlertDispatchService:
    @staticmethod
    def _bool_env(name: str, default: bool) -> bool:
        raw = os.getenv(name, "true" if default else "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def enabled() -> bool:
        return AlertDispatchService._bool_env("OPENSIGNAL_ALERT_WEBHOOK_ENABLED", False)

    @staticmethod
    def webhook_url() -> str:
        return os.getenv("OPENSIGNAL_ALERT_WEBHOOK_URL", "").strip()

    @staticmethod
    def dedup_seconds() -> int:
        raw = os.getenv("OPENSIGNAL_ALERT_WEBHOOK_DEDUP_SECONDS", "300").strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return 300

    @staticmethod
    def timeout_seconds() -> float:
        raw = os.getenv("OPENSIGNAL_ALERT_WEBHOOK_TIMEOUT_SECONDS", "3").strip()
        try:
            return max(0.5, float(raw))
        except ValueError:
            return 3.0

    @staticmethod
    def max_retries() -> int:
        raw = os.getenv("OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES", "2").strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return 2

    @staticmethod
    def batch_size() -> int:
        raw = os.getenv("OPENSIGNAL_ALERT_WEBHOOK_BATCH_SIZE", "50").strip()
        try:
            return max(1, min(500, int(raw)))
        except ValueError:
            return 50

    @staticmethod
    def reset_state() -> None:
        _last_sent_by_alert.clear()

    @staticmethod
    def _iso_to_dt(ts: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _should_send(alert_key: str) -> bool:
        dedup = AlertDispatchService.dedup_seconds()
        if dedup <= 0:
            return True

        previous_raw = _last_sent_by_alert.get(alert_key, "")
        previous = AlertDispatchService._iso_to_dt(previous_raw)
        if previous is None:
            return True

        age = (_utc_now() - previous).total_seconds()
        return age >= dedup

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> bool:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=AlertDispatchService.timeout_seconds()) as response:
            code = int(getattr(response, "status", 200))
            return 200 <= code < 300

    @staticmethod
    def dispatch_persistent_alerts(
        alerts: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, int | bool | str]:
        if not AlertDispatchService.enabled():
            return {
                "enabled": False,
                "sent": 0,
                "skipped": len(alerts),
                "failed": 0,
                "message": "webhook dispatch disabled",
            }

        url = AlertDispatchService.webhook_url()
        if not url:
            return {
                "enabled": False,
                "sent": 0,
                "skipped": len(alerts),
                "failed": 0,
                "message": "webhook dispatch disabled: url not configured",
            }

        sent = 0
        skipped = 0
        failed = 0
        deadlettered = 0
        max_attempts = AlertDispatchService.max_retries() + 1

        for alert in alerts:
            key = alert.strip()
            if not key:
                continue
            if not AlertDispatchService._should_send(key):
                skipped += 1
                continue

            payload = {
                "generated_at": _utc_now().isoformat(),
                "source": "opensignal_its.storage",
                "alert": key,
                "context": context or {},
            }
            STORE.enqueue_alert_webhook(key, payload)

        queue_items = STORE.list_alert_webhook_queue(limit=AlertDispatchService.batch_size())
        for item in queue_items:
            queue_id = int(item.get("id", 0))
            key = str(item.get("alert_key", "")).strip()
            payload = dict(item.get("payload", {}))
            if not key or queue_id <= 0:
                continue

            delivered = False
            moved_to_deadletter = False
            remaining_tries = max(1, max_attempts - int(item.get("attempts", 0)))
            for _attempt in range(remaining_tries):
                try:
                    if AlertDispatchService._post_json(url, payload):
                        delivered = True
                        break
                    error_text = "non-2xx response"
                except Exception as exc:
                    error_text = str(exc)

                moved_to_deadletter = STORE.record_alert_webhook_failure(
                    queue_id=queue_id,
                    max_attempts=max_attempts,
                    error=error_text,
                )
                if moved_to_deadletter:
                    break

            if delivered:
                STORE.mark_alert_webhook_sent(queue_id)
                _last_sent_by_alert[key] = _utc_now().isoformat()
                sent += 1
                continue

            failed += 1
            if moved_to_deadletter:
                deadlettered += 1

        return {
            "enabled": True,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "deadlettered": deadlettered,
            "message": "webhook dispatch complete",
        }

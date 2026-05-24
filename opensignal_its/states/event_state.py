"""Alarms and events state slice for analytics and monitor workflows."""

from __future__ import annotations

from typing import Any

import reflex as rx

from ..models.event import EventDisplayView
from ..services import EventService


def _event_view_to_state_fields(event_view: EventDisplayView) -> dict[str, Any]:
    return {
        "event_timeline_rows": [row.model_dump(mode="json") for row in event_view.timeline],
        "alarm_rows": [row.model_dump(mode="json") for row in event_view.alarms],
        "acknowledged_alarm_rows": [
            row.model_dump(mode="json") for row in event_view.acknowledged_alarms
        ],
        "silenced_alarm_rows": [
            row.model_dump(mode="json") for row in event_view.silenced_alarms
        ],
    }


def _alarm_history_rows_to_state_fields(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "alarm_history_rows": rows,
    }


class EventStateMixin(rx.State, mixin=True):
    event_notice: str = "Timeline feed idle."
    event_window: str = "1h"
    event_timeline_rows: list[dict[str, str]] = []
    alarm_rows: list[dict[str, str]] = []
    acknowledged_alarm_rows: list[dict[str, str]] = []
    silenced_alarm_rows: list[dict[str, str]] = []
    alarm_history_rows: list[dict[str, str]] = []
    alarm_history_action_filter: str = "all"
    alarm_history_actor_filter: str = ""
    alarm_history_key_filter: str = ""
    alarm_history_limit_text: str = "50"
    alarm_history_applied_action_filter: str = "all"
    alarm_history_applied_actor_filter: str = ""
    alarm_history_applied_key_filter: str = ""
    alarm_history_applied_limit_text: str = "50"
    selected_alarm_key: str = ""
    alarm_note_input: str = ""
    alarm_silence_minutes_text: str = "30"
    alarm_action_notice: str = ""

    def update_selected_alarm_key(self, value: str):
        self.selected_alarm_key = value

    def update_event_window(self, value: str):
        self.event_window = value

    def update_alarm_note_input(self, value: str):
        self.alarm_note_input = value

    def update_alarm_silence_minutes_text(self, value: str):
        self.alarm_silence_minutes_text = value

    def update_alarm_history_action_filter(self, value: str):
        self.alarm_history_action_filter = value

    def update_alarm_history_actor_filter(self, value: str):
        self.alarm_history_actor_filter = value

    def update_alarm_history_key_filter(self, value: str):
        self.alarm_history_key_filter = value

    def update_alarm_history_limit_text(self, value: str):
        self.alarm_history_limit_text = value

    def _event_window_minutes(self) -> int | None:
        normalized = self.event_window.strip().lower()
        mapping: dict[str, int | None] = {
            "15m": 15,
            "1h": 60,
            "24h": 24 * 60,
            "all": None,
        }
        return mapping.get(normalized, 60)

    def _alarm_silence_minutes(self) -> int:
        try:
            return max(1, int(self.alarm_silence_minutes_text))
        except ValueError:
            return 30

    def _alarm_history_limit(self) -> int:
        try:
            return min(200, max(5, int(self.alarm_history_limit_text)))
        except ValueError:
            return 50

    def refresh_events_and_alarms(self):
        try:
            payload = EventService.build_timeline_and_alarms(
                command_limit=200,
                snapshot_limit=200,
                window_minutes=self._event_window_minutes(),
            )
            adapted = _event_view_to_state_fields(EventService.build_display_view(payload))
            self.event_timeline_rows = adapted["event_timeline_rows"]
            self.alarm_rows = adapted["alarm_rows"]
            self.acknowledged_alarm_rows = adapted["acknowledged_alarm_rows"]
            self.silenced_alarm_rows = adapted["silenced_alarm_rows"]
            history_rows = EventService.list_alarm_history_rows(
                limit=self._alarm_history_limit(),
                action_filter=self.alarm_history_action_filter,
                actor_contains=self.alarm_history_actor_filter,
                key_contains=self.alarm_history_key_filter,
            )
            history_adapted = _alarm_history_rows_to_state_fields(
                [
                    row.model_dump(mode="json")
                    for row in EventService.build_alarm_history_display_rows(history_rows)
                ]
            )
            self.alarm_history_rows = history_adapted["alarm_history_rows"]
            self.alarm_history_applied_action_filter = self.alarm_history_action_filter
            self.alarm_history_applied_actor_filter = self.alarm_history_actor_filter
            self.alarm_history_applied_key_filter = self.alarm_history_key_filter
            self.alarm_history_applied_limit_text = str(self._alarm_history_limit())
            self.event_notice = (
                f"Timeline refreshed ({self.event_window}): {len(self.event_timeline_rows)} entries, "
                f"{len(self.alarm_rows)} active alarms, "
                f"{len(self.acknowledged_alarm_rows)} acknowledged alarms, "
                f"{len(self.silenced_alarm_rows)} silenced alarms, "
                f"{len(self.alarm_history_rows)} history rows."
            )
            self.error = ""
        except Exception as exc:
            self.event_notice = f"Timeline refresh failed: {exc}"
            self.error = self.event_notice

    def acknowledge_selected_alarm(self):
        if not self._is_role_authorized({"admin"}):
            self.alarm_action_notice = "Alarm acknowledge denied: admin authentication required."
            self.error = self.alarm_action_notice
            return

        ok, message = EventService.acknowledge_alarm(
            alarm_key=self.selected_alarm_key,
            actor=self._actor_name(),
            note=self.alarm_note_input,
        )
        self.alarm_action_notice = message
        self.error = "" if ok else message
        if ok:
            self.refresh_events_and_alarms()

    def clear_selected_alarm_acknowledgement(self):
        if not self._is_role_authorized({"admin"}):
            self.alarm_action_notice = "Alarm clear denied: admin authentication required."
            self.error = self.alarm_action_notice
            return

        ok, message = EventService.clear_alarm_acknowledgement_with_actor(
            self.selected_alarm_key,
            actor=self._actor_name(),
            note=self.alarm_note_input,
        )
        self.alarm_action_notice = message
        self.error = "" if ok else message
        if ok:
            self.refresh_events_and_alarms()

    def silence_selected_alarm(self):
        if not self._is_role_authorized({"admin"}):
            self.alarm_action_notice = "Alarm silence denied: admin authentication required."
            self.error = self.alarm_action_notice
            return

        ok, message = EventService.silence_alarm(
            alarm_key=self.selected_alarm_key,
            actor=self._actor_name(),
            silence_minutes=self._alarm_silence_minutes(),
            note=self.alarm_note_input,
        )
        self.alarm_action_notice = message
        self.error = "" if ok else message
        if ok:
            self.refresh_events_and_alarms()

    def clear_selected_alarm_silence(self):
        if not self._is_role_authorized({"admin"}):
            self.alarm_action_notice = "Alarm silence clear denied: admin authentication required."
            self.error = self.alarm_action_notice
            return

        ok, message = EventService.clear_alarm_silence_with_actor(
            self.selected_alarm_key,
            actor=self._actor_name(),
            note=self.alarm_note_input,
        )
        self.alarm_action_notice = message
        self.error = "" if ok else message
        if ok:
            self.refresh_events_and_alarms()

    def apply_selected_alarm_silence_policy(self):
        minutes = EventService.recommended_silence_minutes(self.selected_alarm_key)
        self.alarm_silence_minutes_text = str(minutes)
        if self.selected_alarm_key.strip():
            self.alarm_action_notice = (
                f"Applied silence policy: {minutes} minutes for selected alarm."
            )
        else:
            self.alarm_action_notice = (
                f"Applied default silence policy: {minutes} minutes."
            )
        self.error = ""
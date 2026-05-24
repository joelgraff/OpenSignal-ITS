import reflex as rx

from ...states.traffic_state import TrafficState
from .event_rows import alarm_display_row, alarm_history_display_row, timeline_display_row
from .section_card import workspace_section_card


_DEFAULT_ALARM_HISTORY_LIMIT = "50"


def _filter_chip(label: str, color_scheme: str = "gray") -> rx.Component:
    return rx.badge(label, size="1", variant="soft", color_scheme=color_scheme)


def _alarm_history_action_chip() -> rx.Component:
    return rx.cond(
        TrafficState.alarm_history_applied_action_filter == "acknowledge",
        _filter_chip("Action: Ack", "green"),
        rx.cond(
            TrafficState.alarm_history_applied_action_filter == "silence",
            _filter_chip("Action: Silence", "orange"),
            rx.cond(
                TrafficState.alarm_history_applied_action_filter == "clear_acknowledgement",
                _filter_chip("Action: Clear Ack"),
                rx.cond(
                    TrafficState.alarm_history_applied_action_filter == "clear_silence",
                    _filter_chip("Action: Clear Silence"),
                    _filter_chip(
                        f"Action: {TrafficState.alarm_history_applied_action_filter}",
                    ),
                ),
            ),
        ),
    )


def _alarm_history_filter_summary() -> rx.Component:
    has_custom_filters = (
        (TrafficState.alarm_history_applied_action_filter != "all")
        | (TrafficState.alarm_history_applied_actor_filter != "")
        | (TrafficState.alarm_history_applied_key_filter != "")
        | (TrafficState.alarm_history_applied_limit_text != _DEFAULT_ALARM_HISTORY_LIMIT)
    )
    return rx.vstack(
        rx.text("Active filters", size="1", color="gray", font_weight="600"),
        rx.cond(
            has_custom_filters,
            rx.hstack(
                rx.cond(
                    TrafficState.alarm_history_applied_action_filter != "all",
                    _alarm_history_action_chip(),
                    rx.fragment(),
                ),
                rx.cond(
                    TrafficState.alarm_history_applied_actor_filter != "",
                    _filter_chip(
                        f"Actor: {TrafficState.alarm_history_applied_actor_filter}",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    TrafficState.alarm_history_applied_key_filter != "",
                    _filter_chip(
                        f"Key: {TrafficState.alarm_history_applied_key_filter}",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    TrafficState.alarm_history_applied_limit_text != _DEFAULT_ALARM_HISTORY_LIMIT,
                    _filter_chip(
                        f"Limit: {TrafficState.alarm_history_applied_limit_text}",
                    ),
                    rx.fragment(),
                ),
                width="100%",
                spacing="2",
                wrap="wrap",
            ),
            rx.hstack(
                _filter_chip("All actions"),
                _filter_chip(f"Limit: {TrafficState.alarm_history_applied_limit_text}"),
                width="100%",
                spacing="2",
                wrap="wrap",
            ),
        ),
        spacing="1",
        width="100%",
    )


def analytics_workspace_section() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "analytics",
        rx.vstack(
            rx.hstack(
                rx.button(
                    "Refresh Timeline",
                    on_click=TrafficState.refresh_events_and_alarms,
                    size="1",
                    variant="outline",
                ),
                rx.button("15m", on_click=lambda: TrafficState.update_event_window("15m"), size="1", variant="soft"),
                rx.button("1h", on_click=lambda: TrafficState.update_event_window("1h"), size="1", variant="soft"),
                rx.button("24h", on_click=lambda: TrafficState.update_event_window("24h"), size="1", variant="soft"),
                rx.button("All", on_click=lambda: TrafficState.update_event_window("all"), size="1", variant="soft"),
                width="100%",
                spacing="2",
                wrap="wrap",
            ),
            rx.text(TrafficState.event_notice, size="1", color="gray"),
            rx.grid(
                workspace_section_card(
                    title="Active Alarms",
                    subtitle="Acknowledge, silence, and annotate active alarms.",
                    body=rx.vstack(
                        rx.hstack(
                            rx.input(
                                value=TrafficState.selected_alarm_key,
                                on_change=TrafficState.update_selected_alarm_key,
                                placeholder="Alarm key",
                                size="1",
                                max_width="14em",
                            ),
                            rx.input(
                                value=TrafficState.alarm_silence_minutes_text,
                                on_change=TrafficState.update_alarm_silence_minutes_text,
                                placeholder="Silence min",
                                size="1",
                                max_width="7em",
                            ),
                            spacing="2",
                            wrap="wrap",
                            width="100%",
                        ),
                        rx.input(
                            value=TrafficState.alarm_note_input,
                            on_change=TrafficState.update_alarm_note_input,
                            placeholder="Alarm note (optional)",
                            size="1",
                            width="100%",
                        ),
                        rx.hstack(
                            rx.button("Use Policy", on_click=TrafficState.apply_selected_alarm_silence_policy, size="1", variant="outline"),
                            rx.button("Ack", on_click=TrafficState.acknowledge_selected_alarm, size="1", variant="outline"),
                            rx.button("Clear Ack", on_click=TrafficState.clear_selected_alarm_acknowledgement, size="1", variant="outline"),
                            rx.button("Silence", on_click=TrafficState.silence_selected_alarm, size="1", variant="outline"),
                            rx.button("Clear Silence", on_click=TrafficState.clear_selected_alarm_silence, size="1", variant="outline"),
                            spacing="2",
                            wrap="wrap",
                            width="100%",
                        ),
                        rx.cond(
                            TrafficState.alarm_action_notice != "",
                            rx.text(TrafficState.alarm_action_notice, size="1", color="gray"),
                            rx.fragment(),
                        ),
                        rx.box(
                            rx.cond(
                                TrafficState.alarm_rows != [],
                                rx.vstack(
                                    rx.foreach(
                                        TrafficState.alarm_rows,
                                        lambda row: alarm_display_row(row, selectable=True),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                rx.text("No active alarms.", size="1", color="gray"),
                            ),
                            max_height="180px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        rx.cond(
                            TrafficState.acknowledged_alarm_rows != [],
                            rx.vstack(
                                rx.text("Acknowledged", size="1", color="gray", font_weight="600"),
                                rx.box(
                                    rx.vstack(
                                        rx.foreach(
                                            TrafficState.acknowledged_alarm_rows,
                                            lambda row: alarm_display_row(row),
                                        ),
                                        spacing="2",
                                        width="100%",
                                    ),
                                    max_height="90px",
                                    overflow_y="auto",
                                    width="100%",
                                ),
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                        rx.cond(
                            TrafficState.silenced_alarm_rows != [],
                            rx.vstack(
                                rx.text("Silenced", size="1", color="gray", font_weight="600"),
                                rx.box(
                                    rx.vstack(
                                        rx.foreach(
                                            TrafficState.silenced_alarm_rows,
                                            lambda row: alarm_display_row(row),
                                        ),
                                        spacing="2",
                                        width="100%",
                                    ),
                                    max_height="90px",
                                    overflow_y="auto",
                                    width="100%",
                                ),
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                workspace_section_card(
                    title="Alarm History",
                    subtitle="Filter by action, actor, or alarm key.",
                    body=rx.vstack(
                        rx.hstack(
                            rx.button("All", on_click=lambda: TrafficState.update_alarm_history_action_filter("all"), size="1", variant="soft"),
                            rx.button("Ack", on_click=lambda: TrafficState.update_alarm_history_action_filter("acknowledge"), size="1", variant="soft"),
                            rx.button("Silence", on_click=lambda: TrafficState.update_alarm_history_action_filter("silence"), size="1", variant="soft"),
                            width="100%",
                            spacing="2",
                            wrap="wrap",
                        ),
                        rx.hstack(
                            rx.input(
                                value=TrafficState.alarm_history_actor_filter,
                                on_change=TrafficState.update_alarm_history_actor_filter,
                                placeholder="Actor contains",
                                size="1",
                                max_width="12em",
                            ),
                            rx.input(
                                value=TrafficState.alarm_history_key_filter,
                                on_change=TrafficState.update_alarm_history_key_filter,
                                placeholder="Key contains",
                                size="1",
                                max_width="12em",
                            ),
                            rx.input(
                                value=TrafficState.alarm_history_limit_text,
                                on_change=TrafficState.update_alarm_history_limit_text,
                                placeholder="Limit",
                                size="1",
                                max_width="6em",
                            ),
                            rx.button(
                                "Apply",
                                on_click=TrafficState.refresh_events_and_alarms,
                                size="1",
                                variant="outline",
                            ),
                            spacing="2",
                            wrap="wrap",
                            width="100%",
                        ),
                        _alarm_history_filter_summary(),
                        rx.box(
                            rx.cond(
                                TrafficState.alarm_history_rows != [],
                                rx.vstack(
                                    rx.foreach(
                                        TrafficState.alarm_history_rows,
                                        lambda row: alarm_history_display_row(row),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                rx.text("No alarm action history.", size="1", color="gray"),
                            ),
                            max_height="300px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                workspace_section_card(
                    title="Timeline Feed",
                    subtitle="Scan recent events in chronological order.",
                    body=rx.vstack(
                        rx.box(
                            rx.cond(
                                TrafficState.event_timeline_rows != [],
                                rx.vstack(
                                    rx.foreach(
                                        TrafficState.event_timeline_rows,
                                        lambda row: timeline_display_row(row),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                rx.text("No timeline rows.", size="1", color="gray"),
                            ),
                            max_height="360px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                template_columns="repeat(auto-fit, minmax(260px, 1fr))",
                spacing="3",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        rx.text(
            "Switch to Alarms & Events workspace for timeline and alarm triage tools.",
            size="1",
            color="gray",
        ),
    )

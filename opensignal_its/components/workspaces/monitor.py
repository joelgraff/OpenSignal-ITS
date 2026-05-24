"""Overview workspace.

Two-view workflow driven by ``TrafficState.monitor_view``:

* ``dashboard``    - high-level overview: stat strip + map + controller list.
                     This is the landing view that maps to Step 2 of the
                     user workflow guide.
* ``intersection`` - detail page for a single selected controller.
                     Maps to Step 4 of the user workflow guide.

Selecting a controller from the dashboard transitions to the intersection
view. The intersection view has a breadcrumb to return to the dashboard.
"""

import reflex as rx
from plotly.graph_objs import Figure
from reflex_components_plotly import plotly as plotly_component

from ...components.phase_status import phase_status_grid
from ...states import TrafficState
from .event_rows import alarm_display_row, timeline_display_row
from .page_frame import workspace_page_frame
from .section_card import workspace_section_card


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _stat_pill(label: str, value, accent: str) -> rx.Component:
    return rx.hstack(
        rx.box(width="4px", height="28px", background=accent, border_radius="2px"),
        rx.vstack(
            rx.text(label, size="1", color="gray", line_height="1"),
            rx.text(value, size="3", font_weight="700", color=accent, line_height="1.1"),
            spacing="0",
            align="start",
        ),
        spacing="2",
        align="center",
        padding_x="2",
        padding_y="1",
    )


def _detail_tab_button(label: str, tab_key: str) -> rx.Component:
    return rx.button(
        label,
        on_click=lambda: TrafficState.update_monitor_detail_tab(tab_key),
        size="1",
        variant=rx.cond(TrafficState.monitor_detail_tab == tab_key, "solid", "soft"),
        color_scheme=rx.cond(TrafficState.monitor_detail_tab == tab_key, "indigo", "gray"),
    )


# ---------------------------------------------------------------------------
# Dashboard view (Step 2)
# ---------------------------------------------------------------------------


def _dashboard_stat_strip() -> rx.Component:
    return rx.hstack(
        _stat_pill("Total", TrafficState.fleet_total_count, "#1d4ed8"),
        rx.divider(orientation="vertical", size="1"),
        _stat_pill("Online", TrafficState.fleet_online_count, "#15803d"),
        rx.divider(orientation="vertical", size="1"),
        _stat_pill("Alarms", TrafficState.alarm_rows.length(), "#c2410c"),
        rx.divider(orientation="vertical", size="1"),
        _stat_pill("Updated", TrafficState.last_updated, "#4338ca"),
        rx.spacer(),
        rx.button(
            "Refresh",
            on_click=TrafficState.refresh_fleet_status,
            size="1",
            variant="outline",
        ),
        rx.button(
            "Manage Controllers",
            on_click=lambda: TrafficState.update_ui_workspace_mode("configuration"),
            size="1",
            variant="outline",
        ),
        spacing="3",
        align="center",
        width="100%",
        wrap="wrap",
    )


def _dashboard_map_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Signal map", size="1", color="#1f2937", font_weight="600"),
                rx.spacer(),
                rx.badge(f"Mapped {TrafficState.fleet_map_markers.length()}", color_scheme="indigo", size="1"),
                rx.badge(
                    f"Need Coordinates {TrafficState.fleet_unmapped_device_ids.length()}",
                    color_scheme="amber",
                    size="1",
                ),
                spacing="1",
                width="100%",
                align="center",
            ),
            rx.cond(
                TrafficState.fleet_map_data != [],
                plotly_component.mapbox(
                    data=TrafficState.fleet_map_figure.to(Figure),
                    config={
                        "displayModeBar": False,
                        "responsive": True,
                        "scrollZoom": True,
                    },
                    on_click=TrafficState.select_controller_from_map_points,
                    use_resize_handler=True,
                    width="100%",
                    height="360px",
                ),
                rx.cond(
                    TrafficState.fleet_unmapped_device_ids != [],
                    rx.center(
                        rx.vstack(
                            rx.heading("Add coordinates to place controllers on the map.", size="4"),
                            rx.text(
                                TrafficState.fleet_map_notice,
                                size="1",
                                color="gray",
                                text_align="center",
                            ),
                            rx.box(
                                rx.foreach(
                                    TrafficState.fleet_unmapped_device_ids,
                                    lambda device_id: rx.badge(device_id, color_scheme="gray", size="1"),
                                ),
                                display="flex",
                                flex_wrap="wrap",
                                gap="6px",
                                justify_content="center",
                                width="100%",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        min_height="360px",
                        width="100%",
                        border_radius="12px",
                        border="1px dashed #93c5fd",
                        background="rgba(255, 255, 255, 0.72)",
                        padding="4",
                    ),
                    rx.center(
                        rx.text(
                            TrafficState.fleet_map_notice,
                            size="1",
                            color="gray",
                            text_align="center",
                        ),
                        min_height="360px",
                        width="100%",
                        border_radius="12px",
                        border="1px dashed #93c5fd",
                        background="rgba(255, 255, 255, 0.72)",
                        padding="4",
                    ),
                ),
            ),
            rx.cond(
                TrafficState.fleet_unmapped_device_ids != [],
                rx.vstack(
                    rx.text(
                        "Awaiting coordinates",
                        size="1",
                        color="gray",
                    ),
                    rx.box(
                        rx.foreach(
                            TrafficState.fleet_unmapped_device_ids,
                            lambda device_id: rx.badge(device_id, color_scheme="gray", size="1", variant="soft"),
                        ),
                        display="flex",
                        flex_wrap="wrap",
                        gap="6px",
                        width="100%",
                    ),
                    width="100%",
                    spacing="1",
                ),
                rx.fragment(),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        min_height="260px",
        border_radius="8px",
        border="1px solid #cbd5e1",
        padding="3",
        background="linear-gradient(160deg, #e0f2fe 0%, #f8fafc 48%, #eef2ff 100%)",
    )


def _dashboard_controller_list() -> rx.Component:
    return rx.vstack(
        rx.text(
            "Select a controller to open its intersection detail and poll focus.",
            size="1",
            color="gray",
        ),
        rx.hstack(
            rx.button(
                "All",
                on_click=lambda: TrafficState.update_fleet_status_mapping_filter("all"),
                size="1",
                variant=rx.cond(TrafficState.fleet_status_mapping_filter == "all", "solid", "soft"),
                color_scheme=rx.cond(
                    TrafficState.fleet_status_mapping_filter == "all",
                    "gray",
                    "gray",
                ),
            ),
            rx.button(
                "Mapped",
                on_click=lambda: TrafficState.update_fleet_status_mapping_filter("mapped"),
                size="1",
                variant=rx.cond(
                    TrafficState.fleet_status_mapping_filter == "mapped",
                    "solid",
                    "soft",
                ),
                color_scheme=rx.cond(
                    TrafficState.fleet_status_mapping_filter == "mapped",
                    "blue",
                    "gray",
                ),
            ),
            rx.button(
                "Needs Coordinates",
                on_click=lambda: TrafficState.update_fleet_status_mapping_filter("unmapped"),
                size="1",
                variant=rx.cond(
                    TrafficState.fleet_status_mapping_filter == "unmapped",
                    "solid",
                    "soft",
                ),
                color_scheme=rx.cond(
                    TrafficState.fleet_status_mapping_filter == "unmapped",
                    "amber",
                    "gray",
                ),
            ),
            spacing="2",
            align="center",
            wrap="wrap",
            width="100%",
        ),
        rx.cond(
            TrafficState.fleet_status_cards != [],
            rx.box(
                rx.foreach(
                    TrafficState.fleet_status_cards,
                    lambda row: rx.button(
                        rx.vstack(
                            rx.vstack(
                                rx.text(row["title"], size="1", font_weight="600", text_align="left"),
                                rx.text(row["subtitle"], size="1", color="gray", text_align="left"),
                                spacing="0",
                                align="start",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.badge(
                                    row["status_label"],
                                    color_scheme=row["status_scheme"],
                                    size="1",
                                    variant="soft",
                                ),
                                rx.badge(
                                    row["mapping_label"],
                                    color_scheme=row["mapping_scheme"],
                                    size="1",
                                    variant="soft",
                                ),
                                rx.spacer(),
                                rx.text(row["coordinate_text"], size="1", color="gray"),
                                width="100%",
                                align="center",
                                spacing="2",
                            ),
                            width="100%",
                            spacing="1",
                            align="start",
                        ),
                        on_click=lambda: TrafficState.select_controller_from_row(row["device_id"]),
                        variant=rx.cond(
                            row["device_id"] == TrafficState.selected_device_id,
                            "soft",
                            "ghost",
                        ),
                        color_scheme=rx.cond(
                            row["device_id"] == TrafficState.selected_device_id,
                            "indigo",
                            "gray",
                        ),
                        width="100%",
                        justify_content="start",
                        size="1",
                    ),
                ),
                width="100%",
                max_height="260px",
                overflow_y="auto",
            ),
            rx.text("Controller list is empty.", size="1", color="gray"),
        ),
        rx.text(TrafficState.fleet_status_card_notice, size="1", color="gray"),
        rx.text(TrafficState.fleet_status_summary, size="1", color="gray"),
        spacing="1",
        width="100%",
    )


def _dashboard_view() -> rx.Component:
    return rx.vstack(
        workspace_section_card(
            title="Overview",
            body=_dashboard_stat_strip(),
        ),
        rx.grid(
            workspace_section_card(
                title="Signal Map",
                body=_dashboard_map_panel(),
                subtitle="Controllers with stored coordinates appear on the map. Click a marker to open intersection detail.",
            ),
            workspace_section_card(
                title="Controllers",
                body=_dashboard_controller_list(),
                subtitle="Use friendly location labels, mapping status, and coordinates to choose the right controller quickly.",
            ),
            template_columns="repeat(auto-fit, minmax(320px, 1fr))",
            spacing="2",
            width="100%",
        ),
        spacing="2",
        width="100%",
    )


# ---------------------------------------------------------------------------
# Intersection detail view (Step 4)
# ---------------------------------------------------------------------------


def _intersection_breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.button(
            "\u2190 Overview",
            on_click=TrafficState.back_to_dashboard,
            size="1",
            variant="ghost",
        ),
        rx.text("/", size="1", color="gray"),
        rx.text("Intersection Detail", size="1", color="gray"),
        rx.spacer(),
        rx.input(
            value=TrafficState.selected_device_id,
            on_change=TrafficState.update_selected_device_id,
            placeholder="Controller ID",
            size="1",
            max_width="10em",
        ),
        rx.button(
            "Connect",
            on_click=TrafficState.connect_and_start_polling,
            size="1",
        ),
        rx.button(
            "Refresh",
            on_click=TrafficState.refresh_status,
            size="1",
            variant="outline",
        ),
        spacing="2",
        align="center",
        width="100%",
        wrap="wrap",
    )


def _intersection_header_card() -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.text("Intersection", size="1", color="gray", line_height="1"),
                rx.heading(
                    rx.cond(
                        TrafficState.selected_device_id != "",
                        TrafficState.selected_device_id,
                        "No controller selected",
                    ),
                    size="4",
                ),
                spacing="0",
                align="start",
            ),
            rx.spacer(),
            rx.badge(
                rx.cond(TrafficState.is_online, "Online", "Offline"),
                color_scheme=rx.cond(TrafficState.is_online, "green", "red"),
                size="2",
            ),
            rx.badge(
                f"Pattern {TrafficState.current_pattern}",
                color_scheme="indigo",
                size="2",
            ),
            rx.badge(
                f"Vehicle {TrafficState.vehicle_calls}",
                color_scheme="gray",
                size="2",
            ),
            rx.badge(
                f"Ped {TrafficState.ped_calls}",
                color_scheme="gray",
                size="2",
            ),
            rx.badge(
                f"Updated {TrafficState.last_updated}",
                color_scheme="cyan",
                size="2",
            ),
            spacing="2",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        width="100%",
        size="1",
    )


def _intersection_control_panel() -> rx.Component:
    return rx.vstack(
        rx.text("Pattern / Mode", size="1", color="gray"),
        rx.hstack(
            rx.button("Pattern 1", on_click=TrafficState.select_pattern_1, size="1"),
            rx.button("Pattern 2", on_click=TrafficState.select_pattern_2, size="1"),
            rx.button("Free", on_click=TrafficState.set_mode_free, size="1", variant="outline"),
            rx.button("Coord", on_click=TrafficState.set_mode_coordinated, size="1", variant="outline"),
            spacing="1",
            wrap="wrap",
            width="100%",
        ),
        rx.text("Manual", size="1", color="gray"),
        rx.hstack(
            rx.button("Hold", on_click=TrafficState.manual_hold, size="1", color_scheme="orange"),
            rx.button("Advance", on_click=TrafficState.advance_phase, size="1"),
            spacing="1",
            wrap="wrap",
            width="100%",
        ),
        rx.divider(),
        rx.text("Unlock Write", size="1", color="gray"),
        rx.hstack(
            rx.input(
                value=TrafficState.operator_key_input,
                on_change=TrafficState.update_operator_key_input,
                placeholder="Key",
                type="password",
                size="1",
                max_width="9em",
            ),
            rx.input(
                value=TrafficState.write_unlock_seconds_text,
                on_change=TrafficState.update_write_unlock_seconds_text,
                placeholder="sec",
                size="1",
                max_width="5em",
            ),
            rx.button(
                "Unlock",
                on_click=TrafficState.unlock_write_mode,
                size="1",
                color_scheme="red",
            ),
            rx.button(
                "Lock",
                on_click=TrafficState.lock_write_mode,
                size="1",
                variant="outline",
            ),
            spacing="1",
            align="center",
            wrap="wrap",
            width="100%",
        ),
        rx.text(TrafficState.safety_notice, size="1", color="gray"),
        spacing="1",
        width="100%",
    )


def _intersection_cabinet_tab() -> rx.Component:
    def row(label: str, color: str) -> rx.Component:
        return rx.hstack(
            rx.badge(label, color_scheme=color, size="1"),
            rx.spacer(),
            rx.text("Not integrated yet", size="1", color="gray"),
            width="100%",
            align="center",
        )

    return rx.vstack(
        row("Video Detection", "blue"),
        row("Battery Backup", "amber"),
        row("Power Supply", "purple"),
        spacing="1",
        width="100%",
    )


def _intersection_logs_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.button(
                "Refresh",
                on_click=TrafficState.refresh_events_and_alarms,
                size="1",
                variant="outline",
            ),
            rx.text(TrafficState.event_notice, size="1", color="gray"),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.grid(
            rx.box(
                rx.text("Active Alarms", size="1", font_weight="600"),
                rx.cond(
                    TrafficState.alarm_rows != [],
                    rx.vstack(
                        rx.foreach(
                            TrafficState.alarm_rows,
                            lambda row: alarm_display_row(row),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.text("None.", size="1", color="gray"),
                ),
                width="100%",
            ),
            rx.box(
                rx.text("Timeline", size="1", font_weight="600"),
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
                        rx.text("Empty.", size="1", color="gray"),
                    ),
                    max_height="220px",
                    overflow_y="auto",
                    width="100%",
                ),
                width="100%",
            ),
            template_columns="repeat(auto-fit, minmax(260px, 1fr))",
            spacing="2",
            width="100%",
        ),
        spacing="2",
        width="100%",
    )


def _intersection_timing_tab() -> rx.Component:
    return rx.vstack(
        rx.text(
            f"Remaining: {TrafficState.remaining_time_summary} | Mode: {TrafficState.timer_mode_text}",
            size="1",
            color="gray",
        ),
        rx.box(
            rx.cond(
                TrafficState.phase_detail_lines != [],
                rx.foreach(
                    TrafficState.phase_detail_lines,
                    lambda row: rx.text(row, size="1", color="gray", font_family="monospace"),
                ),
                rx.text("No timing rows.", size="1", color="gray"),
            ),
            max_height="260px",
            overflow_y="auto",
            width="100%",
        ),
        spacing="1",
        width="100%",
    )


def _intersection_raw_tab() -> rx.Component:
    return rx.cond(
        TrafficState.m60_status_json != "",
        rx.code_block(TrafficState.m60_status_json, language="json", width="100%"),
        rx.text("No raw payload loaded.", size="1", color="gray"),
    )


def _intersection_detail_tabs() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            _detail_tab_button("Logs / Events", "logs"),
            _detail_tab_button("Timing Plan", "timing"),
            _detail_tab_button("Cabinet", "cabinet"),
            _detail_tab_button("Video Feeds", "video"),
            _detail_tab_button("Raw / Advanced", "raw"),
            spacing="1",
            wrap="wrap",
            width="100%",
        ),
        rx.cond(
            TrafficState.monitor_detail_tab == "logs",
            _intersection_logs_tab(),
            rx.cond(
                TrafficState.monitor_detail_tab == "timing",
                _intersection_timing_tab(),
                rx.cond(
                    TrafficState.monitor_detail_tab == "cabinet",
                    _intersection_cabinet_tab(),
                    rx.cond(
                        TrafficState.monitor_detail_tab == "video",
                        rx.text(
                            "Video integration is planned for a future release.",
                            size="1",
                            color="gray",
                        ),
                        _intersection_raw_tab(),
                    ),
                ),
            ),
        ),
        spacing="2",
        width="100%",
    )


def _intersection_view() -> rx.Component:
    return rx.vstack(
        _intersection_breadcrumb(),
        _intersection_header_card(),
        rx.grid(
            workspace_section_card(
                title="Live Phase Diagram",
                body=rx.cond(
                    TrafficState.phase_data != {},
                    phase_status_grid(
                        phases=TrafficState.phase_data,
                        current_pattern=TrafficState.phase_current_pattern,
                        unit_control_status=TrafficState.phase_unit_control_status,
                        ring_status_summary=TrafficState.ring_status_summary,
                        ring_status_lines=TrafficState.ring_status_lines,
                        ring_status_console_text=TrafficState.ring_status_console_text,
                    ),
                    rx.text(
                        "Connect and poll to render the live phase diagram.",
                        size="1",
                        color="gray",
                    ),
                ),
            ),
            workspace_section_card(
                title="Control Panel",
                body=_intersection_control_panel(),
            ),
            template_columns="repeat(auto-fit, minmax(320px, 1fr))",
            spacing="2",
            width="100%",
        ),
        workspace_section_card(
            title="Details",
            body=_intersection_detail_tabs(),
        ),
        spacing="2",
        width="100%",
    )


# ---------------------------------------------------------------------------
# Page entry
# ---------------------------------------------------------------------------


def monitor_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title=rx.cond(
            TrafficState.monitor_view == "dashboard",
            "Network Overview",
            "Intersection Detail",
        ),
        subtitle=rx.cond(
            TrafficState.monitor_view == "dashboard",
            "Select a controller to investigate live status and alarms.",
            "Return to overview at any time while keeping the current controller target.",
        ),
        body=rx.cond(
            TrafficState.monitor_view == "dashboard",
            _dashboard_view(),
            _intersection_view(),
        ),
    )

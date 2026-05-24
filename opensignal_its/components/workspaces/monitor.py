import reflex as rx

from ...states.traffic_state import TrafficState
from .page_frame import workspace_page_frame
from .section_card import workspace_section_card


def monitor_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Signal Sites & Status",
        subtitle="Choose a signal site, then review live status and field communications.",
        body=rx.grid(
            rx.card(
                rx.vstack(
                    rx.heading("Site Connection & Polling", size="4"),
                    rx.input(
                        value=TrafficState.ip_address,
                        on_change=TrafficState.update_ip_address,
                        placeholder="Controller IP",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.port_text,
                            on_change=TrafficState.update_port_text,
                            placeholder="Port",
                            width="40%",
                        ),
                        rx.input(
                            value=TrafficState.community,
                            on_change=TrafficState.update_community,
                            placeholder="Community",
                            width="60%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.timeout_text,
                            on_change=TrafficState.update_timeout_text,
                            placeholder="Timeout sec",
                            width="50%",
                        ),
                        rx.input(
                            value=TrafficState.retries_text,
                            on_change=TrafficState.update_retries_text,
                            placeholder="Retries",
                            width="50%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_refresh_enabled,
                            on_change=TrafficState.update_auto_refresh_enabled,
                        ),
                        rx.text("Auto Refresh"),
                        rx.input(
                            value=TrafficState.refresh_interval_text,
                            on_change=TrafficState.update_refresh_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_reconnect_enabled,
                            on_change=TrafficState.update_auto_reconnect_enabled,
                        ),
                        rx.text("Auto Reconnect"),
                        rx.input(
                            value=TrafficState.reconnect_interval_text,
                            on_change=TrafficState.update_reconnect_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.selected_device_id,
                        on_change=TrafficState.update_selected_device_id,
                        placeholder="Selected site ID (optional)",
                        width="100%",
                    ),
                    workspace_section_card(
                        title="Selected Signal Site",
                        subtitle="Verify the active site target before polling actions.",
                        body=rx.vstack(
                            rx.cond(
                                TrafficState.selected_device_id != "",
                                rx.badge(
                                    f"Targeting site: {TrafficState.selected_device_id}",
                                    color_scheme="indigo",
                                ),
                                rx.badge("No specific site selected (all configured sites)", color_scheme="gray"),
                            ),
                            rx.text(TrafficState.fleet_status_summary, size="1", color="gray"),
                            rx.text(TrafficState.managed_polling_notice, size="1", color="gray"),
                            spacing="2",
                            width="100%",
                        ),
                    ),
                    rx.button(
                        "Refresh Signal Sites",
                        on_click=TrafficState.refresh_fleet_status,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.managed_polling_interval_text,
                            on_change=TrafficState.update_managed_polling_interval_text,
                            placeholder="Poll interval sec",
                            width="8em",
                        ),
                        rx.button(
                            "Start Managed Polling",
                            on_click=TrafficState.start_selected_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Stop Managed Polling",
                            on_click=TrafficState.stop_selected_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.button(
                            "Start Site Polling",
                            on_click=TrafficState.start_fleet_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Stop Site Polling",
                            on_click=TrafficState.stop_fleet_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.button(
                        "Refresh Active Poll Sessions",
                        on_click=TrafficState.refresh_runtime_registry_status,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    workspace_section_card(
                        title="Active Site Sessions",
                        subtitle="Active poll loops and worker sessions by site.",
                        body=rx.vstack(
                            rx.text(TrafficState.runtime_registry_summary, size="1", color="gray"),
                            rx.text(
                                f"Rows: {TrafficState.runtime_registry_rows.length()}",
                                size="1",
                                color="gray",
                            ),
                            rx.box(
                                rx.cond(
                                    TrafficState.runtime_registry_rows != [],
                                    rx.foreach(
                                        TrafficState.runtime_registry_rows,
                                        lambda row: rx.text(row, size="1", color="gray", font_family="monospace"),
                                    ),
                                    rx.text("No active poll session rows.", size="1", color="gray"),
                                ),
                                max_height="180px",
                                overflow_y="auto",
                                width="100%",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                    ),
                    workspace_section_card(
                        title="Signal Site List",
                        subtitle="Current site rows from the most recent refresh.",
                        body=rx.vstack(
                            rx.text(
                                f"Rows: {TrafficState.fleet_device_rows.length()}",
                                size="1",
                                color="gray",
                            ),
                            rx.box(
                                rx.cond(
                                    TrafficState.fleet_device_rows != [],
                                    rx.foreach(
                                        TrafficState.fleet_device_rows,
                                        lambda row: rx.text(row, size="1", color="gray", font_family="monospace"),
                                    ),
                                    rx.text("No signal site rows yet.", size="1", color="gray"),
                                ),
                                max_height="220px",
                                overflow_y="auto",
                                width="100%",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
                height="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("SEPAC Ring Timer Text View", size="4"),
                    rx.text("Controller-style text status", size="1", color="gray"),
                    rx.code_block(TrafficState.ring_status_console_text, language="log", width="100%"),
                    width="100%",
                    spacing="2",
                ),
                width="100%",
                height="100%",
            ),
            template_columns="repeat(auto-fit, minmax(520px, 1fr))",
            spacing="4",
            width="100%",
        ),
    )

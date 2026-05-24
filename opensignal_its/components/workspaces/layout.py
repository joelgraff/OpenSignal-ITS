import reflex as rx

from ...states.traffic_state import TrafficState
from .admin import admin_workspace_page
from .analytics_page import analytics_workspace_page
from .control_page import control_workspace_page
from .monitor import monitor_workspace_page
from .operations_page import operations_workspace_page
from .settings import settings_workspace_page


def _workspace_tab_button(label: str, mode: str) -> rx.Component:
    return rx.button(
        label,
        size="1",
        variant="ghost",
        color_scheme=rx.cond(TrafficState.ui_workspace_mode == mode, "indigo", "gray"),
        border_radius="0",
        border_bottom=rx.cond(
            TrafficState.ui_workspace_mode == mode,
            "2px solid #4338ca",
            "2px solid transparent",
        ),
        font_weight=rx.cond(TrafficState.ui_workspace_mode == mode, "600", "500"),
        padding_x="3",
        on_click=lambda: TrafficState.update_ui_workspace_mode(mode),
    )


def workspace_tabs() -> rx.Component:
    return rx.box(
        rx.hstack(
            _workspace_tab_button("Sites & Status", "monitor"),
            _workspace_tab_button("Signal Control", "control"),
            _workspace_tab_button("Maintenance", "operations"),
            _workspace_tab_button("Alarms & Events", "analytics"),
            _workspace_tab_button("Site Inventory", "configuration"),
            _workspace_tab_button("Sign-In & Roles", "admin"),
            spacing="1",
            wrap="wrap",
            width="100%",
        ),
        bg="#f8fafc",
        border="1px solid #e5e7eb",
        border_radius="10px",
        padding_x="2",
        padding_top="2",
        box_shadow="0 1px 2px rgba(15, 23, 42, 0.06)",
        position="sticky",
        top="0",
        z_index="10",
        width="100%",
    )


def workspace_page_content() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "monitor",
        monitor_workspace_page(),
        rx.cond(
            TrafficState.ui_workspace_mode == "control",
            control_workspace_page(),
            rx.cond(
                TrafficState.ui_workspace_mode == "operations",
                operations_workspace_page(),
                rx.cond(
                    TrafficState.ui_workspace_mode == "analytics",
                    analytics_workspace_page(),
                    rx.cond(
                        TrafficState.ui_workspace_mode == "configuration",
                        settings_workspace_page(),
                        admin_workspace_page(),
                    ),
                ),
            ),
        ),
    )

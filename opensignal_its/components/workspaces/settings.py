import reflex as rx

from ...states.traffic_state import TrafficState
from .configuration import configuration_workspace_fleet_profiles_editor
from .page_frame import workspace_page_frame


def settings_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Site Inventory",
        subtitle="Configure controller defaults and site profile records.",
        body=rx.vstack(
            rx.heading("Signal Site Profiles", size="3"),
            configuration_workspace_fleet_profiles_editor(),
            rx.input(
                value=TrafficState.selected_device_id,
                on_change=TrafficState.update_selected_device_id,
                placeholder="Selected site ID (optional)",
                width="100%",
            ),
            rx.button(
                "Refresh Site Inventory",
                on_click=TrafficState.refresh_fleet_status,
                size="2",
                variant="outline",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
    )

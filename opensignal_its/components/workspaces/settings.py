import reflex as rx

from ...states.traffic_state import TrafficState
from .configuration import configuration_workspace_fleet_profiles_editor
from .page_frame import workspace_page_frame


def settings_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Controllers",
        subtitle="Configure controller defaults and controller profile records.",
        body=rx.vstack(
            rx.hstack(
                rx.heading("Controller Profiles", size="2"),
                rx.spacer(),
                rx.input(
                    value=TrafficState.selected_device_id,
                    on_change=TrafficState.update_selected_device_id,
                    placeholder="Selected controller ID",
                    size="1",
                    max_width="14em",
                ),
                rx.button(
                    "Refresh",
                    on_click=TrafficState.refresh_fleet_status,
                    size="1",
                    variant="outline",
                ),
                spacing="2",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            configuration_workspace_fleet_profiles_editor(),
            spacing="2",
            width="100%",
        ),
    )

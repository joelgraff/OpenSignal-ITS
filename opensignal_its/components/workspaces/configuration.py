import reflex as rx

from ...states.traffic_state import TrafficState


def configuration_workspace_fleet_profiles_editor() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "configuration",
        rx.text_area(
            value=TrafficState.device_profiles_json,
            on_change=TrafficState.update_device_profiles_json,
            placeholder='[{"device_id":"int-1","device_type":"siemens_m60","ip_address":"10.0.0.1"}]',
            width="100%",
            min_height="7em",
        ),
        rx.text(
            "Advanced site-inventory JSON editor is available in the Site Inventory workspace.",
            size="1",
            color="gray",
        ),
    )

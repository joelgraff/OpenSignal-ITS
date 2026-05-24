import reflex as rx

from ...states.traffic_state import TrafficState
from .section_card import workspace_section_card


def _sort_button(label: str, sort_key: str) -> rx.Component:
    return rx.button(
        label,
        on_click=lambda: TrafficState.update_controller_profile_sort_key(sort_key),
        size="1",
        variant=rx.cond(TrafficState.controller_profile_sort_key == sort_key, "solid", "soft"),
        color_scheme=rx.cond(TrafficState.controller_profile_sort_key == sort_key, "indigo", "gray"),
    )


def _controller_profile_roster() -> rx.Component:
    return workspace_section_card(
        title="Configured Controllers",
        subtitle="Select a controller profile to edit or remove.",
        actions=rx.hstack(
            rx.input(
                value=TrafficState.controller_profile_filter_text,
                on_change=TrafficState.update_controller_profile_filter_text,
                placeholder="Search controllers",
                size="1",
                max_width="16em",
            ),
            _sort_button("ID", "device_id"),
            _sort_button("Name", "name"),
            _sort_button("IP", "ip_address"),
            rx.button(
                rx.cond(TrafficState.controller_profile_sort_desc, "Desc", "Asc"),
                on_click=TrafficState.toggle_controller_profile_sort_direction,
                size="1",
                variant="soft",
                color_scheme="gray",
            ),
            rx.button(
                "New",
                on_click=TrafficState.new_controller_profile,
                size="1",
                variant="outline",
            ),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        body=rx.vstack(
            rx.text(TrafficState.controller_profile_notice, size="1", color="gray"),
            rx.cond(
                TrafficState.controller_profile_rows != [],
                rx.box(
                    rx.foreach(
                        TrafficState.controller_profile_rows,
                        lambda row: rx.button(
                            rx.hstack(
                                rx.badge(
                                    row["status_label"],
                                    color_scheme=row["status_scheme"],
                                    size="1",
                                ),
                                rx.text(row["label"], size="1", text_align="left"),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            on_click=lambda: TrafficState.load_controller_profile_from_row(row["device_id"]),
                            variant="ghost",
                            size="1",
                            width="100%",
                            justify_content="start",
                        ),
                    ),
                    max_height="280px",
                    overflow_y="auto",
                    width="100%",
                ),
                rx.text("No controller profiles configured yet.", size="1", color="gray"),
            ),
            spacing="2",
            width="100%",
        ),
    )


def _controller_profile_form() -> rx.Component:
    return workspace_section_card(
        title="Controller Editor",
        subtitle="Structured edits keep controller-profile JSON valid and synchronized.",
        body=rx.vstack(
            rx.cond(
                TrafficState.controller_profile_form_error != "",
                rx.box(
                    rx.text(TrafficState.controller_profile_form_error, size="1", color="tomato"),
                    border="1px solid #fca5a5",
                    bg="#fef2f2",
                    border_radius="6px",
                    padding="2",
                    width="100%",
                ),
                rx.fragment(),
            ),
            rx.grid(
                rx.input(
                    value=TrafficState.controller_profile_form_device_id,
                    on_change=TrafficState.update_controller_profile_form_device_id,
                    placeholder="Controller ID",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_name,
                    on_change=TrafficState.update_controller_profile_form_name,
                    placeholder="Display name",
                    size="1",
                ),
                template_columns="repeat(auto-fit, minmax(220px, 1fr))",
                spacing="2",
                width="100%",
            ),
            rx.grid(
                rx.input(
                    value=TrafficState.controller_profile_form_ip_address,
                    on_change=TrafficState.update_controller_profile_form_ip_address,
                    placeholder="IP address",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_device_type,
                    on_change=TrafficState.update_controller_profile_form_device_type,
                    placeholder="Device type",
                    size="1",
                ),
                template_columns="repeat(auto-fit, minmax(220px, 1fr))",
                spacing="2",
                width="100%",
            ),
            rx.grid(
                rx.input(
                    value=TrafficState.controller_profile_form_port_text,
                    on_change=TrafficState.update_controller_profile_form_port_text,
                    placeholder="Port",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_community,
                    on_change=TrafficState.update_controller_profile_form_community,
                    placeholder="SNMP community",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_snmp_version,
                    on_change=TrafficState.update_controller_profile_form_snmp_version,
                    placeholder="SNMP version",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_timeout_text,
                    on_change=TrafficState.update_controller_profile_form_timeout_text,
                    placeholder="Timeout sec",
                    size="1",
                ),
                rx.input(
                    value=TrafficState.controller_profile_form_retries_text,
                    on_change=TrafficState.update_controller_profile_form_retries_text,
                    placeholder="Retries",
                    size="1",
                ),
                template_columns="repeat(auto-fit, minmax(120px, 1fr))",
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                rx.button(
                    rx.cond(
                        TrafficState.controller_profile_original_device_id != "",
                        "Update Profile",
                        "Add Profile",
                    ),
                    on_click=TrafficState.save_controller_profile,
                    size="1",
                ),
                rx.button(
                    "Delete",
                    on_click=TrafficState.delete_controller_profile,
                    size="1",
                    variant="outline",
                ),
                rx.button(
                    "Clear",
                    on_click=TrafficState.new_controller_profile,
                    size="1",
                    variant="ghost",
                ),
                rx.button(
                    "Open in Status",
                    on_click=TrafficState.open_selected_controller_status,
                    size="1",
                    variant="outline",
                ),
                spacing="2",
                wrap="wrap",
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
    )


def _advanced_json_editor() -> rx.Component:
    return workspace_section_card(
        title="Advanced JSON",
        subtitle="Use for bulk edits or troubleshooting. Structured edits update this source of truth.",
        body=rx.text_area(
            value=TrafficState.device_profiles_json,
            on_change=TrafficState.update_device_profiles_json,
            placeholder='[{"device_id":"int-1","device_type":"siemens_m60","ip_address":"10.0.0.1"}]',
            width="100%",
            min_height="12em",
        ),
    )


def configuration_workspace_fleet_profiles_editor() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "configuration",
        rx.vstack(
            rx.grid(
                _controller_profile_roster(),
                _controller_profile_form(),
                template_columns="1fr 1.4fr",
                spacing="2",
                width="100%",
            ),
            _advanced_json_editor(),
            spacing="2",
            width="100%",
        ),
        rx.text(
            "Advanced controller-profile JSON editor is available in the Controllers workspace.",
            size="1",
            color="gray",
        ),
    )

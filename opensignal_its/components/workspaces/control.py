import reflex as rx

from ...states.traffic_state import TrafficState


def control_workspace_section() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "control",
        rx.vstack(
            rx.heading("Command Safety", size="3"),
            rx.input(
                value=TrafficState.operator_key_input,
                on_change=TrafficState.update_operator_key_input,
                placeholder="Operator key",
                type="password",
                width="100%",
            ),
            rx.hstack(
                rx.input(
                    value=TrafficState.write_unlock_seconds_text,
                    on_change=TrafficState.update_write_unlock_seconds_text,
                    placeholder="Unlock sec",
                    width="8em",
                ),
                rx.button(
                    "Unlock Write Mode",
                    on_click=TrafficState.unlock_write_mode,
                    size="2",
                    color_scheme="red",
                ),
                rx.button(
                    "Lock Write Mode",
                    on_click=TrafficState.lock_write_mode,
                    size="2",
                    variant="outline",
                ),
                width="100%",
                spacing="2",
                align="center",
            ),
            rx.text(TrafficState.safety_notice, size="2", color="gray"),
            rx.heading("Write Confirmation", size="3"),
            rx.input(
                value=TrafficState.confirmation_input,
                on_change=TrafficState.update_confirmation_input,
                placeholder="Confirmation token",
                width="100%",
            ),
            rx.button(
                "Confirm Pending Command",
                on_click=TrafficState.confirm_pending_command,
                size="2",
                variant="outline",
                width="100%",
            ),
            rx.cond(
                TrafficState.pending_confirmation_notice != "",
                rx.text(TrafficState.pending_confirmation_notice, size="2", color="gray"),
                rx.fragment(),
            ),
            spacing="2",
            width="100%",
        ),
        rx.fragment(),
    )

import reflex as rx

from ...states.traffic_state import TrafficState


def control_workspace_section() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "control",
        rx.vstack(
            rx.text("Command Safety", size="1", color="gray", font_weight="600"),
            rx.hstack(
                rx.input(
                    value=TrafficState.operator_key_input,
                    on_change=TrafficState.update_operator_key_input,
                    placeholder="Operator key",
                    type="password",
                    size="1",
                    max_width="12em",
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
                spacing="2",
                align="center",
                wrap="wrap",
                width="100%",
            ),
            rx.text(TrafficState.safety_notice, size="1", color="gray"),
            rx.divider(),
            rx.text("Write Confirmation", size="1", color="gray", font_weight="600"),
            rx.hstack(
                rx.input(
                    value=TrafficState.confirmation_input,
                    on_change=TrafficState.update_confirmation_input,
                    placeholder="Confirmation token",
                    size="1",
                    max_width="18em",
                ),
                rx.button(
                    "Confirm",
                    on_click=TrafficState.confirm_pending_command,
                    size="1",
                    variant="outline",
                ),
                spacing="2",
                align="center",
                wrap="wrap",
                width="100%",
            ),
            rx.cond(
                TrafficState.pending_confirmation_notice != "",
                rx.text(TrafficState.pending_confirmation_notice, size="1", color="gray"),
                rx.fragment(),
            ),
            spacing="2",
            width="100%",
        ),
        rx.fragment(),
    )

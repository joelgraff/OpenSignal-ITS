import reflex as rx

from ...states import TrafficState
from .control import control_workspace_section
from .page_frame import workspace_page_frame


def control_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Signal Control",
        subtitle="Issue signal control commands and confirm pending actions.",
        body=rx.grid(
            rx.card(
                rx.vstack(
                    rx.heading("Signal Command Console", size="2"),
                    control_workspace_section(),
                    width="100%",
                    spacing="2",
                ),
                width="100%",
                size="1",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("SEPAC Ring Timer", size="2"),
                    rx.text("Controller-style text status", size="1", color="gray"),
                    rx.code_block(TrafficState.ring_status_console_text, language="log", width="100%"),
                    width="100%",
                    spacing="1",
                ),
                width="100%",
                size="1",
            ),
            template_columns="repeat(auto-fit, minmax(420px, 1fr))",
            spacing="2",
            width="100%",
        ),
    )

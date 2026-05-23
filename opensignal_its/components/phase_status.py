import reflex as rx
from typing import Dict


def phase_indicator(phase_num: int, data: Dict[str, bool | int]):
    """Single phase indicator with color coding."""
    green = data["green"]
    yellow = data["yellow"]
    red = data["red"]
    has_call = data["has_call"]
    vehicle_call = data["vehicle_call"]
    ped_call = data["ped_call"]
    time_remaining = data["time_remaining"]

    color = rx.cond(
        green,
        "green",
        rx.cond(yellow, "yellow", rx.cond(red, "red", "gray")),
    )

    return rx.vstack(
        rx.box(
            rx.text(f"P{phase_num}", font_weight="bold", font_size="1.1em"),
            rx.badge(
                rx.cond(has_call, "CALL", "-"),
                color_scheme=rx.cond(has_call, "orange", "gray"),
                size="1",
            ),
            background_color=color,
            color=rx.cond(green | yellow | red, "white", "black"),
            padding="8px",
            border_radius="8px",
            text_align="center",
            width="60px",
            height="60px",
            justify_content="center",
        ),
        rx.cond(
            time_remaining > 0,
            rx.text(f"{time_remaining}s", font_size="0.85em", color="gray"),
            rx.text("", font_size="0.85em", color="gray"),
        ),
        rx.hstack(
            rx.badge("V", color_scheme=rx.cond(vehicle_call, "orange", "gray"), size="1"),
            rx.badge("P", color_scheme=rx.cond(ped_call, "orange", "gray"), size="1"),
            spacing="1",
        ),
        align_items="center",
        spacing="1",
    )


def phase_status_grid(
    phases: Dict[str, Dict[str, bool | int]],
    current_pattern: str,
    unit_control_status: str,
    ring_status_summary: str,
    ring_status_lines: list[str],
    ring_status_console_text: str,
):
    """Grid showing all 16 phases with live status."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading("Real-Time Phase Status", size="5"),
                rx.badge("Live", color_scheme="green", variant="solid"),
                rx.spacer(),
                rx.text(f"Pattern: {current_pattern}", font_weight="bold"),
            ),
            rx.hstack(
                rx.badge(f"Unit: {unit_control_status}", color_scheme="blue"),
                rx.badge(f"Ring: {ring_status_summary}", color_scheme="indigo"),
                rx.badge("NTCIP 1202 Focus", color_scheme="indigo"),
                spacing="2",
                wrap="wrap",
            ),
            rx.box(
                rx.vstack(
                    rx.text("Ring Status Timer", font_weight="bold", size="2"),
                    rx.foreach(ring_status_lines, lambda line: rx.text(line, size="2")),
                    spacing="1",
                    width="100%",
                ),
                width="100%",
                max_height="100px",
                overflow_y="auto",
                border="1px solid #e5e7eb",
                border_radius="8px",
                padding="2",
            ),
            rx.code_block(
                ring_status_console_text,
                language="log",
                width="100%",
            ),
            rx.divider(),
            
            # Phase Grid (4 rows x 4 columns)
            rx.grid(
                *[
                    phase_indicator(
                        p,
                        phases[f"Phase_{p}"],
                    )
                    for p in range(1, 17)
                ],
                columns="4",
                spacing="3",
                width="100%",
            ),
            
            rx.text("Green = Active | Yellow = Clearance | Red = Stop | Orange = Any Call", size="2", color="gray"),
            rx.text("Focus objects: phase greens/reds, veh/ped calls, and phase time-to-change", size="2", color="gray"),
            spacing="4",
            width="100%",
        ),
        padding="6",
        width="100%",
    )
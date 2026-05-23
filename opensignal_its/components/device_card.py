#device_card.py
from typing import Any

import reflex as rx
from ..models.device import DeviceStatus


def device_card(status: DeviceStatus):
    """Reusable status card for any device."""
    return rx.card(
        rx.vstack(
            rx.heading(status.device_id, size="5"),
            rx.badge(
                "Online" if status.is_online else "Offline",
                color_scheme="green" if status.is_online else "red",
            ),
            rx.text(status.status_text),
            rx.text(f"Last updated: {status.timestamp.strftime('%H:%M:%S')}"),
            rx.divider(),
            rx.text("Raw Data:", font_weight="bold"),
            rx.scroll_area(
                rx.text(str(status.raw_data)[:500] + "..." if len(str(status.raw_data)) > 500 else status.raw_data),
                height="150px",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="4",
    )
    
def timing_panel(
    current_pattern: str,
    unit_status: str,
    green_phases: str,
    yellow_phases: str,
    red_phases: str,
    vehicle_calls: str,
    ped_calls: str,
    remaining_time_summary: str,
    timer_mode_text: str,
    ring_status_summary: str,
    ring_status_lines: list[str],
    phase_detail_lines: list[str],
    mode_text: str,
    on_select_pattern_1,
    on_select_pattern_2,
    on_set_mode_free,
    on_set_mode_coordinated,
    on_manual_hold,
    on_advance_phase,
):
    """Timing plan viewer and controls for Siemens M60."""
    return rx.card(
        rx.vstack(
            rx.heading("Timing Plan Control", size="5"),
            rx.hstack(
                rx.text("Current Pattern:"),
                rx.badge(current_pattern, color_scheme="blue"),
                rx.text("Unit Status:"),
                rx.badge(unit_status, color_scheme="green"),
            ),
            rx.hstack(
                rx.badge(f"Green: {green_phases}", color_scheme="green"),
                rx.badge(f"Yellow: {yellow_phases}", color_scheme="amber"),
                rx.badge(f"Red: {red_phases}", color_scheme="red"),
                wrap="wrap",
                spacing="2",
            ),
            rx.hstack(
                rx.badge(f"Vehicle Calls: {vehicle_calls}", color_scheme="orange"),
                rx.badge(f"Ped Calls: {ped_calls}", color_scheme="cyan"),
                wrap="wrap",
                spacing="2",
            ),
            rx.badge(f"Phase Countdown / Timer (s): {remaining_time_summary}", color_scheme="blue"),
            rx.text(f"Timer behavior: {timer_mode_text}", size="1", color="gray"),
            rx.badge(f"Ring Timer State: {ring_status_summary}", color_scheme="indigo"),
            rx.box(
                rx.vstack(
                    rx.text("Ring Status Timer", font_weight="bold", size="2"),
                    rx.text("NTCIP ringStatus decoded state and transition flags", size="1", color="gray"),
                    rx.foreach(ring_status_lines, lambda line: rx.text(line, size="2")),
                    spacing="1",
                    width="100%",
                ),
                width="100%",
                max_height="120px",
                overflow_y="auto",
                border="1px solid #e5e7eb",
                border_radius="8px",
                padding="2",
            ),
            rx.box(
                rx.vstack(
                    rx.text("Per-Phase Timer Values", font_weight="bold", size="2"),
                    rx.text("Legend: G=Green, Y=Yellow, R=Red, V=Vehicle Call, P=Ped Call", size="1", color="gray"),
                    rx.foreach(phase_detail_lines, lambda line: rx.text(line, size="2")),
                    spacing="1",
                    width="100%",
                ),
                width="100%",
                max_height="220px",
                overflow_y="auto",
                border="1px solid #e5e7eb",
                border_radius="8px",
                padding="2",
            ),
            rx.text(f"Controller: {mode_text}", size="2", color="gray"),
            rx.divider(),
            
            # Command Buttons
            rx.hstack(
                rx.button("Select Pattern 1", on_click=on_select_pattern_1, size="2"),
                rx.button("Select Pattern 2", on_click=on_select_pattern_2, size="2"),
                rx.button("Free Mode", on_click=on_set_mode_free, size="2", color_scheme="amber"),
                rx.button("Coordinated", on_click=on_set_mode_coordinated, size="2"),
                spacing="3",
                wrap="wrap",
            ),
            
            rx.hstack(
                rx.button("Manual Hold", on_click=on_manual_hold, size="2", color_scheme="red"),
                rx.button("Advance Phase", on_click=on_advance_phase, size="2"),
                spacing="3",
            ),
            
            rx.text("Note: Commands use NTCIP SET or Telnet fallback", size="2", color="gray"),
            spacing="4",
            width="100%",
        ),
        width="100%",
        padding="5",
    )
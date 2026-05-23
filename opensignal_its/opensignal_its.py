import reflex as rx

from .components.device_card import timing_panel
from .states.traffic_state import TrafficState


# Example page
def index():
    return rx.vstack(
        rx.heading("Traffic Controller Platform", size="9"),
        rx.hstack(
            rx.input(
                value=TrafficState.ip_address,
                on_change=TrafficState.update_ip_address,
                placeholder="Controller IP",
                width="18em",
            ),
            rx.input(
                value=TrafficState.port_text,
                on_change=TrafficState.update_port_text,
                placeholder="Port",
                width="7em",
            ),
            rx.input(
                value=TrafficState.community,
                on_change=TrafficState.update_community,
                placeholder="SNMP community",
                width="10em",
            ),
            spacing="3",
            wrap="wrap",
        ),
        rx.hstack(
            rx.input(
                value=TrafficState.snmp_version,
                on_change=TrafficState.update_snmp_version,
                placeholder="SNMP version: auto | v2c | v1",
                width="14em",
            ),
            rx.input(
                value=TrafficState.timeout_text,
                on_change=TrafficState.update_timeout_text,
                placeholder="Timeout seconds",
                width="10em",
            ),
            rx.input(
                value=TrafficState.retries_text,
                on_change=TrafficState.update_retries_text,
                placeholder="Retries",
                width="7em",
            ),
            spacing="3",
            wrap="wrap",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.safe_command_probe,
                on_change=TrafficState.update_safe_command_probe,
            ),
            rx.text("Safe Command Probe (no SNMP SET writes)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.auto_refresh_enabled,
                on_change=TrafficState.update_auto_refresh_enabled,
            ),
            rx.text("Auto Refresh"),
            rx.input(
                value=TrafficState.refresh_interval_text,
                on_change=TrafficState.update_refresh_interval_text,
                placeholder="Seconds",
                width="6em",
            ),
            rx.text("sec"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.auto_reconnect_enabled,
                on_change=TrafficState.update_auto_reconnect_enabled,
            ),
            rx.text("Auto Reconnect"),
            rx.input(
                value=TrafficState.reconnect_interval_text,
                on_change=TrafficState.update_reconnect_interval_text,
                placeholder="Seconds",
                width="6em",
            ),
            rx.text("sec"),
            spacing="2",
            align="center",
        ),
        rx.button("Connect & Poll Siemens M60", on_click=TrafficState.connect_and_start_polling),
        timing_panel(
            TrafficState.current_pattern,
            TrafficState.unit_status,
            TrafficState.green_phases,
            TrafficState.yellow_phases,
            TrafficState.red_phases,
            TrafficState.vehicle_calls,
            TrafficState.ped_calls,
            TrafficState.remaining_time_summary,
            TrafficState.timer_mode_text,
            TrafficState.ring_status_summary,
            TrafficState.ring_status_lines,
            TrafficState.phase_detail_lines,
            TrafficState.status_text,
            TrafficState.select_pattern_1,
            TrafficState.select_pattern_2,
            TrafficState.set_mode_free,
            TrafficState.set_mode_coordinated,
            TrafficState.manual_hold,
            TrafficState.advance_phase,
        ),
        rx.cond(
            TrafficState.m60_status_json != "",
            rx.code_block(TrafficState.m60_status_json, language="json"),
            rx.text("No status yet."),
        ),
        spacing="5",
        padding="2em",
    )


def dashboard():
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading("OpenSignal ITS Controller Console", size="8", color="indigo"),
                    rx.spacer(),
                    rx.button(
                        "Connect",
                        on_click=TrafficState.connect_and_start_polling,
                        is_disabled=TrafficState.is_loading,
                        color_scheme="green",
                        size="3",
                    ),
                    rx.button(
                        "Refresh",
                        on_click=TrafficState.refresh_status,
                        is_disabled=TrafficState.is_loading,
                        size="3",
                    ),
                    width="100%",
                ),
                rx.hstack(
                    rx.badge(
                        rx.cond(TrafficState.is_online, "ONLINE", "OFFLINE"),
                        color_scheme=rx.cond(TrafficState.is_online, "green", "red"),
                    ),
                    rx.badge(f"Pattern {TrafficState.current_pattern}", color_scheme="blue"),
                    rx.badge(f"Unit {TrafficState.unit_status}", color_scheme="gray"),
                    rx.badge(
                        rx.cond(TrafficState.safe_command_probe, "PROBE MODE", "WRITE MODE"),
                        color_scheme=rx.cond(TrafficState.safe_command_probe, "amber", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_refresh_running, "AUTO REFRESH ON", "AUTO REFRESH OFF"),
                        color_scheme=rx.cond(TrafficState.auto_refresh_running, "green", "gray"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_reconnect_enabled, "AUTO RECONNECT ON", "AUTO RECONNECT OFF"),
                        color_scheme=rx.cond(TrafficState.auto_reconnect_enabled, "green", "gray"),
                    ),
                    rx.text(f"SNMP {TrafficState.active_snmp_version}"),
                    rx.text(f"Updated: {TrafficState.last_updated}"),
                    spacing="3",
                    wrap="wrap",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            padding="4",
        ),
        rx.grid(
            rx.card(
                rx.vstack(
                    rx.heading("Connection & Polling", size="4"),
                    rx.input(
                        value=TrafficState.ip_address,
                        on_change=TrafficState.update_ip_address,
                        placeholder="Controller IP",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.port_text,
                            on_change=TrafficState.update_port_text,
                            placeholder="Port",
                            width="40%",
                        ),
                        rx.input(
                            value=TrafficState.community,
                            on_change=TrafficState.update_community,
                            placeholder="Community",
                            width="60%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.timeout_text,
                            on_change=TrafficState.update_timeout_text,
                            placeholder="Timeout sec",
                            width="50%",
                        ),
                        rx.input(
                            value=TrafficState.retries_text,
                            on_change=TrafficState.update_retries_text,
                            placeholder="Retries",
                            width="50%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_refresh_enabled,
                            on_change=TrafficState.update_auto_refresh_enabled,
                        ),
                        rx.text("Auto Refresh"),
                        rx.input(
                            value=TrafficState.refresh_interval_text,
                            on_change=TrafficState.update_refresh_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_reconnect_enabled,
                            on_change=TrafficState.update_auto_reconnect_enabled,
                        ),
                        rx.text("Auto Reconnect"),
                        rx.input(
                            value=TrafficState.reconnect_interval_text,
                            on_change=TrafficState.update_reconnect_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
                height="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("SEPAC Ring Timer Text View", size="4"),
                    rx.text("Controller-style text status", size="1", color="gray"),
                    rx.code_block(TrafficState.ring_status_console_text, language="log", width="100%"),
                    width="100%",
                    spacing="2",
                ),
                width="100%",
                height="100%",
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.cond(
            TrafficState.error != "",
            rx.box(
                rx.text(TrafficState.error),
                border="1px solid #fca5a5",
                bg="#fef2f2",
                padding="3",
                border_radius="8px",
                width="100%",
            ),
            rx.fragment(),
        ),
        spacing="6",
        padding="6",
        width="100%",
        max_width="1400px",
        margin="0 auto",
    )

app = rx.App()
app.add_page(dashboard, route="/", title="OpenSignal ITS")

import reflex as rx

from .components.device_card import timing_panel
from .services import OpsApiService, bootstrap_runtime_safety, start_retention_scheduler
from .states.traffic_state import TrafficState


bootstrap_runtime_safety()
start_retention_scheduler()


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
                        rx.cond(TrafficState.write_mode_active, "WRITE UNLOCKED", "WRITE LOCKED"),
                        color_scheme=rx.cond(TrafficState.write_mode_active, "red", "gray"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_refresh_running, "AUTO REFRESH ON", "AUTO REFRESH OFF"),
                        color_scheme=rx.cond(TrafficState.auto_refresh_running, "green", "gray"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_reconnect_enabled, "AUTO RECONNECT ON", "AUTO RECONNECT OFF"),
                        color_scheme=rx.cond(TrafficState.auto_reconnect_enabled, "green", "gray"),
                    ),
                    rx.badge(f"FLEET {TrafficState.fleet_total_count}", color_scheme="blue"),
                    rx.badge(f"ONLINE {TrafficState.fleet_online_count}", color_scheme="green"),
                    rx.badge(f"OFFLINE {TrafficState.fleet_offline_count}", color_scheme="red"),
                    rx.badge(f"ROLE {TrafficState.current_role.upper()}", color_scheme="indigo"),
                    rx.badge(
                        rx.cond(
                            TrafficState.retention_scheduler_running,
                            "RETENTION SCHEDULER ON",
                            "RETENTION SCHEDULER OFF",
                        ),
                        color_scheme=rx.cond(TrafficState.retention_scheduler_running, "green", "gray"),
                    ),
                    rx.text(f"SNMP {TrafficState.active_snmp_version}"),
                    rx.text(f"Selected: {TrafficState.selected_device_id}"),
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
                    rx.heading("Fleet Profiles", size="3"),
                    rx.text_area(
                        value=TrafficState.device_profiles_json,
                        on_change=TrafficState.update_device_profiles_json,
                        placeholder='[{"device_id":"int-1","device_type":"siemens_m60","ip_address":"10.0.0.1"}]',
                        width="100%",
                        min_height="7em",
                    ),
                    rx.input(
                        value=TrafficState.selected_device_id,
                        on_change=TrafficState.update_selected_device_id,
                        placeholder="Selected device_id (optional)",
                        width="100%",
                    ),
                    rx.button(
                        "Refresh Fleet",
                        on_click=TrafficState.refresh_fleet_status,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.managed_polling_interval_text,
                            on_change=TrafficState.update_managed_polling_interval_text,
                            placeholder="Managed poll sec",
                            width="8em",
                        ),
                        rx.button(
                            "Start Managed Polling",
                            on_click=TrafficState.start_selected_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Stop Managed Polling",
                            on_click=TrafficState.stop_selected_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.button(
                            "Start Fleet Polling",
                            on_click=TrafficState.start_fleet_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Stop Fleet Polling",
                            on_click=TrafficState.stop_fleet_managed_polling,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.text(TrafficState.managed_polling_notice, size="2", color="gray"),
                    rx.button(
                        "Refresh Runtime Registry",
                        on_click=TrafficState.refresh_runtime_registry_status,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.text(TrafficState.runtime_registry_summary, size="2", color="gray"),
                    rx.foreach(
                        TrafficState.runtime_registry_rows,
                        lambda row: rx.text(row, size="1", color="gray"),
                    ),
                    rx.text(TrafficState.fleet_status_summary, size="2", color="gray"),
                    rx.foreach(
                        TrafficState.fleet_device_rows,
                        lambda row: rx.text(row, size="1", color="gray"),
                    ),
                    rx.heading("Operator Access", size="3"),
                    rx.input(
                        value=TrafficState.login_username_input,
                        on_change=TrafficState.update_login_username_input,
                        placeholder="Operator username",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.login_password_input,
                        on_change=TrafficState.update_login_password_input,
                        placeholder="Operator password",
                        type="password",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button(
                            "Login Operator",
                            on_click=TrafficState.login_operator,
                            size="2",
                            color_scheme="green",
                        ),
                        rx.button(
                            "Logout Operator",
                            on_click=TrafficState.logout_operator,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.text(TrafficState.auth_notice, size="2", color="gray"),
                    rx.input(
                        value=TrafficState.admin_recovery_key_input,
                        on_change=TrafficState.update_admin_recovery_key_input,
                        placeholder="Admin recovery key",
                        type="password",
                        width="100%",
                    ),
                    rx.button(
                        "Reset Login Lockout",
                        on_click=TrafficState.reset_login_lockout,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.cond(
                        TrafficState.admin_recovery_notice != "",
                        rx.text(TrafficState.admin_recovery_notice, size="2", color="gray"),
                        rx.fragment(),
                    ),
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
                    rx.heading("Maintenance", size="3"),
                    rx.button(
                        "Refresh Runtime Health",
                        on_click=TrafficState.refresh_runtime_health,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.text(TrafficState.runtime_health_notice, size="2", color="gray"),
                    rx.text(TrafficState.runtime_storage_summary, size="1", color="gray"),
                    rx.text(TrafficState.runtime_alert_dispatch_summary, size="1", color="gray"),
                    rx.cond(
                        TrafficState.runtime_storage_warning_rows != [],
                        rx.foreach(
                            TrafficState.runtime_storage_warning_rows,
                            lambda row: rx.text(row, size="1", color="tomato"),
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        TrafficState.runtime_storage_alert_rows != [],
                        rx.foreach(
                            TrafficState.runtime_storage_alert_rows,
                            lambda row: rx.text(row, size="1", color="red"),
                        ),
                        rx.fragment(),
                    ),
                    rx.button(
                        "Run Retention Cleanup",
                        on_click=TrafficState.run_retention_cleanup,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.button(
                        "Export Audit Report",
                        on_click=TrafficState.export_audit_report,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.text(
                        f"Scheduler enabled: {TrafficState.retention_scheduler_enabled} | "
                        f"running: {TrafficState.retention_scheduler_running} | "
                        f"interval: {TrafficState.retention_scheduler_interval_text}s",
                        size="1",
                        color="gray",
                    ),
                    rx.cond(
                        TrafficState.last_retention_cleanup_at != "",
                        rx.text(
                            f"Last cleanup: {TrafficState.last_retention_cleanup_at}",
                            size="1",
                            color="gray",
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        TrafficState.retention_scheduler_error != "",
                        rx.text(TrafficState.retention_scheduler_error, size="1", color="tomato"),
                        rx.fragment(),
                    ),
                    rx.cond(
                        TrafficState.maintenance_notice != "",
                        rx.text(TrafficState.maintenance_notice, size="2", color="gray"),
                        rx.fragment(),
                    ),
                    rx.cond(
                        TrafficState.audit_export_notice != "",
                        rx.text(TrafficState.audit_export_notice, size="2", color="gray"),
                        rx.fragment(),
                    ),
                    rx.heading("Events & Alarms", size="3"),
                    rx.button(
                        "Refresh Events",
                        on_click=TrafficState.refresh_events_and_alarms,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button("15m", on_click=lambda: TrafficState.update_event_window("15m"), size="1", variant="soft"),
                        rx.button("1h", on_click=lambda: TrafficState.update_event_window("1h"), size="1", variant="soft"),
                        rx.button("24h", on_click=lambda: TrafficState.update_event_window("24h"), size="1", variant="soft"),
                        rx.button("All", on_click=lambda: TrafficState.update_event_window("all"), size="1", variant="soft"),
                        width="100%",
                        spacing="2",
                    ),
                    rx.input(
                        value=TrafficState.selected_alarm_key,
                        on_change=TrafficState.update_selected_alarm_key,
                        placeholder="Alarm key to acknowledge/clear",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.alarm_note_input,
                        on_change=TrafficState.update_alarm_note_input,
                        placeholder="Alarm note (optional)",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.alarm_silence_minutes_text,
                        on_change=TrafficState.update_alarm_silence_minutes_text,
                        placeholder="Silence minutes (default 30)",
                        width="100%",
                    ),
                    rx.button(
                        "Use Silence Policy",
                        on_click=TrafficState.apply_selected_alarm_silence_policy,
                        size="2",
                        variant="outline",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button(
                            "Acknowledge Alarm",
                            on_click=TrafficState.acknowledge_selected_alarm,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Clear Alarm Ack",
                            on_click=TrafficState.clear_selected_alarm_acknowledgement,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Silence Alarm",
                            on_click=TrafficState.silence_selected_alarm,
                            size="2",
                            variant="outline",
                        ),
                        rx.button(
                            "Clear Silence",
                            on_click=TrafficState.clear_selected_alarm_silence,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.cond(
                        TrafficState.alarm_action_notice != "",
                        rx.text(TrafficState.alarm_action_notice, size="2", color="gray"),
                        rx.fragment(),
                    ),
                    rx.text(TrafficState.event_notice, size="2", color="gray"),
                    rx.cond(
                        TrafficState.alarm_rows != [],
                        rx.foreach(
                            TrafficState.alarm_rows,
                            lambda row: rx.text(row, size="1", color="tomato"),
                        ),
                        rx.text("No active alarms.", size="1", color="gray"),
                    ),
                    rx.cond(
                        TrafficState.acknowledged_alarm_rows != [],
                        rx.foreach(
                            TrafficState.acknowledged_alarm_rows,
                            lambda row: rx.text(row, size="1", color="green"),
                        ),
                        rx.text("No acknowledged alarms.", size="1", color="gray"),
                    ),
                    rx.cond(
                        TrafficState.silenced_alarm_rows != [],
                        rx.foreach(
                            TrafficState.silenced_alarm_rows,
                            lambda row: rx.text(row, size="1", color="orange"),
                        ),
                        rx.text("No silenced alarms.", size="1", color="gray"),
                    ),
                    rx.heading("Alarm Action History", size="2"),
                    rx.hstack(
                        rx.button("All", on_click=lambda: TrafficState.update_alarm_history_action_filter("all"), size="1", variant="soft"),
                        rx.button("Ack", on_click=lambda: TrafficState.update_alarm_history_action_filter("acknowledge"), size="1", variant="soft"),
                        rx.button("Clear Ack", on_click=lambda: TrafficState.update_alarm_history_action_filter("clear_acknowledgement"), size="1", variant="soft"),
                        rx.button("Silence", on_click=lambda: TrafficState.update_alarm_history_action_filter("silence"), size="1", variant="soft"),
                        rx.button("Clear Silence", on_click=lambda: TrafficState.update_alarm_history_action_filter("clear_silence"), size="1", variant="soft"),
                        width="100%",
                        spacing="2",
                    ),
                    rx.input(
                        value=TrafficState.alarm_history_actor_filter,
                        on_change=TrafficState.update_alarm_history_actor_filter,
                        placeholder="History actor filter (contains)",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.alarm_history_key_filter,
                        on_change=TrafficState.update_alarm_history_key_filter,
                        placeholder="History alarm key filter (contains)",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.alarm_history_limit_text,
                        on_change=TrafficState.update_alarm_history_limit_text,
                        placeholder="History row limit (5-200)",
                        width="100%",
                    ),
                    rx.button(
                        "Apply History Filters",
                        on_click=TrafficState.refresh_events_and_alarms,
                        size="1",
                        variant="outline",
                        width="100%",
                    ),
                    rx.cond(
                        TrafficState.alarm_history_rows != [],
                        rx.box(
                            rx.foreach(
                                TrafficState.alarm_history_rows,
                                lambda row: rx.text(row, size="1", color="gray"),
                            ),
                            max_height="180px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        rx.text("No alarm action history.", size="1", color="gray"),
                    ),
                    rx.foreach(
                        TrafficState.event_timeline_rows,
                        lambda row: rx.text(row, size="1", color="gray"),
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
OPS_API_ENDPOINTS: dict[str, object] = {}


def _register_operational_api_routes() -> None:
    global OPS_API_ENDPOINTS
    OPS_API_ENDPOINTS = {}
    if not OpsApiService.ops_api_enabled():
        return

    def ops_health(api_token: str = "") -> dict:
        ok, message = OpsApiService.validate_access(api_token)
        if not ok:
            return {"ok": False, "error": message}
        payload = OpsApiService.health_snapshot()
        payload["ok"] = True
        return payload

    def ops_alarms(
        window_minutes: int | None = 60,
        command_limit: int = 200,
        snapshot_limit: int = 200,
        api_token: str = "",
    ) -> dict:
        ok, message = OpsApiService.validate_access(api_token)
        if not ok:
            return {"ok": False, "error": message}
        payload = OpsApiService.alarms_snapshot(
            window_minutes=window_minutes,
            command_limit=command_limit,
            snapshot_limit=snapshot_limit,
        )
        payload["ok"] = True
        return payload

    def ops_alarm_history(
        limit: int = 50,
        action_filter: str = "all",
        actor_contains: str = "",
        key_contains: str = "",
        api_token: str = "",
    ) -> dict:
        ok, message = OpsApiService.validate_access(api_token)
        if not ok:
            return {"ok": False, "error": message}
        payload = OpsApiService.alarm_history_snapshot(
            limit=limit,
            action_filter=action_filter,
            actor_contains=actor_contains,
            key_contains=key_contains,
        )
        payload["ok"] = True
        return payload

    def ops_audit_export(
        file_path: str = "",
        command_limit: int = 200,
        snapshot_limit: int = 200,
        api_token: str = "",
    ) -> dict:
        ok, message = OpsApiService.validate_access(api_token)
        if not ok:
            return {"ok": False, "error": message}
        payload = OpsApiService.audit_export_snapshot(
            file_path=file_path,
            command_limit=command_limit,
            snapshot_limit=snapshot_limit,
        )
        payload["ok"] = True
        return payload

    OPS_API_ENDPOINTS = {
        "/api/ops/health": ops_health,
        "/api/ops/alarms": ops_alarms,
        "/api/ops/alarm-history": ops_alarm_history,
        "/api/ops/audit-export": ops_audit_export,
    }

    api = getattr(app, "api", None) or getattr(app, "_api", None)
    if api is None:
        return
    if hasattr(api, "add_api_route"):
        for path, endpoint in OPS_API_ENDPOINTS.items():
            api.add_api_route(path=path, endpoint=endpoint, methods=["GET"])


_register_operational_api_routes()

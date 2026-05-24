import reflex as rx

from .components.device_card import timing_panel
from .components.workspaces import (
    admin_workspace_page,
    workspace_page_content,
    workspace_tabs,
)
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
                    rx.cond(
                        TrafficState.is_authenticated,
                        rx.hstack(
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
                            spacing="2",
                        ),
                        rx.badge("SIGN-IN REQUIRED", color_scheme="orange"),
                    ),
                    width="100%",
                ),
                rx.hstack(
                    rx.badge(
                        rx.cond(TrafficState.is_online, "ONLINE", "OFFLINE"),
                        color_scheme=rx.cond(TrafficState.is_online, "green", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.safe_command_probe, "PROBE MODE", "WRITE MODE"),
                        color_scheme=rx.cond(TrafficState.safe_command_probe, "amber", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.write_mode_active, "WRITE UNLOCKED", "WRITE LOCKED"),
                        color_scheme=rx.cond(TrafficState.write_mode_active, "red", "gray"),
                    ),
                    rx.badge(f"ROLE {TrafficState.current_role.upper()}", color_scheme="indigo"),
                    rx.badge(f"ALARMS {TrafficState.alarm_rows.length()}", color_scheme="orange"),
                    rx.text(f"Selected: {TrafficState.selected_device_id}"),
                    rx.text(f"Updated: {TrafficState.last_updated}"),
                    spacing="3",
                    wrap="wrap",
                    width="100%",
                ),
                rx.text(
                    f"Pattern {TrafficState.current_pattern} | Unit {TrafficState.unit_status} | "
                    f"SNMP {TrafficState.active_snmp_version} | Fleet {TrafficState.fleet_total_count} total "
                    f"({TrafficState.fleet_online_count} online / {TrafficState.fleet_offline_count} offline)",
                    size="2",
                    color="gray",
                    width="100%",
                ),
                rx.cond(
                    TrafficState.is_authenticated,
                    workspace_tabs(),
                    rx.text(
                        "Sign in to access signal sites, control, maintenance, analytics, and configuration.",
                        size="2",
                        color="gray",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            padding="4",
        ),
        rx.cond(
            TrafficState.is_authenticated,
            workspace_page_content(),
            admin_workspace_page(),
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

    def ops_health(api_token: str = "", authorization: str = "") -> dict:
        token = OpsApiService.extract_api_token(api_token=api_token, authorization=authorization)
        ok, message = OpsApiService.validate_access(token)
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
        authorization: str = "",
    ) -> dict:
        token = OpsApiService.extract_api_token(api_token=api_token, authorization=authorization)
        ok, message = OpsApiService.validate_access(token)
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
        authorization: str = "",
    ) -> dict:
        token = OpsApiService.extract_api_token(api_token=api_token, authorization=authorization)
        ok, message = OpsApiService.validate_access(token)
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
        authorization: str = "",
    ) -> dict:
        token = OpsApiService.extract_api_token(api_token=api_token, authorization=authorization)
        ok, message = OpsApiService.validate_access(token)
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

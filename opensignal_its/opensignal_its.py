import reflex as rx

from .components.workspaces import (
    admin_workspace_page,
    workspace_page_content,
    workspace_tabs,
)
from .services import OpsApiService, bootstrap_runtime_safety, start_retention_scheduler
from .states.traffic_state import TrafficState


def _initialize_runtime() -> None:
    bootstrap_runtime_safety()
    start_retention_scheduler()


def dashboard():
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading("OpenSignal ITS", size="5", color="indigo"),
                    rx.text("Controller Console", size="1", color="gray"),
                    rx.spacer(),
                    rx.badge(
                        rx.cond(TrafficState.is_online, "ONLINE", "OFFLINE"),
                        color_scheme=rx.cond(TrafficState.is_online, "green", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.safe_command_probe, "PROBE", "WRITE"),
                        color_scheme=rx.cond(TrafficState.safe_command_probe, "amber", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.write_mode_active, "UNLOCKED", "LOCKED"),
                        color_scheme=rx.cond(TrafficState.write_mode_active, "red", "gray"),
                    ),
                    rx.badge(f"ROLE {TrafficState.current_role.upper()}", color_scheme="indigo"),
                    rx.badge(f"ALARMS {TrafficState.alarm_rows.length()}", color_scheme="orange"),
                    rx.cond(
                        TrafficState.is_authenticated,
                        rx.hstack(
                            rx.button(
                                "Connect",
                                on_click=TrafficState.connect_and_start_polling,
                                is_disabled=TrafficState.is_loading,
                                color_scheme="green",
                                size="1",
                            ),
                            rx.button(
                                "Refresh",
                                on_click=TrafficState.refresh_status,
                                is_disabled=TrafficState.is_loading,
                                size="1",
                                variant="outline",
                            ),
                            spacing="1",
                        ),
                        rx.badge("SIGN-IN REQUIRED", color_scheme="orange"),
                    ),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                    width="100%",
                ),
                rx.hstack(
                    rx.text(
                        f"Controller: {TrafficState.selected_device_id} | Pattern {TrafficState.current_pattern} | "
                        f"Unit {TrafficState.unit_status} | SNMP {TrafficState.active_snmp_version} | "
                        f"Controllers {TrafficState.fleet_total_count} ({TrafficState.fleet_online_count}\u2191 / {TrafficState.fleet_offline_count}\u2193) | "
                        f"Updated {TrafficState.last_updated}",
                        size="1",
                        color="gray",
                    ),
                    width="100%",
                ),
                rx.cond(
                    TrafficState.is_authenticated,
                    workspace_tabs(),
                    rx.text(
                        "Sign in to access controllers, control, maintenance, alarms/events, and controller profiles.",
                        size="1",
                        color="gray",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
            size="1",
        ),
        rx.cond(
            TrafficState.is_authenticated,
            workspace_page_content(),
            admin_workspace_page(),
        ),
        rx.cond(
            TrafficState.error != "",
            rx.box(
                rx.text(TrafficState.error, size="1"),
                border="1px solid #fca5a5",
                bg="#fef2f2",
                padding="2",
                border_radius="6px",
                width="100%",
            ),
            rx.fragment(),
        ),
        spacing="3",
        padding="3",
        width="100%",
        max_width="1600px",
        margin="0 auto",
    )

app = rx.App()
app.register_lifespan_task(_initialize_runtime)
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

import json
import asyncio
from typing import Any

import reflex as rx
from .components.device_card import timing_panel
from .models.device import DeviceConfig
from .devices.siemens_m60 import SiemensM60

class TrafficState(rx.State):
    """Main app state."""
    m60_status: dict = {}
    m60_status_json: str = ""
    status_text: str = "No status yet"
    active_snmp_version: str = "unknown"
    current_pattern: str = "Unknown"
    unit_status: str = "unknown"
    green_phases: str = "none"
    yellow_phases: str = "none"
    red_phases: str = "none"
    vehicle_calls: str = "none"
    ped_calls: str = "none"
    remaining_time_summary: str = "none"
    timer_mode_text: str = "unknown"
    phase_detail_lines: list[str] = []
    last_timer_snapshot: dict[str, int] = {}
    is_online: bool = False
    last_updated: str = ""
    error: str = ""
    is_loading: bool = False
    ip_address: str = "166.156.88.223"
    port_text: str = "161"
    community: str = "public"
    snmp_version: str = "auto"
    timeout_text: str = "3"
    retries_text: str = "1"
    safe_command_probe: bool = True
    auto_refresh_enabled: bool = True
    refresh_interval_text: str = "5"
    auto_reconnect_enabled: bool = True
    reconnect_interval_text: str = "10"
    auto_refresh_running: bool = False

    def update_ip_address(self, value: str):
        self.ip_address = value

    def update_port_text(self, value: str):
        self.port_text = value

    def update_community(self, value: str):
        self.community = value

    def update_snmp_version(self, value: str):
        self.snmp_version = value

    def update_timeout_text(self, value: str):
        self.timeout_text = value

    def update_retries_text(self, value: str):
        self.retries_text = value

    def update_safe_command_probe(self, value: bool):
        self.safe_command_probe = value

    def update_auto_refresh_enabled(self, value: bool):
        self.auto_refresh_enabled = value

    def update_refresh_interval_text(self, value: str):
        self.refresh_interval_text = value

    def update_auto_reconnect_enabled(self, value: bool):
        self.auto_reconnect_enabled = value

    def update_reconnect_interval_text(self, value: str):
        self.reconnect_interval_text = value

    def _refresh_interval_seconds(self) -> float:
        try:
            return max(1.0, float(self.refresh_interval_text))
        except ValueError:
            return 5.0

    def _reconnect_interval_seconds(self) -> float:
        try:
            return max(2.0, float(self.reconnect_interval_text))
        except ValueError:
            return 10.0

    def _build_config(self) -> DeviceConfig:
        port = int(self.port_text)
        timeout_seconds = float(self.timeout_text)
        retries = int(self.retries_text)
        return DeviceConfig(
            ip_address=self.ip_address.strip(),
            port=port,
            name="Siemens M60 Test",
            community=self.community.strip(),
            snmp_version=self.snmp_version.strip().lower(),
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    def _apply_phase_payload(self, payload: dict):
        raw_data = payload.get("raw_data", {}) if isinstance(payload, dict) else {}
        extra = payload.get("extra", {}) if isinstance(payload, dict) else {}

        self.current_pattern = str(raw_data.get("current_pattern", "Unknown"))
        self.unit_status = str(raw_data.get("unit_status", "unknown"))

        summary = extra.get("phase_summary", {}) if isinstance(extra, dict) else {}
        greens = summary.get("green", []) if isinstance(summary, dict) else []
        yellows = summary.get("yellow", []) if isinstance(summary, dict) else []
        reds = summary.get("red", []) if isinstance(summary, dict) else []
        veh_calls = summary.get("vehicle_calls", []) if isinstance(summary, dict) else []
        ped_calls = summary.get("ped_calls", []) if isinstance(summary, dict) else []

        self.green_phases = ", ".join(str(v) for v in greens) if greens else "none"
        self.yellow_phases = ", ".join(str(v) for v in yellows) if yellows else "none"
        self.red_phases = ", ".join(str(v) for v in reds) if reds else "none"
        self.vehicle_calls = ", ".join(str(v) for v in veh_calls) if veh_calls else "none"
        self.ped_calls = ", ".join(str(v) for v in ped_calls) if ped_calls else "none"

        phases = extra.get("phases", {}) if isinstance(extra, dict) else {}
        lines: list[str] = []
        timer_parts: list[str] = []
        timer_snapshot: dict[str, int] = {}
        if isinstance(phases, dict):
            for phase in range(1, 17):
                phase_key = str(phase)
                entry = phases.get(phase_key, {})
                if not isinstance(entry, dict):
                    continue
                flags = []
                if entry.get("green"):
                    flags.append("G")
                if entry.get("yellow"):
                    flags.append("Y")
                if entry.get("red"):
                    flags.append("R")
                state = "/".join(flags) if flags else "OFF"
                v_call = "Y" if entry.get("vehicle_call") else "N"
                p_call = "Y" if entry.get("ped_call") else "N"
                timer = int(entry.get("time_remaining", 0) or 0)
                timer_snapshot[phase_key] = timer
                lines.append(f"P{phase:02d} {state:6s} V:{v_call} P:{p_call} T:{timer:>3d}s")
                if timer > 0:
                    timer_parts.append(f"P{phase}:{timer}")
        self.phase_detail_lines = lines
        self.remaining_time_summary = ", ".join(timer_parts) if timer_parts else "none"
        if self.last_timer_snapshot:
            self.timer_mode_text = "dynamic" if self.last_timer_snapshot != timer_snapshot else "static"
        else:
            self.timer_mode_text = "unknown"
        self.last_timer_snapshot = timer_snapshot

    async def _collect_status_snapshot(self) -> tuple[dict, int]:
        """Fetch one controller status snapshot without mutating UI state."""
        config = self._build_config()
        device = SiemensM60(config)
        success = await device.connect()
        if success:
            status_payload = (await device.poll()).model_dump(mode="json")
        else:
            status_payload = device.status.model_dump(mode="json")
        mp_model = getattr(device, "_mp_model", 1)
        return status_payload, mp_model

    def _apply_status_snapshot(self, status_payload: dict, mp_model: int):
        """Apply one status snapshot to state fields used by the UI."""
        self.m60_status = status_payload
        self.m60_status_json = json.dumps(self.m60_status, indent=2)
        self.status_text = str(self.m60_status.get("status_text", "Unknown"))
        self.is_online = bool(self.m60_status.get("is_online", False))
        self.last_updated = str(self.m60_status.get("timestamp", ""))
        self._apply_phase_payload(self.m60_status)
        self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
        errors = self.m60_status.get("errors", [])
        self.error = "; ".join(errors) if errors else ""

    async def connect_m60(self):
        await self.add_and_poll_m60()
        if (self.auto_refresh_enabled or self.auto_reconnect_enabled) and not self.auto_refresh_running:
            return TrafficState.auto_refresh_loop

    async def refresh_status(self):
        await self.add_and_poll_m60()

    @rx.event(background=True)
    async def auto_refresh_loop(self):
        """Continuously poll while online and auto-reconnect when offline."""
        async with self:
            if self.auto_refresh_running:
                return
            self.auto_refresh_running = True

        try:
            while True:
                async with self:
                    refresh_enabled = self.auto_refresh_enabled
                    reconnect_enabled = self.auto_reconnect_enabled
                    is_online = self.is_online
                    is_loading = self.is_loading
                    refresh_interval = self._refresh_interval_seconds()
                    reconnect_interval = self._reconnect_interval_seconds()

                    should_continue = refresh_enabled or reconnect_enabled
                if not should_continue:
                    break

                if is_loading:
                    await asyncio.sleep(1.0)
                    continue

                if is_online and refresh_enabled:
                    try:
                        status_payload, mp_model = await self._collect_status_snapshot()
                    except ValueError:
                        async with self:
                            self.m60_status = {
                                "error": "Port, timeout, and retries must be numeric.",
                            }
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Input validation failed"
                            self.is_online = False
                    except Exception as e:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {e}"}
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Unhandled exception"
                            self.is_online = False
                    else:
                        async with self:
                            self._apply_status_snapshot(status_payload, mp_model)
                    await asyncio.sleep(refresh_interval)
                    continue

                if (not is_online) and reconnect_enabled:
                    try:
                        status_payload, mp_model = await self._collect_status_snapshot()
                    except ValueError:
                        async with self:
                            self.m60_status = {
                                "error": "Port, timeout, and retries must be numeric.",
                            }
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Input validation failed"
                            self.is_online = False
                    except Exception as e:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {e}"}
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Unhandled exception"
                            self.is_online = False
                    else:
                        async with self:
                            self._apply_status_snapshot(status_payload, mp_model)
                    await asyncio.sleep(reconnect_interval)
                    continue

                await asyncio.sleep(1.0)
        finally:
            async with self:
                self.auto_refresh_running = False

    async def add_and_poll_m60(self):
        self.is_loading = True
        try:
            try:
                status_payload, mp_model = await self._collect_status_snapshot()
            except ValueError:
                self.m60_status = {
                    "error": "Port, timeout, and retries must be numeric.",
                }
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = self.m60_status["error"]
                self.status_text = "Input validation failed"
                self.is_online = False
                return
            self._apply_status_snapshot(status_payload, mp_model)
        except Exception as e:
            self.m60_status = {"error": f"Unhandled exception: {e}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False
            
    async def send_command(self, cmd_type: str, value: Any):
        """Send timing-related commands to the controller."""
        self.is_loading = True
        try:
            config = self._build_config()
            device = SiemensM60(config)
            if not await device.connect():
                self.m60_status = device.status.model_dump(mode="json")
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = "Controller connection failed before command"
                self.is_online = False
                return

            success = False
            if cmd_type == "select_pattern":
                success = await device.command(
                    "select_pattern",
                    {"pattern": value, "probe_only": self.safe_command_probe},
                )
                self.error = "" if success else "Failed to select pattern"
            elif cmd_type == "set_mode":
                success = await device.command(
                    "set_mode",
                    {"mode": value, "probe_only": self.safe_command_probe},
                )
            elif cmd_type == "manual_hold":
                success = await device.command(
                    "manual_hold",
                    {"hold": value, "probe_only": self.safe_command_probe},
                )
            elif cmd_type == "advance_phase":
                success = await device.command(
                    "advance_phase",
                    {"probe_only": self.safe_command_probe},
                )
            
            if success:
                self.m60_status = (await device.poll()).model_dump(mode="json")
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.status_text = str(self.m60_status.get("status_text", "Command applied"))
                self.is_online = bool(self.m60_status.get("is_online", False))
                self.last_updated = str(self.m60_status.get("timestamp", ""))
                self._apply_phase_payload(self.m60_status)
                self.active_snmp_version = "v2c" if getattr(device, "_mp_model", 1) == 1 else "v1"
            else:
                self.error = self.error or f"Command failed: {cmd_type}"
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_loading = False

    async def connect_and_start_polling(self):
        await self.connect_m60()

    async def select_pattern_1(self):
        await self.send_command("select_pattern", 1)

    async def select_pattern_2(self):
        await self.send_command("select_pattern", 2)

    async def set_mode_free(self):
        await self.send_command("set_mode", "free")

    async def set_mode_coordinated(self):
        await self.send_command("set_mode", "coordinated")

    async def manual_hold(self):
        await self.send_command("manual_hold", True)

    async def advance_phase(self):
        await self.send_command("advance_phase", True)
            
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
        rx.hstack(
            rx.heading("OpenSignal ITS", size="8", color="indigo"),
            rx.spacer(),
            rx.button(
                "Connect Siemens M60",
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
            padding="4",
        ),
        rx.hstack(
            rx.badge(rx.cond(TrafficState.is_online, "ONLINE", "OFFLINE"), color_scheme=rx.cond(TrafficState.is_online, "green", "red")),
            rx.text(f"SNMP: {TrafficState.active_snmp_version}"),
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
            rx.text(f"Updated: {TrafficState.last_updated}"),
            spacing="4",
            width="100%",
        ),
        rx.cond(
            TrafficState.error != "",
            rx.box(rx.text(TrafficState.error), border="1px solid #fca5a5", bg="#fef2f2", padding="3", border_radius="8px", width="100%"),
            rx.fragment(),
        ),
        rx.card(
            rx.heading("Controller Status", size="5"),
            rx.text(TrafficState.status_text),
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
                TrafficState.phase_detail_lines,
                TrafficState.status_text,
                TrafficState.select_pattern_1,
                TrafficState.select_pattern_2,
                TrafficState.set_mode_free,
                TrafficState.set_mode_coordinated,
                TrafficState.manual_hold,
                TrafficState.advance_phase,
            ),
            rx.code_block(TrafficState.m60_status_json, language="json"),
            width="100%",
        ),

        # Map placeholder (we'll make this real next)
        rx.card(
            rx.heading("Intersection Map", size="5"),
            rx.text("Folium / Leaflet map will go here"),
            height="400px",
            width="100%",
        ),

        # Video Grid placeholder
        rx.card(
            rx.heading("Video Detection Feeds", size="5"),
            rx.text("Iteris, GridSmart, Autoscope streams will appear here"),
            height="300px",
            width="100%",
        ),

        spacing="6",
        padding="6",
        width="100%",
        max_width="1200px",
        margin="0 auto",
    )

app = rx.App()
app.add_page(dashboard, route="/", title="OpenSignal ITS")
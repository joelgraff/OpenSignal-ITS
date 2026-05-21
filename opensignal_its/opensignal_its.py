import json
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
    phase_summary: str = "none active"
    detector_summary: str = "none active"
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

    async def connect_m60(self):
        await self.add_and_poll_m60()

    async def refresh_status(self):
        await self.add_and_poll_m60()

    async def add_and_poll_m60(self):
        self.is_loading = True
        try:
            try:
                config = self._build_config()
            except ValueError:
                self.m60_status = {
                    "error": "Port, timeout, and retries must be numeric.",
                }
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = self.m60_status["error"]
                self.status_text = "Input validation failed"
                self.is_online = False
                return

            device = SiemensM60(config)
            success = await device.connect()

            if success:
                self.m60_status = (await device.poll()).model_dump(mode="json")
            else:
                # Surface transport/auth details from the device status for debugging.
                self.m60_status = device.status.model_dump(mode="json")

            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.status_text = str(self.m60_status.get("status_text", "Unknown"))
            self.is_online = bool(self.m60_status.get("is_online", False))
            self.last_updated = str(self.m60_status.get("timestamp", ""))
            raw_data = self.m60_status.get("raw_data", {})
            self.current_pattern = str(raw_data.get("current_pattern", "Unknown"))
            self.unit_status = str(raw_data.get("unit_status", "unknown"))
            self.phase_summary = str(raw_data.get("phase_summary", "none active"))
            self.detector_summary = str(raw_data.get("detector_summary", "none active"))
            self.active_snmp_version = "v2c" if getattr(device, "_mp_model", 1) == 1 else "v1"
            errors = self.m60_status.get("errors", [])
            self.error = "; ".join(errors) if errors else ""
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
                raw_data = self.m60_status.get("raw_data", {})
                self.current_pattern = str(raw_data.get("current_pattern", "Unknown"))
                self.unit_status = str(raw_data.get("unit_status", "unknown"))
                self.phase_summary = str(raw_data.get("phase_summary", "none active"))
                self.detector_summary = str(raw_data.get("detector_summary", "none active"))
                self.active_snmp_version = "v2c" if getattr(device, "_mp_model", 1) == 1 else "v1"
            else:
                self.error = self.error or f"Command failed: {cmd_type}"
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_loading = False

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
        rx.button("Connect & Poll Siemens M60", on_click=TrafficState.add_and_poll_m60),
        timing_panel(
            TrafficState.current_pattern,
            TrafficState.unit_status,
            TrafficState.phase_summary,
            TrafficState.detector_summary,
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
                on_click=TrafficState.connect_m60,
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
                TrafficState.phase_summary,
                TrafficState.detector_summary,
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
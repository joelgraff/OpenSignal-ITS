import json
import reflex as rx
from .models.device import DeviceConfig
from .devices.siemens_m60 import SiemensM60

class TrafficState(rx.State):
    """Main app state."""
    m60_status: dict = {}
    m60_status_json: str = ""
    ip_address: str = "166.156.88.223"
    port_text: str = "161"
    community: str = "public"
    snmp_version: str = "auto"
    timeout_text: str = "3"
    retries_text: str = "1"

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

    async def add_and_poll_m60(self):
        try:
            try:
                port = int(self.port_text)
                timeout_seconds = float(self.timeout_text)
                retries = int(self.retries_text)
            except ValueError:
                self.m60_status = {
                    "error": "Port, timeout, and retries must be numeric.",
                }
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                return

            config = DeviceConfig(
                ip_address=self.ip_address.strip(),
                port=port,
                name="Siemens M60 Test",
                community=self.community.strip(),
                snmp_version=self.snmp_version.strip().lower(),
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
            device = SiemensM60(config)
            success = await device.connect()

            if success:
                self.m60_status = (await device.poll()).model_dump(mode="json")
            else:
                # Surface transport/auth details from the device status for debugging.
                self.m60_status = device.status.model_dump(mode="json")

            self.m60_status_json = json.dumps(self.m60_status, indent=2)
        except Exception as e:
            self.m60_status = {"error": f"Unhandled exception: {e}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)

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
        rx.button("Connect & Poll Siemens M60", on_click=TrafficState.add_and_poll_m60),
        rx.cond(
            TrafficState.m60_status_json != "",
            rx.code_block(TrafficState.m60_status_json, language="json"),
            rx.text("No status yet."),
        ),
        spacing="5",
        padding="2em",
    )

app = rx.App()
app.add_page(index)
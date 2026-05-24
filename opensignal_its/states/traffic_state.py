import reflex as rx

from .auth_state import AuthStateMixin
from .audit_state import AuditStateMixin
from .command_state import CommandStateMixin
from .configuration_state import ConfigurationStateMixin
from .event_state import EventStateMixin
from .fleet_state import FleetStateMixin
from .maintenance_state import MaintenanceStateMixin
from .monitor_state import MonitorStateMixin
from .polling_state import PollingStateMixin
from .safety_state import SafetyStateMixin
from .time_state import TimeStateMixin
from .workspace_state import WorkspaceStateMixin


class TrafficState(WorkspaceStateMixin, AuditStateMixin, FleetStateMixin, CommandStateMixin, TimeStateMixin, MonitorStateMixin, ConfigurationStateMixin, SafetyStateMixin, AuthStateMixin, MaintenanceStateMixin, PollingStateMixin, EventStateMixin, rx.State):
    """Main app state."""

    error: str = ""
    is_loading: bool = False


import reflex as rx

from .analytics import analytics_workspace_section
from .page_frame import workspace_page_frame


def analytics_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Analytics",
        subtitle="Review event timelines and triage alarms quickly.",
        body=analytics_workspace_section(),
    )

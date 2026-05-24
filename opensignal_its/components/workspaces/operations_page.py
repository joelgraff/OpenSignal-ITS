import reflex as rx

from .operations import operations_workspace_section
from .page_frame import workspace_page_frame


def operations_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="System Maintenance",
        subtitle="Review runtime health and run maintenance actions.",
        body=operations_workspace_section(),
    )

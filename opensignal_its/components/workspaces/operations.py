import reflex as rx

from ...states.traffic_state import TrafficState
from .section_card import workspace_section_card


def operations_workspace_section() -> rx.Component:
    return rx.cond(
        TrafficState.ui_workspace_mode == "operations",
        rx.vstack(
            rx.grid(
                workspace_section_card(
                    title="System Health",
                    subtitle="Review storage and alert-dispatch health with severity signals.",
                    actions=rx.button(
                        "Refresh Health",
                        on_click=TrafficState.refresh_runtime_health,
                        size="1",
                        variant="outline",
                    ),
                    body=rx.vstack(
                        rx.text(TrafficState.runtime_health_notice, size="2", color="gray"),
                        rx.text(TrafficState.runtime_storage_summary, size="1", color="gray"),
                        rx.text(TrafficState.runtime_alert_dispatch_summary, size="1", color="gray"),
                        rx.cond(
                            TrafficState.runtime_storage_warning_rows != [],
                            rx.box(
                                rx.hstack(
                                    rx.badge("Warnings", color_scheme="orange"),
                                    rx.text("Needs attention", size="1", color="gray"),
                                    width="100%",
                                    align="center",
                                    spacing="2",
                                ),
                                rx.foreach(
                                    TrafficState.runtime_storage_warning_rows,
                                    lambda row: rx.text(row, size="1", color="tomato"),
                                ),
                                border="1px solid #facc15",
                                bg="#fffbeb",
                                border_radius="8px",
                                padding="2",
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                        rx.cond(
                            TrafficState.runtime_storage_alert_rows != [],
                            rx.box(
                                rx.hstack(
                                    rx.badge("Critical", color_scheme="red"),
                                    rx.text("Persistent risk", size="1", color="gray"),
                                    width="100%",
                                    align="center",
                                    spacing="2",
                                ),
                                rx.foreach(
                                    TrafficState.runtime_storage_alert_rows,
                                    lambda row: rx.text(row, size="1", color="red"),
                                ),
                                border="1px solid #fca5a5",
                                bg="#fef2f2",
                                border_radius="8px",
                                padding="2",
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                workspace_section_card(
                    title="Maintenance Actions",
                    subtitle="Run retention cleanup and export audit data.",
                    body=rx.vstack(
                        rx.hstack(
                            rx.button(
                                "Run Retention Cleanup",
                                on_click=TrafficState.run_retention_cleanup,
                                size="1",
                                variant="outline",
                            ),
                            rx.button(
                                "Export Audit Report",
                                on_click=TrafficState.export_audit_report,
                                size="1",
                                variant="outline",
                            ),
                            spacing="2",
                            wrap="wrap",
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
                        spacing="2",
                        width="100%",
                    ),
                ),
                template_columns="repeat(auto-fit, minmax(320px, 1fr))",
                spacing="2",
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
        rx.fragment(),
    )

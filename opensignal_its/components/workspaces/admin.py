import reflex as rx

from ...states.traffic_state import TrafficState
from .page_frame import workspace_page_frame


def admin_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Sign-In & Roles",
        subtitle="Sign in to access signal sites, control actions, maintenance, and alarms/events.",
        body=rx.vstack(
            rx.card(
                rx.vstack(
                    rx.heading("Operator Sign-In", size="3"),
                    rx.input(
                        value=TrafficState.login_username_input,
                        on_change=TrafficState.update_login_username_input,
                        placeholder="Operator sign-in name",
                        width="100%",
                    ),
                    rx.input(
                        value=TrafficState.login_password_input,
                        on_change=TrafficState.update_login_password_input,
                        placeholder="Operator sign-in password",
                        type="password",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button(
                            "Sign In",
                            on_click=TrafficState.login_operator,
                            size="2",
                            color_scheme="green",
                        ),
                        rx.button(
                            "Sign Out",
                            on_click=TrafficState.logout_operator,
                            size="2",
                            variant="outline",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.text(TrafficState.auth_notice, size="2", color="gray"),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("Admin Recovery", size="3"),
                    rx.input(
                        value=TrafficState.admin_recovery_key_input,
                        on_change=TrafficState.update_admin_recovery_key_input,
                        placeholder="Admin recovery key phrase",
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
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
    )

import reflex as rx

from ...states import TrafficState
from .page_frame import workspace_page_frame


def admin_workspace_page() -> rx.Component:
    return workspace_page_frame(
        title="Access",
        subtitle="Sign in to access controllers, control actions, maintenance, and alarms/events.",
        body=rx.grid(
            rx.card(
                rx.vstack(
                    rx.heading("Operator Sign-In", size="2"),
                    rx.input(
                        value=TrafficState.login_username_input,
                        on_change=TrafficState.update_login_username_input,
                        placeholder="Operator sign-in name",
                        size="1",
                        max_width="20em",
                    ),
                    rx.input(
                        value=TrafficState.login_password_input,
                        on_change=TrafficState.update_login_password_input,
                        placeholder="Operator sign-in password",
                        type="password",
                        size="1",
                        max_width="20em",
                    ),
                    rx.hstack(
                        rx.button(
                            "Sign In",
                            on_click=TrafficState.login_operator,
                            size="1",
                            color_scheme="green",
                        ),
                        rx.button(
                            "Sign Out",
                            on_click=TrafficState.logout_operator,
                            size="1",
                            variant="outline",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(TrafficState.auth_notice, size="1", color="gray"),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
                size="1",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("Admin Recovery", size="2"),
                    rx.input(
                        value=TrafficState.admin_recovery_key_input,
                        on_change=TrafficState.update_admin_recovery_key_input,
                        placeholder="Admin recovery key phrase",
                        type="password",
                        size="1",
                        max_width="20em",
                    ),
                    rx.button(
                        "Reset Login Lockout",
                        on_click=TrafficState.reset_login_lockout,
                        size="1",
                        variant="outline",
                    ),
                    rx.cond(
                        TrafficState.admin_recovery_notice != "",
                        rx.text(TrafficState.admin_recovery_notice, size="1", color="gray"),
                        rx.fragment(),
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
                size="1",
            ),
            template_columns="repeat(auto-fit, minmax(320px, 1fr))",
            spacing="2",
            width="100%",
        ),
    )

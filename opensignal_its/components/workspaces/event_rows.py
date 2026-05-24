import reflex as rx

from ...states.traffic_state import TrafficState


def alarm_display_row(row: dict[str, str], selectable: bool = False) -> rx.Component:
    action = (
        rx.button(
            "Use Key",
            on_click=lambda: TrafficState.update_selected_alarm_key(row["alarm_key"]),
            size="1",
            variant="ghost",
        )
        if selectable
        else rx.fragment()
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.badge(row["severity_label"], color_scheme=row["severity_scheme"], size="1", variant="soft"),
                rx.badge(row["state_label"], color_scheme=row["state_scheme"], size="1", variant="soft"),
                rx.spacer(),
                action,
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.hstack(
                rx.text(row["summary"], size="2", font_weight="600"),
                rx.spacer(),
                rx.text(row["device_ip"], size="1", color="gray"),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.hstack(
                rx.text(row["detail"], size="1", color="gray"),
                rx.spacer(),
                rx.cond(
                    row["state_detail"] != "",
                    rx.text(row["state_detail"], size="1", color="gray"),
                    rx.fragment(),
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        padding="0.65em 0.8em",
        border="1px solid var(--gray-4)",
        border_radius="10px",
        width="100%",
    )


def timeline_display_row(row: dict[str, str]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.badge(row["kind_label"], color_scheme=row["kind_scheme"], size="1", variant="soft"),
                rx.badge(row["status_label"], color_scheme=row["status_scheme"], size="1", variant="soft"),
                rx.spacer(),
                rx.text(row["timestamp"], size="1", color="gray"),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.hstack(
                rx.text(row["summary"], size="2", font_weight="600"),
                rx.spacer(),
                rx.text(row["device_ip"], size="1", color="gray"),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.text(row["detail"], size="1", color="gray", width="100%"),
            spacing="1",
            align="start",
            width="100%",
        ),
        padding="0.65em 0.8em",
        border="1px solid var(--gray-4)",
        border_radius="10px",
        width="100%",
    )


def alarm_history_display_row(row: dict[str, str]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.badge(row["action_label"], color_scheme=row["action_scheme"], size="1", variant="soft"),
                rx.badge(row["severity_label"], color_scheme=row["severity_scheme"], size="1", variant="soft"),
                rx.spacer(),
                rx.text(row["timestamp"], size="1", color="gray"),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.hstack(
                rx.text(row["summary"], size="2", font_weight="600"),
                rx.spacer(),
                rx.text(row["device_ip"], size="1", color="gray"),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.text(row["detail"], size="1", color="gray", width="100%"),
            rx.cond(
                row["note"] != "",
                rx.text(f"Note: {row['note']}", size="1", color="gray", width="100%"),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        padding="0.65em 0.8em",
        border="1px solid var(--gray-4)",
        border_radius="10px",
        width="100%",
    )
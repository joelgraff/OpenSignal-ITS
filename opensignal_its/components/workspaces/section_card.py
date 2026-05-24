import reflex as rx


def workspace_section_card(
    title: str,
    body: rx.Component,
    subtitle: str = "",
    actions: rx.Component | None = None,
) -> rx.Component:
    heading_row = rx.cond(
        actions is not None,
        rx.hstack(
            rx.heading(title, size="2"),
            rx.spacer(),
            actions,
            width="100%",
            align="center",
        ),
        rx.heading(title, size="2"),
    )

    return rx.card(
        rx.vstack(
            heading_row,
            rx.cond(
                subtitle != "",
                rx.text(subtitle, size="1", color="gray"),
                rx.fragment(),
            ),
            body,
            spacing="2",
            width="100%",
        ),
        width="100%",
    )

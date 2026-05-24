import reflex as rx


def workspace_page_frame(
    title: str,
    subtitle: str,
    body: rx.Component,
) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(title, size="3"),
                rx.text(subtitle, size="1", color="gray"),
                spacing="3",
                align="baseline",
                wrap="wrap",
                width="100%",
            ),
            body,
            spacing="2",
            width="100%",
        ),
        width="100%",
    )

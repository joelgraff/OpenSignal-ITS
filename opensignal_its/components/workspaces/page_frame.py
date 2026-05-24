import reflex as rx


def workspace_page_frame(
    title: str,
    subtitle: str,
    body: rx.Component,
) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.vstack(
                rx.heading(title, size="4"),
                rx.text(subtitle, size="2", color="gray"),
                spacing="1",
                width="100%",
            ),
            body,
            spacing="3",
            width="100%",
        ),
        width="100%",
    )

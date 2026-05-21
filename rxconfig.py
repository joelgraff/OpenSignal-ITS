import reflex as rx

config = rx.Config(
    app_name="opensignal_its",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ],
    # Nice defaults for a control-room style app
    theme=rx.theme(
        accent_color="indigo",
        radius="medium",
        scaling="100%",
    ),
    db_url="sqlite:///traffic.db",
)
# OpenSignal ITS

OpenSignal ITS is a Reflex-based traffic controller dashboard and tooling app.

## Ubuntu development setup

Use the bootstrap script on a clean Ubuntu machine:

```bash
chmod +x scripts/setup_ubuntu.sh
./scripts/setup_ubuntu.sh
```

Then run:

```bash
source .venv/bin/activate
.venv/bin/reflex run
```

Open `http://localhost:3000`.

For full instructions and troubleshooting, see:

- [docs/ubuntu-development-setup.md](docs/ubuntu-development-setup.md)
- [docs/operations-runbook.md](docs/operations-runbook.md)
- [docs/sprint1-device-registry-plan.md](docs/sprint1-device-registry-plan.md)
- [docs/ui-architecture-blueprint.md](docs/ui-architecture-blueprint.md)

Operational read-only API endpoints are also available:

- `/api/ops/health`
- `/api/ops/alarms`
- `/api/ops/alarm-history`

Set `OPENSIGNAL_OPS_API_ENABLED=false` to disable these routes.
By default, token configuration is required; provide `Authorization: Bearer <token>` with requests.
For local-only development, unauthenticated access can be explicitly enabled with `OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED=true`.

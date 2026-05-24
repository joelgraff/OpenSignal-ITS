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

UI sign-in is required by default, including local development. If you explicitly need a local admin bypass session for debugging, start Reflex with `OPENSIGNAL_DISABLE_LOGIN=true`.

To run the local regression baseline:

```bash
.venv/bin/python -m unittest discover -s opensignal_its/tests -p 'test_*.py'
```

This suite now includes a dry Reflex compile smoke check so UI compile regressions are caught before a manual `reflex run`.

For a full startup smoke that boots Reflex, probes the frontend and backend, and retries the next sequential frontend port on bind conflicts:

```bash
.venv/bin/python scripts/reflex_boot_smoke.py --frontend-port 3002 --backend-port 8001
```

For a browser-level auth and workspace-navigation smoke, install the Playwright test dependency once and then run:

```bash
npm install
npx playwright install chromium
.venv/bin/python scripts/reflex_playwright_smoke.py
```

That smoke launches Reflex with deterministic local test credentials, verifies the unauthenticated gate, signs in, checks key workspaces, and signs out.

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

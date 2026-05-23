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

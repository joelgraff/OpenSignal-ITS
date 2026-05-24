# Ubuntu Development Setup

This guide provisions OpenSignal ITS on a clean Ubuntu machine.

## Supported target

- Ubuntu 24.04 LTS (recommended)
- Python 3.12+

## Fast path (recommended)

From the repository root:

```bash
chmod +x scripts/setup_ubuntu.sh
./scripts/setup_ubuntu.sh
```

Then start the app:

```bash
source .venv/bin/activate
.venv/bin/reflex run
```

Open the app at `http://localhost:3000`.

UI sign-in is required by default. For a local-only admin bypass session during debugging, launch Reflex with `OPENSIGNAL_DISABLE_LOGIN=true`.

## Manual path

If you prefer not to use the script, run these steps manually.

1. Install system packages:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  curl \
  ffmpeg \
  git \
  libffi-dev \
  libgl1 \
  libglib2.0-0 \
  libssl-dev \
  pkg-config \
  python3 \
  python3-dev \
  python3-venv
```

2. Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

3. Create/sync environment:

```bash
uv venv .venv --python 3.12 --clear
UV_PROJECT_ENVIRONMENT=.venv uv sync
source .venv/bin/activate
```

4. Run the app:

```bash
.venv/bin/reflex run
```

5. Optional full boot smoke:

```bash
.venv/bin/python scripts/reflex_boot_smoke.py --frontend-port 3002 --backend-port 8001
```

## Verify your environment

```bash
uv --version
.venv/bin/python --version
.venv/bin/python -c "import importlib.metadata; import pysnmp, reflex; print(importlib.metadata.version('reflex'))"
test -x .venv/bin/reflex && echo "reflex cli found"
```

## Troubleshooting

### Command `uv` not found

Add uv to your shell path:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### App fails after project folder rename

If the project root directory was renamed, recreate the virtual environment:

```bash
rm -rf .venv
uv venv .venv --python 3.12 --clear
UV_PROJECT_ENVIRONMENT=.venv uv sync
```

### Port already in use

Stop stale Reflex processes:

```bash
pkill -f "reflex run" || true
```

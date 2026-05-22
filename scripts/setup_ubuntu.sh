#!/usr/bin/env bash
set -euo pipefail

# Bootstrap OpenSignal ITS on Ubuntu 24.04+.
# Usage:
#   ./scripts/setup_ubuntu.sh
#   ./scripts/setup_ubuntu.sh --skip-apt

SKIP_APT=0

for arg in "$@"; do
  case "$arg" in
    --skip-apt)
      SKIP_APT=1
      ;;
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/setup_ubuntu.sh [--skip-apt]

Options:
  --skip-apt   Skip apt install/update steps.
  -h, --help   Show this help message.
HELP
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$SKIP_APT" -eq 0 ]]; then
  if [[ "${EUID}" -ne 0 ]]; then
    SUDO="sudo"
  else
    SUDO=""
  fi

  echo "[setup] Installing Ubuntu packages..."
  ${SUDO} apt-get update
  ${SUDO} apt-get install -y \
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
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[setup] Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[setup] ERROR: uv is not in PATH. Add ~/.local/bin to PATH and retry." >&2
  exit 1
fi

echo "[setup] Syncing Python environment with uv..."
uv sync

echo "[setup] Verifying Reflex import..."
uv run python -c "import reflex; print(reflex.__version__)"

echo ""
echo "Setup complete."
echo "Next steps:"
echo "  1) source .venv/bin/activate"
echo "  2) uv run reflex run"

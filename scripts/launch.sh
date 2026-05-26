#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
pwd
if [[ ! -f .env.local ]]; then
  echo "Missing .env.local" >&2
  exit 1
fi

set -a
source .env.local
set +a

exec .venv/bin/reflex run --env dev
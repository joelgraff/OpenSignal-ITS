#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

args=(
  --name development
  --inbox /memories/repo/next-agent-ticket.md
  --outbox /memories/repo/agent-handoff-log.md
  --poll-seconds "${BROKER_POLL_SECONDS:-30}"
  --state-file "${BROKER_STATE_FILE:-$REPO_ROOT/.cache/agent-brokers/development.json}"
)

if [[ -n "${BROKER_COMMAND_TEMPLATE:-}" ]]; then
  args+=(--command-template "$BROKER_COMMAND_TEMPLATE")
fi

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/agent_handoff_broker.py" "${args[@]}"
#!/usr/bin/env bash
set -euo pipefail

umask 077

evidence_root="${SOLAR_EVIDENCE_ROOT:-/evidence}"
mkdir -p \
  "$evidence_root/sprints" \
  "$evidence_root/intents" \
  "$evidence_root/workspace" \
  "$evidence_root/knowledge" \
  "$evidence_root/runtime/claude-state" \
  "$HOME/.claude"

# Authentication is supplied only at runtime through a read-only mount.  Copy
# the minimum CLI-owned files into the container-private writable home because
# Claude may rotate session metadata during a real call.
for name in .credentials.json .claude.json settings.json settings.local.json; do
  if [[ -f "/run/claude-auth/$name" ]]; then
    cp "/run/claude-auth/$name" "$HOME/.claude/$name"
    chmod 600 "$HOME/.claude/$name"
  fi
done

export HARNESS_SPRINTS_DIR="${HARNESS_SPRINTS_DIR:-$evidence_root/sprints}"
export SOLAR_HARNESS_SPRINTS_DIR="${SOLAR_HARNESS_SPRINTS_DIR:-$HARNESS_SPRINTS_DIR}"
export SOLAR_INTENT_GATEWAY_DIR="${SOLAR_INTENT_GATEWAY_DIR:-$evidence_root/intents}"
export SOLAR_INTAKE_WORKSPACE_ROOT="${SOLAR_INTAKE_WORKSPACE_ROOT:-$evidence_root/workspace}"
export SOLAR_KNOWLEDGE_RAW_DIR="${SOLAR_KNOWLEDGE_RAW_DIR:-$evidence_root/knowledge}"
export SOLAR_CODEX_OPERATOR_STATE_ROOT="${SOLAR_CODEX_OPERATOR_STATE_ROOT:-$evidence_root/runtime/claude-state}"
export SOLAR_GATE_LEDGER="${SOLAR_GATE_LEDGER:-1}"
export SOLAR_OPERATORD_AUTO_KICK="${SOLAR_OPERATORD_AUTO_KICK:-1}"
export SOLAR_MULTI_TASK_OPERATORS="${SOLAR_MULTI_TASK_OPERATORS:-$HARNESS_DIR/config/physical-operators.json}"
if [[ -z "${SOLAR_AUTH_TOKEN:-}" ]]; then
  SOLAR_AUTH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export SOLAR_AUTH_TOKEN

case "${1:-status-server}" in
  status-server)
    exec python3 "$HARNESS_DIR/lib/symphony/status-server.py"
    ;;
  driver)
    shift
    exec python3 "$HARNESS_DIR/tools/fixed_research_uat.py" "$@"
    ;;
  *)
    exec "$@"
    ;;
esac

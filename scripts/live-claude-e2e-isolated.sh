#!/usr/bin/env bash
# live-claude-e2e-isolated.sh - guarded real Claude/Anthropic product-path E2E.
#
# This is intentionally not a CI smoke test. It creates a fresh sandbox HOME,
# exports the committed harness with git-archive, starts a unique Claude cockpit
# and status server, submits through /intake, then waits for terminal sprint
# state and route proof. Live execution requires SOLAR_LIVE_E2E_ALLOW=1.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/live-claude-e2e-isolated.sh --prepare-only
  SOLAR_LIVE_E2E_ALLOW=1 scripts/live-claude-e2e-isolated.sh [options]

Options:
  --task TEXT             Task to submit through /intake.
  --workflow-id ID        Route intake through the named workflow contract.
                          Default: code.cli_smoke_anthropic.
  --workflow-input KEY=VALUE
                          Workflow input passed through /intake.
  --timeout-seconds N     Overall live wait timeout. Default: 1800.
  --poll-seconds N        Poll cadence. Default: 30.
  --sandbox DIR           Use an existing/new sandbox directory instead of mktemp.
  --cleanup               Remove the sandbox at exit. Default keeps evidence.
  --prepare-only          Create the isolated harness/evidence scaffold and run
                          deterministic preflight, then exit.
  --help                  Show this help.

Default task:
  Write a Python command-line tool uniqwords.py that reads a UTF-8 text file
  and prints the number of unique case-insensitive words, with tests.
USAGE
}

default_task="Write a Python command-line tool uniqwords.py that reads a UTF-8 text file and prints the number of unique case-insensitive words. Include a small pytest test file and a short README note explaining usage."
task="$default_task"
task_explicit=0
workflow_id="${SOLAR_LIVE_E2E_WORKFLOW_ID:-code.cli_smoke_anthropic}"
workflow_inputs=()
timeout_seconds="${SOLAR_LIVE_E2E_TIMEOUT_SECONDS:-1800}"
poll_seconds="${SOLAR_LIVE_E2E_POLL_SECONDS:-30}"
prepare_only=0
cleanup_sandbox=0
sandbox="${SOLAR_LIVE_E2E_SANDBOX:-}"
caller_home="${HOME:-}"
claude_credentials_source="${SOLAR_LIVE_E2E_CLAUDE_CREDENTIALS:-${caller_home}/.claude/.credentials.json}"
claude_auth_source="none"
planner_operator="mini-claude-opus-planner-print"
builder_operator="mini-claude-sonnet-builder-2"
evaluator_operator="mini-claude-sonnet-evaluator-print"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      [[ -n "${2:-}" ]] || { echo "--task requires text" >&2; exit 2; }
      task="$2"; task_explicit=1; shift 2 ;;
    --workflow-id)
      [[ -n "${2:-}" ]] || { echo "--workflow-id requires an id" >&2; exit 2; }
      workflow_id="$2"; shift 2 ;;
    --workflow-input)
      [[ "${2:-}" == *"="* ]] || { echo "--workflow-input requires KEY=VALUE" >&2; exit 2; }
      workflow_inputs+=("$2"); shift 2 ;;
    --timeout-seconds)
      [[ "${2:-}" =~ ^[0-9]+$ ]] || { echo "--timeout-seconds requires an integer" >&2; exit 2; }
      timeout_seconds="$2"; shift 2 ;;
    --poll-seconds)
      [[ "${2:-}" =~ ^[0-9]+$ ]] || { echo "--poll-seconds requires an integer" >&2; exit 2; }
      poll_seconds="$2"; shift 2 ;;
    --sandbox)
      [[ -n "${2:-}" ]] || { echo "--sandbox requires a path" >&2; exit 2; }
      sandbox="$2"; shift 2 ;;
    --cleanup)
      cleanup_sandbox=1; shift ;;
    --prepare-only)
      prepare_only=1; shift ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

if [[ "$poll_seconds" -lt 5 ]]; then
  echo "--poll-seconds must be >= 5 for live E2E stability" >&2
  exit 2
fi
if [[ "$timeout_seconds" -lt "$poll_seconds" ]]; then
  echo "--timeout-seconds must be >= --poll-seconds" >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
source_harness="$repo_dir/harness"
[[ -f "$repo_dir/install.sh" && -d "$source_harness" ]] || {
  echo "cannot locate repo/harness from $repo_dir" >&2
  exit 2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 127
  }
}

require_cmd git
require_cmd tar
require_cmd python3

if [[ -z "$sandbox" ]]; then
  sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-live-claude-e2e.XXXXXX")"
else
  mkdir -p "$sandbox"
  sandbox="$(cd "$sandbox" && pwd)"
fi

home_dir="$sandbox/home"
iso_harness="$home_dir/.solar/harness"
workspace="$sandbox/workspace"
evidence_dir="$sandbox/evidence"
logs_dir="$evidence_dir/logs"
bin_dir="$home_dir/.solar/bin"
archive_dir="$sandbox/archive"
env_file="$evidence_dir/e2e.env"
manifest="$evidence_dir/manifest.json"
commit_sha="$(git -C "$repo_dir" rev-parse HEAD)"
branch_name="$(git -C "$repo_dir" rev-parse --abbrev-ref HEAD)"
run_id="claude-e2e-$(date -u +%Y%m%dT%H%M%SZ)-$$"
tmux_session="solar-${run_id}"
tmux_lab_session="${tmux_session}-lab"
tmux_bg_session="${tmux_session}-bg"
status_pid=""
interrupted=0

classify_claude_auth_source() {
  if [[ -s "$claude_credentials_source" ]]; then
    claude_auth_source="HOME/.claude/.credentials.json"
    return 0
  fi
  claude_auth_source="missing"
  return 1
}

provision_sandbox_claude_auth() {
  local target_dir="$home_dir/.claude"
  local target_auth="$target_dir/.credentials.json"
  if [[ ! -s "$claude_credentials_source" ]]; then
    return 0
  fi
  mkdir -p "$target_dir"
  ln -sfn "$claude_credentials_source" "$target_auth"
}

write_invalid_marker() {
  local reason="$1"
  mkdir -p "$evidence_dir"
  python3 - "$evidence_dir/INVALID_EVIDENCE.json" "$reason" "$run_id" <<'PY'
import json, sys, time
path, reason, run_id = sys.argv[1:4]
payload = {
    "valid": False,
    "reason": reason,
    "run_id": run_id,
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "note": "Manual interruption or forced termination invalidates product-proof claims for this run.",
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
}

model_registry_preflight() {
  local failure_path="$evidence_dir/MODEL_REGISTRY_PREFLIGHT_FAILED.json"
  PYTHONPATH="$iso_harness/lib" python3 - "$iso_harness" "$failure_path" <<'PY'
import json
import sys
import time
from pathlib import Path

import model_registry

harness = Path(sys.argv[1])
failure_path = Path(sys.argv[2])
registry_path = harness / "config" / "model-registry.json"
config_path = harness / "config" / "solar-user-config.json"
roles = ["pm", "planner", "builder", "evaluator"]

errors = []
resolved = {}
try:
    registry = model_registry.load_registry(registry_path)
except Exception as exc:
    registry = {}
    errors.append({
        "kind": "registry_load_failed",
        "path": str(registry_path),
        "error": f"{type(exc).__name__}: {exc}",
    })

try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
except Exception as exc:
    config = {}
    errors.append({
        "kind": "runtime_config_load_failed",
        "path": str(config_path),
        "error": f"{type(exc).__name__}: {exc}",
    })

models = config.get("models") if isinstance(config.get("models"), dict) else {}
for role in roles:
    alias = str(models.get(role) or "").strip()
    if not alias:
        errors.append({"kind": "missing_role_model", "role": role})
        continue
    try:
        spec = model_registry.spec(registry, alias)
        if not spec.get("main_allowed"):
            raise SystemExit(f"model not allowed on main panes: {alias}")
        provider = str(spec.get("provider") or "").strip().lower()
        if provider != "anthropic":
            raise SystemExit(f"model provider {provider!r} is not anthropic: {alias}")
        resolved[role] = {
            "alias": alias,
            "canonical": spec.get("id"),
            "provider": spec.get("provider"),
            "model_key": spec.get("model_key"),
        }
    except SystemExit as exc:
        errors.append({
            "kind": "unsupported_role_model",
            "role": role,
            "alias": alias,
            "error": str(exc),
        })

if errors:
    payload = {
        "ok": False,
        "reason": "model_registry_preflight_failed",
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registry": str(registry_path),
        "runtime_config": str(config_path),
        "selected_runtime": config.get("runtime"),
        "errors": errors,
        "resolved": resolved,
    }
    failure_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)
PY
}

operator_registry_preflight() {
  local failure_path="$evidence_dir/OPERATOR_REGISTRY_PREFLIGHT_FAILED.json"
  PYTHONPATH="$iso_harness/lib" python3 - "$iso_harness" "$failure_path" "$planner_operator" "$builder_operator" "$evaluator_operator" <<'PY'
import json
import sys
import time
from pathlib import Path

harness = Path(sys.argv[1])
failure_path = Path(sys.argv[2])
required = {
    "planner": sys.argv[3],
    "builder": sys.argv[4],
    "evaluator": sys.argv[5],
}
registry_path = harness / "config" / "physical-operators.json"
errors = []
resolved = {}
try:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    operators = payload.get("operators") if isinstance(payload.get("operators"), dict) else {}
except Exception as exc:
    operators = {}
    errors.append({
        "kind": "registry_load_failed",
        "path": str(registry_path),
        "error": f"{type(exc).__name__}: {exc}",
    })

for role, operator_id in required.items():
    spec = operators.get(operator_id)
    if not isinstance(spec, dict):
        errors.append({"kind": "missing_required_operator", "role": role, "operator_id": operator_id})
        continue
    provider = str(spec.get("provider") or spec.get("vendor") or "").strip().lower()
    actual_role = str(spec.get("role") or spec.get("profile") or "").strip().lower()
    backend = str(spec.get("backend") or "").strip().lower()
    resolved[role] = {
        "operator_id": operator_id,
        "provider": provider,
        "role": actual_role,
        "backend": backend,
        "model": spec.get("model"),
        "model_config": spec.get("model_config"),
    }
    if provider != "anthropic":
        errors.append({
            "kind": "required_operator_provider_mismatch",
            "role": role,
            "operator_id": operator_id,
            "provider": provider,
        })
    if actual_role != role:
        errors.append({
            "kind": "required_operator_role_mismatch",
            "role": role,
            "operator_id": operator_id,
            "actual_role": actual_role,
        })
    if backend != "claude-cli":
        errors.append({
            "kind": "required_operator_backend_mismatch",
            "role": role,
            "operator_id": operator_id,
            "backend": backend,
        })

if errors:
    payload = {
        "ok": False,
        "reason": "operator_registry_preflight_failed",
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registry": str(registry_path),
        "errors": errors,
        "resolved": resolved,
    }
    failure_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)
PY
}

claude_credentials_preflight() {
  local failure_path="$evidence_dir/CLAUDE_AUTH_PREFLIGHT_FAILED.json"
  local target_auth="$home_dir/.claude/.credentials.json"
  if [[ -s "$target_auth" ]]; then
    return 0
  fi
  python3 - "$failure_path" "$claude_credentials_source" "$target_auth" <<'PY'
import json, sys, time
path, source, target = sys.argv[1:4]
payload = {
    "ok": False,
    "reason": "claude_credentials_missing",
    "source": source,
    "target": target,
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "required": "Provide a non-empty host $HOME/.claude/.credentials.json; the sandbox exposes it as a symlink and never reads token contents.",
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
  return 1
}

anthropic_contract_preflight() {
  local contract_path="$iso_harness/config/workflows/${workflow_id}.workflow.json"
  local failure_path="$evidence_dir/ANTHROPIC_CONTRACT_PREFLIGHT_FAILED.json"
  if [[ ! -f "$contract_path" ]]; then
    python3 - "$failure_path" "$contract_path" "$workflow_id" <<'PY'
import json, sys, time
path, contract_path, workflow_id = sys.argv[1:4]
payload = {
    "ok": False,
    "reason": "workflow_contract_missing",
    "workflow_id": workflow_id,
    "contract": contract_path,
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
    return 1
  fi
  set +e
  (
    # shellcheck disable=SC1090
    source "$env_file"
    python3 "$iso_harness/lib/run_preflight.py" \
      --sid live-claude-preflight \
      --providers anthropic \
      --contract "$contract_path" \
      --expect-harness-dir "$iso_harness"
  ) > "$logs_dir/anthropic-contract-preflight.out.log" 2> "$logs_dir/anthropic-contract-preflight.err.log"
  local rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    return 0
  fi
  python3 - "$failure_path" "$contract_path" "$rc" "$iso_harness/sprints/live-claude-preflight.preflight.json" <<'PY'
import json, sys, time
path, contract_path, rc, report_path = sys.argv[1:5]
payload = {
    "ok": False,
    "reason": "anthropic_contract_preflight_failed",
    "contract": contract_path,
    "exit_code": int(rc),
    "report_path": report_path,
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
  return "$rc"
}

cleanup() {
  local exit_code=$?
  if [[ "$interrupted" == "1" ]]; then
    write_invalid_marker "manual_interrupt_or_termination"
  fi
  if [[ -n "$status_pid" ]]; then
    kill "$status_pid" >/dev/null 2>&1 || true
    wait "$status_pid" >/dev/null 2>&1 || true
  fi
  # G3 zombie-factory fix: mark the sandbox run terminal and reap its
  # registered daemons (watchdog-first) BEFORE killing sessions — killing
  # only the tmux sessions left marker-less coordinator/watchdog daemons
  # respawning harness startup indefinitely.
  if [[ -n "$sandbox" && -f "$sandbox/home/.solar/harness/lib/run_process_registry.py" ]]; then
    python3 "$sandbox/home/.solar/harness/lib/run_process_registry.py" \
      teardown --run-id harness --grace 5 >/dev/null 2>&1 || true
  fi
  if command -v tmux >/dev/null 2>&1; then
    tmux kill-session -t "$tmux_session" >/dev/null 2>&1 || true
    tmux kill-session -t "$tmux_lab_session" >/dev/null 2>&1 || true
    tmux kill-session -t "$tmux_bg_session" >/dev/null 2>&1 || true
  fi
  if [[ "$cleanup_sandbox" == "1" && "$sandbox" == /tmp/solar-live-claude-e2e.* ]]; then
    rm -rf "$sandbox"
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'interrupted=1; exit 130' INT
trap 'interrupted=1; exit 143' TERM

prepare_isolated_harness() {
  mkdir -p "$home_dir/.solar" "$workspace" "$evidence_dir" "$logs_dir" "$bin_dir" "$archive_dir"
  if [[ -e "$iso_harness" ]]; then
    echo "isolated harness already exists: $iso_harness" >&2
    echo "choose a fresh --sandbox or remove it explicitly" >&2
    exit 2
  fi

  git -C "$repo_dir" archive --format=tar HEAD harness | tar -xf - -C "$archive_dir"
  mv "$archive_dir/harness" "$iso_harness"
  mkdir -p "$iso_harness/run" "$iso_harness/sprints" "$iso_harness/events" "$iso_harness/sessions" "$iso_harness/logs" "$iso_harness/state" "$iso_harness/config"

  cat > "$iso_harness/config/solar-user-config.json" <<'JSON'
{
  "runtime": "claude",
  "models": {
    "pm": "anthropic-opus",
    "planner": "anthropic-opus",
    "builder": "anthropic-sonnet",
    "evaluator": "anthropic-sonnet"
  },
  "route_policy": {
    "fail_closed": true,
    "allow_role_spillover": false,
    "allow_mixed_provider": false
  }
}
JSON

  provision_sandbox_claude_auth

  cat > "$bin_dir/solar" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "harness" ]]; then
  shift
  exec "${HARNESS_DIR:?HARNESS_DIR required}/solar-harness.sh" "$@"
fi
echo "isolated live E2E solar shim only supports: solar harness ..." >&2
exit 64
SH
  cat > "$bin_dir/solar-harness" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
exec "${HARNESS_DIR:?HARNESS_DIR required}/solar-harness.sh" "$@"
SH
  chmod +x "$bin_dir/solar" "$bin_dir/solar-harness"

  cat > "$env_file" <<ENV
export HOME=$(printf '%q' "$home_dir")
export HARNESS_DIR=$(printf '%q' "$iso_harness")
export SOLAR_HARNESS_DIR=$(printf '%q' "$iso_harness")
export SPRINTS_DIR=$(printf '%q' "$iso_harness/sprints")
export PYTHONPATH=$(printf '%q' "$iso_harness/lib")
export SOLAR_PANE_RUNTIME=claude
export SOLAR_PM_DEFAULT_PROVIDERS=anthropic
export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=anthropic
# P2 product flags (smoke 20260707T180639Z: zero route records because this
# generated env is authoritative for every sandbox process and the flags were
# left to shell inheritance). Explicit, never inherited.
# G4 default-on: the governed-spine flags (plan validator, gate ledger)
# resolve ON at the parser level — deliberately NOT set here so e2e runs
# prove the runtime default a fresh machine gets (probe: env-status).
# Their names must never appear in this generated file: the rung gate is
# a bare substring grep expecting zero matches.
export SOLAR_PRODUCT_MODE=1
export SOLAR_WORKFLOW_ROUTER=1
export SOLAR_INTAKE_WORKSPACE_ROOT=$(printf '%q' "$workspace")
export SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH=1
export SOLAR_GRAPH_BUILDER_OPERATOR_POOL=1
export SOLAR_GRAPH_EVAL_OPERATOR_POOL=1
export SOLAR_COORD_MULTITASK_SELFCOMPLETE=1
export SOLAR_HARNESS_SESSION=$(printf '%q' "$tmux_session")
export SOLAR_HARNESS_LAB_SESSION=$(printf '%q' "$tmux_lab_session")
export SOLAR_HARNESS_BG_SESSION=$(printf '%q' "$tmux_bg_session")
export SOLAR_LIVE_E2E_RUN_ID=$(printf '%q' "$run_id")
export PATH=$(printf '%q' "$bin_dir"):\$PATH
ENV

  python3 - "$manifest" "$branch_name" "$commit_sha" "$repo_dir" "$source_harness" "$sandbox" "$home_dir" "$iso_harness" "$workspace" "$evidence_dir" "$run_id" "$task" "$task_explicit" "$workflow_id" "$claude_credentials_source" "$claude_auth_source" "$planner_operator" "$builder_operator" "$evaluator_operator" <<'PY'
import json, sys, time
(
    path,
    branch,
    commit,
    repo_dir,
    source_harness,
    sandbox,
    home_dir,
    iso_harness,
    workspace,
    evidence_dir,
    run_id,
    task,
    task_explicit,
    workflow_id,
    claude_credentials_source,
    claude_auth_source,
    planner_operator,
    builder_operator,
    evaluator_operator,
) = sys.argv[1:20]
payload = {
    "run_id": run_id,
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "branch": branch,
    "commit": commit,
    "repo_dir": repo_dir,
    "source_harness": source_harness,
    "sandbox": sandbox,
    "home_dir": home_dir,
    "harness_dir": iso_harness,
    "workspace": workspace,
    "evidence_dir": evidence_dir,
    "selected_runtime": "claude",
    "allowed_providers": ["anthropic"],
    "workflow_id": workflow_id,
    "claude_credentials_source": claude_credentials_source,
    "claude_auth_source": claude_auth_source,
    "required_operators": {
        "planner": planner_operator,
        "builder": builder_operator,
        "evaluator": evaluator_operator,
    },
    "task": task if task_explicit == "1" else "",
    "task_provided": task_explicit == "1",
    "task_note": "" if task_explicit == "1" else "no --task given; prompt (if any) is submitted separately via /intake",
    "live_execution_requires": "SOLAR_LIVE_E2E_ALLOW=1",
    "validity_rules": [
        "uses sandbox HOME and HARNESS_DIR only",
        "submits through status-server /intake with sandbox-local solar shim first in PATH",
        "manual interruption writes INVALID_EVIDENCE.json",
        "success requires terminal sprint state plus route-proof ok with Anthropic-only providers"
    ],
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
PY
}

wait_for_status_server() {
  local port_file="$iso_harness/run/status-server.port"
  local waited=0
  while [[ "$waited" -lt 60 ]]; do
    if [[ -s "$port_file" ]]; then
      local port
      port="$(cat "$port_file" 2>/dev/null || true)"
      if [[ -n "$port" ]] && curl -fsS --connect-timeout 1 --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
        printf '%s\n' "$port"
        return 0
      fi
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

submit_intake() {
  local base_url="$1"
  local request_id="live-e2e-${run_id}"
  python3 - "$base_url/intake" "$task" "$request_id" "$evidence_dir/intake-response.json" "$workflow_id" ${workflow_inputs[@]+"${workflow_inputs[@]}"} <<'PY'
import json, sys, urllib.request
url, task, request_id, out_path, workflow_id = sys.argv[1:6]
payload_body = {"task": task, "request_id": request_id}
if workflow_id.strip():
    payload_body["workflow_id"] = workflow_id.strip()
    inputs = {}
    for item in sys.argv[6:]:
        key, _, value = item.partition("=")
        if key.strip():
            inputs[key.strip()] = value
    if inputs:
        payload_body["workflow_inputs"] = inputs
body = json.dumps(payload_body).encode("utf-8")
req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=240) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
except Exception as exc:
    payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
open(out_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
sid = str(payload.get("sprint_id") or "")
if not payload.get("ok") or not sid:
    raise SystemExit(f"intake failed: {payload}")
print(sid)
PY
}

write_route_proof() {
  local sid="$1"
  PYTHONPATH="$iso_harness/lib" python3 - "$iso_harness" "$sid" <<'PY'
import json, sys
from pathlib import Path
import route_proof
harness, sid = Path(sys.argv[1]), sys.argv[2]
proof = route_proof.write_route_proof(harness, sid, selected_runtime="claude")
print(json.dumps({"ok": proof.get("ok"), "path": proof.get("path"), "stage_count": proof.get("stage_count"), "violations": proof.get("violations", [])}, ensure_ascii=False))
PY
}

capture_http_snapshot() {
  local base_url="$1"
  local sid="$2"
  curl -fsS "$base_url/runtime-info" > "$evidence_dir/runtime-info.json" 2>"$logs_dir/runtime-info.err" || true
  curl -fsS "$base_url/settings" > "$evidence_dir/settings.json" 2>"$logs_dir/settings.err" || true
  curl -fsS "$base_url/status?sprint_id=$sid" > "$evidence_dir/status-projection.json" 2>"$logs_dir/status-projection.err" || true
  curl -fsS "$base_url/events?limit=200&sprint_id=$sid" > "$evidence_dir/events-projection.json" 2>"$logs_dir/events-projection.err" || true
}

poll_until_terminal() {
  local sid="$1"
  local base_url="$2"
  local status_file="$iso_harness/sprints/${sid}.status.json"
  local deadline=$(( $(date +%s) + timeout_seconds ))
  local poll_index=0
  while [[ "$(date +%s)" -le "$deadline" ]]; do
    poll_index=$((poll_index + 1))
    capture_http_snapshot "$base_url" "$sid"
    python3 - "$status_file" "$evidence_dir/poll-${poll_index}.json" <<'PY'
import json, sys, time
status_path, out_path = sys.argv[1:3]
try:
    data = json.load(open(status_path, encoding="utf-8"))
except Exception as exc:
    data = {"status": "missing", "error": f"{type(exc).__name__}: {exc}"}
snapshot = {
    "polled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "status": data.get("status") or data.get("phase") or "unknown",
    "phase": data.get("phase"),
    "sprint_id": data.get("sprint_id"),
}
open(out_path, "w", encoding="utf-8").write(json.dumps(snapshot, indent=2) + "\n")
print(snapshot["status"])
PY
    local status
    status="$(python3 - "$evidence_dir/poll-${poll_index}.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1])).get("status", "unknown"))
PY
)"
    printf 'poll %03d: status=%s\n' "$poll_index" "$status" | tee -a "$evidence_dir/poll.log"
    case "$status" in
      completed|finalized|passed)
        return 0 ;;
      failed|error|cancelled|rejected|failed_*)
        return 1 ;;
    esac
    sleep "$poll_seconds"
  done
  python3 - "$evidence_dir/TIMEOUT_NOT_PRODUCT_PROOF.json" "$sid" "$timeout_seconds" <<'PY'
import json, sys, time
path, sid, timeout = sys.argv[1:4]
payload = {
    "valid": False,
    "reason": "timeout_before_terminal_state",
    "sprint_id": sid,
    "timeout_seconds": int(timeout),
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
  return 124
}

assert_route_proof_ok() {
  local sid="$1"
  local proof_path="$iso_harness/sprints/${sid}.route-proof.json"
  python3 - "$proof_path" <<'PY'
import json, sys
proof = json.load(open(sys.argv[1], encoding="utf-8"))
errors = []
if not proof.get("ok"):
    errors.append(f"route proof not ok: {proof.get('violations')}")
if proof.get("selected_runtime") != "claude":
    errors.append(f"selected_runtime={proof.get('selected_runtime')!r}")
allowed = set(proof.get("allowed_providers") or [])
if allowed != {"anthropic"}:
    errors.append(f"allowed_providers={sorted(allowed)!r}")
if int(proof.get("stage_count") or 0) < 1:
    errors.append("stage_count < 1")
for stage in proof.get("stages") or []:
    provider = str(stage.get("provider") or "")
    if provider and provider != "anthropic":
        errors.append(f"non-anthropic stage: {stage.get('task_id')} provider={provider}")
if errors:
    raise SystemExit("; ".join(errors))
print("route proof ok: claude/anthropic only")
PY
}

classify_claude_auth_source >/dev/null 2>&1 || true
prepare_isolated_harness
if ! claude_credentials_preflight; then
  echo "Claude auth preflight failed: missing sandbox HOME/.claude/.credentials.json symlink target." >&2
  echo "Evidence: $evidence_dir/CLAUDE_AUTH_PREFLIGHT_FAILED.json" >&2
  exit 4
fi
if ! model_registry_preflight; then
  echo "Model registry preflight failed before live run or /intake." >&2
  echo "Evidence: $evidence_dir/MODEL_REGISTRY_PREFLIGHT_FAILED.json" >&2
  exit 5
fi
if ! operator_registry_preflight; then
  echo "Operator registry preflight failed before live run or /intake." >&2
  echo "Evidence: $evidence_dir/OPERATOR_REGISTRY_PREFLIGHT_FAILED.json" >&2
  exit 5
fi
if ! anthropic_contract_preflight; then
  echo "Anthropic contract preflight failed before live run or /intake." >&2
  echo "Evidence: $evidence_dir/ANTHROPIC_CONTRACT_PREFLIGHT_FAILED.json" >&2
  exit 5
fi

if [[ "$prepare_only" == "1" ]]; then
  echo "PREPARE_ONLY PASS"
  echo "sandbox=$sandbox"
  echo "harness=$iso_harness"
  echo "workspace=$workspace"
  echo "evidence=$evidence_dir"
  echo "env_file=$env_file"
  exit 0
fi

if [[ "${SOLAR_LIVE_E2E_ALLOW:-}" != "1" ]]; then
  echo "Live Claude E2E not started." >&2
  echo "Set SOLAR_LIVE_E2E_ALLOW=1 to run and spend real Claude/Anthropic quota." >&2
  echo "Prepared sandbox: $sandbox" >&2
  exit 3
fi

require_cmd curl
require_cmd tmux
require_cmd claude

export HOME="$home_dir"
export HARNESS_DIR="$iso_harness"
export SOLAR_HARNESS_DIR="$iso_harness"
export SPRINTS_DIR="$iso_harness/sprints"
export PYTHONPATH="$iso_harness/lib"
export SOLAR_PANE_RUNTIME=claude
export SOLAR_PM_DEFAULT_PROVIDERS=anthropic
export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=anthropic
# P2 product flags - keep in lockstep with the generated e2e.env block above.
# G4 default-on: SOLAR_GATE_LEDGER / SOLAR_PLAN_VALIDATOR resolve ON at the
# parser level — deliberately NOT exported so e2e runs prove the runtime
# default a fresh machine gets (probe: plan_validator.py env-status).
export SOLAR_PRODUCT_MODE=1
export SOLAR_WORKFLOW_ROUTER=1
export SOLAR_INTAKE_WORKSPACE_ROOT="$workspace"
export SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH=1
export SOLAR_GRAPH_BUILDER_OPERATOR_POOL=1
export SOLAR_GRAPH_EVAL_OPERATOR_POOL=1
export SOLAR_COORD_MULTITASK_SELFCOMPLETE=1
export SOLAR_HARNESS_SESSION="$tmux_session"
export SOLAR_HARNESS_LAB_SESSION="$tmux_lab_session"
export SOLAR_HARNESS_BG_SESSION="$tmux_bg_session"
export PATH="$bin_dir:$PATH"

claude --version > "$evidence_dir/claude-version.txt" 2>&1 || true

(
  cd "$workspace"
  python3 "$iso_harness/lib/symphony/status-server.py" > "$logs_dir/status-server.out.log" 2> "$logs_dir/status-server.err.log"
) &
status_pid="$!"
port="$(wait_for_status_server)" || {
  tail -80 "$logs_dir/status-server.err.log" >&2 || true
  echo "status server did not become healthy" >&2
  exit 1
}
base_url="http://127.0.0.1:${port}"
echo "$port" > "$evidence_dir/status-server.port"

bash "$iso_harness/solar-harness.sh" start "$workspace" --skip-doctor > "$logs_dir/cockpit-start.log" 2>&1

sid="$(submit_intake "$base_url")"
echo "$sid" > "$evidence_dir/sprint_id.txt"
echo "submitted sprint: $sid"

set +e
poll_until_terminal "$sid" "$base_url"
poll_rc=$?
set -e
write_route_proof "$sid" | tee "$evidence_dir/route-proof-summary.json"
capture_http_snapshot "$base_url" "$sid"

if [[ "$poll_rc" -ne 0 ]]; then
  echo "sprint did not finish successfully; evidence kept at $evidence_dir" >&2
  exit "$poll_rc"
fi

assert_route_proof_ok "$sid"
echo "LIVE CLAUDE E2E PASS"
echo "sandbox=$sandbox"
echo "evidence=$evidence_dir"

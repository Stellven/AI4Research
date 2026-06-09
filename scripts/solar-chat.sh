#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/solar-chat.sh [options] "message"
  echo "message" | bash scripts/solar-chat.sh [options] --stdin

Options:
  --source VALUE     Source channel metadata. Default: codex_cli
  --actor VALUE      Actor metadata. Default: current user or codex
  --no-dispatch      Capture/consume intent without dispatch.
  --trace            After intake, locate the latest sprint and dry-run DAG dispatch.
  --dry-run          Print resolved repo-local environment and command.
  --stdin            Read message from stdin.
  -h, --help         Show this help.

This is a repo-local Solar chat probe. It pins Harness paths to this checkout,
then uses the existing Codex intake path. It is not a streaming chat runtime.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
harness_dir="$repo_dir/harness"
intake_bin="$repo_dir/scripts/solar-codex-intake.sh"
harness_bin="$harness_dir/solar-harness.sh"
venv_dir="$repo_dir/.venv"

[[ -f "$intake_bin" ]] || die "Codex intake script not found: $intake_bin"
[[ -f "$harness_bin" ]] || die "solar-harness not found: $harness_bin"

if [[ -x "$venv_dir/bin/python3" ]]; then
  export VIRTUAL_ENV="$venv_dir"
  export PATH="$venv_dir/bin:$PATH"
fi

export HARNESS_DIR="$harness_dir"
export SOLAR_HARNESS_DIR="$harness_dir"
export SOLAR_HARNESS_BIN="$harness_bin"
export SOLAR_HARNESS_SPRINTS_DIR="${SOLAR_HARNESS_SPRINTS_DIR:-$harness_dir/sprints}"
export SOLAR_INTENT_GATEWAY_DIR="${SOLAR_INTENT_GATEWAY_DIR:-$harness_dir/intents}"

source_channel="codex_cli"
actor="${USER:-codex}"
dispatch=1
trace=0
dry_run=0
use_stdin=0
declare -a message_parts=()

while (($#)); do
  case "$1" in
    --source|--source-channel)
      shift || die "$1 requires a value"
      source_channel="$1"
      ;;
    --actor)
      shift || die "--actor requires a value"
      actor="$1"
      ;;
    --no-dispatch)
      dispatch=0
      ;;
    --trace)
      trace=1
      ;;
    --dry-run)
      dry_run=1
      ;;
    --stdin)
      use_stdin=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      message_parts+=("$@")
      break
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      message_parts+=("$1")
      ;;
  esac
  shift || true
done

input_count=0
[[ "$use_stdin" == "1" ]] && input_count=$((input_count + 1))
((${#message_parts[@]} > 0)) && input_count=$((input_count + 1))
[[ "$input_count" == "1" ]] || die "provide exactly one message source: args or --stdin"

if [[ "$use_stdin" == "1" ]]; then
  message="$(cat)"
else
  message="${message_parts[*]}"
fi
[[ -n "${message//[[:space:]]/}" ]] || die "message is empty"

declare -a intake_args=(--source "$source_channel" --actor "$actor" --json)
[[ "$dispatch" == "0" ]] && intake_args+=(--no-dispatch)

if [[ "$dry_run" == "1" ]]; then
  printf 'repo_dir=%q\n' "$repo_dir"
  printf 'HARNESS_DIR=%q\n' "$HARNESS_DIR"
  printf 'SOLAR_HARNESS_DIR=%q\n' "$SOLAR_HARNESS_DIR"
  printf 'SOLAR_HARNESS_BIN=%q\n' "$SOLAR_HARNESS_BIN"
  printf 'SOLAR_HARNESS_SPRINTS_DIR=%q\n' "$SOLAR_HARNESS_SPRINTS_DIR"
  printf 'SOLAR_INTENT_GATEWAY_DIR=%q\n' "$SOLAR_INTENT_GATEWAY_DIR"
  printf 'python3=%q\n' "$(command -v python3 2>/dev/null || printf 'N/A')"
  printf 'intake_command='
  printf '%q ' bash "$intake_bin" "${intake_args[@]}" "$message"
  printf '\n'
  exit 0
fi

cd "$repo_dir"
before_epoch="$(date +%s)"
if ! intake_output="$(bash "$intake_bin" "${intake_args[@]}" "$message" 2>&1)"; then
  printf '%s\n' "$intake_output"
  exit 1
fi
printf '%s\n' "$intake_output"

if [[ "$trace" != "1" ]]; then
  exit 0
fi

trace_intent_id="$(printf '%s\n' "$intake_output" | python3 - <<'PY' 2>/dev/null || true
import json
import sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
print(((data.get("intent_gateway") or {}).get("intent_id") or ""))
PY
)"
latest_status=""
if [[ -n "$trace_intent_id" ]]; then
  latest_status="$(python3 - "$harness_dir" "$trace_intent_id" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

harness_dir = Path(sys.argv[1])
intent_id = sys.argv[2]
token = intent_id.rsplit("-", 1)[-1][:8]
sprints = harness_dir / "sprints"
exact = []
fuzzy = []
for status in sprints.glob(f"sprint-*{token}*.status.json"):
    fuzzy.append(status)
    sid = status.name[:-len(".status.json")]
    raw = status.with_name(sid + ".raw_intent.json")
    req = status.with_name(sid + ".requirement_ir.json")
    for candidate in (raw, req):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("intent_id") == intent_id:
            exact.append(status)
            break
selected = exact or fuzzy
if selected:
    selected.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    print(selected[0])
PY
)"
fi
if [[ -z "$latest_status" ]]; then
  latest_status="$(ls -t "$harness_dir"/sprints/sprint-*intent*.status.json 2>/dev/null | head -1 || true)"
fi
if [[ -z "$latest_status" ]]; then
  printf '\n[solar-chat trace] error: no sprint status found\n' >&2
  exit 2
fi

sid="$(basename "$latest_status" .status.json)"
graph_path="$harness_dir/sprints/$sid.task_graph.json"
printf '\n[solar-chat trace] sprint_id=%s\n' "$sid"
printf '[solar-chat trace] status=%s\n' "$latest_status"

if [[ ! -f "$graph_path" ]]; then
  printf '[solar-chat trace] error: task graph not found: %s\n' "$graph_path" >&2
  exit 3
fi

python3 - "$harness_bin" "$graph_path" <<'PY'
import json
import os
import subprocess
import sys

harness_bin, graph_path = sys.argv[1:3]
cmd = ["bash", harness_bin, "graph-dispatch", "dispatch-ready", "--graph", graph_path, "--dry-run"]
completed = subprocess.run(cmd, capture_output=True, text=True, env=os.environ, timeout=60)
print(f"[solar-chat trace] graph_dispatch_returncode={completed.returncode}")
if completed.stderr.strip():
    print("[solar-chat trace] graph_dispatch_stderr_tail=" + completed.stderr[-1200:].strip())
if completed.returncode != 0:
    print(completed.stdout[-4000:])
    sys.exit(completed.returncode)
try:
    data = json.loads(completed.stdout or "{}")
except Exception as exc:
    print(f"[solar-chat trace] error: graph dispatch output is not JSON: {exc}")
    print(completed.stdout[-4000:])
    sys.exit(4)
enqueue = data.get("enqueue") or {}
drain = data.get("drain") or {}
print(f"[solar-chat trace] graph_ok={data.get('ok')}")
print("[solar-chat trace] enqueued=" + json.dumps(
    [(x.get("node"), x.get("pane")) for x in enqueue.get("enqueued", [])],
    ensure_ascii=False,
))
print("[solar-chat trace] queued=" + json.dumps(enqueue.get("queued", []), ensure_ascii=False))
print("[solar-chat trace] worker_blocked=" + json.dumps(enqueue.get("worker_blocked", []), ensure_ascii=False))
print("[solar-chat trace] drain=" + json.dumps(
    [
        (
            r.get("node"),
            r.get("dispatch_mode"),
            (r.get("pm_dispatch") or {}).get("operator_id"),
            r.get("pane"),
        )
        for r in drain.get("results", [])
    ],
    ensure_ascii=False,
))
PY

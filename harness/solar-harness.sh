#!/bin/bash
# ================================================================
# Solar Harness — 一键启动多化身协同环境
#
# 用法:
#   solar-harness.sh [工作目录]          启动3化身 (默认)
#   solar-harness.sh 2 [工作目录]        启动2化身
#   solar-harness.sh status              查看状态
#   solar-harness.sh kill                关闭
#   solar-harness.sh sprint "需求"       创建 Sprint
#   solar-harness.sh intent-gateway capture --text "需求"  捕获 RawIntent/重写/IR
#
# @module solar-farm/harness
# ================================================================
set -eu

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
# Every installed entry point must import from the harness it is executing.
# Live campaign runners used to inject this externally, which hid a fresh-
# install failure where product-mode intake rejected its own child process as
# path-inconsistent.  Keep caller paths, but make the active tree authoritative.
case "${PYTHONPATH:-}" in
  "$HARNESS_DIR/lib"|"$HARNESS_DIR/lib:"*) ;;
  *) export PYTHONPATH="$HARNESS_DIR/lib${PYTHONPATH:+:$PYTHONPATH}" ;;
esac
# Operator-owned config: when SOLAR_PANE_RUNTIME isn't set in the env, default to the pane
# runtime the dashboard's runtime selector persisted (config key "runtime"). Env still wins.
# Source the config helper early (it only needs HARNESS_DIR); harmless if re-sourced below.
[[ -f "$HARNESS_DIR/lib/harness-config.sh" ]] && . "$HARNESS_DIR/lib/harness-config.sh"
if [[ -z "${SOLAR_PANE_RUNTIME:-}" ]] && declare -F solar_config_json_get >/dev/null 2>&1; then
  SOLAR_PANE_RUNTIME="$(solar_config_json_get "runtime" "claude" 2>/dev/null || echo claude)"
fi
SOLAR_PANE_RUNTIME="${SOLAR_PANE_RUNTIME:-claude}"
case "$SOLAR_PANE_RUNTIME" in
  claude|codex) ;;
  *) echo "ERROR: unsupported SOLAR_PANE_RUNTIME='$SOLAR_PANE_RUNTIME' (expected claude|codex)" >&2; exit 64 ;;
esac
# Default codex launch flags from operator config (config keys codex.search / codex.effort) when
# the env didn't set them and the runtime is codex. This is what makes a dashboard-selected codex
# runtime actually use web search + the chosen reasoning effort — without it codex panes launch
# with no --search and research stalls on the human-search gate. Env SOLAR_CODEX_EXTRA_FLAGS wins.
if [[ "$SOLAR_PANE_RUNTIME" == "codex" && -z "${SOLAR_CODEX_EXTRA_FLAGS:-}" ]] && declare -F solar_config_json_get >/dev/null 2>&1; then
  _codex_search="$(solar_config_json_get "codex.search" "true" 2>/dev/null || echo true)"
  _codex_effort="$(solar_config_json_get "codex.effort" "medium" 2>/dev/null || echo medium)"
  _codex_flags=""
  case "$_codex_search" in [Tt]rue|1|yes|on|ON) _codex_flags="--search" ;; esac
  case "$_codex_effort" in
    low|medium|high|xhigh|minimal)
      _codex_flags="${_codex_flags:+$_codex_flags }-c model_reasoning_effort=${_codex_effort}" ;;
  esac
  [[ -n "$_codex_flags" ]] && export SOLAR_CODEX_EXTRA_FLAGS="$_codex_flags"
  unset _codex_search _codex_effort _codex_flags
fi
# Runtime selector contract: when the dashboard/runtime config says "codex", route the whole DAG
# surface toward Codex/OpenAI by default (PM/planner dispatch, builder pool, eval pool, and the
# self-completing multi-task loop). Env values still win for advanced/hybrid rigs.
case "$SOLAR_PANE_RUNTIME" in
  codex)
    export SOLAR_PM_DEFAULT_PROVIDERS="${SOLAR_PM_DEFAULT_PROVIDERS:-openai}"
    export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS="${SOLAR_MULTI_TASK_DEFAULT_PROVIDERS:-openai}"
    export SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH="${SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH:-1}"
    export SOLAR_GRAPH_BUILDER_OPERATOR_POOL="${SOLAR_GRAPH_BUILDER_OPERATOR_POOL:-1}"
    export SOLAR_GRAPH_EVAL_OPERATOR_POOL="${SOLAR_GRAPH_EVAL_OPERATOR_POOL:-1}"
    export SOLAR_COORD_MULTITASK_SELFCOMPLETE="${SOLAR_COORD_MULTITASK_SELFCOMPLETE:-1}"
    ;;
  claude)
    export SOLAR_PM_DEFAULT_PROVIDERS="${SOLAR_PM_DEFAULT_PROVIDERS:-anthropic}"
    export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS="${SOLAR_MULTI_TASK_DEFAULT_PROVIDERS:-anthropic}"
    ;;
esac
case "$SOLAR_PANE_RUNTIME" in
  codex) PANE_RUNTIME_LABEL="Codex" ;;
  *) PANE_RUNTIME_LABEL="Claude" ;;
esac
SESSION_NAME="${SOLAR_HARNESS_SESSION:-solar-harness}"
LAB_SESSION_NAME="${SOLAR_HARNESS_LAB_SESSION:-${SESSION_NAME}-lab}"
LEGACY_LAB_SESSION_NAME="solar-harness-strategy"
BG_SESSION_NAME="${SOLAR_HARNESS_BG_SESSION:-solar-harness-bg}"
SPRINTS_DIR="${HARNESS_SPRINTS_DIR:-$HARNESS_DIR/sprints}"
BG_TASKS_DIR="$HARNESS_DIR/run/bg-tasks"
EXPECTED_PRODUCT_DELIVERY_PANES=4
export HARNESS_DIR SPRINTS_DIR SOLAR_PANE_RUNTIME

# sprint-20260503-094659 D2: 统一 state helper
. "$HARNESS_DIR/lib/run-state.sh"
[[ -f "$HARNESS_DIR/lib/events.sh" ]] && . "$HARNESS_DIR/lib/events.sh"

# Shared qmd resolver. Optional source keeps older installs doctor-capable.
[[ -f "$HARNESS_DIR/lib/qmd-resolver.sh" ]] && . "$HARNESS_DIR/lib/qmd-resolver.sh"

# Operator-owned config. Runtime launchers consume this instead of hardcoding
# model policy in multiple places.
[[ -f "$HARNESS_DIR/lib/harness-config.sh" ]] && . "$HARNESS_DIR/lib/harness-config.sh"

# sprint-20260503-163542 D3: bridge ledger
[[ -f "$HARNESS_DIR/lib/bridge-ledger.sh" ]] && . "$HARNESS_DIR/lib/bridge-ledger.sh"

# Human-facing capability visibility prefixes.
[[ -f "$HARNESS_DIR/lib/capability-prefix.sh" ]] && . "$HARNESS_DIR/lib/capability-prefix.sh"
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"

# ---- Colors ----
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[0;34m'; N='\033[0m'
log()  { echo -e "${C}[Harness]${N} $*"; }
ok()   { echo -e "${G}[Harness]${N} $*"; }
warn() { echo -e "${Y}[Harness]${N} $*"; }
err()  { echo -e "${R}[Harness]${N} $*"; }
human_prefix() {
  local module="$1"; shift || true
  case " $* " in *" --json "*) return 0 ;; esac
  type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "$module" "$*"
}

ensure_dirs() { mkdir -p "$SPRINTS_DIR" "$HARNESS_DIR/personas" "$HARNESS_DIR/templates"; }

load_workdir_dotenv() {
  local work_dir="${1:-$(pwd)}"
  local env_file="$work_dir/.env"
  [[ -f "$env_file" ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" == export[[:space:]]* ]]; then
      line="${line#export}"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[[:space:]]/}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value#"${value%%[![:space:]]*}"}"
    if [[ "$value" == \"*\" && "$value" == *\" && "${#value}" -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' && "${#value}" -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
}

persist_workspace_root() {
  local candidate="${1:-}" source="${2:-harness_start}"
  [[ -n "$candidate" ]] || { err "workspace root is empty"; return 1; }
  [[ -f "$HARNESS_DIR/lib/workspace_binding.py" ]] || {
    err "workspace binding helper missing: $HARNESS_DIR/lib/workspace_binding.py"
    return 1
  }
  python3 "$HARNESS_DIR/lib/workspace_binding.py" bind \
    --harness-dir "$HARNESS_DIR" --workspace-root "$candidate" --source "$source" >/dev/null
}

active_workspace_root() {
  [[ -f "$HARNESS_DIR/lib/workspace_binding.py" ]] || return 1
  python3 "$HARNESS_DIR/lib/workspace_binding.py" show --harness-dir "$HARNESS_DIR"
}

resolve_intake_workspace_root() {
  local candidate="${SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT:-${SOLAR_INTAKE_WORKSPACE_ROOT:-}}"
  local had_explicit=0 had_binding=0 harness_real candidate_real
  [[ -n "$candidate" ]] && had_explicit=1
  if [[ -z "$candidate" ]]; then
    candidate="$(active_workspace_root 2>/dev/null || true)"
    [[ -n "$candidate" ]] && had_binding=1
  fi
  [[ -n "$candidate" ]] || candidate="$(pwd)"
  [[ -d "$candidate" ]] || {
    echo "[Harness] intake workspace does not exist: $candidate" >&2
    return 1
  }
  candidate_real="$(cd "$candidate" && pwd -P)"
  harness_real="$(cd "$HARNESS_DIR" && pwd -P)"
  if [[ "$had_explicit" == "0" && "$had_binding" == "0" && "$candidate_real" == "$harness_real" ]]; then
    echo "[Harness] no user workspace is bound; run 'solar harness start /path/to/project' first, or run intake from the project directory" >&2
    return 1
  fi
  printf '%s\n' "$candidate_real"
}

# tmux treats a unique session-name prefix as a valid target.  Solar owns
# several sessions whose names begin with "solar-harness" (dashboard, lab,
# background work), so a prefix probe can mistake one of those for the main
# cockpit.  Enumerating names makes every ownership check exact.
tmux_has_exact_session() {
  local wanted="$1"
  tmux list-sessions -F '#{session_name}' 2>/dev/null | grep -Fxq -- "$wanted"
}

# Fix 4 (clean-cockpit-start): reset stale runtime coordination state that otherwise
# carries across restarts and walls fresh runs — a needs_respawn hygiene latch, stale
# pane leases, stale pane assignments, and the fire-once drafting/builder dispatch
# markers. NEVER touches sprint state (sprints/), logs, model config, or venvs. Safe on a
# fresh session (no in-flight work); for an already-running cockpit the caller gates this
# behind explicit --clean / SOLAR_HARNESS_CLEAN_START so in-flight work is preserved.
reset_stale_runtime_state() {
  local why="${1:-fresh-session}"
  local run_dir="$HARNESS_DIR/run"
  local reset_count=0 lease_dir marker

  # 1) Hygiene registry → empty, so freshly-launched panes re-register clean (clears any
  #    stale needs_respawn/needs_recover latch). Recreated on first registry access.
  if [[ -f "$run_dir/pane-hygiene.json" ]]; then
    printf '{}\n' > "$run_dir/pane-hygiene.json"
    reset_count=$((reset_count+1))
  fi

  # 2) Pane/actor leases: on a clean start no pane holds a live lease.
  for lease_dir in "$run_dir/pane-leases" "$run_dir/actor-leases"; do
    if [[ -d "$lease_dir" ]]; then
      find "$lease_dir" -maxdepth 1 -type f \( -name '*.json' -o -name '*.json.lock' \) -delete 2>/dev/null || true
      reset_count=$((reset_count+1))
    fi
  done

  # 3) Stale pane assignments + fire-once dispatch markers (root dotfiles). These reserve
  #    panes / suppress re-dispatch for sprints that may be long gone; rebuilt on demand.
  for marker in .pane-assignments .drafting-flow-dispatched .drafting-flow-retry .builder-flow-dispatched; do
    if [[ -f "$HARNESS_DIR/$marker" ]]; then
      rm -f "$HARNESS_DIR/$marker"
      reset_count=$((reset_count+1))
    fi
  done

  log "${G:-}[clean-start] reset ${reset_count} stale runtime state item(s) (${why})${N:-}"
}

bg_now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

bg_write_status() {
  local task_dir="$1" id="$2" status="$3" mode="$4" title="$5" window="$6" work_dir="$7" exit_code="${8:-}"
  mkdir -p "$task_dir"
  python3 - "$task_dir/status.json" "$id" "$status" "$mode" "$title" "$BG_SESSION_NAME" "$window" "$work_dir" "$exit_code" "$(bg_now_iso)" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "id": sys.argv[2],
    "status": sys.argv[3],
    "mode": sys.argv[4],
    "title": sys.argv[5],
    "session": sys.argv[6],
    "window": sys.argv[7],
    "work_dir": sys.argv[8],
    "exit_code": None if sys.argv[9] == "" else int(sys.argv[9]),
    "updated_at": sys.argv[10],
}
if path.exists():
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    old.update(payload)
    payload = old
else:
    payload["created_at"] = sys.argv[10]
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

bg_task_id() {
  printf 'bg-%s-%04d\n' "$(date +%Y%m%d-%H%M%S)" "$((RANDOM % 10000))"
}

bg_short_title() {
  python3 - "$1" <<'PY'
import re
import sys
s = re.sub(r"\s+", "-", sys.argv[1].strip().lower())
s = re.sub(r"[^a-z0-9._-]+", "", s)[:28].strip("-")
print(s or "task")
PY
}

bg_runner_script() {
  local task_dir="$1" id="$2" mode="$3" title="$4" work_dir="$5"
  local runner="$task_dir/runner.sh"
  local harness_q task_dir_q work_dir_q id_q mode_q title_q
  harness_q=$(printf '%q' "$HARNESS_DIR")
  task_dir_q=$(printf '%q' "$task_dir")
  work_dir_q=$(printf '%q' "$work_dir")
  id_q=$(printf '%q' "$id")
  mode_q=$(printf '%q' "$mode")
  title_q=$(printf '%q' "$title")
  cat > "$runner" <<EOF
#!/usr/bin/env bash
set -u
HARNESS_DIR=${harness_q}
TASK_DIR=${task_dir_q}
WORK_DIR=${work_dir_q}
ID=${id_q}
MODE=${mode_q}
TITLE=${title_q}
LOG="\$TASK_DIR/output.log"
STATUS="\$TASK_DIR/status.json"

write_status() {
  local status="\$1" exit_code="\${2:-}"
  python3 - "\$STATUS" "\$ID" "\$status" "\$MODE" "\$TITLE" "$BG_SESSION_NAME" "\$(tmux display-message -p '#{window_name}' 2>/dev/null || echo "$id")" "\$WORK_DIR" "\$exit_code" "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
old = {}
if path.exists():
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        old = {}
old.update({
    "id": sys.argv[2],
    "status": sys.argv[3],
    "mode": sys.argv[4],
    "title": sys.argv[5],
    "session": sys.argv[6],
    "window": sys.argv[7],
    "work_dir": sys.argv[8],
    "exit_code": None if sys.argv[9] == "" else int(sys.argv[9]),
    "updated_at": sys.argv[10],
})
old.setdefault("created_at", sys.argv[10])
path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
}

mkdir -p "\$TASK_DIR"
cd "\$WORK_DIR" || exit 1
write_status running
{
  echo "[solar-harness bg] id=\$ID mode=\$MODE start=\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ "\$MODE" == "command" ]]; then
    bash "\$TASK_DIR/command.sh"
  else
    "\$HARNESS_DIR/solar-harness.sh" intake --request "\$(cat "\$TASK_DIR/request.txt")"
  fi
} > >(tee -a "\$LOG") 2>&1
rc=\$?
if [[ "\$rc" -eq 0 ]]; then
  write_status completed "\$rc"
  [[ -x "\$HARNESS_DIR/osascript-notify.sh" ]] && bash "\$HARNESS_DIR/osascript-notify.sh" "Solar bg completed" "\$ID: \$TITLE" "Glass" >/dev/null 2>&1 || true
else
  write_status failed "\$rc"
  [[ -x "\$HARNESS_DIR/osascript-notify.sh" ]] && bash "\$HARNESS_DIR/osascript-notify.sh" "Solar bg failed" "\$ID: \$TITLE" "Blow" >/dev/null 2>&1 || true
fi
echo "[solar-harness bg] id=\$ID exit=\$rc end=\$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "\$LOG"
exit "\$rc"
EOF
  chmod +x "$runner"
  printf '%s\n' "$runner"
}

do_bg_command() {
  local subcmd="${1:-}"
  case "$subcmd" in
    help|--help|-h|"")
      echo "Solar Harness BG"
      echo ""
      echo "Usage:"
      echo "  $0 bg \"自然语言任务\""
      echo "  $0 bg --cwd /path \"自然语言任务\""
      echo "  $0 bg run [--cwd /path] -- <shell command>"
      echo "  $0 bg status|list"
      echo "  $0 bg logs <id>"
      echo "  $0 bg attach <id>"
      echo "  $0 bg cancel <id>"
      return 0
      ;;
    status|list)
      mkdir -p "$BG_TASKS_DIR"
      python3 - "$BG_TASKS_DIR" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
rows = []
for status in sorted(root.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True):
    try:
        data = json.loads(status.read_text(encoding="utf-8"))
    except Exception:
        continue
    rows.append(data)
print("┌────────────────────────────┬────────────┬──────────┬────────────────────────────┬────────────────────────────┐")
print("│ id                         │ status     │ mode     │ updated_at                 │ title                      │")
print("├────────────────────────────┼────────────┼──────────┼────────────────────────────┼────────────────────────────┤")
for row in rows[:30]:
    print("│ %-26s │ %-10s │ %-8s │ %-26s │ %-26s │" % (
        str(row.get("id", "N/A"))[:26],
        str(row.get("status", "N/A"))[:10],
        str(row.get("mode", "N/A"))[:8],
        str(row.get("updated_at", "N/A"))[:26],
        str(row.get("title", "N/A"))[:26],
    ))
print("└────────────────────────────┴────────────┴──────────┴────────────────────────────┴────────────────────────────┘")
PY
      return 0
      ;;
    logs|log)
      shift || true
      local id="${1:-}"
      [[ -n "$id" ]] || { err "Usage: $0 bg logs <id>"; return 2; }
      local log_file="$BG_TASKS_DIR/$id/output.log"
      [[ -f "$log_file" ]] || { err "log not found: $log_file"; return 1; }
      tail -200 "$log_file"
      return 0
      ;;
    attach)
      shift || true
      local id="${1:-}"
      [[ -n "$id" ]] || { err "Usage: $0 bg attach <id>"; return 2; }
      local status_file="$BG_TASKS_DIR/$id/status.json"
      [[ -f "$status_file" ]] || { err "status not found: $status_file"; return 1; }
      local window
      window=$(python3 - "$status_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("window", ""))
PY
)
      if [[ -t 1 && -n "${TERM:-}" && "${TERM:-}" != "dumb" ]]; then
        tmux select-window -t "${BG_SESSION_NAME}:${window}" 2>/dev/null || true
        tmux attach -t "${BG_SESSION_NAME}"
      else
        ok "bg task 在后台运行: tmux attach -t ${BG_SESSION_NAME}:${window}"
      fi
      return 0
      ;;
    cancel)
      shift || true
      local id="${1:-}"
      [[ -n "$id" ]] || { err "Usage: $0 bg cancel <id>"; return 2; }
      local status_file="$BG_TASKS_DIR/$id/status.json"
      [[ -f "$status_file" ]] || { err "status not found: $status_file"; return 1; }
      local window task_dir
      task_dir="$BG_TASKS_DIR/$id"
      window=$(python3 - "$status_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("window", ""))
PY
)
      tmux kill-window -t "${BG_SESSION_NAME}:${window}" 2>/dev/null || true
      bg_write_status "$task_dir" "$id" "cancelled" "$(python3 - "$status_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("mode", "task"))
PY
)" "$(python3 - "$status_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("title", "N/A"))
PY
)" "$window" "$(pwd)" ""
      ok "cancelled: $id"
      return 0
      ;;
  esac

  local mode="task" work_dir="$(pwd)" task_text="" id title window task_dir runner
  if [[ "$subcmd" == "run" ]]; then
    mode="command"
    shift || true
  fi
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --cwd)
        shift || { err "bg --cwd needs path"; return 1; }
        work_dir="$1"
        ;;
      --)
        shift
        task_text="$*"
        break
        ;;
      *)
        task_text+="${task_text:+ }$1"
        ;;
    esac
    shift || true
  done
  [[ -d "$work_dir" ]] || { err "bg cwd not found: $work_dir"; return 1; }
  [[ -n "$task_text" ]] || { err "Usage: $0 bg \"任务\" 或 $0 bg run -- <command>"; return 2; }

  id="$(bg_task_id)"
  title="$(bg_short_title "$task_text")"
  window="${id#bg-}-${title}"
  window="${window:0:48}"
  task_dir="$BG_TASKS_DIR/$id"
  mkdir -p "$task_dir"
  if [[ "$mode" == "command" ]]; then
    printf '%s\n' "$task_text" > "$task_dir/command.sh"
    chmod +x "$task_dir/command.sh"
  else
    printf '%s\n' "$task_text" > "$task_dir/request.txt"
  fi
  runner="$(bg_runner_script "$task_dir" "$id" "$mode" "$title" "$work_dir")"
  bg_write_status "$task_dir" "$id" "queued" "$mode" "$title" "$window" "$work_dir" ""

  # tmux windows inherit the tmux SERVER's environment, not this shell's —
  # prefix the product flags into the command so flag-gated behavior (gate
  # ledger, product mode, provider pinning) survives a long-lived server
  # (P2 smoke 20260707T190540Z: zero route records via this gap).
  local _penv=""
  local _pvar
  for _pvar in SOLAR_GATE_LEDGER SOLAR_PRODUCT_MODE SOLAR_WORKFLOW_ROUTER SOLAR_MULTI_TASK_DEFAULT_PROVIDERS SOLAR_PM_DEFAULT_PROVIDERS HARNESS_SPRINTS_DIR; do
    if [[ -n "${!_pvar:-}" ]]; then
      _penv+="$_pvar=$(printf '%q' "${!_pvar}") "
    fi
  done
  if tmux_has_exact_session "$BG_SESSION_NAME"; then
    tmux new-window -d -t "$BG_SESSION_NAME" -n "$window" -c "$work_dir" "${_penv}bash $(printf '%q' "$runner"); exec \${SHELL:-/bin/zsh}"
  else
    tmux new-session -d -s "$BG_SESSION_NAME" -n "$window" -c "$work_dir" "${_penv}bash $(printf '%q' "$runner"); exec \${SHELL:-/bin/zsh}"
  fi
  ok "bg task queued: $id"
  log "status: $0 bg status"
  log "logs:   $0 bg logs $id"
  log "attach: tmux attach -t ${BG_SESSION_NAME}:${window}"
}

cleanup_legacy_sessions() {
  if ! tmux_has_exact_session "$LEGACY_LAB_SESSION_NAME"; then
    return 0
  fi

  local attached="0"
  attached=$(tmux display-message -p -t "$LEGACY_LAB_SESSION_NAME" '#{session_attached}' 2>/dev/null || echo "0")
  if [[ "$attached" != "0" ]]; then
    warn "检测到旧 Strategy Lab session 仍被附着: $LEGACY_LAB_SESSION_NAME"
    warn "请先退出旧会话，再运行: tmux kill-session -t $LEGACY_LAB_SESSION_NAME"
    return 0
  fi

  tmux kill-session -t "$LEGACY_LAB_SESSION_NAME" 2>/dev/null || true
  ok "已清理旧残留 session: $LEGACY_LAB_SESSION_NAME"
}

sanitize_tmux_claude_env() {
  local session="$1"
  tmux set-environment -t "$session" -gu CLAUDECODE 2>/dev/null || true
  tmux set-environment -t "$session" -gu CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true
  tmux set-environment -t "$session" -gu CLAUDE_CODE_EXECPATH 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_BASE_URL 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_AUTH_TOKEN 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_API_KEY 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_DEFAULT_OPUS_MODEL 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_DEFAULT_SONNET_MODEL 2>/dev/null || true
  tmux set-environment -t "$session" -gu ANTHROPIC_DEFAULT_HAIKU_MODEL 2>/dev/null || true
  tmux set-environment -t "$session" -gu SOLAR_LAB_BUILDER_MODEL_MATRIX 2>/dev/null || true
}

claude_clean_env_prefix() {
  printf '%s' "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY -u ANTHROPIC_DEFAULT_OPUS_MODEL -u ANTHROPIC_DEFAULT_SONNET_MODEL -u ANTHROPIC_DEFAULT_HAIKU_MODEL"
}

pane_runtime_cli_path() {
  local c
  local candidates=()
  case "$SOLAR_PANE_RUNTIME" in
    codex)
      [[ -n "${SOLAR_CODEX_BIN:-}" ]] && candidates+=("$SOLAR_CODEX_BIN")
      candidates+=("$HOME/.npm-global/bin/codex" "$HOME/bin/codex" "$HOME/n/bin/codex")
      c="$(command -v codex 2>/dev/null || true)"
      ;;
    claude)
      [[ -n "${SOLAR_CLAUDE_BIN:-}" ]] && candidates+=("$SOLAR_CLAUDE_BIN")
      candidates+=("$HOME/.npm-global/bin/claude" "$HOME/bin/claude" "$HOME/n/bin/claude")
      c="$(command -v claude 2>/dev/null || true)"
      ;;
  esac
  [[ -n "${c:-}" ]] && candidates+=("$c")
  for c in "${candidates[@]}"; do
    [[ -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

pane_runtime_env_assignments() {
  local harness_session="${SOLAR_HARNESS_SESSION:-$SESSION_NAME}"
  case "$SOLAR_PANE_RUNTIME" in
    codex)
      printf 'SOLAR_PANE_RUNTIME=codex SOLAR_CODEX_BYPASS=%q' "${SOLAR_CODEX_BYPASS:-1}"
      printf ' SOLAR_HARNESS_SESSION=%q' "$harness_session"
      [[ -n "${SOLAR_CODEX_SOURCE_HOME:-}" ]] && printf ' SOLAR_CODEX_SOURCE_HOME=%q' "$SOLAR_CODEX_SOURCE_HOME"
      [[ -n "${SOLAR_CODEX_BIN:-}" ]] && printf ' SOLAR_CODEX_BIN=%q' "$SOLAR_CODEX_BIN"
      [[ -n "${SOLAR_CODEX_MODEL:-}" ]] && printf ' SOLAR_CODEX_MODEL=%q' "$SOLAR_CODEX_MODEL"
      [[ -n "${SOLAR_CODEX_EXTRA_FLAGS:-}" ]] && printf ' SOLAR_CODEX_EXTRA_FLAGS=%q' "$SOLAR_CODEX_EXTRA_FLAGS"
      [[ -n "${SOLAR_CODEX_TRUST_WORKSPACE:-}" ]] && printf ' SOLAR_CODEX_TRUST_WORKSPACE=%q' "$SOLAR_CODEX_TRUST_WORKSPACE"
      ;;
    claude)
      printf 'SOLAR_PANE_RUNTIME=claude SOLAR_CLAUDE_BYPASS=%q' "${SOLAR_CLAUDE_BYPASS:-1}"
      [[ -n "${SOLAR_CLAUDE_BIN:-}" ]] && printf ' SOLAR_CLAUDE_BIN=%q' "$SOLAR_CLAUDE_BIN"
      ;;
  esac
}

pane_launch_prefix() {
  printf '%s HARNESS_DIR=%q SOLAR_HARNESS_DIR=%q %s' "$(claude_clean_env_prefix)" "$HARNESS_DIR" "$HARNESS_DIR" "$(pane_runtime_env_assignments)"
}

configure_tmux_pane_runtime_env() {
  local session="$1" var
  local harness_session="${SOLAR_HARNESS_SESSION:-$SESSION_NAME}"
  tmux set-environment -t "$session" HARNESS_DIR "$HARNESS_DIR" 2>/dev/null || true
  tmux set-environment -t "$session" SOLAR_HARNESS_DIR "$HARNESS_DIR" 2>/dev/null || true
  tmux set-environment -t "$session" SOLAR_PANE_RUNTIME "$SOLAR_PANE_RUNTIME" 2>/dev/null || true
  tmux set-environment -t "$session" SOLAR_HARNESS_SESSION "$harness_session" 2>/dev/null || true
  case "$SOLAR_PANE_RUNTIME" in
    codex)
      tmux set-environment -t "$session" SOLAR_CODEX_BYPASS "${SOLAR_CODEX_BYPASS:-1}" 2>/dev/null || true
      tmux set-environment -t "$session" -gu SOLAR_CLAUDE_BYPASS 2>/dev/null || true
      tmux set-environment -t "$session" -gu CODEX_HOME 2>/dev/null || true
      for var in SOLAR_CODEX_SOURCE_HOME SOLAR_CODEX_BIN SOLAR_CODEX_MODEL SOLAR_CODEX_EXTRA_FLAGS SOLAR_CODEX_TRUST_WORKSPACE; do
        if [[ -n "${!var:-}" ]]; then
          tmux set-environment -t "$session" "$var" "${!var}" 2>/dev/null || true
        else
          tmux set-environment -t "$session" -gu "$var" 2>/dev/null || true
        fi
      done
      ;;
    claude)
      tmux set-environment -t "$session" SOLAR_CLAUDE_BYPASS "${SOLAR_CLAUDE_BYPASS:-1}" 2>/dev/null || true
      tmux set-environment -t "$session" -gu SOLAR_CODEX_BYPASS 2>/dev/null || true
      [[ -n "${SOLAR_CLAUDE_BIN:-}" ]] && tmux set-environment -t "$session" SOLAR_CLAUDE_BIN "$SOLAR_CLAUDE_BIN" 2>/dev/null || true
      ;;
  esac
}

attach_or_print() {
  local session="${1:-$SESSION_NAME}"
  if [[ -t 1 && -n "${TERM:-}" && "${TERM:-}" != "dumb" ]]; then
    tmux attach -t "$session" || {
      warn "tmux attach 失败，session 已在后台运行: $session"
      log "重新接入: tmux attach -t $session"
      return 0
    }
  else
    ok "tmux session 已在后台运行: $session"
    log "重新接入: tmux attach -t $session"
  fi
}

configure_role_footer_style() {
  local session="$1" active_color="${2:-#89b4fa}"
  tmux set-window-option -t "$session:0" pane-border-status bottom 2>/dev/null || true
  tmux set-window-option -t "$session:0" pane-border-format "#[fg=${active_color},bold] #P #{pane_title} #[default]" 2>/dev/null || true
  tmux set-option -t "$session" allow-set-title off 2>/dev/null || true
}

pane_footer_label() {
  local persona="$1" label="$2" slot="${3:-}"
  local base
  base="$(bash "$HARNESS_DIR/quota-footer.sh" "$persona" "$label" "$slot" 2>/dev/null || printf "%s | 模型:N/A | 剩余:N/A | 已用:N/A tok" "$label")"
  printf "%s | 能力:K/I/S/G/A" "$base"
}

configure_product_delivery_labels() {
  tmux_has_exact_session "$SESSION_NAME" || return 0
  tmux rename-window -t "$SESSION_NAME:0" "Product Delivery" 2>/dev/null || true
  configure_role_footer_style "$SESSION_NAME" "#89b4fa"
  tmux select-pane -t "$SESSION_NAME:0.0" -T "$(pane_footer_label pm "PM 产品经理")" 2>/dev/null || true
  tmux select-pane -t "$SESSION_NAME:0.1" -T "$(pane_footer_label planner "Planner 规划者")" 2>/dev/null || true
  tmux select-pane -t "$SESSION_NAME:0.2" -T "$(pane_footer_label builder "Builder 主建设者")" 2>/dev/null || true
  tmux select-pane -t "$SESSION_NAME:0.3" -T "$(pane_footer_label evaluator "Evaluator 审判官")" 2>/dev/null || true
}

product_delivery_pane_count() {
  tmux_has_exact_session "$SESSION_NAME" || { printf '0\n'; return 1; }
  tmux list-panes -t "$SESSION_NAME:Product Delivery" 2>/dev/null | wc -l | tr -d ' '
}

warn_if_product_delivery_layout_incomplete() {
  tmux_has_exact_session "$SESSION_NAME" || return 0
  local panes_count
  panes_count="$(product_delivery_pane_count 2>/dev/null || printf '0')"
  if [[ "$panes_count" != "$EXPECTED_PRODUCT_DELIVERY_PANES" ]]; then
    warn "Product Delivery layout 异常: expected=${EXPECTED_PRODUCT_DELIVERY_PANES} actual=${panes_count}; 当前不是健康四分屏"
    warn "不要只看 status 报喜；请先修复 tmux layout，再派发/唤醒任务"
    return 1
  fi
  return 0
}

apply_product_delivery_models() {
  tmux_has_exact_session "$SESSION_NAME" || { warn "主屏未运行: $SESSION_NAME"; return 0; }
  local personas=(pm planner builder evaluator)
  local panes=("$SESSION_NAME:Product Delivery.0" "$SESSION_NAME:Product Delivery.1" "$SESSION_NAME:Product Delivery.2" "$SESSION_NAME:Product Delivery.3")
  local i target persona pane_id work_dir _esc_harness _esc_work
  _esc_harness=$(printf '%q' "$HARNESS_DIR")
  for i in 0 1 2 3; do
    target="${panes[$i]}"
    persona="${personas[$i]}"
    tmux display-message -p -t "$target" '#{pane_id}' >/dev/null 2>&1 || continue
    pane_id=$(tmux display-message -p -t "$target" '#{pane_id}' 2>/dev/null || true)
    work_dir=$(tmux display-message -p -t "$target" '#{pane_current_path}' 2>/dev/null || pwd)
    _esc_work=$(printf '%q' "$work_dir")
    tmux respawn-pane -k -t "$target" "$(pane_launch_prefix) TMUX_PANE=${pane_id} bash ${_esc_harness}/pane-launcher.sh ${persona} ${_esc_work}" 2>/dev/null || true
    sleep 0.3
  done
  # Fix C: each pane was just respawned into a fresh Claude, so drop any stale
  # pane-hygiene state (needs_respawn/dirty/cooling/cooldown) that would otherwise
  # strand the freshly-respawned pane from dispatch (the root of the operator-respawn
  # walls). The next dispatch boundary re-registers each pane clean.
  local _reg="$HARNESS_DIR/run/pane-hygiene.json" _pi
  for _pi in 0 1 2 3; do
    python3 "$HARNESS_DIR/lib/pane_role_pool.py" reset-hygiene --pane "$SESSION_NAME:0.${_pi}" --registry "$_reg" >/dev/null 2>&1 || true
  done
  configure_product_delivery_labels
}

configure_builder_lab_labels() {
  tmux_has_exact_session "$LAB_SESSION_NAME" || return 0
  configure_role_footer_style "$LAB_SESSION_NAME" "#f9e2af"
  tmux select-pane -t "$LAB_SESSION_NAME:Builder Lab.0" -T "$(pane_footer_label lab-builder "Builder 1" "lab-builder-1")" 2>/dev/null || true
  tmux select-pane -t "$LAB_SESSION_NAME:Builder Lab.1" -T "$(pane_footer_label lab-builder "Builder 2" "lab-builder-2")" 2>/dev/null || true
  tmux select-pane -t "$LAB_SESSION_NAME:Builder Lab.2" -T "$(pane_footer_label lab-builder "Builder 3" "lab-builder-3")" 2>/dev/null || true
  tmux select-pane -t "$LAB_SESSION_NAME:Builder Lab.3" -T "$(pane_footer_label lab-builder "Builder 4" "lab-builder-4")" 2>/dev/null || true
}

# ---- Bash 4+ 检测 ----

resolve_bash4() {
  local candidates=(
    /opt/homebrew/bin/bash
    /usr/local/bin/bash
    "$(command -v bash 2>/dev/null)"
  )
  for b in "${candidates[@]}"; do
    [[ -z "$b" || ! -x "$b" ]] && continue
    local major
    major=$("$b" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || echo 0)
    if [[ "$major" -ge 4 ]]; then
      echo "$b"
      return 0
    fi
  done
  return 1
}

# 缓存 bash4 路径 (启动时解析一次)
BASH4=""
_ensure_bash4() {
  [[ -n "$BASH4" ]] && return 0
  BASH4=$(resolve_bash4) || return 1
}

install_hint_for_required_dep() {
  case "$1" in
    bash4)
      printf '%s\n' "macOS: brew install bash; Ubuntu/Debian: sudo apt-get install bash"
      ;;
    python3)
      printf '%s\n' "macOS: brew install python; Ubuntu/Debian: sudo apt-get install python3"
      ;;
    tmux)
      printf '%s\n' "macOS: brew install tmux; Ubuntu/Debian: sudo apt-get install tmux"
      ;;
    claude)
      printf '%s\n' "Install the Claude Code CLI and confirm 'claude --version' works before launching panes"
      ;;
    codex)
      printf '%s\n' "Install the Codex CLI and confirm 'codex --version' works before launching panes"
      ;;
    jq)
      printf '%s\n' "macOS: brew install jq; Ubuntu/Debian: sudo apt-get install jq"
      ;;
    *)
      printf '%s\n' "Install '$1' and ensure it is on PATH"
      ;;
  esac
}

harness_launch_preflight() {
  local failed=0 bash4 cmd path runtime_path

  echo "Solar Harness launch preflight"
  echo "selected pane runtime: ${SOLAR_PANE_RUNTIME}"
  if bash4=$(resolve_bash4); then
    local bash_version
    bash_version=$("$bash4" --version 2>/dev/null | head -1 || printf 'bash version unknown')
    echo "required ok: bash>=4 path=${bash4} (${bash_version})"
  else
    echo "required fail: bash>=4 not found"
    echo "  install hint: $(install_hint_for_required_dep bash4)"
    failed=$((failed + 1))
  fi

  for cmd in python3 tmux jq; do
    if path=$(command -v "$cmd" 2>/dev/null); then
      echo "required ok: ${cmd} path=${path}"
    else
      echo "required fail: ${cmd} not found on PATH"
      echo "  install hint: $(install_hint_for_required_dep "$cmd")"
      failed=$((failed + 1))
    fi
  done

  if runtime_path=$(pane_runtime_cli_path); then
    echo "required ok: ${SOLAR_PANE_RUNTIME} path=${runtime_path}"
  else
    echo "required fail: ${SOLAR_PANE_RUNTIME} runtime CLI not found"
    echo "  install hint: $(install_hint_for_required_dep "$SOLAR_PANE_RUNTIME")"
    failed=$((failed + 1))
  fi

  if [[ -w "$HARNESS_DIR" ]]; then
    echo "required ok: harness dir writable (${HARNESS_DIR})"
  else
    echo "required fail: harness dir is not writable (${HARNESS_DIR})"
    echo "  install hint: fix ownership/permissions for ${HARNESS_DIR}; do not run Solar as root"
    failed=$((failed + 1))
  fi

  if (( failed == 0 )); then
    echo "manual-pending: live ${SOLAR_PANE_RUNTIME} pane behavior is not verified by preflight; after tmux opens, resolve any trust/auth/quota prompts."
    return 0
  fi

  echo "preflight failed: ${failed} required launch check(s) failed"
  return 1
}

# ---- Doctor 自检 ----

do_doctor() {
  local failed=0

  harness_launch_preflight || failed=$((failed + 1))

  # (a) bash 4+ 可用
  local bash4=""
  bash4=$(resolve_bash4) || {
    :
  }

  # (c) coordinator.sh bash -n 通过
  if [[ -n "$bash4" ]]; then
    "$bash4" -n "$HARNESS_DIR/coordinator.sh" 2>/dev/null || {
      echo "required fail: coordinator.sh syntax check failed"
      echo "  inspect: $bash4 -n $HARNESS_DIR/coordinator.sh"
      ((failed++))
    }
    "$bash4" -n "$HARNESS_DIR/lib/persona-config.sh" 2>/dev/null || {
      echo "required fail: persona-config.sh syntax check failed"
      echo "  inspect: $bash4 -n $HARNESS_DIR/lib/persona-config.sh"
      ((failed++))
    }
    if [[ -x "$HARNESS_DIR/test-gateway-compat.sh" ]]; then
      "$bash4" "$HARNESS_DIR/test-gateway-compat.sh" >/dev/null 2>&1 || {
        echo "required fail: third-party gateway compatibility check failed"
        echo "  inspect: $bash4 $HARNESS_DIR/test-gateway-compat.sh"
        ((failed++))
      }
    fi
  fi

  # (d) 关键目录可写
  [[ -w "$HARNESS_DIR" ]] || {
    echo "required fail: $HARNESS_DIR is not writable"
    ((failed++))
  }

  # (e) coordinator pidfile 进程活
  if [[ -f "$HARNESS_DIR/.coordinator.pid" ]]; then
    local cpid
    cpid=$(cat "$HARNESS_DIR/.coordinator.pid" 2>/dev/null)
    if [[ -n "$cpid" ]] && ! kill -0 "$cpid" 2>/dev/null; then
      echo "optional warning: coordinator pidfile points at a dead process (PID=$cpid); start will self-heal"
    fi
  fi

  # (f) coordinator.sh 语法已由 bash -n 覆盖。
  # 旧版曾用全文件双引号奇偶数做阻塞检查；它不理解 heredoc、Python
  # 三引号和跨行 dispatch 文本，会把合法脚本误判为坏脚本。

  # (g) qmd launcher Node ABI 风险可检测可修复
  if [[ -x "$HARNESS_DIR/lib/qmd-launcher-repair.sh" ]]; then
    local qmd_bin_check=""
    qmd_bin_check="$(env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/sbin:/sbin" QMD_BIN="${QMD_BIN:-}" bash "$HARNESS_DIR/lib/qmd-resolver.sh" --print 2>/dev/null || true)"
    if [[ -z "$qmd_bin_check" ]]; then
      echo "optional warning: qmd resolver stripped-PATH check found no qmd executable"
      echo "  install hint: install qmd/mineru-document-explorer or set QMD_BIN"
    fi
    local qmd_repair_out qmd_repair_rc
    qmd_repair_out="$("$HARNESS_DIR/lib/qmd-launcher-repair.sh" --check 2>&1)" || qmd_repair_rc=$?
    qmd_repair_rc="${qmd_repair_rc:-0}"
    if [[ "$qmd_repair_rc" == "2" ]]; then
      echo "optional warning: qmd launcher has Node ABI risk"
      echo "  repair: $0 wiki qmd-repair --apply"
    elif [[ "$qmd_repair_rc" != "0" ]]; then
      echo "optional warning: qmd launcher check failed: $qmd_repair_out"
    fi
  fi

  # (h) 所有 sprint 状态机合法
  for f in "$SPRINTS_DIR"/*.status.json; do
    [[ -f "$f" ]] || continue
    local st
    st=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    case "$st" in
      drafting|queued|active|planning|approved|reviewing|ready_for_review|failed_review|passed|done|failed|eval_pass|cancelled|interrupted|superseded|needs_human_review|blocked) ;;
      *)
        echo "optional warning: $(basename "$f") has nonstandard sprint status: $st"
        ;;
    esac
  done

  if (( failed == 0 )); then
    echo "Solar Harness doctor: required checks passed"
    echo "manual-pending: live ${SOLAR_PANE_RUNTIME} panes and real delegation are verified only after the selected runtime starts and responds in the tmux panes."
    return 0
  else
    echo "Solar Harness doctor: ${failed} required check group(s) failed"
    return 1
  fi
}

# ---- 同步启动 Coordinator ----

find_live_coordinator_pids() {
  ps ax -o pid= -o args= | awk -v script="$HARNESS_DIR/coordinator.sh" '
    $0 ~ "^[[:space:]]*[0-9]+[[:space:]]+([^[:space:]]*/)?bash[[:space:]]+" script "([[:space:]]|$)" { print $1 }
  '
}

find_live_watchdog_pids() {
  ps ax -o pid= -o args= | awk -v script="$HARNESS_DIR/coordinator-watchdog.sh" '
    $0 ~ "^[[:space:]]*[0-9]+[[:space:]]+([^[:space:]]*/)?bash[[:space:]]+" script "([[:space:]]|$)" { print $1 }
  '
}

terminate_harness_pid() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  kill "$pid" 2>/dev/null || true
  local waited=0
  while (( waited < 20 )); do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.1
    ((waited++))
  done
  kill -9 "$pid" 2>/dev/null || true
  return 0
}

stop_harness_background_processes() {
  local stopped=0 pidfile pid pids
  for pidfile in "$HARNESS_DIR/.coordinator.pid" "$HARNESS_DIR/.watchdog.pid"; do
    if [[ -f "$pidfile" ]]; then
      pid=$(cat "$pidfile" 2>/dev/null || true)
      if terminate_harness_pid "$pid"; then
        stopped=1
      fi
      rm -f "$pidfile"
    fi
  done
  pids="$(find_live_coordinator_pids; find_live_watchdog_pids)"
  for pid in $pids; do
    if terminate_harness_pid "$pid"; then
      stopped=1
    fi
  done
  [[ "$stopped" == "1" ]]
}

start_coordinator_sync() {
  _ensure_bash4 || { err "bash 4+ 不可用，无法启动 coordinator"; return 1; }

  local pidfile="$HARNESS_DIR/.coordinator.pid"

  # 已有活进程 → 跳过
  if [[ -f "$pidfile" ]]; then
    local existing_pid
    existing_pid=$(cat "$pidfile" 2>/dev/null)
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      ok "Coordinator 已在运行 (PID: $existing_pid)"
      # D7: doctor summary
      [[ "${SOLAR_SKIP_DOCTOR:-0}" == "1" ]] || bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null || true
      return 0
    fi
    # 死进程 → 清锁
    rm -f "$pidfile"
  fi

  # pidfile 缺失/过期时，先查真实进程，避免 launcher/watchdog 并发启动多个 coordinator。
  local real_pids real_pid
  real_pids=$(find_live_coordinator_pids || true)
  if [[ -n "$real_pids" ]]; then
    real_pid=$(echo "$real_pids" | head -1)
    echo "$real_pid" > "$pidfile"
    ok "Coordinator 已在运行，pidfile 已自愈 (PID: $real_pid)"
    [[ "${SOLAR_SKIP_DOCTOR:-0}" == "1" ]] || bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null || true
    return 0
  fi

  # A terminal marker denotes the PREVIOUS run's end; a new run birth must
  # clear it, or register() silently refuses the new daemons (|| true below)
  # and the watchdog exits on its first tick — an unsupervised harness with
  # unregistered daemons after every kill+start cycle.
  if [[ -f "$HARNESS_DIR/lib/run_process_registry.py" && -f "$HARNESS_DIR/run/process-registry/harness.terminal" ]]; then
    python3 "$HARNESS_DIR/lib/run_process_registry.py" clear-terminal --run-id harness >/dev/null 2>&1 || true
  fi

  # 启动 (setsid isolates from non-interactive launchers that reap process groups;
  # fallback keeps the installed/default behavior on platforms without setsid).
  if command -v setsid >/dev/null 2>&1; then
    setsid "$BASH4" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 </dev/null &
  else
    nohup "$BASH4" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 </dev/null &
    disown 2>/dev/null || true
  fi
  # Lane 0 fix (round-3 Finding C): register the spawned daemon so teardown can
  # reap it (AC-R7.4). Module-guarded; inert until Lane 0.5 merges.
  if [[ -f "$HARNESS_DIR/lib/run_process_registry.py" ]]; then
    python3 "$HARNESS_DIR/lib/run_process_registry.py" register --run-id harness --role coordinator --pid $! >/dev/null 2>&1 || true
  fi

  # 等待 pidfile 出现 (最多 3 秒)
  local waited=0
  while (( waited < 30 )); do
    if [[ -f "$pidfile" ]]; then
      local pid
      pid=$(cat "$pidfile" 2>/dev/null)
      if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        ok "Coordinator 启动成功 (PID: $pid)"
        # D7: doctor summary
        [[ "${SOLAR_SKIP_DOCTOR:-0}" == "1" ]] || bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null || true
        return 0
      fi
    fi
    sleep 0.1
    ((waited++))
  done

  err "Coordinator 启动失败: 3 秒内 pidfile 未出现"
  err "查看日志: cat $HARNESS_DIR/.coordinator.log"
  return 1
}

# ---- 同步启动 Watchdog ----

start_watchdog_sync() {
  _ensure_bash4 || { warn "bash 4+ 不可用，跳过 watchdog"; return 0; }

  local pidfile="$HARNESS_DIR/.watchdog.pid"

  if [[ -f "$pidfile" ]]; then
    local existing_pid
    existing_pid=$(cat "$pidfile" 2>/dev/null)
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      ok "Watchdog 已在运行 (PID: $existing_pid)"
      return 0
    fi
    rm -f "$pidfile"
  fi

  if command -v setsid >/dev/null 2>&1; then
    setsid "$BASH4" "$HARNESS_DIR/coordinator-watchdog.sh" start >> "$HARNESS_DIR/.watchdog.log" 2>&1 </dev/null &
  else
    nohup "$BASH4" "$HARNESS_DIR/coordinator-watchdog.sh" start >> "$HARNESS_DIR/.watchdog.log" 2>&1 </dev/null &
    disown 2>/dev/null || true
  fi
  # Lane 0 fix (round-3 Finding C): register the watchdog — teardown kills
  # watchdog-first, so this registration is what makes AC-R7.4 real.
  if [[ -f "$HARNESS_DIR/lib/run_process_registry.py" ]]; then
    python3 "$HARNESS_DIR/lib/run_process_registry.py" register --run-id harness --role watchdog --pid $! >/dev/null 2>&1 || true
  fi

  sleep 0.5
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    ok "Watchdog 启动成功 (PID: $(cat "$pidfile"))"
  else
    warn "Watchdog 启动未确认 (可能需要手动检查)"
  fi
  return 0
}

# ---- Start Harness ----

start_harness() {
  local mode="${1:-3}"
  local work_dir="${2:-$(pwd)}"
  local skip_doctor="${3:-}"
  [[ -d "$work_dir" ]] || { err "工作目录不存在: $work_dir"; return 1; }
  work_dir="$(cd "$work_dir" && pwd -P)"
  # G4-lite run-3 deviation: --skip-doctor skipped the PRE-start doctor but the
  # coordinator-start D7 summaries still ran doctor.sh — honor the skip there too.
  [[ "$skip_doctor" == "--skip-doctor" ]] && export SOLAR_SKIP_DOCTOR=1

  # Lane 0 fix (round-3 Finding B, HIGH): clear stale run-terminal markers from a
  # previous stop BEFORE the watchdog launches — otherwise the d5858918 respawn
  # gate reads last run's marker forever and the watchdog never respawns a
  # crashed coordinator again.
  rm -f "$HARNESS_DIR/run/process-registry"/*.terminal 2>/dev/null || true

  load_workdir_dotenv "$work_dir"

  # Fix 4: clean-start opt-in for an ALREADY-RUNNING cockpit (a fresh session always
  # resets). Triggered by SOLAR_HARNESS_CLEAN_START=1 or a --clean argument.
  local clean_start=0 _a
  [[ "${SOLAR_HARNESS_CLEAN_START:-0}" == "1" ]] && clean_start=1
  for _a in "$@"; do [[ "$_a" == "--clean" ]] && clean_start=1; done

  cleanup_legacy_sessions

  # 启动前自检 (除非 --skip-doctor)
  if [[ "$skip_doctor" != "--skip-doctor" ]]; then
    log "运行启动自检..."
    do_doctor || { err "启动前自检失败，修复后再试 (或用 --skip-doctor 跳过)"; exit 1; }
  else
    log "运行启动必需依赖预检..."
    harness_launch_preflight || { err "启动必需依赖缺失，拒绝创建部分 tmux session"; exit 1; }
  fi

  command -v tmux &>/dev/null || { err "tmux 未安装: brew install tmux"; exit 1; }
  pane_runtime_cli_path >/dev/null || { err "${SOLAR_PANE_RUNTIME} runtime CLI 未安装或不在 PATH"; exit 1; }

  if tmux_has_exact_session "$SESSION_NAME"; then
    # 安全优先: pane_current_command 经常是 bash/zsh，因为 Claude TUI 是子进程。
    # 旧逻辑只数 current_command=claude，容易把真实运行中的 session 误判为死
    # session 并 kill 掉用户现场。已有 session 一律复用/attach，不自动销毁。
    local panes_count
    panes_count="$(product_delivery_pane_count 2>/dev/null || printf '0')"
    if [[ "$panes_count" == "$EXPECTED_PRODUCT_DELIVERY_PANES" ]]; then
      ok "Solar Harness 已在运行 (${panes_count} panes)，直接接入"
    else
      warn "Solar Harness 已在运行，但 Product Delivery layout 异常 (${panes_count}/${EXPECTED_PRODUCT_DELIVERY_PANES} panes)"
    fi
    if tmux list-windows -t "$SESSION_NAME" -F '#{window_name}' 2>/dev/null | grep -qx "Product Delivery"; then
      tmux select-window -t "$SESSION_NAME:Product Delivery" 2>/dev/null || true
    fi
    warn_if_product_delivery_layout_incomplete || true
    configure_product_delivery_labels
    # Re-attaching must not silently rebind a live cockpit to a newly supplied
    # argument. Keep its durable binding; recover once from the PM pane only
    # for installs created before workspace binding existed.
    local bound_workspace pane_workspace
    bound_workspace="$(active_workspace_root 2>/dev/null || true)"
    if [[ -z "$bound_workspace" ]]; then
      pane_workspace="$(tmux display-message -p -t "$SESSION_NAME:Product Delivery.0" '#{pane_current_path}' 2>/dev/null || true)"
      [[ -n "$pane_workspace" ]] || pane_workspace="$work_dir"
      persist_workspace_root "$pane_workspace" "existing_cockpit_recovery" || {
        err "无法恢复现有 cockpit 的用户工作区绑定"
        return 1
      }
    fi
    if (( clean_start )); then
      reset_stale_runtime_state "already-running --clean"
    fi
    start_coordinator_sync || { err "Coordinator 启动失败，中止"; exit 1; }
    start_watchdog_sync
    attach_or_print
    return
  fi

  ensure_dirs
  persist_workspace_root "$work_dir" "harness_start" || {
    err "无法绑定用户工作区，拒绝启动"
    return 1
  }

  # Fix 4: a brand-new cockpit must start from clean coordination state (no in-flight
  # work exists yet), so stale latches/leases/assignments from a prior session can't wall it.
  reset_stale_runtime_state "fresh-session"

  log "启动 Solar Harness (${mode} 化身 + 监控)..."
  log "工作目录: ${work_dir}"

  # ================================================================
  # 四分屏布局 — Product Delivery (Window 0)
  #
  # ┌──────────────┬──────────────┐
  # │   产品经理    │   规划者      │
  # │   pm         │   planner    │
  # ├──────────────┼──────────────┤
  # │   建设者      │   审判官      │
  # │   builder    │   evaluator  │
  # └──────────────┴──────────────┘
  # ================================================================

  tmux new-session -d -s "$SESSION_NAME" -c "$work_dir"
  sanitize_tmux_claude_env "$SESSION_NAME"
  configure_tmux_pane_runtime_env "$SESSION_NAME"

  # D3: pane 保留现场 — 进程退出后 pane 不消失 (remain-on-exit)
  tmux set-option -t "$SESSION_NAME" remain-on-exit on

  # 创建4个 pane (tmux 会重编号！)
  # Step 1: 上下分 → 0(上) + 1(下)
  tmux split-window -v -t "$SESSION_NAME" -c "$work_dir"
  # Step 2: 上半左右分 → 0(左上) + 1(右上), 原1(下)变2
  tmux split-window -h -t "$SESSION_NAME:0.0" -c "$work_dir"
  # Step 3: 下半左右分 → 2(左下) + 3(右下)
  tmux split-window -h -t "$SESSION_NAME:0.2" -c "$work_dir"

  # Rename window 0
  tmux rename-window -t "$SESSION_NAME:0" "Product Delivery"

  # 最终编号: 0=左上 1=右上 2=左下 3=右下
  # 启动 pane-launcher (统一配置, 无交互阻塞)
  # D5 sprint-20260502-191700: printf '%q' 路径转义
  local _esc_harness _esc_work
  _esc_harness=$(printf '%q' "$HARNESS_DIR")
  _esc_work=$(printf '%q' "$work_dir")
  launch_persona_pane() {
    local target="$1" persona="$2"
    local pane_id
    pane_id=$(tmux display-message -p -t "$target" '#{pane_id}')
    tmux send-keys -t "$target" "$(pane_launch_prefix) TMUX_PANE=${pane_id} bash ${_esc_harness}/pane-launcher.sh ${persona} ${_esc_work}" Enter
  }
  if [[ "${SOLAR_PRODUCT_MODE:-0}" == "1" ]]; then
    # Product-mode pane gate (Lane 0, R8/AC-R8.1): persona pane DISPATCH is
    # disabled — the operator pool executes; panes remain viewers only. The
    # silent pane-fallback hang class (corpus F-044) is unreachable here.
    echo "[Harness] product mode: persona pane dispatch disabled (operator pool executes)"
  else
    sleep 1
    launch_persona_pane "$SESSION_NAME:Product Delivery.0" "pm"
    sleep 1
    launch_persona_pane "$SESSION_NAME:Product Delivery.1" "planner"
    if [[ "$mode" == "3" ]]; then
      sleep 1
      launch_persona_pane "$SESSION_NAME:Product Delivery.2" "builder"
      sleep 1
      launch_persona_pane "$SESSION_NAME:Product Delivery.3" "evaluator"
    else
      sleep 1
      launch_persona_pane "$SESSION_NAME:Product Delivery.2" "builder"
    fi
  fi

  # 设置活跃 pane 为 PM (非监控)
  tmux select-pane -t "$SESSION_NAME:Product Delivery.0"

  # 开启鼠标支持 (点击切换 pane)
  tmux set-option -t "$SESSION_NAME" mouse on

  # tmux 样式
  tmux set-option -t "$SESSION_NAME" status-style "bg=#1a1a2e,fg=#cdd6f4"
  tmux set-option -t "$SESSION_NAME" pane-border-style "fg=#45475a"
  tmux set-option -t "$SESSION_NAME" pane-active-border-style "fg=#89b4fa"
  tmux set-option -t "$SESSION_NAME" status-right-length 60
  tmux set-option -t "$SESSION_NAME" status-right "#[fg=#89b4fa]Solar Harness #[fg=#a6e3a1]${mode}化身+并行 #[default]%H:%M"
  configure_product_delivery_labels

  # 打印帮助 (attach 前输出到 stdout)
  echo ""
  ok "══════════════════════════════════════════════════"
  ok "  Solar Harness 启动完成!"
  echo ""
  if [[ "$mode" == "3" ]]; then
    echo "  布局 (四分屏同时可见):"
    echo ""
    echo "  ┌──────────────┬──────────────┐"
    echo "  │   产品经理    │   规划者      │"
    echo "  │   pm         │   planner    │"
    echo "  ├──────────────┼──────────────┤"
    echo "  │   建设者      │   审判官      │"
    echo "  │   builder    │   evaluator  │"
    echo "  └──────────────┴──────────────┘"
  else
    echo "  布局 (三分屏):"
    echo ""
    echo "  ┌──────────────┬──────────────┐"
    echo "  │   产品经理    │   规划者      │"
    echo "  │   pm         │   planner    │"
    echo "  ├──────────────┴──────────────┤"
    echo "  │         建设者 builder       │"
    echo "  └─────────────────────────────┘"
  fi
  echo ""
  log "tmux 快捷键:"
  echo "  切 pane:   Ctrl+B → 方向键"
  echo "  全屏当前:  Ctrl+B → z (再按一次恢复)"
  echo "  后台运行:  Ctrl+B → d"
  echo "  重新接入:  tmux attach -t $SESSION_NAME"
  echo ""
  log "使用方法:"
  echo "  1. 切到化身 pane (Ctrl+B → 方向键 / 鼠标点击)"
  echo "  2. 按 Enter 启动该化身的 ${PANE_RUNTIME_LABEL}"
  echo "  3. 处理 ${PANE_RUNTIME_LABEL} 的确认提示 (信任文件夹等)"
  echo ""

  # ── 同步拉 Coordinator + Watchdog (SIGHUP 隔离) ──
  start_coordinator_sync || { err "Coordinator 启动失败，中止"; exit 1; }
  start_watchdog_sync

  attach_or_print
}

# ---- Status ----

show_status() {
  cleanup_legacy_sessions
  echo ""
  if tmux_has_exact_session "$SESSION_NAME"; then
    ok "Solar Harness Product Delivery 运行中 ($SESSION_NAME)"
    echo ""
    tmux list-windows -t "$SESSION_NAME" 2>/dev/null | sed 's/^/  /'
    echo ""
    if tmux_has_exact_session "$LAB_SESSION_NAME"; then
      ok "Solar Harness Parallel Builder Lab 运行中 ($LAB_SESSION_NAME)"
      echo ""
      tmux list-windows -t "$LAB_SESSION_NAME" 2>/dev/null | sed 's/^/  /'
      echo ""
    fi
    local cnt
    cnt=$(ls "$SPRINTS_DIR"/*.status.json 2>/dev/null | wc -l | tr -d ' ')
    log "Sprints: ${cnt}"
    for f in "$SPRINTS_DIR"/*.status.json; do
      [[ -f "$f" ]] || continue
      local sid st stitle
      sid=$(python3 -c "import json; print(json.load(open('$f')).get('id','?'))" 2>/dev/null)
      st=$(python3 -c  "import json; print(json.load(open('$f')).get('status','?'))" 2>/dev/null)
      stitle=$(python3 -c "import json; print(json.load(open('$f')).get('title',''))" 2>/dev/null)
      if [[ -n "$stitle" ]]; then
        echo -e "  ${G}${stitle}${N} — ${st} (${sid})"
      else
        echo -e "  ${G}${sid}${N} — ${st}"
      fi
    done
  else
    if tmux_has_exact_session "$LAB_SESSION_NAME"; then
      ok "Solar Harness Parallel Builder Lab 运行中 ($LAB_SESSION_NAME)"
      echo ""
      tmux list-windows -t "$LAB_SESSION_NAME" 2>/dev/null | sed 's/^/  /'
    else
      warn "Solar Harness 未运行"
      log "启动: $0 [工作目录]"
    fi
  fi
  echo ""
  bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null || true
}

# ---- Kill ----

reap_managed_codex_trust_profiles() {
  local helper="$HARNESS_DIR/lib/codex_trust_profiles.py"
  local registry="$HARNESS_DIR/run/codex-trust-profiles"
  local session owner_id result failed=0
  [[ -f "$helper" && -d "$registry" ]] || return 0
  while (( $# >= 2 )); do
    session="$1"
    owner_id="$2"
    shift 2
    local -a args=(reap --harness-dir "$HARNESS_DIR" --session "$session")
    [[ -n "$owner_id" ]] && args+=(--owner-id "$owner_id")
    if ! result="$(python3 "$helper" "${args[@]}" 2>&1)"; then
      warn "Codex trust profile cleanup was incomplete for session '$session': $result"
      failed=1
    fi
  done
  [[ "$failed" == "0" ]]
}

managed_codex_trust_owner_id() {
  local session="$1"
  tmux display-message -p -t "$session" '#{socket_path}|#{session_id}|#{session_name}' 2>/dev/null || true
}

kill_harness() {
  cleanup_legacy_sessions
  local killed=0 cleanup_failed=0
  local session_owner_id lab_owner_id
  session_owner_id="$(managed_codex_trust_owner_id "$SESSION_NAME")"
  lab_owner_id="$(managed_codex_trust_owner_id "$LAB_SESSION_NAME")"
  # G3 zombie-factory fix: the registry teardown (write the run-terminal
  # marker, reap registered daemons watchdog-first) must run on EVERY kill,
  # not only when the tmux session still exists — e2e cleanups kill sessions
  # directly, and completed sandboxes whose kill skipped this left
  # marker-less watchdogs respawning harness startup for 30+ hours.
  if [[ -f "$HARNESS_DIR/lib/run_process_registry.py" ]]; then
    python3 "$HARNESS_DIR/lib/run_process_registry.py" teardown --run-id harness --grace 5 >/dev/null 2>&1 || true
  fi
  if tmux_has_exact_session "$SESSION_NAME"; then
    log "关闭..."
    # Mark active sprints as interrupted
    for f in "$SPRINTS_DIR"/*.status.json; do
      [[ -f "$f" ]] || continue
      python3 - "$f" "$HARNESS_DIR/lib/runtime_status.py" <<'PY' 2>/dev/null || true
import json, subprocess, sys
status_path, runtime_status = sys.argv[1:]
with open(status_path, encoding="utf-8") as fh:
    data = json.load(fh)
if data.get("status") in ("active", "reviewing"):
    subprocess.run(
        ["python3", runtime_status, status_path, "interrupted", "harness_killed", "solar-harness", "{}"],
        check=False,
    )
PY
    done
    # Registry teardown already ran unconditionally above (Lane 0 PR-3 /
    # F4 / AC-R7.4 semantics preserved: marker + watchdog-first reap happen
    # BEFORE the session dies).
    tmux kill-session -t "$SESSION_NAME"
    killed=1
  fi
  if tmux_has_exact_session "$LAB_SESSION_NAME"; then
    tmux kill-session -t "$LAB_SESSION_NAME"
    killed=1
  fi
  if stop_harness_background_processes; then
    killed=1
  fi
  # A pane-local EXIT trap is the normal cleanup path, but tmux teardown can
  # hard-kill a launcher before that trap runs. Reap only registry-owned
  # profiles for these exact product sessions; foreign Codex config is never
  # scanned or removed.
  if ! reap_managed_codex_trust_profiles \
    "$SESSION_NAME" "$session_owner_id" \
    "$LAB_SESSION_NAME" "$lab_owner_id"; then
    warn "One or more managed Codex trust profiles require manual inspection"
    cleanup_failed=1
  fi
  if (( killed == 1 )); then
    ok "已关闭"
  else
    warn "未运行"
  fi
  return "$cleanup_failed"
}

pane_process_persona_simple() {
  local target="$1"
  local pane_pid
  pane_pid=$(tmux display-message -p -t "$target" '#{pane_pid}' 2>/dev/null || true)
  [[ -n "$pane_pid" ]] || return 1

  local queue="$pane_pid" visited=""
  while [[ -n "$queue" ]]; do
    local next_queue=""
    local pid
    for pid in $queue; do
      case " $visited " in *" $pid "*) continue ;; esac
      visited="$visited $pid"

      local args
      args=$(ps -p "$pid" -o args= 2>/dev/null || true)
      if [[ "$args" =~ start-(incarnation|launcher)\.sh[[:space:]]+([A-Za-z0-9_-]+) ]]; then
        echo "${BASH_REMATCH[2]}"
        return 0
      fi

      local children
      children=$(pgrep -P "$pid" 2>/dev/null || true)
      [[ -n "$children" ]] && next_queue="$next_queue $children"
    done
    queue="$next_queue"
  done
  return 1
}

detect_pane_by_persona_simple() {
  local session="$1" window="$2" persona="$3" fallback="$4"
  tmux_has_exact_session "$session" || { echo "$fallback"; return 0; }
  local idx target proc_persona content
  while IFS= read -r idx; do
    [[ -z "$idx" ]] && continue
    target="${session}:${window}.${idx}"
    proc_persona=$(pane_process_persona_simple "$target" 2>/dev/null || true)
    if [[ "$proc_persona" == "$persona" ]]; then
      echo "$target"
      return 0
    fi
    content=$(tmux capture-pane -t "$target" -p -S -80 2>/dev/null | tail -80 || true)
    if printf '%s\n' "$content" | grep -qE "Persona:[[:space:]]*${persona}([[:space:]]|$)"; then
      echo "$target"
      return 0
    fi
  done < <(tmux list-panes -t "${session}:${window}" -F '#{pane_index}' 2>/dev/null || true)
  echo "$fallback"
}

write_parallel_lab_state() {
  local work_dir="$1"
  local model_matrix
  model_matrix="$(solar_lab_builder_matrix)"
  mkdir -p "$HARNESS_DIR/state"
  {
    printf "WORK_DIR='%s'\n" "$work_dir"
    printf "LAB_SESSION='%s'\n" "$LAB_SESSION_NAME"
    printf "LAB_MODEL_MATRIX='%s'\n" "$model_matrix"
    printf "UPDATED_AT='%s'\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$HARNESS_DIR/state/parallel-builder-lab.env"
}

ensure_parallel_builder_lab() {
  local work_dir="${1:-$(pwd)}"
  tmux_has_exact_session "$LAB_SESSION_NAME" || return 0
  local state_file="$HARNESS_DIR/state/parallel-builder-lab.env"
  local desired_matrix matrix_label
  desired_matrix="$(solar_lab_builder_matrix)"
  matrix_label="$(solar_lab_builder_matrix_label "$desired_matrix")"
  local current_matrix=""
  if [[ -f "$state_file" ]]; then
    current_matrix=$(grep '^LAB_MODEL_MATRIX=' "$state_file" 2>/dev/null | sed "s/^LAB_MODEL_MATRIX='//;s/'$//" || true)
  fi
  local rebuild_for_model_matrix=0
  if [[ "$current_matrix" != "$desired_matrix" ]]; then
    rebuild_for_model_matrix=1
    warn "Parallel Builder Lab 模型矩阵变化: ${current_matrix:-N/A} -> ${desired_matrix}; 将 respawn 四个 builder"
  fi
  write_parallel_lab_state "$work_dir"

  tmux rename-window -t "$LAB_SESSION_NAME:0" "Builder Lab" 2>/dev/null || true
  tmux set-option -t "$LAB_SESSION_NAME" status-right "#[fg=#f9e2af]Solar Builder Lab #[fg=#a6e3a1]${matrix_label} #[default]%H:%M" 2>/dev/null || true
  configure_tmux_pane_runtime_env "$LAB_SESSION_NAME"
  configure_builder_lab_labels

  local pane_count
  pane_count=$(tmux list-panes -t "$LAB_SESSION_NAME:0" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$pane_count" != "4" ]]; then
    warn "Parallel Builder Lab 需要 4 个 pane，当前为 ${pane_count}；请重建 lab session"
    return 0
  fi

  local _esc_harness _esc_work i target pane_id slot content
  _esc_harness=$(printf '%q' "$HARNESS_DIR")
  _esc_work=$(printf '%q' "$work_dir")
  for i in 0 1 2 3; do
    target="$LAB_SESSION_NAME:0.$i"
    slot="lab-builder-$((i + 1))"
    content=$(tmux capture-pane -t "$target" -p -S -80 2>/dev/null | tail -80 || true)
    current_cmd=$(tmux display-message -p -t "$target" '#{pane_current_command}' 2>/dev/null || echo "")
    if (( rebuild_for_model_matrix == 0 )) \
      && [[ ! "$current_cmd" =~ ^(bash|zsh|sh|fish)$ ]] \
      && printf '%s\n' "$content" | grep -qE "Persona:[[:space:]]*lab-builder([[:space:]]|$)"; then
      continue
    fi
    pane_id=$(tmux display-message -p -t "$target" '#{pane_id}')
    tmux respawn-pane -k -t "$target" "$(pane_launch_prefix) TMUX_PANE=${pane_id} SOLAR_BUILDER_SLOT=${slot} SOLAR_LAB_BUILDER_MODEL_MATRIX=${desired_matrix} bash ${_esc_harness}/pane-launcher.sh lab-builder ${_esc_work}"
  done
  configure_builder_lab_labels
}

# ---- Extend: 启动独立第二四分屏 (Parallel Builder Lab) ----

start_extension() {
  local work_dir="${1:-$(pwd)}"
  local model_matrix matrix_label
  model_matrix="$(solar_lab_builder_matrix)"
  matrix_label="$(solar_lab_builder_matrix_label "$model_matrix")"

  cleanup_legacy_sessions
  write_parallel_lab_state "$work_dir"

  # 第二屏必须是独立 session。不要做成同一 session 的 window，否则两个终端
  # attach 同一 session 时会互相切 window，看起来像镜像。
  if tmux_has_exact_session "$LAB_SESSION_NAME"; then
    ensure_parallel_builder_lab "$work_dir"
    ok "Parallel Builder Lab 已在独立 session 运行 ($LAB_SESSION_NAME)"
    attach_or_print "$LAB_SESSION_NAME"
    return
  fi

  log "启动独立 Parallel Builder Lab 四分屏..."
  log "session: $LAB_SESSION_NAME"
  log "工作目录: ${work_dir}"

  tmux new-session -d -s "$LAB_SESSION_NAME" -n "Builder Lab" -c "$work_dir"
  sanitize_tmux_claude_env "$LAB_SESSION_NAME"
  configure_tmux_pane_runtime_env "$LAB_SESSION_NAME"
  tmux set-option -t "$LAB_SESSION_NAME" remain-on-exit on

  # Split into 4 panes (same layout as window 0)
  tmux split-window -v -t "$LAB_SESSION_NAME:Builder Lab" -c "$work_dir"
  tmux split-window -h -t "$LAB_SESSION_NAME:Builder Lab.0" -c "$work_dir"
  tmux split-window -h -t "$LAB_SESSION_NAME:Builder Lab.2" -c "$work_dir"

  # Launch four isolated builders. SOLAR_BUILDER_SLOT gives each pane its own
  # git worktree under .worktrees/, so parallel work does not collide.
  local _esc_harness _esc_work
  _esc_harness=$(printf '%q' "$HARNESS_DIR")
  _esc_work=$(printf '%q' "$work_dir")
  launch_persona_pane() {
    local target="$1" persona="$2" slot="$3"
    local pane_id
    pane_id=$(tmux display-message -p -t "$target" '#{pane_id}')
    tmux send-keys -t "$target" "$(pane_launch_prefix) TMUX_PANE=${pane_id} SOLAR_BUILDER_SLOT=${slot} SOLAR_LAB_BUILDER_MODEL_MATRIX=${model_matrix} bash ${_esc_harness}/pane-launcher.sh ${persona} ${_esc_work}" Enter
  }
  sleep 1
  launch_persona_pane "$LAB_SESSION_NAME:Builder Lab.0" "lab-builder" "lab-builder-1"
  sleep 1
  launch_persona_pane "$LAB_SESSION_NAME:Builder Lab.1" "lab-builder" "lab-builder-2"
  sleep 1
  launch_persona_pane "$LAB_SESSION_NAME:Builder Lab.2" "lab-builder" "lab-builder-3"
  sleep 1
  launch_persona_pane "$LAB_SESSION_NAME:Builder Lab.3" "lab-builder" "lab-builder-4"

  tmux select-pane -t "$LAB_SESSION_NAME:Builder Lab.0"
  tmux set-option -t "$LAB_SESSION_NAME" mouse on
  tmux set-option -t "$LAB_SESSION_NAME" status-style "bg=#1a1a2e,fg=#cdd6f4"
  tmux set-option -t "$LAB_SESSION_NAME" pane-border-style "fg=#45475a"
  tmux set-option -t "$LAB_SESSION_NAME" pane-active-border-style "fg=#f9e2af"
  tmux set-option -t "$LAB_SESSION_NAME" status-right-length 60
  tmux set-option -t "$LAB_SESSION_NAME" status-right "#[fg=#f9e2af]Solar Builder Lab #[fg=#a6e3a1]${matrix_label} #[default]%H:%M"
  configure_builder_lab_labels

  ok "Parallel Builder Lab 四分屏已启动"
  echo ""
  echo "  ┌──────────────┬──────────────┐"
  echo "  │  Builder 1   │  Builder 2   │"
  printf "  │ %-12s │ %-12s │\n" \
    "$(solar_lab_builder_matrix_item_label "$model_matrix" 0)" \
    "$(solar_lab_builder_matrix_item_label "$model_matrix" 1)"
  echo "  ├──────────────┼──────────────┤"
  echo "  │  Builder 3   │  Builder 4   │"
  printf "  │ %-12s │ %-12s │\n" \
    "$(solar_lab_builder_matrix_item_label "$model_matrix" 2)" \
    "$(solar_lab_builder_matrix_item_label "$model_matrix" 3)"
  echo "  └──────────────┴──────────────┘"
  echo ""
  echo "  重新接入:  tmux attach -t $LAB_SESSION_NAME"
  echo ""
  attach_or_print "$LAB_SESSION_NAME"
}

# ---- New Sprint ----

should_epic_decompose_request() {
  local req="$1"
  # Workflow-contract router stub (Lane 0): a matched workflow contract bypasses
  # epic decomposition entirely (R1). Inert unless the flag is on AND the Lane 1
  # module exists — flag-off behavior is bit-identical.
  if [[ "${SOLAR_WORKFLOW_ROUTER:-0}" == "1" && -f "$HARNESS_DIR/lib/workflow_router.py" ]]; then
    if python3 "$HARNESS_DIR/lib/workflow_router.py" match --request "$req" >/dev/null 2>&1; then
      return 1
    fi
  fi
  [[ "${SOLAR_EPIC_AUTO_DECOMPOSE:-1}" == "0" ]] && return 1
  local min_chars="${SOLAR_EPIC_MIN_CHARS:-420}"
  local min_lines="${SOLAR_EPIC_MIN_LINES:-4}"
  local min_signals="${SOLAR_EPIC_MIN_SIGNALS:-3}"
  local chars lines signals large_shape explicit_decomposition broad_scope
  chars=$(printf "%s" "$req" | wc -m | tr -d ' ')
  lines=$(printf "%s" "$req" | awk 'END{print NR}')
  large_shape=0
  if (( chars >= min_chars || lines >= min_lines )); then
    large_shape=1
  fi

  # Length describes request detail, not work topology. A long, precise request
  # for one CLI/file must remain one sprint. Automatic Epic routing therefore
  # also requires evidence of explicit decomposition or genuinely broad system
  # scope. This avoids the rc.9 live failure where a bounded line_stats.py task
  # became five unrelated child sprints solely because it exceeded 420 chars.
  signals=0
  explicit_decomposition=0
  broad_scope=0
  printf "%s" "$req" | grep -Eiq 'PRDs?|requirements?|contracts?|documentation|README|需求|合约|文档' \
    && signals=$((signals + 1))
  printf "%s" "$req" | grep -Eiq '架构|设计|方案|规划|路线图|architecture|architectural|design|roadmap|technical plan' \
    && signals=$((signals + 1))
  if printf "%s" "$req" | grep -Eiq '任务图|(^|[^[:alnum:]_])DAG([^[:alnum:]_]|$)|拆分|依赖图|依赖关系|并行调度|多.*PRD|一系列|split .*into|split (the )?(work|request|project)|dependency (DAG|graph|order)|parallel (work|execution|implementation)|workstreams?|orchestrat(e|ion)|multi[- ](stage|component|service|workstream)|multiple (PRDs?|workstreams?|components?|services?|subsystems?)'; then
    signals=$((signals + 1))
    explicit_decomposition=1
  fi
  printf "%s" "$req" | grep -Eiq '开发|实现|重构|改造|集成|优化|修复|implement|build|develop|refactor|integrat(e|ion)|optimi[sz]e|fix' \
    && signals=$((signals + 1))
  printf "%s" "$req" | grep -Eiq '验证|测试|回归|验收|证明|闭环|端到端|verify|verification|validat(e|ion)|tests?|pytest|regression|acceptance|end[- ]to[- ]end|evidence' \
    && signals=$((signals + 1))
  printf "%s" "$req" | grep -Eiq '自动|默认|持续|不要.*问|做完|搞定|防.*半截|半截|automat(e|ic|ion)|continuous|without (manual|asking)|close the parent' \
    && signals=$((signals + 1))
  if printf "%s" "$req" | grep -Eiq '多个(组件|系统|服务|工作流|子系统|PRD)|全量|全面|系统|框架|平台|产品化|entire (system|platform|product|stack)|whole (system|platform|product|stack)|platform-wide|framework|producti[sz]ation|multiple (components?|services?|workstreams?|PRDs?|subsystems?|applications?|packages?)|cross[- ](component|service|system|platform)|across (the )?.*(subsystems?|services?|components?)'; then
    signals=$((signals + 1))
    broad_scope=1
  fi

  if (( explicit_decomposition == 1 && signals >= 2 )); then
    return 0
  fi
  if (( broad_scope == 1 && large_shape == 1 && signals >= min_signals )); then
    return 0
  fi
  return 1
}

new_epic_from_request() {
  local req="$1"
  ensure_dirs
  local title tmp out rc
  tmp=$(mktemp "${TMPDIR:-/tmp}/solar-epic-request.XXXXXX")
  printf "%s\n" "$req" > "$tmp"
  title=$(python3 - "$tmp" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines()
title = ""

if lines and lines[0].strip() == "---":
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"\s*title\s*:\s*(.+?)\s*$", line)
        if match:
            title = match.group(1).strip().strip('"').strip("'")
            break

if not title:
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_frontmatter:
            if index > 0 and stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break
        if stripped:
            title = stripped
            break

title = title[:60].strip()
if not title:
    title = "Untitled Epic"
if title.startswith("-"):
    title = "Request " + title.lstrip("- ").strip()
print(title or "Untitled Epic")
PY
)
  set +e
  out=$(python3 "$HARNESS_DIR/lib/epic_decomposer.py" create \
    --title "$title" \
    --request-file "$tmp" \
    --priority "${SOLAR_EPIC_PRIORITY:-P0}" \
    --activate-ready \
    --json 2>&1)
  rc=$?
  set -e
  rm -f "$tmp"
  if [[ "$rc" != "0" ]]; then
    err "Epic 分解失败，拒绝退回单 sprint 吞复杂需求"
    echo "$out"
    return "$rc"
  fi
  ok "Requirement decomposed into Epic"
  echo "$out"
  if command -v jq >/dev/null 2>&1; then
    log "Epic: $(printf "%s" "$out" | jq -r '.epic_id')"
    log "Root child: $(printf "%s" "$out" | jq -r '.children[] | select(.active==true) | .sid' | head -1)"
  fi
  log "Next: autopilot activates child sprints by dependency; each child still goes PM/Planner/DAG/Builder/Evaluator."
}

write_intake_raw_record() {
  local req="$1"
  local result="$2"
  local ts raw_dir raw_file
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  raw_dir="${SOLAR_KNOWLEDGE_RAW_DIR:-$HOME/Knowledge/_raw/solar-harness/intake}"
  mkdir -p "$raw_dir" 2>/dev/null || return 0
  raw_file="$raw_dir/intake-${ts}.md"
  cat > "$raw_file" <<EOF
# Solar-Harness Intake Record

created_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
source: solar-harness intake

## User Request

${req}

## Intake Result

\`\`\`text
${result}
\`\`\`

## Runtime Rule

User requests must enter PM requirements analysis first, then Planner
architecture/design/plan/task_graph, then DAG builder dispatch and evaluator
closeout. Do not send a large raw request directly to a builder pane.
EOF
  echo "$raw_file"
}

intake_request() {
  # Lane 0 PR-3 (F4): fail-closed preflight in product mode (R5/R7/R8 — routes,
  # auth presence, capacity, path self-consistency). Module-guarded, inert until
  # Lane 0.5 merges; flag-off behavior unchanged.
  if [[ "${SOLAR_PRODUCT_MODE:-0}" == "1" && -f "$HARNESS_DIR/lib/run_preflight.py" ]]; then
    local _pf_sid="preflight-$(date +%Y%m%d-%H%M%S)"
    if ! python3 "$HARNESS_DIR/lib/run_preflight.py" --sid "$_pf_sid"; then
      err "preflight failed — run blocked (report: sprints/${_pf_sid}.preflight.json)"
      return 1
    fi
  fi
  local req="" file="" use_stdin=0 dispatch=1 json=0 arg
  local -a parts=()
  while (($#)); do
    arg="$1"
    case "$arg" in
      --stdin)
        use_stdin=1
        ;;
      --file)
        shift || { err "intake --file 需要路径"; return 1; }
        file="$1"
        ;;
      --request)
        shift || { err "intake --request 需要文本"; return 1; }
        parts+=("$1")
        ;;
      --no-dispatch)
        dispatch=0
        ;;
      --json)
        json=1
        ;;
      --help|-h)
        echo "用法:"
        echo "  $0 intake \"需求\""
        echo "  $0 intake --file request.md [--no-dispatch]"
        echo "  echo \"需求\" | $0 intake --stdin"
        echo ""
        echo "行为: 创建 sprint/epic，写 Knowledge/_raw intake 记录，并默认触发一次 autopilot dispatch。"
        return 0
        ;;
      *)
        parts+=("$arg")
        ;;
    esac
    shift || true
  done

  if [[ -n "$file" ]]; then
    [[ -f "$file" ]] || { err "intake file not found: $file"; return 1; }
    req+=$(cat "$file")
  fi
  if [[ "$use_stdin" == "1" ]]; then
    [[ -n "$req" ]] && req+=$'\n'
    req+=$(cat)
  fi
  if ((${#parts[@]})); then
    [[ -n "$req" ]] && req+=$'\n'
    req+="${parts[*]}"
  fi
  req="$(printf '%s' "$req" | sed 's/[[:space:]]*$//')"
  [[ -n "$req" ]] || { err "intake 需要需求文本"; return 1; }

  ensure_dirs
  local intake_workspace_root
  intake_workspace_root="$(resolve_intake_workspace_root)" || return 1
  persist_workspace_root "$intake_workspace_root" "intake" || {
    err "无法绑定 intake 用户工作区"
    return 1
  }

  # P2 contracted intake (design §0): an explicit workflow_id routes through the
  # contract compiler — fail-closed, never a silent fall-through to the generic
  # planner path (smoke 20260707T180639Z ran a 5-node planner DAG because this
  # seam did not exist and code.cli_smoke's trigger is explicit-workflow_id-only).
  if [[ "${SOLAR_INTAKE_COMPAT_MODE:-}" == "legacy" && -n "${SOLAR_INTAKE_WORKFLOW_ID:-}" && "${SOLAR_INTAKE_WORKFLOW_ID}" != "research.evidence_to_poc.v1" ]]; then
    if [[ "${SOLAR_WORKFLOW_ROUTER:-0}" != "1" || ! -f "$HARNESS_DIR/lib/workflow_intake.py" ]]; then
      err "SOLAR_INTAKE_WORKFLOW_ID is set but the workflow router is unavailable (need SOLAR_WORKFLOW_ROUTER=1 and lib/workflow_intake.py) — refusing generic fallback"
      return 1
    fi
    local wf_out wf_rc
    set +e
    wf_out=$(python3 "$HARNESS_DIR/lib/workflow_intake.py" \
      --workflow-id "$SOLAR_INTAKE_WORKFLOW_ID" \
      --request "$req" \
      --workspace-root "${SOLAR_INTAKE_WORKSPACE_ROOT:-$intake_workspace_root}" 2>&1)
    wf_rc=$?
    set -e
    if [[ "$wf_rc" != "0" ]]; then
      err "contract intake failed (rc=$wf_rc): $wf_out"
      return 1
    fi
    printf '%s\n' "$wf_out"
    return 0
  fi
  local out rc raw_file autopilot_out autopilot_rc intent_out intent_rc intent_id intent_lane intent_readiness_status sid_from_out consumer_out consumer_rc consumer_status planner_handoff_status planner_handoff_mode fixed_route planner_selected_workflow
  intent_out=""
  intent_rc=0
  intent_id=""
  intent_lane=""
  intent_readiness_status=""
  fixed_route=0
  planner_selected_workflow="${SOLAR_PLANNER_SELECTED_WORKFLOW_ID:-}"
  consumer_out=""
  consumer_rc=0
  consumer_status=""
  planner_handoff_status=""
  planner_handoff_mode=""
  if [[ -f "$HARNESS_DIR/lib/intent_gateway.py" ]]; then
    set +e
    intent_out=$(SOLAR_HARNESS_SPRINTS_DIR="$SPRINTS_DIR" python3 "$HARNESS_DIR/lib/intent_gateway.py" capture \
      --source-channel "${SOLAR_INTENT_SOURCE_CHANNEL:-cli_intake}" \
      --actor "${SOLAR_INTENT_ACTOR:-user}" \
      --device "${SOLAR_INTENT_DEVICE:-}" \
      --repo "$intake_workspace_root" \
      --cwd "$intake_workspace_root" \
      --text "$req" \
      --json 2>&1)
    intent_rc=$?
    set -e
    if [[ "$intent_rc" == "0" ]]; then
      intent_id=$(python3 -c 'import json,sys; print((json.loads(sys.stdin.read()).get("intent_id") or ""))' <<<"$intent_out" 2>/dev/null || true)
      intent_lane=$(python3 -c 'import json,sys; print((json.loads(sys.stdin.read()).get("lane") or ""))' <<<"$intent_out" 2>/dev/null || true)
      intent_readiness_status=$(python3 -c 'import json,sys; print((json.loads(sys.stdin.read()).get("readiness_status") or ""))' <<<"$intent_out" 2>/dev/null || true)
    fi
  fi
  if [[ "$intent_rc" == "0" && -n "$intent_id" && "$intent_readiness_status" =~ ^(needs_clarification|failed)$ ]]; then
    printf '%s\n' "$intent_out"
    return 3
  fi
  if [[ -n "$planner_selected_workflow" && "$planner_selected_workflow" != "research.evidence_to_poc.v1" ]]; then
    err "unsupported planner-selected workflow: $planner_selected_workflow"
    return 2
  fi
  if [[ "$planner_selected_workflow" == "research.evidence_to_poc.v1" && "$intent_lane" != "research" ]]; then
    err "planner selected the research template but Requirement IR lane was ${intent_lane:-unavailable}"
    return 2
  fi
  # Requirement compilation may expose this registered workflow as a memoized
  # TaskGraph candidate, but only the elastic planner may select it. A research
  # lane by itself must continue into the normal Planner handoff.
  if [[ "${SOLAR_INTAKE_COMPAT_MODE:-}" == "legacy" && "$intent_rc" == "0" && -n "$intent_id" && "$intent_lane" == "research" && "$planner_selected_workflow" == "research.evidence_to_poc.v1" ]]; then
    local fixed_args fixed_out fixed_rc fixed_sid fixed_execution_profile fixed_acquisition_mode
    fixed_execution_profile="${SOLAR_RESEARCH_EXECUTION_PROFILE:-part_a_only}"
    fixed_acquisition_mode="${SOLAR_RESEARCH_ACQUISITION_MODE:-source_pack}"
    case "$fixed_execution_profile" in
      part_a_only|part_a_plus_poc) ;;
      *)
        err "fixed research intake rejected invalid SOLAR_RESEARCH_EXECUTION_PROFILE=$fixed_execution_profile"
        return 2
        ;;
    esac
    case "$fixed_acquisition_mode" in
      source_pack|live_search|hybrid) ;;
      *)
        err "fixed research intake rejected invalid SOLAR_RESEARCH_ACQUISITION_MODE=$fixed_acquisition_mode"
        return 2
        ;;
    esac
    fixed_args=(
      --workflow-id research.evidence_to_poc.v1
      --request "$req"
      --workspace-root "$intake_workspace_root"
      --sprints-dir "$SPRINTS_DIR"
      --intent-id "$intent_id"
      --input "execution_profile=${fixed_execution_profile}"
      --input "acquisition_mode=${fixed_acquisition_mode}"
    )
    if [[ "$fixed_acquisition_mode" == "live_search" || "$fixed_acquisition_mode" == "hybrid" ]]; then
      [[ "${SOLAR_RESEARCH_RETRIEVAL_POLICY:-}" == "public_bibliographic_no_key_v1" ]] || {
        err "fixed research live acquisition requires SOLAR_RESEARCH_RETRIEVAL_POLICY=public_bibliographic_no_key_v1"
        return 2
      }
      fixed_args+=(--input "retrieval_policy=${SOLAR_RESEARCH_RETRIEVAL_POLICY}")
    fi
    if [[ -n "${SOLAR_RESEARCH_EXPERIMENT_POLICY:-}" ]]; then
      [[ -n "${SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR:-}" ]] || {
        err "fixed research experiment policy requires SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR"
        return 2
      }
      [[ -n "${SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT:-}" ]] || {
        err "fixed research experiment policy requires SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT"
        return 2
      }
      fixed_args+=(
        --input "experiment_policy=${SOLAR_RESEARCH_EXPERIMENT_POLICY}"
        --input "experiment_policy_actor=${SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR}"
        --input "experiment_policy_statement=${SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT}"
      )
    fi
    if [[ -n "${SOLAR_RESEARCH_SOURCE_PACK:-}" ]]; then
      fixed_args+=(--input "source_pack_root=${SOLAR_RESEARCH_SOURCE_PACK}")
    fi
    set +e
    fixed_out=$(HARNESS_SPRINTS_DIR="$SPRINTS_DIR" python3 "$HARNESS_DIR/lib/workflow_intake.py" "${fixed_args[@]}" 2>&1)
    fixed_rc=$?
    set -e
    if [[ "$fixed_rc" != "0" ]]; then
      err "fixed research intake failed (rc=$fixed_rc): $fixed_out"
      return "$fixed_rc"
    fi
    set +e
    fixed_sid=$(python3 -c 'import re,sys; m=re.search(r"Sprint created:\s*(\S+)",sys.stdin.read()); print(m.group(1)) if m else sys.exit(2)' <<<"$fixed_out" 2>/dev/null)
    local fixed_sid_rc=$?
    set -e
    if [[ "$fixed_sid_rc" != "0" || -z "$fixed_sid" ]]; then
      err "fixed research intake attribution failed: sprint id was not present in workflow_intake output"
      return 2
    fi
    out="$fixed_out"
    rc=0
    sid_from_out="$fixed_sid"
    fixed_route=1
  fi
  if [[ "$fixed_route" != "1" ]]; then
    if [[ "$intent_rc" == "0" && -n "$intent_id" && -f "$HARNESS_DIR/lib/intent_consumer.py" ]] && { [[ "${SOLAR_INTAKE_COMPAT_MODE:-}" != "legacy" ]] || ! should_epic_decompose_request "$req"; }; then
      set +e
      consumer_out=$(SOLAR_HARNESS_SPRINTS_DIR="$SPRINTS_DIR" \
        SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT="$intake_workspace_root" \
        python3 "$HARNESS_DIR/lib/intent_consumer.py" consume \
        --intent-id "$intent_id" \
        --json 2>&1)
      consumer_rc=$?
      set -e
      if [[ "$consumer_rc" == "0" ]]; then
        sid_from_out=$(python3 -c 'import json,sys; payload=json.loads(sys.stdin.read()); results=payload.get("results") or [{}]; print((results[0] or {}).get("sprint_id") or "")' <<<"$consumer_out" 2>/dev/null || true)
        consumer_status=$(python3 -c 'import json,sys; payload=json.loads(sys.stdin.read()); results=payload.get("results") or [{}]; print((results[0] or {}).get("status") or "")' <<<"$consumer_out" 2>/dev/null || true)
        planner_handoff_status=$(python3 -c 'import json,sys; payload=json.loads(sys.stdin.read()); results=payload.get("results") or [{}]; handoff=((results[0] or {}).get("planner_handoff") or {}); print(handoff.get("status") or handoff.get("reason") or "")' <<<"$consumer_out" 2>/dev/null || true)
        planner_handoff_mode=$(python3 -c 'import json,sys; payload=json.loads(sys.stdin.read()); results=payload.get("results") or [{}]; handoff=((results[0] or {}).get("planner_handoff") or {}); print(handoff.get("mode") or "")' <<<"$consumer_out" 2>/dev/null || true)
        out=$(python3 - "$sid_from_out" "$intent_id" "$consumer_status" "$planner_handoff_status" <<'PY'
import sys
sid, intent_id, consumer_status, planner = sys.argv[1:5]
planner = planner or "N/A"
print(f"Sprint created: {sid}")
print(f"RawIntent consumed: {intent_id} ({consumer_status or 'N/A'})")
print(f"Planner handoff: {planner}")
PY
)
        rc=0
      else
        out="$consumer_out"
        rc="$consumer_rc"
      fi
    elif [[ "${SOLAR_INTAKE_COMPAT_MODE:-}" == "legacy" ]]; then
      set +e
      out=$(new_sprint "$req" 2>&1)
      rc=$?
      set -e
      sid_from_out=$(python3 -c 'import re,sys; text=re.sub(r"\x1b\[[0-9;]*m","",sys.stdin.read());
patterns=(r"Sprint created:\s*(\S+)", r"Epic:\s*(\S+)", r"\"epic_id\":\s*\"([^\"]+)\"");
print(next((m.group(1) for p in patterns for m in [re.search(p,text)] if m), ""))' <<<"$out" 2>/dev/null || true)
      if [[ "$rc" == "0" && -n "$intent_id" && -n "$sid_from_out" && -f "$HARNESS_DIR/lib/intent_gateway.py" ]]; then
        SOLAR_HARNESS_SPRINTS_DIR="$SPRINTS_DIR" python3 "$HARNESS_DIR/lib/intent_gateway.py" bind --intent-id "$intent_id" --sprint-id "$sid_from_out" --json >/dev/null 2>&1 || true
      fi
    else
      rc="$intent_rc"
      [[ "$rc" != "0" ]] || rc=2
      if [[ ! -f "$HARNESS_DIR/lib/intent_gateway.py" ]]; then
        out="production intake refused: LLM Intent Compiler is unavailable"
      elif [[ -z "$intent_id" ]]; then
        out="production intake refused: LLM Intent Compiler did not produce an accepted IntentIR"
        [[ -n "$intent_out" ]] && out="$out
$intent_out"
      else
        out="production intake refused: Requirement Compiler / Intent Consumer is unavailable"
      fi
    fi
  fi
  raw_file="$(write_intake_raw_record "$req" "$out" 2>/dev/null || true)"
  if [[ "$rc" != "0" ]]; then
    echo "$out"
    return "$rc"
  fi

  autopilot_out=""
  autopilot_rc=0
  if [[ "$dispatch" == "1" && "$fixed_route" == "1" ]]; then
    if [[ ! -f "$HARNESS_DIR/lib/graph_node_dispatcher.py" ]]; then
      autopilot_out="fixed research dispatcher is not installed: $HARNESS_DIR/lib/graph_node_dispatcher.py"
      autopilot_rc=1
    else
      set +e
      autopilot_out=$(HARNESS_SPRINTS_DIR="$SPRINTS_DIR" python3 "$HARNESS_DIR/lib/graph_node_dispatcher.py" \
        dispatch-ready --graph "$SPRINTS_DIR/${sid_from_out}.task_graph.json" --max-parallel 1 2>&1)
      autopilot_rc=$?
      set -e
    fi
    if [[ "$autopilot_rc" != "0" ]]; then
      rc="$autopilot_rc"
    fi
  elif [[ "$dispatch" == "1" && "$planner_handoff_mode" =~ ^(direct_answer|elastic_planner)$ ]]; then
    # The consumer already started a typed downstream path. Running the legacy
    # global autopilot here could dispatch an uncertified task_graph before the
    # frozen SchedulerInput exists.
    autopilot_out="typed_planner_runtime_submitted"
    autopilot_rc=0
  elif [[ "$dispatch" == "1" && -f "$HARNESS_DIR/tools/solar-autopilot-monitor.py" ]]; then
    set +e
    autopilot_out=$(python3 "$HARNESS_DIR/tools/solar-autopilot-monitor.py" --apply --dispatch --max-iterations 1 --json 2>&1)
    autopilot_rc=$?
    set -e
  fi

  if [[ "$json" == "1" ]]; then
    python3 - "$rc" "$raw_file" "$dispatch" "$autopilot_rc" "$intent_rc" "$intent_id" <<'PY'
import json, sys
print(json.dumps({
    "ok": int(sys.argv[1]) == 0,
    "raw_record": sys.argv[2],
    "dispatch_requested": sys.argv[3] == "1",
    "autopilot_returncode": int(sys.argv[4]),
    "intent_gateway": {
        "ok": int(sys.argv[5]) == 0,
        "intent_id": sys.argv[6],
    },
}, ensure_ascii=False, indent=2))
PY
  else
    echo "$out"
    if [[ -n "$intent_id" ]]; then
      log "RawIntent: $intent_id"
    elif [[ "$intent_rc" != "0" ]]; then
      warn "Intent gateway failed rc=${intent_rc}"
      echo "$intent_out" | tail -20
    fi
    [[ -n "$raw_file" ]] && log "Raw intake: $raw_file"
    if [[ "$dispatch" == "1" ]]; then
      if [[ "$autopilot_rc" == "0" ]]; then
        if [[ "$fixed_route" == "1" ]]; then
          ok "Fixed research A1 dispatch triggered"
        elif [[ "$planner_handoff_mode" =~ ^(direct_answer|elastic_planner)$ ]]; then
          ok "Typed Planner path started; legacy autopilot skipped"
        else
          ok "Autopilot scan/dispatch triggered"
        fi
      else
        warn "Autopilot dispatch trigger failed rc=${autopilot_rc}"
        echo "$autopilot_out" | tail -40
      fi
    fi
  fi
  return "$rc"
}

new_sprint() {
  local req="$1"
  local sid
  ensure_dirs
  if should_epic_decompose_request "$req"; then
    new_epic_from_request "$req"
    return $?
  fi
  sid=$(date +"sprint-%Y%m%d-%H%M%S")
  while [[ -e "$SPRINTS_DIR/$sid.status.json" || -e "$SPRINTS_DIR/$sid.contract.md" || -e "$SPRINTS_DIR/$sid.events.jsonl" ]]; do
    sleep 1
    sid=$(date +"sprint-%Y%m%d-%H%M%S")
  done

  local template="$HARNESS_DIR/templates/contract-template-v2.md"
  local title summary
  title=$(echo "$req" | head -1 | cut -c1-60)
  summary=$(echo "$req" | tr '\n' ' ' | sed 's/[[:space:]]\\{1,\\}/ /g' | cut -c1-180)
  [[ -z "$title" ]] && title="Untitled Sprint"
  [[ -z "$summary" ]] && summary="$title"
  local created_at
  created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # Prefer v2 template if it exists, otherwise fall back to inline
  if [[ -f "$template" ]]; then
    sed \
      -e "s|{{sprint_id}}|${sid}|g" \
      -e "s|{{created_at}}|${created_at}|g" \
      -e "s|{{project_dir}}|$(pwd)|g" \
      -e "s|{{name}}|${title}|g" \
      -e "s|{{description}}|${req}|g" \
      -e "s|{{summary}}|${summary}|g" \
      -e "s|{{triggers}}|auto|g" \
      -e "s|{{requirements}}|${req}|g" \
      "$template" > "${SPRINTS_DIR}/${sid}.contract.md"
  else
    # Fallback: inline template (backward compat)
    cat > "${SPRINTS_DIR}/${sid}.contract.md" << EOF
# Sprint Contract — ${title} (${sid})
Created: ${created_at}
Status: drafting
Project: $(pwd)

## Summary

${summary}

## Requirements

${req}

## Definition of Done

> Planner fills in

- [ ] (criterion 1)
- [ ] (criterion 2)
- [ ] (criterion 3)

## Scope

- In: (planner fills)
- Out: (planner fills)

## Constraints

> Planner fills in

## Implementation Files

> Builder fills in after completion

## Evaluation Dimensions

1. Functional completeness: Done criteria checked
2. Code quality: Error handling, edge cases, security
3. Contract compliance: Within scope
4. Maintainability: Naming, structure
EOF
  fi

  cat > "${SPRINTS_DIR}/${sid}.status.json" << EOF2
{
  "id": "${sid}",
  "title": "${title}",
  "summary": "${summary}",
  "status": "drafting",
  "phase": "spec",
  "handoff_to": "pm",
  "created_at": "${created_at}",
  "round": 0,
  "history": [{"ts": "${created_at}", "event": "pm_intake_created", "by": "user"}]
}
EOF2

  # Log phase_init event through unified events + adopt the initial status into
  # session-log v2, so newly created sprints do not start as legacy-only state.
  events_emit "solar-harness" "phase_transition" "info" "$sid" '{"from":"none","to":"spec"}' 2>/dev/null || true
  if [[ -f "$HARNESS_DIR/lib/runtime_bridge.py" ]]; then
    python3 "$HARNESS_DIR/lib/runtime_bridge.py" adopt "$sid" --quiet 2>/dev/null || true
  fi

  ok "Sprint created: ${sid}"
  log "Contract: ${SPRINTS_DIR}/${sid}.contract.md"
  log "Phase: spec"
  log "Next: PM researches request and writes PRD, then Planner/architect designs plan"
}

# ---- Wake: 从崩溃恢复 Sprint ----

wake_sprint() {
  local sid="${2:-}"

  # wake --help / wake -h: 打印 usage
  if [[ "$sid" == "--help" || "$sid" == "-h" ]]; then
    echo "Solar Harness — wake: 从崩溃恢复 Sprint"
    echo ""
    echo "用法:"
    echo "  $0 wake              列出所有未完成 Sprint 供选择"
    echo "  $0 wake <sprint-id>  恢复指定 Sprint"
    echo "  $0 wake --help       显示帮助"
    echo ""
    echo "恢复流程:"
    echo "  1. 确保 tmux session 存在 (不存在则重建)"
    echo "  2. 从 events.jsonl 检查幂等性 (防止重复 wake)"
    echo "  3. 从 sprint 状态推导派发目标 (planner/builder/evaluator)"
    echo "  4. 生成 dispatch.md 并派发到对应 pane"
    echo "  5. 记录 wake 事件"
    echo "  6. 确保 coordinator 运行"
    echo ""
    echo "覆盖状态: drafting/active/planning/approved/reviewing/failed_review/interrupted"
    return 0
  fi

  if [[ -z "$sid" ]]; then
    # 无参数时列出所有未完成 sprint
    echo ""
    ok "未完成 Sprint 列表:"
    echo ""
    local found=0
    for f in "$SPRINTS_DIR"/*.status.json; do
      [[ -f "$f" ]] || continue
      local fst fstitle fstid
      fst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
      case "$fst" in
        passed|done|failed|eval_pass) continue ;;
      esac
      fstid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
      fstitle=$(python3 -c "import json; t=json.load(open('$f')).get('title',''); print(t[:50])" 2>/dev/null)
      echo -e "  ${G}${fstid}${N}  ${fst}  ${fstitle}"
      found=$((found + 1))
    done
    echo ""
    if [[ "$found" -eq 0 ]]; then
      warn "无活跃 Sprint"
    else
      log "用法: $0 wake <sprint-id>"
    fi
    return 0
  fi

  local sf="$SPRINTS_DIR/${sid}.status.json"
  [[ -f "$sf" ]] || { err "Sprint 不存在: $sid"; exit 1; }

  # Managed Agent Runtime adoption: before routing, mirror legacy artifacts into
  # session-log v2 and refresh status.json from ProjectionEngine. This keeps
  # wake recoverable from durable events while preserving legacy compatibility.
  if [[ -f "$HARNESS_DIR/lib/runtime_bridge.py" ]]; then
    python3 "$HARNESS_DIR/lib/runtime_bridge.py" adopt "$sid" --write-cache --quiet 2>/dev/null || true
  fi

  local st phase handoff_to auto_held contract_bypass contract_handoff contract_target
  st=$(python3 -c "import json; print(json.load(open('$sf')).get('status',''))" 2>/dev/null)
  phase=$(python3 -c "import json; print(json.load(open('$sf')).get('phase',''))" 2>/dev/null || true)
  handoff_to=$(python3 -c "import json; print(json.load(open('$sf')).get('handoff_to',''))" 2>/dev/null || true)
  auto_held=$(python3 -c "import json; print('true' if json.load(open('$sf')).get('auto_held') else 'false')" 2>/dev/null || echo false)
  contract_bypass=$(grep -Eiq '^(bypass_pm|bypass pm):[[:space:]]*true[[:space:]]*$' "$SPRINTS_DIR/${sid}.contract.md" 2>/dev/null && echo true || echo false)
  contract_handoff=$(grep -m1 '^handoff_to:' "$SPRINTS_DIR/${sid}.contract.md" 2>/dev/null | sed 's/^handoff_to:[[:space:]]*//' || true)
  contract_target=$(grep -m1 '^target_role:' "$SPRINTS_DIR/${sid}.contract.md" 2>/dev/null | sed 's/^target_role:[[:space:]]*//' || true)
  local original_st="$st"
  case "$st" in
    passed|done|failed|eval_pass)
      ok "Sprint ${sid} 已完成 (${st})，无需恢复"
      return 0
      ;;
  esac
  if [[ "$phase" =~ ^(completed|finalized|eval_passed|release_passed)$ ]] && [[ -z "$handoff_to" || "$handoff_to" =~ ^(done|completed)$ ]]; then
    ok "Sprint ${sid} 已完成 (${st}/${phase}/${handoff_to:-none})，无需恢复"
    return 0
  fi

  log "恢复 Sprint: ${sid} (当前状态: ${st})"

  # Step 1: 确保 tmux session 存在
  if ! tmux_has_exact_session "$SESSION_NAME"; then
    warn "tmux session 不存在，重建..."
    # 用当前目录启动 (不 attach)
    local work_dir
    work_dir=$(grep '^Project:' "$SPRINTS_DIR/${sid}.contract.md" 2>/dev/null | sed 's/^Project:[[:space:]]*//' || echo "$HOME")
    [[ -z "$work_dir" ]] && work_dir="$HOME"

    # 重建 4-pane 布局 (后台)
    tmux new-session -d -s "$SESSION_NAME" -c "$work_dir"
    sanitize_tmux_claude_env "$SESSION_NAME"
    configure_tmux_pane_runtime_env "$SESSION_NAME"
    tmux split-window -v -t "$SESSION_NAME" -c "$work_dir"
    tmux split-window -h -t "$SESSION_NAME:0.0" -c "$work_dir"
    tmux split-window -h -t "$SESSION_NAME:0.2" -c "$work_dir"
    tmux set-option -t "$SESSION_NAME" mouse on
    sleep 1

    # 启动各 pane (D5 sprint-20260502-191700: 路径转义)
    local _esc_h _esc_w
    _esc_h=$(printf '%q' "$HARNESS_DIR")
    _esc_w=$(printf '%q' "$work_dir")
    tmux send-keys -t "$SESSION_NAME:0.0" "$(pane_launch_prefix) bash ${_esc_h}/pane-launcher.sh pm ${_esc_w}" Enter
    sleep 1
    tmux send-keys -t "$SESSION_NAME:0.1" "$(pane_launch_prefix) bash ${_esc_h}/pane-launcher.sh planner ${_esc_w}" Enter
    sleep 1
    tmux send-keys -t "$SESSION_NAME:0.2" "$(pane_launch_prefix) bash ${_esc_h}/pane-launcher.sh builder ${_esc_w}" Enter
    sleep 1
    tmux send-keys -t "$SESSION_NAME:0.3" "$(pane_launch_prefix) bash ${_esc_h}/pane-launcher.sh evaluator ${_esc_w}" Enter
    sleep 1
    configure_product_delivery_labels

    ok "tmux session 已重建"
  fi

  # Step 2: 幂等检查 — 从 events.jsonl 看是否已经 wake 过且无新活动
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"
  if [[ -f "$events_file" ]]; then
    local last_event
    last_event=$(tail -1 "$events_file" 2>/dev/null | python3 -c "
import json, sys
line = sys.stdin.read().strip()
if line:
    try:
        d = json.loads(line)
        if d.get('event') == 'waked':
            print('already_waked')
        else:
            print('ok')
    except:
        print('ok')
else:
    print('no_events')
" 2>/dev/null)
    if [[ "$last_event" == "already_waked" ]]; then
      # 检查 events.jsonl 最后修改时间 vs status.json
      local ev_mtime sf_mtime
      ev_mtime=$(solar_file_mtime "$events_file" 2>/dev/null || echo 0)
      sf_mtime=$(solar_file_mtime "$sf" 2>/dev/null || echo 0)
      if [[ "$sf_mtime" -le "$ev_mtime" ]]; then
        ok "Sprint ${sid} 已 wake 且无新活动，跳过 (幂等)"
        return 0
      fi
    fi
  fi

  # Step 3: 从最后状态推导派发目标
  local PANE_PM="$SESSION_NAME:0.0"
  local PANE_PLANNER="$SESSION_NAME:0.1"
  local PANE_BUILDER="$SESSION_NAME:0.2"
  local PANE_EVALUATOR="$SESSION_NAME:0.3"
  local LIVE_PM LIVE_PLANNER LIVE_BUILDER LIVE_EVALUATOR
  LIVE_PM=$(detect_pane_by_persona_simple "$SESSION_NAME" 0 "pm" "$PANE_PM")
  LIVE_PLANNER=$(detect_pane_by_persona_simple "$SESSION_NAME" 0 "planner" "$PANE_PLANNER")
  LIVE_BUILDER=$(detect_pane_by_persona_simple "$SESSION_NAME" 0 "builder" "$PANE_BUILDER")
  LIVE_EVALUATOR=$(detect_pane_by_persona_simple "$SESSION_NAME" 0 "evaluator" "$PANE_EVALUATOR")
  if [[ "$LIVE_PM" == "$PANE_PM" ]]; then
    local pm_actual
    pm_actual=$(pane_process_persona_simple "$LIVE_PM" 2>/dev/null || true)
    [[ "$pm_actual" == "pm" ]] || LIVE_PM="$LIVE_PLANNER"
  fi
  local target_pane="" target_task="" dispatch_role="" dispatch_task_type=""
  local workflow_role workflow_stage workflow_reason workflow_violations
  workflow_role=$(python3 "$HARNESS_DIR/lib/workflow_guard.py" route "$sid" --field route_role 2>/dev/null || echo pm)
  workflow_stage=$(python3 "$HARNESS_DIR/lib/workflow_guard.py" route "$sid" --field stage 2>/dev/null || echo intake)
  workflow_reason=$(python3 "$HARNESS_DIR/lib/workflow_guard.py" route "$sid" --field reason 2>/dev/null || echo missing_pm_prd)
  workflow_violations=$(python3 "$HARNESS_DIR/lib/workflow_guard.py" route "$sid" --field violations 2>/dev/null || echo '[]')

  route_by_workflow_guard() {
    case "$workflow_role" in
      none)
        ok "Sprint ${sid} 已完成或无需派发 (${workflow_stage}/${workflow_reason})"
        return 2
        ;;
      pm)
        python3 "$HARNESS_DIR/lib/runtime_status.py" "$sf" "drafting" "wake_workflow_guard_to_pm" "wake" '{"status_fields":{"phase":"spec","handoff_to":"pm","target_role":"pm","auto_held":false},"note":"Workflow guard: PM PRD is required before planner or builder dispatch."}' >/dev/null 2>&1 || true
        st="drafting"
        target_pane="$LIVE_PM"
        target_task="Sprint ${sid} 恢复：Workflow Guard 判定必须先走 PM。请研究用户要求，产出正式 PRD 到 ${SPRINTS_DIR}/${sid}.prd.md；完成后只交给 Planner，不要直接给 Builder。原因: ${workflow_reason}; violations=${workflow_violations}"
        ;;
      planner)
        python3 "$HARNESS_DIR/lib/runtime_status.py" "$sf" "drafting" "wake_workflow_guard_to_planner" "wake" '{"status_fields":{"phase":"prd_ready","handoff_to":"planner","target_role":"planner","auto_held":false},"note":"Workflow guard: planner must produce design.md, plan.md, and task_graph.json before builder dispatch."}' >/dev/null 2>&1 || true
        st="drafting"
        target_pane="$LIVE_PLANNER"
        dispatch_role="planner"
        dispatch_task_type="planning"
        target_task="Sprint ${sid} 恢复：Workflow Guard 判定 PRD 已就绪，请 Planner 读取 PRD/contract，产出 design.md、plan.md、task_graph.json；完成后再进入 builder DAG 派发。原因: ${workflow_reason}; violations=${workflow_violations}"
        ;;
      builder|builder_main)
        python3 "$HARNESS_DIR/lib/runtime_status.py" "$sf" "active" "wake_workflow_guard_to_builder" "wake" '{"status_fields":{"phase":"planning_complete","handoff_to":"builder_main","target_role":"builder_main","auto_held":false},"note":"Workflow guard: PM PRD + planner design/plan/task_graph are ready; builder DAG dispatch is allowed."}' >/dev/null 2>&1 || true
        st="active"
        target_pane="$LIVE_BUILDER"
        dispatch_role="builder"
        dispatch_task_type="implementation"
        target_task="Sprint ${sid} 恢复：Workflow Guard 判定 PM+Planner 产物齐全，请读取 task_graph.json 并按 DAG/并行 builder 流程执行，不要绕开 graph scheduler。"
        ;;
      evaluator)
        target_pane="$LIVE_EVALUATOR"
        dispatch_role="evaluator"
        dispatch_task_type="review"
        target_task="Sprint ${sid} 恢复：Workflow Guard 判定已有 handoff，需要 Evaluator 评审。读取 ${SPRINTS_DIR}/${sid}.handoff.md"
        ;;
      *)
        target_pane="$LIVE_PM"
        target_task="Sprint ${sid} 恢复：Workflow Guard 未识别 route_role=${workflow_role}，交给 PM 诊断状态，不直接实现。"
        ;;
    esac
    return 0
  }

  case "$st" in
    queued)
      if [[ "$auto_held" == "true" ]]; then
        ok "Sprint ${sid} 当前为 queued/auto_held，wake 不强推。请先人工解除 hold 或 activate。"
        return 0
      else
        route_by_workflow_guard || return 0
      fi
      ;;
    drafting|drafting_held)
      if [[ "$auto_held" == "true" || "$st" == "drafting_held" ]]; then
        ok "Sprint ${sid} 当前为 ${st}/auto_held，wake 不强推。请先人工解除 hold 或 activate。"
        return 0
      else
        route_by_workflow_guard || return 0
      fi
      ;;
    active)
      route_by_workflow_guard || return 0
      ;;
    planning)
      target_pane="$LIVE_EVALUATOR"
      dispatch_role="evaluator"
      dispatch_task_type="review"
      target_task="Sprint ${sid} 恢复：建设者已提交计划，请审批。读取 ${SPRINTS_DIR}/${sid}.plan.md"
      ;;
    approved)
      if [[ "$workflow_role" != "builder" && "$workflow_role" != "builder_main" ]]; then
        route_by_workflow_guard || return 0
      else
        target_pane="$LIVE_BUILDER"
        dispatch_role="builder"
        dispatch_task_type="implementation"
        target_task="Sprint ${sid} 恢复：计划已批准，请继续实现。读取 ${SPRINTS_DIR}/${sid}.plan.md"
      fi
      ;;
    reviewing|ready_for_review)
      target_pane="$LIVE_EVALUATOR"
      dispatch_role="evaluator"
      dispatch_task_type="review"
      target_task="Sprint ${sid} 恢复：建设者已提交，请评审。读取 ${SPRINTS_DIR}/${sid}.handoff.md"
      ;;
    failed_review)
      target_pane="$LIVE_BUILDER"
      dispatch_role="builder"
      dispatch_task_type="implementation"
      target_task="Sprint ${sid} 恢复：评审未通过，请修复。读取 ${SPRINTS_DIR}/${sid}.eval.md"
      ;;
    interrupted)
      # 被 kill_harness 打断，改回 reviewing 让 coordinator 重新派发
      python3 "$HARNESS_DIR/lib/runtime_status.py" "$sf" "reviewing" "wake_resumed_interrupted" "wake" '{}' >/dev/null 2>&1 || true
      target_pane="$LIVE_EVALUATOR"
      dispatch_role="evaluator"
      dispatch_task_type="review"
      target_task="Sprint ${sid} 恢复 (从 interrupted)：请评审。读取 ${SPRINTS_DIR}/${sid}.handoff.md"
      ;;
    *)
      warn "未知状态: ${st}，派发给 PM 做状态诊断，不直接给建设者执行"
      target_pane="$LIVE_PM"
      target_task="Sprint ${sid} 恢复：当前状态 ${st} 未被 wake 状态机识别。请先诊断 status/phase/handoff_to，修正状态后再派发，不要直接实现。"
      ;;
  esac

  # The pre-write hook contract refers to one stable state file. Older installs
  # could dispatch that requirement without provisioning the file, which made
  # every role stop before its first write. Create a minimal, non-secret
  # locator once; per-sprint status/events remain the runtime source of truth.
  local state_file="${SOLAR_STATE_FILE:-$HOME/.solar/STATE.md}"
  if [[ ! -f "$state_file" ]]; then
    mkdir -p "$(dirname "$state_file")" || return 78
    {
      printf '# Solar Runtime State\n\n'
      printf -- '- Canonical harness root: `%s`\n' "$HARNESS_DIR"
      printf -- '- Canonical sprint directory: `%s`\n' "$SPRINTS_DIR"
      printf -- '- Runtime truth: read the active sprint status/events files; do not infer completion from this locator.\n'
    } > "$state_file" || return 78
    chmod 600 "$state_file" 2>/dev/null || true
  fi

  # Step 4: 重新生成 dispatch.md 并派发
  cat > "$SPRINTS_DIR/${sid}.dispatch.md" << DISPATCH_EOF
# 协调器恢复指令 (Wake)

<!-- SOLAR_STATE_READ_PREFLIGHT -->
## 必须先读状态 (防写入 hook 卡死)

在任何 Write/Edit/handoff/eval/status 更新之前，必须先用 Claude/Codex 的 **Read 工具**读取：

\`${state_file}\`

不要用 \`cat\` 替代这一步；本地 \`state-read-enforcer.sh\` hook 只认 Read 工具标记。

如果 Write/Edit hook 仍阻断，立刻 Read 上面的 STATE 文件后重试原写入一次，不要停在“已读”等待。

---

${target_task}
DISPATCH_EOF

  # G2b review finding 5: a planner woken through this dispatch file (or the
  # fixed-pane send-keys fallback below) never saw the compile policy. The
  # helper is env-gated: with SOLAR_PLAN_VALIDATOR off it prints nothing and
  # the dispatch file stays byte-identical.
  if [[ "$dispatch_role" == "planner" ]]; then
    local planner_compile_policy_block=""
    planner_compile_policy_block=$(python3 "$HARNESS_DIR/lib/plan_validator.py" planner-policy-block "$sid" --sprints-dir "$SPRINTS_DIR" 2>/dev/null || true)
    if [[ -n "$planner_compile_policy_block" ]]; then
      printf '\n%s\n' "$planner_compile_policy_block" >> "$SPRINTS_DIR/${sid}.dispatch.md"
    fi
  fi

  if [[ "${SOLAR_NO_DISPATCH:-0}" == "1" || -f "$HARNESS_DIR/run/no-dispatch.flag" ]]; then
    warn "no-dispatch flag active; wake wrote dispatch file but did not send: ${dispatch_role:+operator-pool:${dispatch_role}}${dispatch_role:+ / }${target_pane}"
    return 4
  fi

  codex_runtime_suppresses_pm_operator_dispatch() {
    local runtime="${SOLAR_PANE_RUNTIME:-}"
    local allow="${SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH:-}"
    runtime="${runtime,,}"
    allow="${allow,,}"
    [[ "$runtime" == "codex" && "$allow" != "1" && "$allow" != "true" && "$allow" != "yes" && "$allow" != "on" ]]
  }

  dispatch_via_operator_pool() {
    local role="$1"
    local task_type="$2"
    local fallback_pane="$3"
    local objective="执行 Sprint 恢复任务。先完整读取并执行指令文件 ${SPRINTS_DIR}/${sid}.dispatch.md 中的全部步骤。"
    local context
    context=$(cat <<CTX
wake_sprint recovery
sprint_id=${sid}
original_status=${original_st}
current_status=${st}
workflow_role=${workflow_role}
workflow_stage=${workflow_stage}
workflow_reason=${workflow_reason}
fallback_pane=${fallback_pane}
dispatch_md=${SPRINTS_DIR}/${sid}.dispatch.md
CTX
)
    local -a work_dir_args=()
    if [[ "$role" == "builder" ]]; then
      local project_dir=""
      project_dir=$(grep -m1 '^Project:' "$SPRINTS_DIR/${sid}.contract.md" 2>/dev/null | sed 's/^Project:[[:space:]]*//' || true)
      if [[ -n "$project_dir" && -d "$project_dir" ]]; then
        work_dir_args=(--work-dir "$project_dir")
      elif [[ -n "$project_dir" ]]; then
        warn "builder project directory from compiled contract is unavailable: ${project_dir}"
        return 1
      fi
    fi
    local submit_output="" attempt
    for attempt in 1 2; do
      if submit_output=$(SOLAR_PM_DISPATCH_ALLOW_DIRECT=1 python3 "$HARNESS_DIR/tools/pm_dispatch.py" submit \
        --role "$role" \
        --task-type "$task_type" \
        --sprint "$sid" \
        --node "wake-${role}" \
        --objective "$objective" \
        --context "$context" \
        "${work_dir_args[@]}" 2>&1); then
        bash "$HARNESS_DIR/session.sh" append "$sid" "{\"event\":\"waked\",\"by\":\"wake\",\"data\":{\"from_status\":\"${original_st}\",\"target_pane\":\"operator-pool:${role}\",\"fallback_pane\":\"${fallback_pane}\",\"attempt\":${attempt}}}" 2>/dev/null || true
        ok "Sprint ${sid} 已恢复 → operator-pool:${role} (从 ${original_st})"
        [[ -n "$submit_output" ]] && printf '%s\n' "$submit_output"
        return 0
      fi
      if [[ "$submit_output" != *"not dispatchable"* && "$submit_output" != *"state=leased"* && "$submit_output" != *"state=running"* ]]; then
        break
      fi
      warn "operator pool 第 ${attempt} 次派发命中瞬时占用，重试选算子..."
      sleep 0.2
    done
    warn "operator pool 派发失败，回退固定 pane ${fallback_pane}"
    [[ -n "$submit_output" ]] && printf '%s\n' "$submit_output" >&2
    return 1
  }

  if [[ -n "$dispatch_role" ]]; then
    if codex_runtime_suppresses_pm_operator_dispatch; then
      warn "Codex pane runtime selected; skipping PM operator pool for ${dispatch_role}, using fixed pane ${target_pane}"
    elif dispatch_via_operator_pool "$dispatch_role" "$dispatch_task_type" "$target_pane"; then
      _ensure_bash4 2>/dev/null || true
      local coord_bash="${BASH4:-bash}"
      if [[ -f "$HARNESS_DIR/.coordinator.pid" ]]; then
        local pid
        pid=$(cat "$HARNESS_DIR/.coordinator.pid")
        if ! kill -0 "$pid" 2>/dev/null; then
          warn "Coordinator PID ${pid} 已死，重启..."
          rm -f "$HARNESS_DIR/.coordinator.pid"
          nohup "$coord_bash" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
          disown 2>/dev/null || true
          ok "Coordinator 重启中..."
        else
          ok "Coordinator 运行中 (PID: ${pid})"
        fi
      else
        warn "无 coordinator PID 文件，启动新的..."
        nohup "$coord_bash" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
        ok "Coordinator 启动中..."
      fi
      return 0
    fi
  fi

  local short_cmd="读取并执行指令文件 $SPRINTS_DIR/${sid}.dispatch.md 中的所有步骤"
  # Claude TUI can leave stale input in the prompt after interrupts; clear the
  # current input line and send Enter twice so wake does not stop at a queued
  # prompt requiring a manual second Enter.
  tmux send-keys -t "$target_pane" C-u 2>/dev/null || true
  sleep 0.2
  tmux send-keys -t "$target_pane" "$short_cmd" 2>/dev/null || true
  sleep 0.5
  tmux send-keys -t "$target_pane" Enter 2>/dev/null || true
  sleep 0.3
  tmux send-keys -t "$target_pane" Enter 2>/dev/null || true

  # Step 5: 记录 wake 事件
  bash "$HARNESS_DIR/session.sh" append "$sid" "{\"event\":\"waked\",\"by\":\"wake\",\"data\":{\"from_status\":\"${original_st}\",\"target_pane\":\"${target_pane}\"}}" 2>/dev/null || true

  ok "Sprint ${sid} 已恢复 → ${target_pane} (从 ${original_st})"

  # Step 6: 确保 coordinator 在运行
  _ensure_bash4 2>/dev/null || true
  local coord_bash="${BASH4:-bash}"
  if [[ -f "$HARNESS_DIR/.coordinator.pid" ]]; then
    local pid
    pid=$(cat "$HARNESS_DIR/.coordinator.pid")
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "Coordinator PID ${pid} 已死，重启..."
      rm -f "$HARNESS_DIR/.coordinator.pid"
      nohup "$coord_bash" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
      disown 2>/dev/null || true
      ok "Coordinator 重启中..."
    else
      ok "Coordinator 运行中 (PID: ${pid})"
    fi
  else
    warn "无 coordinator PID 文件，启动新的..."
    nohup "$coord_bash" "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
    ok "Coordinator 启动中..."
  fi
}

# ---- Atomic Commands (Sprint 20260420-113026) ----

do_handoff_submit() {
  local sid="$1"
  local sf="$SPRINTS_DIR/${sid}.status.json"
  local hf="$SPRINTS_DIR/${sid}.handoff.md"
  rs_exists "$sid" || { err "Sprint not found: $sid"; exit 1; }
  [[ -f "$hf" ]] || { err "handoff.md not found for $sid — 先写 handoff 再提交"; exit 1; }

  local handoff_mtime
  handoff_mtime=$(solar_file_mtime "$hf" 2>/dev/null || echo 0)

  # Idempotent: same handoff mtime = already submitted
  python3 -c "
import json
d=json.load(open('$sf'))
if d.get('last_handoff_mtime') == float('${handoff_mtime}'):
    exit(0)
exit(1)
" 2>/dev/null && { ok "handoff-submit: $sid already submitted (handoff unchanged)"; return 0; } || true

  rs_transition_with_round_bump "$sid" "reviewing" "implementation_completed" "builder" \
    || { err "handoff-submit 写入失败"; exit 1; }

  # Write last_handoff_mtime as top-level field
  python3 -c "
import json, os, tempfile
sf=os.path.expanduser('$sf')
d=json.load(open(sf))
d['last_handoff_mtime']=float('${handoff_mtime}')
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(sf))
with os.fdopen(fd,'w') as f: json.dump(d,f,indent=2)
os.rename(tmp,sf)
" || true

  bash "$HARNESS_DIR/session.sh" append "$sid" "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"handoff_submitted\",\"by\":\"builder\",\"sid\":\"$sid\"}" 2>/dev/null || true
  type ledger_emit &>/dev/null && ledger_emit "produced" "$sid.handoff.md" "{\"by\":\"builder\"}" 2>/dev/null || true

  # sprint-20260508-coordinator-control-plane-v2 S3: write ack file so ack-watcher can confirm
  local _did_file="$SPRINTS_DIR/${sid}.current-dispatch-id"
  if [[ -f "$_did_file" ]]; then
    local _did
    _did=$(cat "$_did_file" 2>/dev/null || true)
    if [[ -n "$_did" ]]; then
      local _ack_file="$SPRINTS_DIR/${sid}.ack-${_did}.json"
      python3 -c "
import json, datetime, os, sys
sid=sys.argv[1]; did=sys.argv[2]; path=sys.argv[3]
now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
ack={'dispatch_id':did,'sid':sid,'role':'builder','status':'success',
     'exit_code':0,'message':'handoff submitted','artifacts':['handoff.md'],'wrote_at':now}
with open(path,'w') as f: json.dump(ack,f,indent=2)
" "$sid" "$_did" "$_ack_file" 2>/dev/null || true
    fi
  fi

  ok "handoff-submit: $sid → reviewing"
}

do_plan_verdict() {
  local sid="$1" verdict="$2" reason="${3:-}"
  rs_exists "$sid" || { err "Sprint not found: $sid"; exit 1; }

  local new_status verdict_upper
  case "$verdict" in
    approve|approved) new_status="approved"; verdict_upper="APPROVE" ;;
    reject|rejected)  new_status="active";   verdict_upper="REJECT" ;;
    *) err "verdict 必须是 approve 或 reject"; exit 1 ;;
  esac

  local extra_json
  if [[ -n "$reason" ]]; then
    extra_json=$(python3 -c "import json; print(json.dumps({'verdict':'$verdict_upper','reason':'$reason'}))")
  else
    extra_json="{\"verdict\":\"$verdict_upper\"}"
  fi

  rs_transition "$sid" "$new_status" "plan_reviewed" "evaluator" "$extra_json" \
    || { err "plan-verdict 写入失败"; exit 1; }

  bash "$HARNESS_DIR/session.sh" append "$sid" "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"plan_verdict\",\"by\":\"evaluator\",\"verdict\":\"${verdict}\",\"sid\":\"$sid\"}" 2>/dev/null || true
  ok "plan-verdict: $sid → $new_status"
}

do_eval_verdict() {
  local sid="$1" verdict="$2" reason="${3:-}"
  rs_exists "$sid" || { err "Sprint not found: $sid"; exit 1; }

  local new_status event_name verdict_upper
  case "$verdict" in
    pass|passed)
      new_status="passed"; event_name="eval_passed"; verdict_upper="PASS" ;;
    fail|failed)
      new_status="failed_review"; event_name="eval_failed"; verdict_upper="FAIL" ;;
    *) err "verdict 必须是 pass 或 fail"; exit 1 ;;
  esac

  local extra_json
  if [[ -n "$reason" ]]; then
    extra_json=$(python3 -c "import json; print(json.dumps({'verdict':'$verdict_upper','reason':'$reason'}))")
  else
    extra_json="{\"verdict\":\"$verdict_upper\"}"
  fi

  if [[ "$new_status" == "passed" ]]; then
    local gate_json
    gate_json=$(HARNESS_DIR="$HARNESS_DIR" python3 - "$sid" <<'PY'
import json
import os
import sys

sid = sys.argv[1]
lib_dir = os.path.join(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or os.path.expanduser("~/.solar/harness"),
    "lib",
)
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
from coordinator_hooks import gate_status_transition  # noqa: E402

decision = gate_status_transition(sid, "reviewing", "passed")
print(json.dumps(decision.to_dict(), ensure_ascii=False))
if decision.action == "abort":
    sys.exit(2)
PY
    ) || { err "eval-verdict evidence gate blocked: ${gate_json:-N/A}"; exit 1; }
  fi

  if [[ "$new_status" == "failed_review" ]]; then
    rs_transition_with_round_bump "$sid" "$new_status" "eval_completed" "evaluator" "$extra_json" \
      || { err "eval-verdict 写入失败"; exit 1; }
  else
    rs_transition "$sid" "$new_status" "eval_completed" "evaluator" "$extra_json" \
      || { err "eval-verdict 写入失败"; exit 1; }
  fi

  bash "$HARNESS_DIR/session.sh" append "$sid" "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"${event_name}\",\"by\":\"evaluator\",\"verdict\":\"${verdict}\",\"sid\":\"$sid\"}" 2>/dev/null || true
  local ledger_event
  if [[ "$new_status" == "passed" ]]; then
    ledger_event="accepted"
  else
    ledger_event="rejected"
  fi
  type ledger_emit &>/dev/null && ledger_emit "$ledger_event" "$sid.handoff.md" "{\"verdict\":\"$verdict_upper\",\"by\":\"evaluator\"}" 2>/dev/null || true
  ok "eval-verdict: $sid → $new_status"
}

do_verify_events() {
  local sid="$1"
  local sf="$SPRINTS_DIR/${sid}.status.json"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"
  [[ ! -f "$sf" ]] && { err "Sprint not found: $sid"; exit 1; }

  local issues=0 fixed=0

  # 1. Check history events vs events.jsonl
  local history_events
  history_events=$(python3 -c "
import json
d = json.load(open('$sf'))
for h in d.get('history', []):
    print(h.get('event',''))
" 2>/dev/null)

  if [[ -f "$events_file" ]]; then
    local events_recorded
    events_recorded=$(grep -c '.' "$events_file" 2>/dev/null || echo 0)

    for evt in $history_events; do
      if ! grep -q "\"$evt\"" "$events_file" 2>/dev/null; then
        log "[verify] history has '$evt' but events.jsonl missing it"
        ((issues++))
        bash "$HARNESS_DIR/session.sh" append "$sid" "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"${evt}\",\"by\":\"verify-repair\",\"sid\":\"$sid\",\"source\":\"history_backfill\"}" 2>/dev/null || true
        ((fixed++))
      fi
    done
  else
    log "[verify] no events.jsonl for $sid"
    ((issues++))
  fi

  # 2. Check status consistency
  local st
  st=$(python3 -c "import json; print(json.load(open('$sf')).get('status',''))" 2>/dev/null)
  if [[ "$st" == "passed" ]] && [[ ! -f "$SPRINTS_DIR/${sid}.finalized" ]]; then
    log "[verify] status=passed but no .finalized"
    ((issues++))
  fi

  # 3. Per-round completeness check (Sprint 20260420-191039)
  python3 -c "
import json
d = json.load(open('$sf'))
history = d.get('history', [])
max_round = d.get('round', 0)
for r in range(1, max_round + 1):
    has_impl = any(h.get('event') == 'implementation_completed' and h.get('round') == r for h in history)
    # eval_completed may have round=N (FAIL) or no round key (final PASS)
    has_eval = any(h.get('event') == 'eval_completed' and (h.get('round') == r or (r == max_round and 'round' not in h)) for h in history)
    if not has_impl:
        print(f'WARN: round {r} missing implementation_completed — 补齐: python3 -c ... append history')
    if not has_eval:
        print(f'WARN: round {r} missing eval_completed — 补齐: bash solar-harness.sh eval-verdict $sid pass/fail')
" 2>/dev/null | while IFS= read -r line; do
    log "[verify] $line"
    ((issues++))
  done

  if (( issues == 0 )); then
    ok "verify-events: $sid — 一致 (0 issues)"
  else
    log "verify-events: $sid — ${issues} issues, ${fixed} fixed"
  fi
}

# ---- Main ----

# ---- Capsule / Ledger (sprint-20260503-163542 D5) ----

CAPSULE_FIELDS=("goal" "facts_established" "changes_made" "risks" "open_questions" "required_next_action" "recursion_round" "topology")

do_capsule_show() {
  local sid="$1"
  local sf="$SPRINTS_DIR/${sid}.status.json"
  rs_exists "$sid" || { err "Sprint not found: $sid"; exit 1; }

  local topology round mode
  topology=$(rs_read_field "$sid" "topology")
  [[ -z "$topology" ]] && topology="standard"
  round=$(rs_read_field "$sid" "round")
  [[ -z "$round" ]] && round="0"
  mode=$(rs_read_field "$sid" "mode")
  [[ -z "$mode" ]] && mode="balanced"

  echo "=== Capsule: $sid ==="
  echo "topology: $topology"
  echo "recursion_round: $round"
  echo "mode: $mode"

  # Extract 8 fields from plan/handoff/eval files
  for doc in plan handoff eval; do
    local f="$SPRINTS_DIR/${sid}.${doc}.md"
    [[ -f "$f" ]] || continue
    echo ""
    echo "--- from ${doc}.md ---"
    for field in "${CAPSULE_FIELDS[@]}"; do
      local field_title
      field_title=$(echo "$field" | sed 's/_/ /g')
      # Try ## Section header format (case-insensitive via awk)
      local val
      val=$(awk -v pat="$field_title" 'BEGIN{IGNORECASE=1} tolower($0) ~ "^##+ *"tolower(pat)" *$"{found=1; next} found && /^##+/{exit} found && NF{print}' "$f" | head -3)
      if [[ -z "$val" ]]; then
        # Try yaml frontmatter
        val=$(grep -i "^${field}:" "$f" 2>/dev/null | head -1 | sed "s/^[^:]*:[[:space:]]*//")
      fi
      [[ -n "$val" ]] && echo "  $field: $val"
    done
  done
  echo ""
}

do_ledger_show() {
  local sid="$1"
  type ledger_events_for_sid &>/dev/null || { err "bridge-ledger.sh not loaded"; exit 1; }
  echo "=== Ledger: $sid ==="
  local events
  events=$(ledger_events_for_sid "$sid")
  if [[ -z "$events" ]]; then
    echo "(no events)"
  else
    echo "$events" | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        print(f\"  {d.get('ts','')} [{d.get('event','')}] {d.get('artifact','')}\" + (' → ' + d.get('verdict','') if 'verdict' in d else ''))
    except: pass
"
  fi
}

# ---- Update Contract (Sprint 20260420-082442, D4: 从 case 分支提取为函数) ----

do_update_contract() {
  local usid="${2:-}" section="${3:-}" content="${4:-}"
  if [[ -z "$usid" ]] || [[ -z "$section" ]] || [[ -z "$content" ]]; then
    usid=$(ls "$SPRINTS_DIR"/*.status.json 2>/dev/null | sort | tail -1 | xargs -I{} python3 -c "import json; print(json.load(open('{}'))['id'])" 2>/dev/null)
    [[ -z "$usid" ]] && { err "无活跃 Sprint"; exit 1; }
    err "用法: $0 update-contract <sprint-id> done \"- [ ] 条件1\n- [ ] 条件2\""
    log "当前 Sprint: $usid"
    exit 2
  fi
  local cfile="$SPRINTS_DIR/${usid}.contract.md"
  [[ -f "$cfile" ]] || { err "合约不存在: $cfile"; exit 1; }

  case "$section" in
    done)
      # D7: 用 base64 编码避免 HEREDOC 特殊字符吞参数 (Sprint 20260423-062851)
      local encoded
      encoded=$(printf '%s' "$content" | solar_base64_one_line)
      python3 -c "
import re, base64, sys
content = open('$cfile').read()
new_done = base64.b64decode('$encoded').decode('utf-8')
pattern = r'(## (?:Done 定义|Definition of Done)\n\n(?:>.*?\n\n)?)(.*?)(\n## )'
def replacer(m):
    return m.group(1) + new_done + '\n\n' + m.group(3)
result = re.sub(pattern, replacer, content, flags=re.DOTALL)
if result == content:
    print('Warning: update-contract regex did not match, contract unchanged', file=sys.stderr)
    sys.exit(1)
open('$cfile', 'w').write(result)
print('Done 定义已更新')
" 2>/dev/null
      ok "合约更新: $cfile"
      ;;
    scope)
      local encoded
      encoded=$(printf '%s' "$content" | solar_base64_one_line)
      python3 -c "
import re, base64
content = open('$cfile').read()
new_scope = base64.b64decode('$encoded').decode('utf-8')
pattern = r'(## 范围\n\n)(.*?)(\n## )'
def replacer(m):
    return m.group(1) + new_scope + '\n\n' + m.group(3)
result = re.sub(pattern, replacer, content, flags=re.DOTALL)
open('$cfile', 'w').write(result)
" 2>/dev/null
      ok "范围已更新"
      ;;
    constraints)
      local encoded
      encoded=$(printf '%s' "$content" | solar_base64_one_line)
      python3 -c "
import re, base64
content = open('$cfile').read()
new_c = base64.b64decode('$encoded').decode('utf-8')
pattern = r'(## 约束\n\n>.*?\n\n)(.*?)(\n## )'
def replacer(m):
    return m.group(1) + new_c + '\n\n' + m.group(3)
result = re.sub(pattern, replacer, content, flags=re.DOTALL)
open('$cfile', 'w').write(result)
" 2>/dev/null
      ok "约束已更新"
      ;;
    *)
      err "未知 section: $section (支持: done, scope, constraints)"
      ;;
  esac
}

# Sprint 20260420-090726 D2: 僵尸 cancelled 文件清理
do_clean_corrupted() {
  local apply="${1:-}"
  local qdir="$SPRINTS_DIR/.quarantine/$(date +%Y-%m-%d)"
  local count=0

  echo "扫描僵尸文件..."
  for f in "$SPRINTS_DIR"/sprint-*.status.json; do
    [[ -f "$f" ]] || continue
    local fid
    fid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
    if [[ -z "$fid" ]]; then
      ((count++))
      echo "  僵尸: $(basename "$f")"
      if [[ "$apply" == "--apply" ]]; then
        mkdir -p "$qdir"
        mv "$f" "$qdir/"
        mkdir -p "$SPRINTS_DIR/.quarantine"
        echo "- $(basename "$f") | id为空 | $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$SPRINTS_DIR/.quarantine/MANIFEST.md"
      fi
    fi
  done

  if [[ "$apply" != "--apply" ]]; then
    echo "共 ${count} 个僵尸文件 (dry-run, 用 --apply 执行)"
  else
    echo "已隔离 ${count} 个僵尸文件到 .quarantine/"
  fi
}

# sprint-20260503-195627 D3: telemetry stats
TELEMETRY_FILE="${HARNESS_DIR}/telemetry/runs.jsonl"

do_stats_overview() {
  [[ -f "$TELEMETRY_FILE" ]] || { echo "无 telemetry 数据"; return 0; }
  python3 - "$TELEMETRY_FILE" <<'PY'
import json, sys
from collections import Counter
tf = sys.argv[1]
runs = []
with open(tf) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: runs.append(json.loads(line))
        except: pass
if not runs:
    print("无 telemetry 数据"); sys.exit(0)
total = len(runs)
passed = sum(1 for r in runs if r.get("verdict") == "passed")
failed = total - passed
avg_rounds = sum(r.get("rounds", 0) for r in runs) / total
durations = [r.get("duration_sec", 0) for r in runs if r.get("duration_sec", 0) > 0]
avg_dur = sum(durations) / len(durations) if durations else 0
print(f"总览 (最近 {total} 个 sprint 终态)")
print(f"  总数: {total}  |  通过: {passed}  |  失败: {failed}  |  通过率: {passed/total*100:.1f}%")
print(f"  平均轮次: {avg_rounds:.1f}  |  平均耗时: {avg_dur:.0f}s")
print()
topos = {}
for r in runs:
    t = r.get("topology", "standard")
    if t not in topos:
        topos[t] = {"total": 0, "passed": 0, "rounds": [], "dur": []}
    topos[t]["total"] += 1
    if r.get("verdict") == "passed":
        topos[t]["passed"] += 1
    topos[t]["rounds"].append(r.get("rounds", 0))
    d = r.get("duration_sec", 0)
    if d > 0: topos[t]["dur"].append(d)
print("各拓扑通过率:")
for t in sorted(topos.keys()):
    v = topos[t]
    rate = v["passed"] / v["total"] * 100 if v["total"] else 0
    ar = sum(v["rounds"]) / len(v["rounds"]) if v["rounds"] else 0
    ad = sum(v["dur"]) / len(v["dur"]) if v["dur"] else 0
    print(f"  {t:15s}  {v['passed']}/{v['total']}  ({rate:5.1f}%)  avg {ar:.1f}轮  {ad:.0f}s")
fail_counter = Counter()
for r in runs:
    for d in r.get("fail_dones", []):
        fail_counter[d] += 1
if fail_counter:
    print()
    print("Top 5 最常 FAIL 的 Done:")
    for done, cnt in fail_counter.most_common(5):
        print(f"  {done}: {cnt} 次")
PY
}

do_stats_topology() {
  local name="$1"
  [[ -z "$name" ]] && { err "用法: solar-harness stats topology <name>"; exit 2; }
  [[ -f "$TELEMETRY_FILE" ]] || { echo "无 telemetry 数据"; return 0; }
  python3 - "$TELEMETRY_FILE" "$name" <<'PY'
import json, sys
tf, name = sys.argv[1:]
runs = []
with open(tf) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: runs.append(json.loads(line))
        except: pass
filtered = [r for r in runs if r.get("topology") == name]
if not filtered:
    print(f"无 topology={name} 的数据"); sys.exit(0)
total = len(filtered)
passed = sum(1 for r in filtered if r.get("verdict") == "passed")
avg_r = sum(r.get("rounds", 0) for r in filtered) / total
durs = [r.get("duration_sec", 0) for r in filtered if r.get("duration_sec", 0) > 0]
avg_d = sum(durs) / len(durs) if durs else 0
print(f"拓扑: {name}")
print(f"  总数: {total}  |  通过: {passed}  |  通过率: {passed/total*100:.1f}%")
print(f"  平均轮次: {avg_r:.1f}  |  平均耗时: {avg_d:.0f}s")
print()
print("最近 runs:")
for r in filtered[-10:]:
    v = r.get("verdict", "?")
    s = r.get("sid", "?")[:20]
    print(f"  {s}  round={r.get('rounds',0)}  {v}  {r.get('duration_sec',0):.0f}s")
PY
}

do_stats_sprint() {
  local sid="$1"
  [[ -z "$sid" ]] && { err "用法: solar-harness stats sprint <sid>"; exit 2; }
  [[ -f "$TELEMETRY_FILE" ]] || { echo "无 telemetry 数据"; return 0; }
  python3 - "$TELEMETRY_FILE" "$sid" <<'PY'
import json, sys
tf, sid = sys.argv[1:]
with open(tf) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            r = json.loads(line)
            if r.get("sid") == sid:
                for k, v in r.items():
                    print(f"  {k}: {v}")
                sys.exit(0)
        except: pass
print(f"未找到 sid={sid} 的 telemetry 记录")
PY
}

# sprint-20260520-203709 N5: refresh CLI bridge.
# Bash wrapper that exec's the orchestrator python module; passthrough exit
# code so callers (and tests) see the real refresh.run.v1 exit_code.
#
# Help-only fast path: `refresh -h | --help | help` returns a static usage
# block that names the deeper alternatives (reload / wiki rebuild / wiki
# qmd-embed) so users picking the wrong tool can self-correct.
do_refresh() {
  case "${1:-}" in
    -h|--help|help)
      cat <<'REFRESH_HELP'
solar-harness refresh — read-only multi-source status view

Usage:
  solar-harness refresh [--scope CSV] [--json] [--deep] [--timeout N]

Flags:
  --scope CSV    status,sprints,dashboards,autopilot,kb,all   (default: all)
  --json         emit refresh.run.v1 JSON; suppresses table render
  --deep         opt-in heavier probes; budget extends to 30s
  --timeout N    override budget seconds (0..30; meaningful with --deep)
  -h, --help     this help text

Exit codes:
  0  all sources ok
  1  >=1 source error
  2  >=1 source degraded (no error)
  3  all sources skipped

See also (heavier ops — NOT what refresh does):
  solar-harness reload          coordinator hot-reload (re-source config)
  solar-harness wiki rebuild    full knowledge-base rebuild
  solar-harness wiki qmd-embed  process embedding backlog
REFRESH_HELP
      return 0
      ;;
  esac
  human_prefix "refresh" "$@"
  ( cd "${HARNESS_DIR%/harness}" && exec python3 -m harness.lib.refresh.orchestrator "$@" )
}

pane_hygiene_field() {
  local pane="$1" field="$2" registry="${HARNESS_DIR}/run/pane-hygiene.json"
  [[ -f "$registry" ]] || return 1
  python3 - "$registry" "$pane" "$field" <<'PY' 2>/dev/null || return 1
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
entry = data.get(sys.argv[2]) if isinstance(data, dict) else None
if not isinstance(entry, dict):
    raise SystemExit(1)
value = entry.get(sys.argv[3], "")
print("" if value is None else value)
PY
}

display_role_label() {
  case "${1:-}" in
    pm) printf '%s' "PM" ;;
    planner) printf '%s' "Planner" ;;
    builder) printf '%s' "Builder" ;;
    evaluator) printf '%s' "Evaluator" ;;
    architect) printf '%s' "Architect" ;;
    observer) printf '%s' "Observer" ;;
    *) printf '%s' "${1:-N/A}" ;;
  esac
}

pane_host_role() {
  local pane="$1" title="${2:-}" role
  role="$(pane_hygiene_field "$pane" "pane_role" 2>/dev/null || true)"
  if [[ -n "$role" ]]; then
    printf '%s' "$role"
    return 0
  fi
  local base lowered
  base="${title%%|*}"
  lowered="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')"
  if [[ "$pane" == "$SESSION_NAME:0.0" && ( "$lowered" == *"pm"* || "$base" == *"产品经理"* ) ]]; then
    printf '%s' "pm"
  elif [[ "$lowered" == *"planner"* || "$base" == *"规划者"* ]]; then
    printf '%s' "planner"
  elif [[ "$lowered" == *"evaluator"* || "$base" == *"审判官"* ]]; then
    printf '%s' "evaluator"
  elif [[ "$lowered" == *"architect"* || "$base" == *"架构师"* ]]; then
    printf '%s' "architect"
  elif [[ "$lowered" == *"observer"* || "$base" == *"观察"* ]]; then
    printf '%s' "observer"
  else
    printf '%s' "builder"
  fi
}

do_main_status() {
  printf '%s\n' "Solar Harness Main Status"
  printf '%s\n' "host role / hygiene / runtime / assignment / artifact are separate signals."
  local physical_panes
  physical_panes="$(product_delivery_pane_count 2>/dev/null || printf '0')"
  if [[ "$physical_panes" == "$EXPECTED_PRODUCT_DELIVERY_PANES" ]]; then
    printf '%s\n' "layout: ok expected=${EXPECTED_PRODUCT_DELIVERY_PANES} actual=${physical_panes}"
  else
    printf '%s\n' "layout: error expected=${EXPECTED_PRODUCT_DELIVERY_PANES} actual=${physical_panes}"
  fi
  local route_out route_rc route_status
  route_out="$(models_live_route_check 2>&1)" || route_rc=$?
  route_rc="${route_rc:-0}"
  route_status="ok"
  [[ "$route_rc" -eq 1 ]] && route_status="error"
  [[ "$route_rc" -eq 2 ]] && route_status="warn"
  printf '%s\n' "route: ${route_status} $(printf '%s' "$route_out" | tail -1)"
  printf '%s\n' ""
  # AP-3: benchmark banner (one line before status table)
  local _bench_banner
  _bench_banner="$(python3 -c 'from harness.lib.benchmark.orchestration.status_banner import render_banner; print(render_banner())' 2>/dev/null)" || _bench_banner="Benchmark: no recent benchmark run"
  printf '%s\n' "$_bench_banner"
  printf '%s\n' ""
  printf '┌────────────┬────────────┬──────────────┬──────────────┬────────────────────────────┬─────────────────────┬────────────────────────────┐\n'
  printf '│ Pane       │ Host Role  │ Hygiene      │ Runtime      │ Assignment                 │ Artifact            │ Title                      │\n'
  printf '├────────────┼────────────┼──────────────┼──────────────┼────────────────────────────┼─────────────────────┼────────────────────────────┤\n'

  local i pane role title tail runtime assignment sid artifact file host_role hygiene_state artifact_role
  for i in 0 1 2 3; do
    pane="$SESSION_NAME:0.$i"
    case "$i" in
      0) role="PM" ;;
      1) role="Planner" ;;
      2) role="Builder" ;;
      3) role="Evaluator" ;;
    esac
    title="N/A"; runtime="missing"; assignment="N/A"; artifact="N/A"; hygiene_state="missing"

    if tmux display-message -p -t "$pane" '#{pane_id}' >/dev/null 2>&1; then
      title=$(tmux display-message -p -t "$pane" '#{pane_title}' 2>/dev/null || echo "N/A")
      tail=$(tmux capture-pane -t "$pane" -p -S -40 2>/dev/null | tail -40 || true)
      local recent_tail
      recent_tail="$(printf '%s\n' "$tail" | sed '/^[[:space:]]*$/d' | tail -12)"
      if printf '%s\n' "$tail" | grep -q '❯' && \
         printf '%s\n' "$recent_tail" | grep -qE '\? for shortcuts|new task\? /clear|bypass permissions|shift\+tab to cycle' && \
         ! printf '%s\n' "$recent_tail" | grep -qE 'esc to interrupt|Press up to edit queued messages'; then
        runtime="idle"
      elif printf '%s\n' "$recent_tail" | grep -qiE 'Generating|thinking|Thinking|Hmm|Reading|Bash|Write|Edit|Update|Inferring|Hatching|Whirlpooling|Enchanting|Meandering|Philosophising|Brewing|Baking|Calculating|Percolating|Marinating|Befuddling|Clauding|Computing|Cooking|Billowing|Frosting|Discombobulating|Levitating|Cultivating|Twisting|Perambulating|Jitterbugging|Transfiguring|Cogitating|Channeling|Fluttering|Fiddle-faddling|Warping|Vibing|Whirring|Cascading|Razzmatazzing|Transmuting|Bootstrapping|Churned|Compacting conversation|Press up to edit queued messages'; then
        runtime="active"
      else
        runtime="idle"
      fi
    fi
    host_role="$(pane_host_role "$pane" "$title")"
    hygiene_state="$(pane_hygiene_field "$pane" "state" 2>/dev/null || printf '%s' "$hygiene_state")"

    if [[ -f "$HARNESS_DIR/.pane-assignments" ]]; then
      assignment=$(awk -F'[=:]' -v p="$pane" '$1":"$2 == p {print $3}' "$HARNESS_DIR/.pane-assignments" 2>/dev/null | tail -1)
      [[ -z "$assignment" ]] && assignment="N/A"
    fi

    sid="$assignment"
    if [[ "$sid" != "N/A" ]]; then
      artifact_role="$(display_role_label "$host_role")"
      case "$artifact_role" in
        PM)
          file="$SPRINTS_DIR/${sid}.prd.md"
          [[ -f "$file" ]] || file="$SPRINTS_DIR/${sid}.product-brief.md"
          ;;
        Planner) file="$SPRINTS_DIR/${sid}.plan.md" ;;
        Builder) file="$SPRINTS_DIR/${sid}.handoff.md" ;;
        Evaluator) file="$SPRINTS_DIR/${sid}.eval.md" ;;
      esac
      if [[ -f "$file" ]]; then
        artifact=$(solar_file_mtime_human "$file" 2>/dev/null || echo "present")
      else
        artifact="missing"
      fi
    fi

    printf '│ %-10s │ %-10s │ %-12s │ %-12s │ %-26s │ %-19s │ %-26s │\n' \
      "pane$i" "$(display_role_label "$host_role")" "$hygiene_state" "$runtime" "$(printf '%.26s' "$assignment")" "$(printf '%.19s' "$artifact")" "$(printf '%.26s' "$title")"
  done

  printf '└────────────┴────────────┴──────────────┴──────────────┴────────────────────────────┴─────────────────────┴────────────────────────────┘\n'
}

do_lab_status() {
  local sid="${1:-}"
  local lab_dir="$SPRINTS_DIR"
  [[ -n "$sid" ]] && lab_dir="$SPRINTS_DIR/${sid#sprint-20260507-obsidian-wiki}"
  # Current Obsidian Wiki lab uses a fixed sidecar directory. Keep this generic
  # enough for operators while making artifact-vs-runtime status explicit.
  if [[ -d "$SPRINTS_DIR/obsidian-wiki-lab" ]]; then
    lab_dir="$SPRINTS_DIR/obsidian-wiki-lab"
  fi

  printf '%s\n' "Solar Harness Lab Status"
  printf '%s\n' "artifact != runtime: handoff files prove delivery; pane state proves current activity."
  printf '%s\n' ""
  printf '┌───────────────┬──────────────┬──────────────┬─────────────────────┬────────────────────────────┐\n'
  printf '│ Pane          │ Runtime      │ Artifact     │ Latest Handoff      │ Title                      │\n'
  printf '├───────────────┼──────────────┼──────────────┼─────────────────────┼────────────────────────────┤\n'

  local i pane title tail runtime artifact latest latest_ts
  for i in 0 1 2 3; do
    pane="$LAB_SESSION_NAME:0.$i"
    title="N/A"
    runtime="missing"
    artifact="missing"
    latest_ts="N/A"
    if tmux display-message -p -t "$pane" '#{pane_id}' >/dev/null 2>&1; then
      title=$(tmux display-message -p -t "$pane" '#{pane_title}' 2>/dev/null || echo "N/A")
      tail=$(tmux capture-pane -t "$pane" -p -S -40 2>/dev/null | tail -40 || true)
      local recent_tail
      recent_tail="$(printf '%s\n' "$tail" | sed '/^[[:space:]]*$/d' | tail -12)"
      if printf '%s\n' "$tail" | grep -q '❯' && \
         printf '%s\n' "$recent_tail" | grep -qE '\? for shortcuts|new task\? /clear|bypass permissions|shift\+tab to cycle' && \
         ! printf '%s\n' "$recent_tail" | grep -qE 'esc to interrupt|Press up to edit queued messages'; then
        runtime="idle"
      elif printf '%s\n' "$recent_tail" | grep -qiE 'Generating|thinking|Thinking|Hmm|Reading|Bash|Write|Edit|Update|Inferring|Hatching|Whirlpooling|Enchanting|Meandering|Philosophising|Brewing|Baking|Calculating|Percolating|Marinating|Befuddling|Clauding|Computing|Cooking|Billowing|Frosting|Discombobulating|Levitating|Cultivating|Compacting conversation|Press up to edit queued messages'; then
        runtime="active"
      else
        runtime="idle"
      fi
    fi

    latest=$(ls -t "$lab_dir"/lab-builder-$((i+1))*handoff.md 2>/dev/null | head -1 || true)
    if [[ -n "$latest" && -f "$latest" ]]; then
      artifact="present"
      latest_ts=$(solar_file_mtime_human "$latest" 2>/dev/null || echo "N/A")
    fi
    printf '│ %-13s │ %-12s │ %-12s │ %-19s │ %-26s │\n' \
      "lab-builder-$((i+1))" "$runtime" "$artifact" "$latest_ts" "$(printf '%.26s' "$title")"
  done

  printf '└───────────────┴──────────────┴──────────────┴─────────────────────┴────────────────────────────┘\n'
}

models_live_route_check() {
  if ! command -v tmux >/dev/null 2>&1; then
    printf 'skipped: tmux unavailable\n'
    return 2
  fi
  if ! tmux_has_exact_session "$SESSION_NAME"; then
    printf 'skipped: session %s unavailable\n' "$SESSION_NAME"
    return 2
  fi

  local panes pane_count errors checked
  panes="$(tmux list-panes -t "$SESSION_NAME:0" -F '#{pane_index} #{pane_id}' 2>/dev/null || true)"
  pane_count="$(printf '%s\n' "$panes" | awk 'NF {n++} END {print n+0}')"
  if [[ "$pane_count" -lt "$EXPECTED_PRODUCT_DELIVERY_PANES" ]]; then
    printf 'error: live layout has %s panes, expected %s\n' "$pane_count" "$EXPECTED_PRODUCT_DELIVERY_PANES"
    return 1
  fi

  errors=0
  checked=0
  local index pane_id pane_safe persona configured expected_flag marker tail_text
  for index in 0 1 2 3; do
    case "$index" in
      0) persona="pm" ;;
      1) persona="planner" ;;
      2) persona="builder" ;;
      3) persona="evaluator" ;;
    esac
    pane_id="$(printf '%s\n' "$panes" | awk -v idx="$index" '$1 == idx {print $2; exit}')"
    if [[ -z "$pane_id" ]]; then
      printf 'error: missing pane index %s\n' "$index"
      errors=$((errors + 1))
      continue
    fi
    checked=$((checked + 1))

    configured="$(solar_persona_model "$persona" 2>/dev/null || printf 'N/A')"
    expected_flag="$(solar_model_flag "$configured" 2>/dev/null || true)"
    pane_safe="${pane_id//[^A-Za-z0-9_.-]/_}"
    marker="$HARNESS_DIR/run/pane-env/${pane_safe}.json"
    if [[ -f "$marker" && -n "$expected_flag" ]]; then
      local marker_flag
      marker_flag="$(python3 - "$marker" <<'PY' 2>/dev/null || true
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("model_flag", ""))
PY
)"
      if [[ -n "$marker_flag" && "$marker_flag" != "$expected_flag" ]]; then
        printf 'error: pane%d %s marker model_flag=%s expected=%s\n' "$index" "$persona" "$marker_flag" "$expected_flag"
        errors=$((errors + 1))
      fi
    fi

    tail_text="$(tmux capture-pane -t "$SESSION_NAME:0.$index" -p -S -80 2>/dev/null | tail -80 || true)"
    if [[ "$configured" == "claude-opus" && "$tail_text" == *"API Usage Billing"* ]]; then
      printf 'error: pane%d %s configured Opus but live banner is API Usage Billing\n' "$index" "$persona"
      errors=$((errors + 1))
    fi
    if [[ "$tail_text" == *"API Error: 400"* && "$tail_text" == *"1210"* ]]; then
      if [[ "$tail_text" == *"API Usage Billing"* ]]; then
        printf 'error: pane%d %s live output contains API Usage Billing plus API 400 code=1210\n' "$index" "$persona"
      else
        printf 'error: pane%d %s live output contains API 400 code=1210\n' "$index" "$persona"
      fi
      errors=$((errors + 1))
    fi
  done

  if [[ "$errors" -gt 0 ]]; then
    printf 'checked=%s errors=%s\n' "$checked" "$errors"
    return 1
  fi
  printf 'checked=%s errors=0\n' "$checked"
  return 0
}

do_models_command() {
  local subcmd="${1:-show}"
  shift || true
  case "$subcmd" in
    show|status)
      local matrix label source pm_model planner_model builder_model evaluator_model
      matrix="$(solar_lab_builder_matrix)"
      label="$(solar_lab_builder_matrix_label "$matrix")"
      pm_model="$(solar_persona_model pm)"
      planner_model="$(solar_persona_model planner)"
      builder_model="$(solar_persona_model builder)"
      evaluator_model="$(solar_persona_model evaluator)"
      if [[ -n "${SOLAR_LAB_BUILDER_MODEL_MATRIX:-}" ]]; then
        source="env:SOLAR_LAB_BUILDER_MODEL_MATRIX"
      else
        source="$SOLAR_USER_CONFIG"
      fi
      printf '┌────────────────────┬──────────────────────────────────────────────┐\n'
      printf '│ %-18s │ %-44s │\n' "配置项" "当前值"
      printf '├────────────────────┼──────────────────────────────────────────────┤\n'
      printf '│ %-18s │ %-44s │\n' "main pm" "$(printf '%.44s' "$pm_model")"
      printf '│ %-18s │ %-44s │\n' "main planner" "$(printf '%.44s' "$planner_model")"
      printf '│ %-18s │ %-44s │\n' "main builder" "$(printf '%.44s' "$builder_model")"
      printf '│ %-18s │ %-44s │\n' "main evaluator" "$(printf '%.44s' "$evaluator_model")"
      printf '│ %-18s │ %-44s │\n' "lab matrix" "$(printf '%.44s' "$matrix")"
      printf '│ %-18s │ %-44s │\n' "显示" "$(printf '%.44s' "$label")"
      printf '│ %-18s │ %-44s │\n' "来源" "$(printf '%.44s' "$source")"
      printf '└────────────────────┴──────────────────────────────────────────────┘\n'
      ;;
    set-main)
      local alias="${1:-}"
      [[ -n "$alias" ]] || { err "用法: $0 models set-main <opus|anthropic-sonnet> [--apply]"; exit 2; }
      solar_set_main_model "$alias"
      ok "已写入主屏模型: pm/planner/builder/evaluator -> $alias"
      if [[ "${2:-}" == "--apply" ]]; then
        apply_product_delivery_models
        ok "已按配置刷新 Product Delivery 四分屏"
      else
        log "生效方式: solar-harness models apply-main 或重启 solar-harness"
      fi
      ;;
    apply-main)
      apply_product_delivery_models
      ;;
    set-lab-matrix)
      local matrix="${1:-}"
      [[ -n "$matrix" ]] || { err "用法: $0 models set-lab-matrix <matrix> [--apply]"; exit 2; }
      solar_set_lab_builder_matrix "$matrix"
      ok "已写入 lab builder 模型矩阵: $matrix"
      if [[ "${2:-}" == "--apply" ]]; then
        ensure_parallel_builder_lab "$(pwd)"
        ok "已按配置刷新 Builder Lab"
      else
        log "生效方式: solar-harness models apply-lab 或重新运行 solar-harness extend"
      fi
      ;;
    apply-lab)
      ensure_parallel_builder_lab "$(pwd)"
      ;;
    refresh-labels)
      configure_product_delivery_labels
      configure_builder_lab_labels
      ;;
    doctor)
      local guard="$HARNESS_DIR/tests/test-model-registry-guard.sh"
      local single="$HARNESS_DIR/tests/test-model-config-single-source.sh"
      local live_out guard_out single_out live_rc guard_rc single_rc overall live_status
      live_out="$(mktemp)"
      guard_out="$(mktemp)"
      single_out="$(mktemp)"
      live_rc=0
      guard_rc=0
      single_rc=0
      models_live_route_check >"$live_out" 2>&1 || live_rc=$?
      bash "$guard" >"$guard_out" 2>&1 || guard_rc=$?
      bash "$single" >"$single_out" 2>&1 || single_rc=$?
      overall="ok"
      [[ "$guard_rc" -eq 0 && "$single_rc" -eq 0 && "$live_rc" -ne 1 ]] || overall="error"
      live_status="ok"
      [[ "$live_rc" -eq 1 ]] && live_status="error"
      [[ "$live_rc" -eq 2 ]] && live_status="warn"
      printf '┌──────────────────────────────┬────────┬────────────────────────────────────┐\n'
      printf '│ %-28s │ %-6s │ %-34s │\n' "检查项" "状态" "证据"
      printf '├──────────────────────────────┼────────┼────────────────────────────────────┤\n'
      printf '│ %-28s │ %-6s │ %-34s │\n' "live pane route" "$live_status" "$(tail -1 "$live_out" | cut -c1-34)"
      printf '│ %-28s │ %-6s │ %-34s │\n' "registry guard" "$([[ "$guard_rc" -eq 0 ]] && echo ok || echo error)" "$(tail -1 "$guard_out" | cut -c1-34)"
      printf '│ %-28s │ %-6s │ %-34s │\n' "model config single source" "$([[ "$single_rc" -eq 0 ]] && echo ok || echo error)" "$(tail -1 "$single_out" | cut -c1-34)"
      printf '│ %-28s │ %-6s │ %-34s │\n' "overall" "$overall" "$SOLAR_USER_CONFIG"
      printf '└──────────────────────────────┴────────┴────────────────────────────────────┘\n'
      if [[ "$overall" != "ok" ]]; then
        err "models doctor failed"
        printf '\n--- live pane route ---\n'
        cat "$live_out"
        printf '\n--- registry guard ---\n'
        cat "$guard_out"
        printf '\n--- model config ---\n'
        cat "$single_out"
        rm -f "$live_out" "$guard_out" "$single_out"
        return 1
      fi
      rm -f "$live_out" "$guard_out" "$single_out"
      ;;
    help|--help|-h)
      echo "Solar Harness Models"
      echo ""
      echo "Usage:"
      echo "  $0 models show"
      echo "  $0 models doctor"
      echo "  $0 models set-main opus [--apply]"
      echo "  $0 models set-main anthropic-sonnet [--apply]"
      echo "  $0 models apply-main"
      echo "  $0 models set-lab-matrix glm,glm,glm,anthropic-sonnet [--apply]"
      echo "  $0 models apply-lab"
      echo "  $0 models refresh-labels"
      ;;
    *)
      err "Unknown models subcommand: $subcmd"; exit 2
      ;;
  esac
}

do_runtime_selector_command() {
  local subcmd="${1:-show}"
  shift || true
  case "$subcmd" in
    show|selector|pane)
      local cfg_runtime cfg_source cfg_search cfg_effort effective
      cfg_runtime="$(solar_config_json_get "runtime" "" 2>/dev/null || true)"
      cfg_source="$SOLAR_USER_CONFIG"
      cfg_search="$(solar_config_json_get "codex.search" "true" 2>/dev/null || echo true)"
      cfg_effort="$(solar_config_json_get "codex.effort" "medium" 2>/dev/null || echo medium)"
      effective="${SOLAR_PANE_RUNTIME:-claude}"
      [[ -n "$cfg_runtime" ]] || cfg_runtime="(unset -> claude)"
      printf '┌────────────────────┬──────────────────────────────────────────────┐\n'
      printf '│ %-18s │ %-44s │\n' "配置项" "当前值"
      printf '├────────────────────┼──────────────────────────────────────────────┤\n'
      printf '│ %-18s │ %-44s │\n' "effective runtime" "$(printf '%.44s' "$effective")"
      printf '│ %-18s │ %-44s │\n' "config runtime" "$(printf '%.44s' "$cfg_runtime")"
      printf '│ %-18s │ %-44s │\n' "codex.search" "$(printf '%.44s' "$cfg_search")"
      printf '│ %-18s │ %-44s │\n' "codex.effort" "$(printf '%.44s' "$cfg_effort")"
      printf '│ %-18s │ %-44s │\n' "来源" "$(printf '%.44s' "$cfg_source")"
      printf '└────────────────────┴──────────────────────────────────────────────┘\n'
      ;;
    use|set|select)
      local runtime="${1:-}"
      shift || true
      case "$runtime" in
        claude|codex) ;;
        *) err "用法: $0 runtime use <claude|codex>"; exit 2 ;;
      esac
      solar_config_json_set "runtime" "$runtime"
      if [[ "$runtime" == "codex" ]]; then
        [[ -n "$(solar_config_json_get "codex.search" "" 2>/dev/null || true)" ]] || solar_config_json_set "codex.search" "true"
        [[ -n "$(solar_config_json_get "codex.effort" "" 2>/dev/null || true)" ]] || solar_config_json_set "codex.effort" "medium"
      fi
      ok "已写入 pane runtime: $runtime"
      log "配置文件: $SOLAR_USER_CONFIG"
      log "运行中的 panes 不会热切换；重启 cockpit 后生效。"
      ;;
    help|--help|-h)
      echo "Solar Pane Runtime Selector"
      echo ""
      echo "Usage:"
      echo "  $0 runtime show"
      echo "  $0 runtime use codex"
      echo "  $0 runtime use claude"
      echo ""
      echo "Session-only override:"
      echo "  SOLAR_PANE_RUNTIME=codex $0 start [workdir]"
      ;;
    *)
      return 64
      ;;
  esac
}

do_autosci_command() {
  local script_harness_dir shim py candidate command_text
  load_workdir_dotenv "$(pwd)"
  script_harness_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  shim="$script_harness_dir/plugins/autosci/bin/autosci_skill_shim.py"
  if [[ ! -f "$shim" ]]; then
    shim="$HARNESS_DIR/plugins/autosci/bin/autosci_skill_shim.py"
  fi
  if [[ ! -f "$shim" ]]; then
    err "AutoSci shim not found: $HARNESS_DIR/plugins/autosci/bin/autosci_skill_shim.py"
    exit 1
  fi
  export HARNESS_DIR
  export SOLAR_AUTOSCI_OUTPUT_HARNESS="${SOLAR_AUTOSCI_OUTPUT_HARNESS:-$HARNESS_DIR}"
  export AUTOSCI_ARTIFACT_ROOT="${AUTOSCI_ARTIFACT_ROOT:-$HARNESS_DIR/artifacts/autosci}"
  export SCIENTIFIC_ARTIFACT_ROOT="${SCIENTIFIC_ARTIFACT_ROOT:-$HARNESS_DIR/artifacts/scientific}"

  py=""
  for candidate in "$HARNESS_DIR/bin/python3" "$script_harness_dir/bin/python3" python3; do
    if [[ "$candidate" == "python3" ]]; then
      command -v python3 >/dev/null 2>&1 || continue
    elif [[ ! -x "$candidate" ]]; then
      continue
    fi
    if "$candidate" -c 'import sys' >/dev/null 2>&1; then
      py="$candidate"
      break
    fi
  done
  if [[ -z "$py" ]]; then
    err "No usable python3 found for AutoSci shim"
    exit 1
  fi

  if [[ "$#" -eq 0 ]]; then
    "$py" "$shim" skills list
    return
  fi

  case "${1:-}" in
    skills|skill)
      "$py" "$shim" "$@"
      ;;
    *)
      command_text="$*"
      "$py" "$shim" text "$command_text"
      ;;
  esac
}

# ---- Main ----

# G4 UI-rung run 4: `start --skip-doctor` (no workdir) parsed the FLAG as the
# working directory — doctor ran and the cockpit aimed at a directory named
# '--skip-doctor'. Start args are order-independent now: flags are recognized
# anywhere, the first non-flag argument is the workdir, and unknown --flags
# never become a workdir.
normalize_start_args() {
  START_WORKDIR=""
  START_SKIP_DOCTOR=""
  START_CLEAN=""
  local _arg
  for _arg in "$@"; do
    case "$_arg" in
      --skip-doctor) START_SKIP_DOCTOR="--skip-doctor" ;;
      --clean)       START_CLEAN="--clean" ;;
      --*)           ;;
      "")            ;;
      *)             [[ -z "$START_WORKDIR" ]] && START_WORKDIR="$_arg" ;;
    esac
  done
  [[ -z "$START_WORKDIR" ]] && START_WORKDIR="$(pwd)"
  # the && above returns 1 when the workdir was provided; never leak that
  # non-zero status to set -e
  return 0
}

case "${1:-help}" in
  start)     shift || true; normalize_start_args "$@"; start_harness 3 "$START_WORKDIR" "$START_SKIP_DOCTOR" $START_CLEAN ;;
  2)         shift || true; normalize_start_args "$@"; start_harness 2 "$START_WORKDIR" "$START_SKIP_DOCTOR" $START_CLEAN ;;
  3)         shift || true; normalize_start_args "$@"; start_harness 3 "$START_WORKDIR" "$START_SKIP_DOCTOR" $START_CLEAN ;;
  debug-start-args) shift || true; normalize_start_args "$@"; echo "workdir=$START_WORKDIR skip=$START_SKIP_DOCTOR clean=$START_CLEAN"; exit 0 ;;
  status)    show_status ;;
  main-status) do_main_status ;;
  lab-status) do_lab_status "${2:-}" ;;
  preflight|launch-preflight) harness_launch_preflight ;;
  refresh)   shift || true; do_refresh "$@" ;;
  doctor)    bash "$HARNESS_DIR/doctor.sh" "${2:-}" ;;
  session)
    shift || true
    human_prefix "runtime" "session $*"
    python3 "$HARNESS_DIR/lib/session_tools.py" "$@"
    ;;
  verify-integrations|capability-e2e)
    _cap_fail=0
    for _cap_e2e in \
      "$HARNESS_DIR/tests/integrations/test-capability-plane-e2e.sh" \
      "$HARNESS_DIR/tests/integrations/test-expanded-capability-plane-e2e.sh" \
      "$HARNESS_DIR/tests/integrations/test-capability-fusion-benchmark.sh" \
      "$HARNESS_DIR/tests/integrations/test-platform-workflow-benchmark.sh"
    do
      [[ -f "$_cap_e2e" ]] || { err "capability E2E test not found: $_cap_e2e"; exit 1; }
      [[ -x "$_cap_e2e" ]] || chmod +x "$_cap_e2e" 2>/dev/null || true
      bash "$_cap_e2e" || _cap_fail=1
    done
    exit "$_cap_fail"
    ;;
  --skip-doctor) normalize_start_args "$@"; start_harness 3 "$START_WORKDIR" "--skip-doctor" $START_CLEAN ;;
  coord-status)
    # Sprint 20260420-082442 D2: 协调器状态诊断
    pidfile="$HARNESS_DIR/.coordinator.pid"
    running=false; stale_lock=false; pid=0; uptime_s=0
    if [[ -f "$pidfile" ]]; then
      pid=$(cat "$pidfile" 2>/dev/null)
      if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        running=true
        # 计算运行时间
        start_ts=$(ps -p "$pid" -o lstart= 2>/dev/null)
        if [[ -n "$start_ts" ]]; then
          start_epoch=$(solar_parse_epoch "%a %b %d %H:%M:%S %Y" "$start_ts" 2>/dev/null || date +%s)
          uptime_s=$(( $(date +%s) - start_epoch ))
        fi
      else
        stale_lock=true
      fi
    fi
    python3 -c "
import json
print(json.dumps({
    'running': '$running' == 'true',
    'pid': $pid,
    'uptime_s': $uptime_s,
    'stale_lock': '$stale_lock' == 'true'
}, indent=2))
" 2>/dev/null
    ;;
  # Sprint 20260420-090726 D2: 僵尸文件清理
  clean-corrupted)
    do_clean_corrupted "${2:-}"
    ;;
  queue-reap-stale)
    # Archive old terminal queue files whose events are already consumed.
    # This prevents consumed .jsonl/.lock residue from looking like live backlog.
    . "$HARNESS_DIR/lib/queue.sh"
    queue_archive_consumed_terminal "${2:-24}" "${3:-queue-reaper}"
    ;;
  kill|stop) kill_harness ;;
  扩展|extend) start_extension "${2:-$(pwd)}" ;;
  models) shift; do_models_command "$@" ;;
  autosci)
    shift || true
    do_autosci_command "$@"
    ;;
  \$*)
    do_autosci_command "$@"
    ;;
  research)
    shift || true
    python3 "$HARNESS_DIR/lib/research/cli.py" "$@"
    ;;
  browser)
    shift || true
    _browser_scope="${1:-}"
    if [[ "$_browser_scope" == "profile" ]]; then
      shift || true
      _browser_action="${1:-doctor}"
      shift || true
      case "$_browser_action" in
        doctor)
          python3 "$HARNESS_DIR/tools/browser_profile_control.py" doctor "$@"
          ;;
        init)
          python3 "$HARNESS_DIR/tools/browser_profile_control.py" profile-init "$@"
          ;;
        verify)
          python3 "$HARNESS_DIR/tools/browser_profile_control.py" profile-verify "$@"
          ;;
        recover)
          python3 "$HARNESS_DIR/tools/browser_profile_control.py" profile-recover "$@"
          ;;
        *)
          err "unknown browser profile subcommand: $_browser_action"
          exit 1
          ;;
      esac
    else
      err "unknown browser command: ${_browser_scope:-N/A}"
      exit 1
    fi
    ;;
  intake|request)
    shift || true
    intake_request "$@"
    ;;
  intent-gateway|intent)
    shift || true
    python3 "$HARNESS_DIR/lib/intent_gateway.py" "$@"
    ;;
  intent-consumer|intent-consume)
    shift || true
    python3 "$HARNESS_DIR/lib/intent_consumer.py" "$@"
    ;;
  bg)
    shift || true
    do_bg_command "$@"
    ;;
  tvs)
    shift || true
    _tvs_subcmd="${1:-render}"
    shift || true
    case "$_tvs_subcmd" in
      render)
        command -v bun >/dev/null 2>&1 || { err "bun not found; TVS renderer requires bun"; exit 1; }
        if [[ -z "${SOLAR_ROOT:-}" && -f "$HARNESS_DIR/../package.json" ]]; then
          export SOLAR_ROOT="$(cd "$HARNESS_DIR/.." && pwd)"
        fi
        if [[ -z "${SOLAR_TVS_ROOT:-}" ]]; then
          for _tvs_candidate in "$HARNESS_DIR/../../TVS" "$HOME/TVS" "$HOME/Solar/../TVS"; do
            if [[ -f "$_tvs_candidate/index.ts" ]]; then
              export SOLAR_TVS_ROOT="$(cd "$_tvs_candidate" && pwd)"
              break
            fi
          done
        fi
        bun run "$HARNESS_DIR/lib/tvs_render_cli.ts" render "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Harness TVS renderer"
        echo ""
        echo "Usage:"
        echo "  $0 tvs render [--mode auto|v1|v2] [--style NAME] [--width N] < payload.json"
        ;;
      *)
        err "Unknown tvs subcommand: $_tvs_subcmd"; exit 2
        ;;
    esac
    ;;
  multi-task)
    shift || true
    python3 "$HARNESS_DIR/lib/multi_task_runner.py" "$@"
    ;;
  sprint)
    shift || true
    [[ "$#" -eq 0 ]] && { err "用法: $0 sprint \"需求描述\""; exit 2; }
    intake_request --no-dispatch "$@"
    ;;
  attach)
    if tmux_has_exact_session "$SESSION_NAME"; then
      attach_or_print
    else
      err "未运行"
    fi
    ;;
  monitor)
    shift || true
    if [[ "${1:-}" == "tui" ]]; then
      shift || true
      if ! tmux_has_exact_session "$SESSION_NAME"; then
        err "Harness 未运行，先启动: $0"
        exit 1
      fi
      tmux new-window -t "$SESSION_NAME" -n "monitor" -c "$HOME"
      tmux send-keys -t "$SESSION_NAME:monitor" "bash $HARNESS_DIR/monitor.sh" Enter
      ok "monitor tui 已在独立窗口打开"
      log "Ctrl-b n 切到下一个窗口, Ctrl-b p 切回上一个"
    else
      python3 "$HARNESS_DIR/lib/remote_multi_task_monitor.py" "$@"
    fi
    ;;
  wake)
    wake_sprint "$@"
    ;;
  webhook)
    case "${2:-start}" in
      start)
        if [[ -f "$HARNESS_DIR/.webhook.pid" ]] && kill -0 "$(cat "$HARNESS_DIR/.webhook.pid")" 2>/dev/null; then
          ok "Webhook server 已在运行 (PID: $(cat "$HARNESS_DIR/.webhook.pid"))"
        else
          bun "$HARNESS_DIR/webhook-server.ts" >> "$HARNESS_DIR/.webhook.log" 2>&1 &
          echo $! > "$HARNESS_DIR/.webhook.pid"
          ok "Webhook server 启动 (PID: $!, port: ${HARNESS_PORT:-9876})"
          log "日志: $HARNESS_DIR/.webhook.log"
          log "测试: curl -X POST localhost:${HARNESS_PORT:-9876}/sprint -H 'Content-Type: application/json' -d '{\"title\":\"测试\"}'"
        fi
        ;;
      stop)
        if [[ -f "$HARNESS_DIR/.webhook.pid" ]]; then
          kill "$(cat "$HARNESS_DIR/.webhook.pid")" 2>/dev/null
          rm -f "$HARNESS_DIR/.webhook.pid"
          ok "Webhook server 已停止"
        else
          warn "Webhook server 未运行"
        fi
        ;;
      status)
        if [[ -f "$HARNESS_DIR/.webhook.pid" ]] && kill -0 "$(cat "$HARNESS_DIR/.webhook.pid")" 2>/dev/null; then
          ok "运行中 (PID: $(cat "$HARNESS_DIR/.webhook.pid"))"
          curl -s "http://localhost:${HARNESS_PORT:-9876}/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
        else
          warn "未运行"
        fi
        ;;
      *) err "用法: $0 webhook [start|stop|status]"; exit 2 ;;
    esac
    ;;
  status-server)
    _SS_PID="$HARNESS_DIR/run/status-server.pid"
    _SS_LOG="$HARNESS_DIR/run/status-server.log"
    _SS_PORT_FILE="$HARNESS_DIR/run/status-server.port"
    _SS_PORT_START="${SOLAR_STATUS_PORT_START:-8765}"
    _SS_PORT_END="${SOLAR_STATUS_PORT_END:-$((_SS_PORT_START + 10))}"
    # G3 run-2 fix (p5-g3-live-rung-20260709T190808Z): the session name was a
    # fixed global, so with parallel harnesses on one machine any harness's
    # start saw another's session as "already running" and any stop killed
    # it. The name is now scoped to THIS HARNESS_DIR; the legacy fixed name
    # is only ever touched after an ownership check.
    _SS_TMUX_LEGACY_SESSION="solar-harness-status-server"
    _SS_TMUX_SESSION="solar-harness-status-server-$(printf '%s' "$HARNESS_DIR" | cksum | awk '{print $1}')"
    mkdir -p "$HARNESS_DIR/run"
    _ss_is_windows() {
      [ "${OS_KIND:-}" = "windows" ] || [[ "$(uname -s)" =~ MINGW|MSYS|CYGWIN|Windows_NT ]]
    }
    _status_server_live_pids() {
      if _ss_is_windows; then
        return 0
      fi
      # Match the exact script as a substring of the full command line rather
      # than splitting argv on spaces. Installed harness paths commonly contain
      # spaces on WSL-mounted Windows workspaces.
      ps ax -o pid= -o comm= -o args= 2>/dev/null | awk -v script="$HARNESS_DIR/lib/symphony/status-server.py" '
        $2 ~ /^python([0-9]+([.][0-9]+)*)?$/ && index($0, script) > 0 { print $1 }
      ' || true
    }
    _ss_pid_owned() {
      # True when the pid's command line references THIS harness — the
      # ownership test every kill below must pass (G3 run-2 fix: stop's
      # port sweep killed every /healthz listener on the machine).
      local _pid="$1"
      [[ "$_pid" =~ ^[0-9]+$ ]] || return 1
      if _ss_is_windows; then
        # Git Bash PIDs are not reliable Windows process identities.  Only
        # taskkill a process whose command line names this exact harness.
        powershell.exe -NoProfile -NonInteractive -Command \
          "\$p = Get-CimInstance Win32_Process -Filter 'ProcessId=$_pid' -ErrorAction SilentlyContinue; if (\$null -ne \$p -and \$p.CommandLine -like '*$HARNESS_DIR*status-server.py*') { exit 0 }; exit 1" \
          >/dev/null 2>&1
        return $?
      fi
      ps -o args= -p "$_pid" 2>/dev/null | grep -qF -- "$HARNESS_DIR"
    }
    _ss_tmux_session_owned() {
      local _session="$1" _pane_pid
      _pane_pid=$(tmux list-panes -t "$_session" -F '#{pane_pid}' 2>/dev/null | head -1)
      [[ -n "$_pane_pid" ]] || return 1
      _ss_pid_owned "$_pane_pid"
    }
    _status_server_live_ports() {
      local _p
      for _p in $(seq "$_SS_PORT_START" "$_SS_PORT_END"); do
        # Bound the probe: on some hosts (e.g. WSL2) a closed localhost port drops
        # the SYN instead of refusing, so without --connect-timeout curl falls back
        # to its ~300s default and `status-server start/stop` wedges (F1 hang).
        if curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:${_p}/healthz" >/dev/null 2>&1; then
          printf '%s\n' "$_p"
        fi
      done
    }
    _status_server_terminate_pids() {
      local _pids="$1" _pid
      [[ -n "$_pids" ]] || return 0
      if _ss_is_windows; then
        for _pid in $_pids; do
          _ss_pid_owned "$_pid" || continue
          # /T is required: status handlers can have child helper processes,
          # and a parent-only kill leaves the listener alive on Windows.
          MSYS_NO_PATHCONV=1 taskkill.exe /PID "$_pid" /T /F >/dev/null 2>&1 || true
        done
        return 0
      fi
      kill $_pids 2>/dev/null || true
      sleep 0.3
      for _pid in $_pids; do
        if kill -0 "$_pid" 2>/dev/null; then
          kill -9 "$_pid" 2>/dev/null || true
        fi
      done
    }
    case "${2:-start}" in
      start)
        _live_pids="$(_status_server_live_pids || true)"
        if tmux_has_exact_session "$_SS_TMUX_SESSION"; then
          ok "Status server 已在运行 (tmux: $_SS_TMUX_SESSION, port: $(cat "$_SS_PORT_FILE" 2>/dev/null || echo '?'))"
        elif tmux_has_exact_session "$_SS_TMUX_LEGACY_SESSION" && _ss_tmux_session_owned "$_SS_TMUX_LEGACY_SESSION"; then
          ok "Status server 已在运行 (tmux: $_SS_TMUX_LEGACY_SESSION, port: $(cat "$_SS_PORT_FILE" 2>/dev/null || echo '?'))"
        elif [[ -f "$_SS_PID" ]] && [[ "$(cat "$_SS_PID" 2>/dev/null)" =~ ^[0-9]+$ ]] && _ss_pid_owned "$(cat "$_SS_PID")"; then
          ok "Status server 已在运行 (PID: $(cat "$_SS_PID"), port: $(cat "$_SS_PORT_FILE" 2>/dev/null || echo '?'))"
        elif [[ -n "$_live_pids" ]]; then
          # Heal only from path-scoped evidence: a foreign /healthz listener
          # in the shared port range is NOT our server and must not be
          # adopted (G3 run-2 fix).
          _live_ports="$(_status_server_live_ports || true)"
          _port="$(printf '%s\n' "$_live_ports" | head -1)"
          printf '%s\n' "$(printf '%s\n' "$_live_pids" | head -1)" > "$_SS_PID"
          [[ -n "$_port" ]] && printf '%s\n' "$_port" > "$_SS_PORT_FILE"
          ok "Status server 已在运行 (healed from live runtime; pid: $(printf '%s\n' "$_live_pids" | head -1), port: ${_port:-?})"
        else
          rm -f "$_SS_PID" "$_SS_PORT_FILE"
          _ss_py="${SOLAR_PYTHON:-$(command -v python3 || echo python3)}"
          # A shared tmux server retains the environment of the client that
          # created it.  The status server is also the dashboard intake
          # authority, so inheriting another harness's sprint/intent/workspace
          # roots can display stale sessions and submit a new request into the
          # wrong run.  Freeze every routing-critical, non-secret setting into
          # this pane command instead of consulting tmux's global environment.
          _ss_sprints_dir="${HARNESS_SPRINTS_DIR:-$HARNESS_DIR/sprints}"
          _ss_intents_dir="${SOLAR_INTENT_GATEWAY_DIR:-$HARNESS_DIR/intents}"
          _ss_workspace_root="${SOLAR_INTAKE_WORKSPACE_ROOT:-$(active_workspace_root 2>/dev/null || true)}"
          _ss_runtime_env=(
            "HOME=$HOME"
            "USERPROFILE=${USERPROFILE:-$HOME}"
            "SOLAR_HOME=${SOLAR_HOME:-$HOME/.solar}"
            "HARNESS_DIR=$HARNESS_DIR"
            "SOLAR_HARNESS_DIR=$HARNESS_DIR"
            "HARNESS_SPRINTS_DIR=$_ss_sprints_dir"
            "SPRINTS_DIR=$_ss_sprints_dir"
            "SOLAR_HARNESS_SPRINTS_DIR=$_ss_sprints_dir"
            "SOLAR_INTENT_GATEWAY_DIR=$_ss_intents_dir"
            "SOLAR_INTAKE_WORKSPACE_ROOT=$_ss_workspace_root"
            "SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT=${SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT:-$_ss_workspace_root}"
            "SOLAR_BIND_HOST=${SOLAR_BIND_HOST:-127.0.0.1}"
            "SOLAR_STATUS_PORT_START=$_SS_PORT_START"
            "SOLAR_STATUS_PORT_END=$_SS_PORT_END"
            "CODEX_HOME=${CODEX_HOME:-$HOME/.codex}"
            "SOLAR_PRODUCT_MODE=${SOLAR_PRODUCT_MODE:-0}"
            "SOLAR_WORKFLOW_ROUTER=${SOLAR_WORKFLOW_ROUTER:-0}"
            "SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH=${SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH:-0}"
            "SOLAR_GRAPH_BUILDER_OPERATOR_POOL=${SOLAR_GRAPH_BUILDER_OPERATOR_POOL:-0}"
            "SOLAR_GRAPH_EVAL_OPERATOR_POOL=${SOLAR_GRAPH_EVAL_OPERATOR_POOL:-0}"
            "SOLAR_COORD_MULTITASK_SELFCOMPLETE=${SOLAR_COORD_MULTITASK_SELFCOMPLETE:-0}"
            "SOLAR_PANE_RUNTIME=${SOLAR_PANE_RUNTIME:-codex}"
            "SOLAR_PM_DEFAULT_PROVIDERS=${SOLAR_PM_DEFAULT_PROVIDERS:-}"
            "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=${SOLAR_MULTI_TASK_DEFAULT_PROVIDERS:-}"
            "SOLAR_INTENT_COMPILER_PROVIDER=${SOLAR_INTENT_COMPILER_PROVIDER:-}"
            "SOLAR_INTENT_REVIEWER_PROVIDER=${SOLAR_INTENT_REVIEWER_PROVIDER:-}"
            "SOLAR_INTENT_COMPILER_MODEL=${SOLAR_INTENT_COMPILER_MODEL:-}"
            "SOLAR_INTENT_REVIEWER_MODEL=${SOLAR_INTENT_REVIEWER_MODEL:-}"
            "SOLAR_INTENT_MODEL_TIMEOUT_SEC=${SOLAR_INTENT_MODEL_TIMEOUT_SEC:-}"
            "SOLAR_HARNESS_SESSION=${SOLAR_HARNESS_SESSION:-$SESSION_NAME}"
            "SOLAR_HARNESS_LAB_SESSION=${SOLAR_HARNESS_LAB_SESSION:-$LAB_SESSION_NAME}"
            "SOLAR_HARNESS_BG_SESSION=${SOLAR_HARNESS_BG_SESSION:-$BG_SESSION_NAME}"
          )
          _ss_env_prefix="env"
          for _ss_assignment in "${_ss_runtime_env[@]}"; do
            _ss_env_prefix+=" $(printf '%q' "$_ss_assignment")"
          done
          _ss_cd_q=$(printf '%q' "$HARNESS_DIR")
          _ss_py_q=$(printf '%q' "$_ss_py")
          _ss_script_q=$(printf '%q' "$HARNESS_DIR/lib/symphony/status-server.py")
          _ss_log_q=$(printf '%q' "$_SS_LOG")
          if command -v tmux >/dev/null 2>&1; then
            tmux new-session -d -s "$_SS_TMUX_SESSION" \
              "cd $_ss_cd_q && exec $_ss_env_prefix $_ss_py_q $_ss_script_q >> $_ss_log_q 2>&1"
          else
            nohup env "${_ss_runtime_env[@]}" "$_ss_py" "$HARNESS_DIR/lib/symphony/status-server.py" >> "$_SS_LOG" 2>&1 &
          fi
          _ready=0
          for _i in {1..40}; do
            if [[ -s "$_SS_PORT_FILE" ]]; then
              _port=$(cat "$_SS_PORT_FILE" 2>/dev/null || true)
              if [[ "$_port" =~ ^[0-9]+$ ]] \
                && curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:${_port}/healthz" >/dev/null 2>&1 \
                && curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:${_port}/runtime-info" | grep -q '"pid"'; then
                _ready=1
                break
              fi
            fi
            sleep 0.2
          done
          if [[ "$_ready" != "1" ]]; then
            _pid_val=$(cat "$_SS_PID" 2>/dev/null || true)
            _status_server_terminate_pids "$_pid_val"
            rm -f "$_SS_PID" "$_SS_PORT_FILE"
            err "Status server did not become ready (/healthz and /runtime-info)"
            exit 1
          fi
          _port=$(cat "$_SS_PORT_FILE" 2>/dev/null || echo "8765")
          ok "Status server 启动 (port: $_port)"
          log "Dashboard: http://127.0.0.1:$_port/"
          log "日志: $_SS_LOG"
        fi
        ;;
      stop)
        _stopped=0
        _recorded_port="$(cat "$_SS_PORT_FILE" 2>/dev/null || true)"
        _live_pids="$(_status_server_live_pids || true)"
        _live_ports="$(_status_server_live_ports || true)"
        if tmux_has_exact_session "$_SS_TMUX_SESSION"; then
          tmux kill-session -t "$_SS_TMUX_SESSION" 2>/dev/null || true
          _stopped=1
        elif tmux_has_exact_session "$_SS_TMUX_LEGACY_SESSION" && _ss_tmux_session_owned "$_SS_TMUX_LEGACY_SESSION"; then
          # Pre-scoping servers of THIS harness live under the legacy fixed
          # name; another harness's server under that name is not ours to
          # kill (G3 run-2 fix).
          tmux kill-session -t "$_SS_TMUX_LEGACY_SESSION" 2>/dev/null || true
          _stopped=1
        elif [[ -f "$_SS_PID" ]]; then
          _pid_val=$(cat "$_SS_PID" 2>/dev/null || true)
          if [[ "$_pid_val" =~ ^[0-9]+$ ]] && _ss_pid_owned "$_pid_val"; then
            _status_server_terminate_pids "$_pid_val"
            _stopped=1
          fi
        fi
        if [[ -n "$_live_pids" ]]; then
          _status_server_terminate_pids "$_live_pids"
          _stopped=1
        fi
        if [[ -n "$_recorded_port" ]]; then
          _live_ports="$(printf '%s\n%s\n' "$_recorded_port" "$_live_ports" | awk 'NF && !seen[$0]++')"
        fi
        if [[ -n "$_live_ports" ]]; then
          # G3 run-2 fix: this sweep used to lsof-kill EVERY /healthz
          # listener on 8765-8775, machine-wide — with parallel harness
          # sessions on one machine, any session's stop killed every other
          # session's status server (run 2 died at the /intake seam this
          # way). A port listener is only reaped when its command line
          # proves it belongs to THIS harness.
          while IFS= read -r _port; do
            [[ -n "$_port" ]] || continue
            _listen_pids=$(lsof -tiTCP:"$_port" -sTCP:LISTEN 2>/dev/null || true)
            for _listen_pid in $_listen_pids; do
              if _ss_pid_owned "$_listen_pid"; then
                kill "$_listen_pid" 2>/dev/null || true
                _stopped=1
              fi
            done
          done <<< "$_live_ports"
        fi
        # Do not report success until the exact owned listener releases its
        # recorded port. This makes repeated start/stop deterministic instead
        # of hiding a lingering process behind removed pid files.
        if [[ "$_recorded_port" =~ ^[0-9]+$ ]]; then
          for _i in {1..25}; do
            if ! curl -fsS --connect-timeout 1 --max-time 1 "http://127.0.0.1:${_recorded_port}/healthz" >/dev/null 2>&1; then
              break
            fi
            sleep 0.2
          done
          if curl -fsS --connect-timeout 1 --max-time 1 "http://127.0.0.1:${_recorded_port}/healthz" >/dev/null 2>&1; then
            err "Status server listener did not release port $_recorded_port"
            exit 1
          fi
        fi
        rm -f "$_SS_PID" "$_SS_PORT_FILE"
        if [[ "$_stopped" == "1" ]]; then
          ok "Status server 已停止"
        fi
        if [[ "$_stopped" == "0" ]]; then
          warn "Status server 未运行"
        fi
        ;;
      restart)
        "$0" status-server stop 2>/dev/null || true
        sleep 0.3
        "$0" status-server start
        ;;
      status)
        _live_pids="$(_status_server_live_pids || true)"
        if tmux_has_exact_session "$_SS_TMUX_SESSION"; then
          _port=$(cat "$_SS_PORT_FILE" 2>/dev/null || echo "8765")
          ok "运行中 (tmux: $_SS_TMUX_SESSION, port: $_port)"
          curl -s "http://127.0.0.1:$_port/healthz" 2>/dev/null && echo || true
        elif tmux_has_exact_session "$_SS_TMUX_LEGACY_SESSION" && _ss_tmux_session_owned "$_SS_TMUX_LEGACY_SESSION"; then
          _port=$(cat "$_SS_PORT_FILE" 2>/dev/null || echo "8765")
          ok "运行中 (tmux: $_SS_TMUX_LEGACY_SESSION, port: $_port)"
          curl -s "http://127.0.0.1:$_port/healthz" 2>/dev/null && echo || true
        elif [[ -f "$_SS_PID" ]] && [[ "$(cat "$_SS_PID" 2>/dev/null)" =~ ^[0-9]+$ ]] && kill -0 "$(cat "$_SS_PID")" 2>/dev/null; then
          _port=$(cat "$_SS_PORT_FILE" 2>/dev/null || echo "8765")
          ok "运行中 (PID: $(cat "$_SS_PID"), port: $_port)"
          curl -s "http://127.0.0.1:$_port/healthz" 2>/dev/null && echo || true
        elif [[ -n "$_live_pids" ]]; then
          # Path-scoped evidence only — a foreign /healthz listener in the
          # shared port range must not be reported (or healed) as ours
          # (G3 run-2 fix).
          _live_ports="$(_status_server_live_ports || true)"
          _port=$(printf '%s\n' "$_live_ports" | head -1)
          printf '%s\n' "$(printf '%s\n' "$_live_pids" | head -1)" > "$_SS_PID"
          [[ -n "$_port" ]] && printf '%s\n' "$_port" > "$_SS_PORT_FILE"
          ok "运行中 (healed from live runtime, pid: $(printf '%s\n' "$_live_pids" | head -1), port: ${_port:-?})"
          curl -s "http://127.0.0.1:$_port/healthz" 2>/dev/null && echo || true
        else
          warn "Status server 未运行"
        fi
        ;;
      *) err "用法: $0 status-server [start|stop|restart|status]" ;;
    esac
    ;;
  mermaid)
    _MMD_OPEN=0
    _MMD_FILE="${2:-}"
    if [[ "${_MMD_FILE:-}" == "--open" ]]; then
      _MMD_OPEN=1
      _MMD_FILE="${3:-}"
    fi
    if [[ "${3:-}" == "--open" ]]; then
      _MMD_OPEN=1
    fi
    "$0" status-server start >/dev/null 2>&1 || true
    _MMD_PORT=$(cat "$HARNESS_DIR/run/status-server.port" 2>/dev/null || echo "8765")
    if [[ -n "${_MMD_FILE:-}" ]]; then
      _MMD_URL_PATH=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$_MMD_FILE")
      _MMD_URL="http://127.0.0.1:${_MMD_PORT}/mermaid/view?file=${_MMD_URL_PATH}"
    else
      _MMD_URL="http://127.0.0.1:${_MMD_PORT}/mermaid"
    fi
    ok "Mermaid Viewer: $_MMD_URL"
    if [[ "$_MMD_OPEN" == "1" ]]; then
      open "$_MMD_URL" >/dev/null 2>&1 || true
    fi
    ;;
  benchmark|bench)
    shift || true
    _benchmark_runner="$HARNESS_DIR/lib/benchmark/runner.py"
    [[ -f "$_benchmark_runner" ]] || { err "benchmark runner not found: $_benchmark_runner"; exit 1; }
    python3 -m harness.lib.benchmark.runner "$@"
    ;;
  integrations)
    _integrations_probe="$HARNESS_DIR/lib/external-integrations-health.py"
    _plugin_loader="$HARNESS_DIR/lib/plugin_loader.py"
    _capability_reg="$HARNESS_DIR/lib/capability_registry.py"
    _capability_bench="$HARNESS_DIR/lib/capability_fusion_benchmark.py"
    _platform_bench="$HARNESS_DIR/lib/platform_workflow_benchmark.py"
    _heavy_proof_bench="$HARNESS_DIR/lib/heavy_proof_benchmark.py"
    _agent_arena_bench="$HARNESS_DIR/lib/agent_arena_benchmark.py"
    _cert_suite="$HARNESS_DIR/lib/capability_certification_suite.py"
    _activation_proof="$HARNESS_DIR/lib/capability_activation_proof.py"
    _ruflo_adapter="$HARNESS_DIR/lib/ruflo_adapter.py"
    _autoresearch_adapter="$HARNESS_DIR/lib/autoresearch_adapter.py"
    case "${2:-status}" in
      status|health)
        shift 2 || true
        [[ -f "$_integrations_probe" ]] || { err "external integrations probe not found: $_integrations_probe"; exit 1; }
        human_prefix "skills" "integrations health $*"
        python3 "$_integrations_probe" "$@"
        ;;
      plugins|plugin-status)
        shift 2 || true
        [[ -f "$_plugin_loader" ]] || { err "plugin_loader not found: $_plugin_loader"; exit 1; }
        python3 "$_plugin_loader" status "$@"
        ;;
      install)
        shift 2 || true
        [[ -f "$_plugin_loader" ]] || { err "plugin_loader not found: $_plugin_loader"; exit 1; }
        python3 "$_plugin_loader" install "$@"
        ;;
      disable)
        shift 2 || true
        [[ -f "$_plugin_loader" ]] || { err "plugin_loader not found: $_plugin_loader"; exit 1; }
        python3 "$_plugin_loader" disable "$@"
        ;;
      list)
        shift 2 || true
        [[ -f "$_plugin_loader" ]] || { err "plugin_loader not found: $_plugin_loader"; exit 1; }
        python3 "$_plugin_loader" list "$@"
        ;;
      validate)
        shift 2 || true
        [[ -f "$_plugin_loader" ]] || { err "plugin_loader not found: $_plugin_loader"; exit 1; }
        python3 "$_plugin_loader" validate "$@"
        ;;
      capabilities|caps)
        shift 2 || true
        [[ -f "$_capability_reg" ]] || { err "capability_registry not found: $_capability_reg"; exit 1; }
        python3 "$_capability_reg" "${1:-list}" "${@:2}"
        ;;
      sync-caps)
        shift 2 || true
        [[ -f "$_capability_reg" ]] || { err "capability_registry not found: $_capability_reg"; exit 1; }
        python3 "$_capability_reg" sync "$@"
        ;;
      benchmark|bench)
        shift 2 || true
        [[ -f "$_capability_bench" ]] || { err "capability_fusion_benchmark not found: $_capability_bench"; exit 1; }
        python3 "$_capability_bench" "$@"
        ;;
      platform-benchmark|workflow-benchmark)
        shift 2 || true
        [[ -f "$_platform_bench" ]] || { err "platform_workflow_benchmark not found: $_platform_bench"; exit 1; }
        python3 "$_platform_bench" "$@"
        ;;
      heavy-proof|heavy-benchmark)
        shift 2 || true
        [[ -f "$_heavy_proof_bench" ]] || { err "heavy_proof_benchmark not found: $_heavy_proof_bench"; exit 1; }
        python3 "$_heavy_proof_bench" "$@"
        ;;
      agent-arena|arena)
        shift 2 || true
        [[ -f "$_agent_arena_bench" ]] || { err "agent_arena_benchmark not found: $_agent_arena_bench"; exit 1; }
        python3 "$_agent_arena_bench" "$@"
        ;;
      certify|certification|cert)
        shift 2 || true
        [[ -f "$_cert_suite" ]] || { err "capability_certification_suite not found: $_cert_suite"; exit 1; }
        human_prefix "skills" "integrations certify $*"
        python3 "$_cert_suite" "$@"
        ;;
      activation-proof|prove-activation|prove-use)
        shift 2 || true
        [[ -f "$_activation_proof" ]] || { err "capability_activation_proof not found: $_activation_proof"; exit 1; }
        human_prefix "skills" "activation-proof $*"
        python3 "$_activation_proof" "$@"
        ;;
      ruflo-status|ruflo)
        shift 2 || true
        [[ -f "$_ruflo_adapter" ]] || { err "ruflo_adapter not found: $_ruflo_adapter"; exit 1; }
        human_prefix "ruflo" "status $*"
        python3 "$_ruflo_adapter" status "$@"
        ;;
      ruflo-vendor)
        shift 2 || true
        [[ -f "$_ruflo_adapter" ]] || { err "ruflo_adapter not found: $_ruflo_adapter"; exit 1; }
        python3 "$_ruflo_adapter" vendor "$@"
        ;;
      ruflo-runtime-status)
        shift 2 || true
        [[ -f "$_ruflo_adapter" ]] || { err "ruflo_adapter not found: $_ruflo_adapter"; exit 1; }
        human_prefix "ruflo" "runtime-status $*"
        python3 "$_ruflo_adapter" runtime-status "$@"
        ;;
      ruflo-runtime-bootstrap)
        shift 2 || true
        [[ -f "$_ruflo_adapter" ]] || { err "ruflo_adapter not found: $_ruflo_adapter"; exit 1; }
        python3 "$_ruflo_adapter" runtime-bootstrap "$@"
        ;;
      ruflo-runtime-smoke)
        shift 2 || true
        [[ -f "$_ruflo_adapter" ]] || { err "ruflo_adapter not found: $_ruflo_adapter"; exit 1; }
        human_prefix "ruflo" "runtime-smoke $*"
        python3 "$_ruflo_adapter" runtime-smoke "$@"
        ;;
      autoresearch-status|autoresearch)
        shift 2 || true
        [[ -f "$_autoresearch_adapter" ]] || { err "autoresearch_adapter not found: $_autoresearch_adapter"; exit 1; }
        human_prefix "autoresearch" "status $*"
        python3 "$_autoresearch_adapter" status "$@"
        ;;
      autoresearch-doctor)
        shift 2 || true
        [[ -f "$_autoresearch_adapter" ]] || { err "autoresearch_adapter not found: $_autoresearch_adapter"; exit 1; }
        human_prefix "autoresearch" "doctor $*"
        python3 "$_autoresearch_adapter" doctor "$@"
        ;;
      autoresearch-vendor)
        shift 2 || true
        [[ -f "$_autoresearch_adapter" ]] || { err "autoresearch_adapter not found: $_autoresearch_adapter"; exit 1; }
        python3 "$_autoresearch_adapter" vendor "$@"
        ;;
      autoresearch-run-local)
        shift 2 || true
        [[ -f "$_autoresearch_adapter" ]] || { err "autoresearch_adapter not found: $_autoresearch_adapter"; exit 1; }
        human_prefix "autoresearch" "run-local $*"
        python3 "$_autoresearch_adapter" run-local "$@"
        ;;
      meta-harness|meta-harness-status)
        shift 2 || true
        _meta_harness_adapter="$HARNESS_DIR/lib/meta_harness_adapter.py"
        [[ -f "$_meta_harness_adapter" ]] || { err "meta_harness_adapter not found: $_meta_harness_adapter"; exit 1; }
        human_prefix "meta-harness" "status $*"
        python3 "$_meta_harness_adapter" status "$@"
        ;;
      meta-harness-doctor)
        shift 2 || true
        _meta_harness_adapter="$HARNESS_DIR/lib/meta_harness_adapter.py"
        [[ -f "$_meta_harness_adapter" ]] || { err "meta_harness_adapter not found: $_meta_harness_adapter"; exit 1; }
        human_prefix "meta-harness" "doctor $*"
        python3 "$_meta_harness_adapter" doctor "$@"
        ;;
      *)
        err "用法: $0 integrations [status|plugins|install|disable|list|validate|capabilities|sync-caps|benchmark|platform-benchmark|heavy-proof|agent-arena|certify|activation-proof|ruflo-status|ruflo-runtime-status|ruflo-runtime-bootstrap|ruflo-runtime-smoke|autoresearch-status|autoresearch-doctor|autoresearch-vendor|autoresearch-run-local|meta-harness-status|meta-harness-doctor] [--json]"
        exit 2
        ;;
    esac
    ;;
  meta-harness|metaharness)
    shift
    _meta_harness_adapter="$HARNESS_DIR/lib/meta_harness_adapter.py"
    [[ -f "$_meta_harness_adapter" ]] || { err "meta_harness_adapter not found: $_meta_harness_adapter"; exit 1; }
    case "${1:-status}" in
      status|doctor|init|run|propose|evaluate|apply|history)
        _mh_sub="${1:-status}"; shift || true
        human_prefix "meta-harness" "${_mh_sub} $*"
        python3 "$_meta_harness_adapter" "$_mh_sub" "$@"
        ;;
      help|--help|-h)
        echo "用法: $0 meta-harness [status|doctor|init|run|propose|evaluate|apply|history] [--json]"
        echo "安全: init/run/propose/evaluate/history 默认 dry-run；真实执行需 --execute。apply 默认 --dry-run，真实应用需 --execute。"
        ;;
      *)
        err "用法: $0 meta-harness [status|doctor|init|run|propose|evaluate|apply|history] [--json] [--execute]"
        exit 2
        ;;
    esac
    ;;
  agent-arena|arena)
    shift
    _agent_arena_bench="$HARNESS_DIR/lib/agent_arena_benchmark.py"
    [[ -f "$_agent_arena_bench" ]] || { err "agent_arena_benchmark not found: $_agent_arena_bench"; exit 1; }
    python3 "$_agent_arena_bench" "$@"
    ;;
  evolution)
    shift
    _evolution_py="$HARNESS_DIR/lib/evolution_engine.py"
    _failure_py="$HARNESS_DIR/lib/failure_miner.py"
    _eval_py="$HARNESS_DIR/lib/eval_runner.py"
    case "${1:-status}" in
      status|scorecard|recommend|run-loop|promote|demote-degraded)
        [[ -f "$_evolution_py" ]] || { err "evolution_engine not found: $_evolution_py"; exit 1; }
        python3 "$_evolution_py" "$@"
        ;;
      mine-failures)
        shift || true
        [[ -f "$_failure_py" ]] || { err "failure_miner not found: $_failure_py"; exit 1; }
        python3 "$_failure_py" mine "$@"
        ;;
      eval-run)
        shift || true
        [[ -f "$_eval_py" ]] || { err "eval_runner not found: $_eval_py"; exit 1; }
        python3 "$_eval_py" run "$@"
        ;;
      curriculum-evaluate)
        shift || true
        _curriculum_py="$HARNESS_DIR/lib/curriculum_loop.py"
        [[ -f "$_curriculum_py" ]] || { err "curriculum_loop not found: $_curriculum_py"; exit 1; }
        python3 "$_curriculum_py" evaluate "$@"
        ;;
      routing-evaluate)
        shift || true
        _routing_py="$HARNESS_DIR/lib/routing_bandit.py"
        [[ -f "$_routing_py" ]] || { err "routing_bandit not found: $_routing_py"; exit 1; }
        python3 "$_routing_py" evaluate "$@"
        ;;
      reranker-train)
        shift || true
        _reranker_py="$HARNESS_DIR/lib/retrieval_reranker.py"
        [[ -f "$_reranker_py" ]] || { err "retrieval_reranker not found: $_reranker_py"; exit 1; }
        python3 "$_reranker_py" train "$@"
        ;;
      legal-risk-screen)
        shift || true
        _legal_risk_py="$HARNESS_DIR/lib/legal_ip_risk.py"
        [[ -f "$_legal_risk_py" ]] || { err "legal_ip_risk not found: $_legal_risk_py"; exit 1; }
        python3 "$_legal_risk_py" screen "$@"
        ;;
      self-rag-evaluate)
        shift || true
        _self_rag_py="$HARNESS_DIR/lib/self_rag.py"
        [[ -f "$_self_rag_py" ]] || { err "self_rag not found: $_self_rag_py"; exit 1; }
        python3 "$_self_rag_py" run "$@"
        ;;
      scientific-compare)
        shift || true
        _scientific_compare_py="$HARNESS_DIR/lib/scientific_experiment_comparison.py"
        [[ -f "$_scientific_compare_py" ]] || { err "scientific_experiment_comparison not found: $_scientific_compare_py"; exit 1; }
        python3 "$_scientific_compare_py" compare "$@"
        ;;
      *)
        err "用法: $0 evolution [status|scorecard|recommend|run-loop|promote|demote-degraded|mine-failures|eval-run|curriculum-evaluate|routing-evaluate|reranker-train|self-rag-evaluate|scientific-compare] [--json]"
        exit 2
        ;;
    esac
    ;;
  everything-claude-code|ecc)
    shift
    _ecc_adapter="$HARNESS_DIR/lib/everything_claude_code_adapter.py"
    [[ -f "$_ecc_adapter" ]] || { err "everything claude code adapter not found: $_ecc_adapter"; exit 1; }
    case "${1:-doctor}" in
      doctor|inventory|report)
        python3 "$_ecc_adapter" "$@"
        ;;
      install)
        shift
        case "${1:-}" in
          --dry-run|dry-run)
            shift || true
            python3 "$_ecc_adapter" install-dry-run "$@"
            ;;
          *)
            err "用法: $0 everything-claude-code install --dry-run [--json]"
            exit 2
            ;;
        esac
        ;;
      sync)
        shift
        _al=""
        _dr=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --allowlist) _al="$2"; shift 2 ;;
            --allowlist=*) _al="${1#--allowlist=}"; shift ;;
            --dry-run) _dr="--dry-run"; shift ;;
            --json) set -- "--json" "$@"; break ;;
            *) shift ;;
          esac
        done
        [[ -n "$_al" ]] || { err "用法: $0 everything-claude-code sync --allowlist <path> [--dry-run] [--json]"; exit 2; }
        python3 "$_ecc_adapter" sync-allowlisted --allowlist "$_al" $_dr "$@"
        ;;
      rollback)
        shift
        python3 "$_ecc_adapter" rollback "$@"
        ;;
      help|--help|-h)
        echo "用法: $0 everything-claude-code [doctor|inventory|report|install --dry-run|sync --allowlist <path>|rollback] [--json]"
        ;;
      *)
        err "用法: $0 everything-claude-code [doctor|inventory|report|install --dry-run|sync --allowlist <path>|rollback] [--json]"
        exit 2
        ;;
    esac
    ;;
  agent-rules-books|arb)
    shift
    _arb_adapter="$HARNESS_DIR/lib/agent_rules_books_adapter.py"
    [[ -f "$_arb_adapter" ]] || { err "agent_rules_books_adapter.py not found: $_arb_adapter"; exit 1; }
    case "${1:-doctor}" in
      doctor|inventory|report|vendor|prove)
        _sub="${1:-doctor}"; shift || true
        human_prefix "skills" "agent-rules-books ${_sub} $*"
        python3 "$_arb_adapter" "$_sub" "$@" ;;
      sync|install)
        _sub="${1:-sync}"; shift || true
        human_prefix "skills" "agent-rules-books ${_sub} $*"
        python3 "$_arb_adapter" "$_sub" "$@" ;;
      help|--help|-h)
        echo "用法: $0 agent-rules-books [doctor|inventory|report|vendor|prove|sync|install] [--json] [--dry-run] [--version mini|nano|full]" ;;
      *)
        err "用法: $0 agent-rules-books [doctor|inventory|report|vendor|prove|sync|install] [--json] [--dry-run] [--version mini|nano|full]"
        exit 2 ;;
    esac
    ;;
  notes)
    shift
    _notes_adapter="$HARNESS_DIR/lib/apple_notes_ingest.py"
    [[ -f "$_notes_adapter" ]] || { err "apple notes adapter not found: $_notes_adapter"; exit 1; }
    case "${1:-doctor}" in
      doctor)
        shift; python3 "$_notes_adapter" doctor --json "$@" ;;
      scan)
        shift; python3 "$_notes_adapter" scan --json "$@" ;;
      status)
        shift; python3 "$_notes_adapter" status --json "$@" ;;
      install-scheduler)
        shift; python3 "$_notes_adapter" install-scheduler --json "$@" ;;
      uninstall-scheduler)
        shift; python3 "$_notes_adapter" uninstall-scheduler --json "$@" ;;
      *)
        err "用法: $0 notes [doctor|scan|status|install-scheduler|uninstall-scheduler] [--dry-run] [--force-dispatch] [--interval N] [--json]"
        exit 2 ;;
    esac
    ;;
  data-plane)
    shift
    _dp_audit="$HARNESS_DIR/lib/data_plane_audit.py"
    [[ -f "$_dp_audit" ]] || { err "data plane audit script not found: $_dp_audit"; exit 1; }
    case "${1:-audit}" in
      audit)        shift; python3 "$_dp_audit" audit "$@" ;;
      repair-state) shift; python3 "$_dp_audit" repair-state "$@" ;;
      refresh-ledger) shift; python3 "$_dp_audit" refresh-ledger "$@" ;;
      *) err "用法: solar-harness data-plane <audit|repair-state|refresh-ledger> [--json] [--dry-run] [--verbose]"; exit 2 ;;
    esac
    ;;
  skills)
    shift
    _skills_py="$HARNESS_DIR/lib/solar_skills.py"
    [[ -f "$_skills_py" ]] || { err "solar_skills.py not found: $_skills_py"; exit 1; }
    case "${1:-inventory}" in
      inventory)     shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "inventory"; python3 "$_skills_py" inventory "$@" ;;
      doctor)        shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "doctor"; python3 "$_skills_py" doctor "$@" ;;
      pane-status)   shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "pane-status"; python3 "$_skills_py" pane-status "$@" ;;
      readiness)     shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "readiness"; python3 "$_skills_py" readiness "$@" ;;
      certify|certification|cert) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "certify"; python3 "$_skills_py" certify "$@" ;;
      inject)        shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "inject"; python3 "$_skills_py" inject "$@" ;;
      effect-scan)   shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "effect-scan"; python3 "$_skills_py" effect-scan "$@" ;;
      healthcheck|skill-healthcheck) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "healthcheck"; python3 "$HARNESS_DIR/lib/skill_healthcheck.py" "$@" ;;
      evolve|evolution) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "evolve"; python3 "$HARNESS_DIR/lib/skill_evolution_runner.py" "$@" ;;
      native-extract) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "native-extract"; python3 "$_skills_py" native-extract "$@" ;;
      registry)      shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "registry"; python3 "$_skills_py" registry "$@" ;;
      eval)          shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "eval"; python3 "$_skills_py" eval "$@" ;;
      promote)       shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "promote"; python3 "$_skills_py" promote "$@" ;;
      rollback)      shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "rollback"; python3 "$_skills_py" rollback "$@" ;;
      export)        shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "skills" "export"; python3 "$_skills_py" export "$@" ;;
      *) err "用法: solar-harness skills <inventory|doctor|readiness|certify|inject|effect-scan|healthcheck|evolve|export|eval|promote|rollback|registry> [opts]"; exit 2 ;;
    esac
    ;;
  intent)
    shift
    _intent_py="$HARNESS_DIR/lib/intent_engine_adapter.py"
    [[ -f "$_intent_py" ]] || { err "intent_engine_adapter.py not found: $_intent_py"; exit 1; }
    case "${1:-match}" in
      match) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "intent" "match"; python3 "$_intent_py" match "$@" ;;
      learn) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "intent" "learn"; python3 "$_intent_py" learn "$@" ;;
      audit) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "intent" "audit"; python3 "$_intent_py" audit "$@" ;;
      summarize) shift; type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "intent" "summarize"; python3 "$_intent_py" summarize "$@" ;;
      *) err "用法: solar-harness intent <match|learn|audit|summarize> [opts]"; exit 2 ;;
    esac
    ;;
  graph)
    shift
    _graph_py="$HARNESS_DIR/lib/harness_graph.py"
    [[ -f "$_graph_py" ]] || { err "harness_graph.py not found: $_graph_py"; exit 1; }
    type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "graph" "${1:-run}"
    python3 "$_graph_py" "$@"
    ;;
  mineru)
    # sprint-20260509-mineru-mirage-closeout S2: PDF extraction
    shift
    _mineru_subcmd="${1:-help}"; shift || true
    case "$_mineru_subcmd" in
      extract)
        _ex_py="$HARNESS_DIR/lib/mineru_extract.py"
        [[ -f "$_ex_py" ]] || { err "mineru_extract.py not found"; exit 1; }
        human_prefix "mineru" "extract $*"
        python3 "$_ex_py" "$@"
        ;;
      doctor)
        _md_py="$HARNESS_DIR/lib/mineru_doctor.py"
        [[ -f "$_md_py" ]] || { err "mineru_doctor.py not found"; exit 1; }
        human_prefix "mineru" "doctor $*"
        python3 "$_md_py" "$@"
        ;;
      bootstrap)
        human_prefix "mineru" "bootstrap $*"
        bash "$HARNESS_DIR/vendor/mineru/bootstrap.sh" "$@"
        ;;
      help|"")
        echo "Usage: $0 mineru <extract|doctor|bootstrap> [args]"
        echo "  extract <pdf>  Extract PDF to Obsidian references/ (--background --vault PATH)"
        echo "  doctor         Check venv and model status (--json)"
        echo "  bootstrap      Create/repair vendor venv (--force)"
        ;;
      *) err "unknown mineru subcommand: $_mineru_subcmd"; exit 1 ;;
    esac
    ;;
  autopilot)
    shift
    _autopilot="$HARNESS_DIR/tools/solar-autopilot-monitor.py"
    [[ -f "$_autopilot" ]] || { err "autopilot monitor not found: $_autopilot"; exit 1; }
    _autopilot_label="com.solar.autopilot"
    _autopilot_plist="$HOME/Library/LaunchAgents/${_autopilot_label}.plist"
    case "${1:-status}" in
      status|scan)
        human_prefix "autopilot" "${1:-status}"
        python3 "$_autopilot" --json
        ;;
      apply)
        shift
        human_prefix "autopilot" "apply $*"
        python3 "$_autopilot" --apply --json "$@"
        ;;
      dispatch)
        shift
        human_prefix "autopilot" "dispatch $*"
        python3 "$_autopilot" --apply --dispatch --json "$@"
        ;;
      loop)
        shift
        human_prefix "autopilot" "loop $*"
        python3 "$_autopilot" --apply --dispatch --loop --json "$@"
        ;;
      start)
        mkdir -p "$HOME/Library/LaunchAgents" "$HARNESS_DIR/state" "$HARNESS_DIR/run"
        cat > "$_autopilot_plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${_autopilot_label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${_autopilot}</string>
    <string>--apply</string>
    <string>--dispatch</string>
    <string>--loop</string>
    <string>--interval</string>
    <string>60</string>
    <string>--cooldown</string>
    <string>300</string>
    <string>--stall-seconds</string>
    <string>180</string>
    <string>--json</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>${HARNESS_DIR}</string>
  <key>StandardOutPath</key>
  <string>${HARNESS_DIR}/.autopilot-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${HARNESS_DIR}/.autopilot-launchd.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:${HOME}/.solar/bin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF
        launchctl bootout "gui/$(id -u)" "$_autopilot_plist" >/dev/null 2>&1 || true
        launchctl bootstrap "gui/$(id -u)" "$_autopilot_plist"
        launchctl kickstart -k "gui/$(id -u)/${_autopilot_label}" >/dev/null 2>&1 || true
        ok "autopilot started: ${_autopilot_label}"
        ;;
      stop)
        launchctl bootout "gui/$(id -u)" "$_autopilot_plist" >/dev/null 2>&1 || true
        rm -f "$HARNESS_DIR/run/autopilot.lock"
        ok "autopilot stopped"
        ;;
      service-status)
        launchctl print "gui/$(id -u)/${_autopilot_label}" 2>/dev/null | sed -n '1,80p' || true
        [[ -f "$HARNESS_DIR/state/autopilot-state.json" ]] && python3 -m json.tool "$HARNESS_DIR/state/autopilot-state.json" | sed -n '1,120p'
        ;;
      queue)
        _q="$HARNESS_DIR/run/autopilot-queue.jsonl"
        if [[ -f "$_q" ]]; then
          python3 - <<PY
import json, pathlib, time
q = pathlib.Path("$_q")
items = []
for raw in q.read_text(errors="ignore").splitlines():
    try:
        d = json.loads(raw)
    except Exception:
        continue
    if not d.get("done") and not d.get("expired"):
        items.append(d)
print(f"autopilot queue depth: {len(items)}")
print("┌──────────────────────────────────────────────┬──────────────────────┬────────────────────┬──────────┐")
print("│ Sprint                                       │ Target               │ Reason             │ Attempts │")
print("├──────────────────────────────────────────────┼──────────────────────┼────────────────────┼──────────┤")
for d in items[-20:]:
    print(f"│ {d.get('sid','')[:44]:<44} │ {d.get('target','')[:20]:<20} │ {d.get('reason','')[:18]:<18} │ {int(d.get('attempts',0)):>8} │")
if not items:
    print("│ N/A                                          │ N/A                  │ N/A                │        0 │")
print("└──────────────────────────────────────────────┴──────────────────────┴────────────────────┴──────────┘")
PY
        else
          echo "autopilot queue empty"
        fi
        ;;
      help|--help|-h)
        echo "用法: $0 autopilot [status|apply|dispatch|loop|start|stop|service-status|queue]"
        echo "  status   扫描断头 sprint/pane，不修改"
        echo "  apply    写入本地状态/events，安全默认推进"
        echo "  dispatch apply 后向对应 tmux pane 发送接手指令"
        echo "  loop     常驻巡逻：自动发现阻塞并 wake/dispatch"
        echo "  start    用 launchd 启动常驻巡逻器"
        echo "  stop     停止 launchd 巡逻器"
        echo "  queue    查看因 pane lease/assignment/busy 被排队的动作"
        ;;
      *) err "用法: $0 autopilot [status|apply|dispatch|loop|start|stop|service-status|queue]" ; exit 2 ;;
    esac
    ;;
  plan-verdict)
    [[ -z "${2:-}" ]] && { err "用法: solar-harness plan-verdict <sid> approve|reject [reason]"; exit 2; }
    do_plan_verdict "$2" "${3:-}" "${4:-}"
    ;;
  handoff-submit)
    [[ -z "${2:-}" ]] && { err "用法: solar-harness handoff-submit <sid>"; exit 2; }
    do_handoff_submit "$2"
    ;;
  parallel-integrate)
    [[ -z "${2:-}" ]] && { err "用法: solar-harness parallel-integrate <sid> [repo-root]"; exit 2; }
    bash "$HARNESS_DIR/lib/parallel-integrate.sh" "$2" "${3:-}"
    ;;
  eval-verdict)
    [[ -z "${2:-}" ]] && { err "用法: solar-harness eval-verdict <sid> pass|fail [reason]"; exit 2; }
    do_eval_verdict "$2" "${3:-}" "${4:-}"
    ;;
  capsule)
    shift
    case "${1:-}" in
      show)
        [[ -z "${2:-}" ]] && { err "用法: solar-harness capsule show <sid>"; exit 2; }
        do_capsule_show "$2"
        ;;
      *)
        echo "Solar Harness Capsule — State Capsule 查看"
        echo "用法: solar-harness capsule show <sid>"
        ;;
    esac
    ;;
  ledger)
    shift
    case "${1:-}" in
      show)
        [[ -z "${2:-}" ]] && { err "用法: solar-harness ledger show <sid>"; exit 2; }
        do_ledger_show "$2"
        ;;
      *)
        echo "Solar Harness Ledger — Bridge Ledger 查看"
        echo "用法: solar-harness ledger show <sid>"
        ;;
    esac
    ;;
  verify-events)
    [[ -z "${2:-}" ]] && { err "用法: solar-harness verify-events <sid>"; exit 2; }
    do_verify_events "$2"
    ;;
  stats)
    shift
    case "${1:-}" in
      "")        do_stats_overview ;;
      topology)  do_stats_topology "${2:-}" ;;
      sprint)    do_stats_sprint "${2:-}" ;;
      *)         echo "用法: solar-harness stats [topology <name>|sprint <sid>]" ;;
    esac
    ;;
  migrate)
    # Sprint 20260422-162434: 一键跨机迁移 + Sprint 20260423-151839 D8
    migrate_subcmd="${2:-help}"
    migrate_script="$HARNESS_DIR/migrate/${migrate_subcmd}.sh"
    if [[ -f "$migrate_script" ]]; then
      bash "$migrate_script" "${@:3}"
    else
      echo "Solar Migrate — 跨机迁移工具"
      echo ""
      echo "用法:"
      echo "  $0 migrate export [--out <path>] [--include-secrets] [--password <pw>] [--push <host:path>] [--cleanup-local]"
      echo "  $0 migrate import <bundle|ssh://host/path> [--password <pw>] [--dry-run] [--install-deps]"
      echo "                   [--skip-diff-backup] [--skip-full-backup] [--keep-local]"
      echo "  $0 migrate verify <bundle> [--password <pw>]"
      echo "  $0 migrate rollback [--diff|--full] [--confirm] [--backup-dir <path>] [--remote <user@host>]"
      echo "  $0 migrate deploy <user@host> [--force]"
      echo "  $0 migrate bootstrap <user@host>"
      echo ""
      echo "子命令: export, import, verify, rollback, deploy, bootstrap"
      exit 1
    fi
    ;;
  deploy)
    # Sprint 20260423-151839 D8: 一键部署
    DEPLOY_TARGET="${2:-}"
    DEPLOY_FORCE="${3:-}"
    [[ -z "$DEPLOY_TARGET" ]] && { err "用法: $0 deploy <user@host> [--force]"; exit 2; }

    SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
    BUNDLE_OUT="/tmp/solar-deploy-$$"
    LATEST_REMOTE="\$HOME/solar-bundles/latest.tar"

    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  Solar Deploy — 一键部署"
    echo "══════════════════════════════════════════════════"
    echo ""

    # Step 1: Check remote doesn't already have ~/.solar (unless --force)
    HAS_SOLAR=$(ssh $SSH_OPTS "$DEPLOY_TARGET" "test -d ~/.solar && echo yes || echo no" 2>/dev/null || echo "error")
    if [[ "$HAS_SOLAR" == "yes" && "$DEPLOY_FORCE" != "--force" ]]; then
      err "目标机已有 ~/.solar, 使用 --force 覆盖"
      exit 1
    fi

    # Step 2: Export + push
    ok "Step 1/4: Export + Push..."
    mkdir -p "$BUNDLE_OUT"
    bash "$HARNESS_DIR/migrate/export.sh" --out "$BUNDLE_OUT" "${@:4}" 2>&1
    DEPLOY_TAR=$(ls -t "$BUNDLE_OUT"/solar-bundle-*.tar 2>/dev/null | head -1)
    if [[ -z "$DEPLOY_TAR" ]]; then
      err "Export 失败: 未找到 bundle"
      rm -rf "$BUNDLE_OUT"
      exit 1
    fi

    # Push to remote
    ok "Step 2/4: Push bundle..."
    ssh $SSH_OPTS "$DEPLOY_TARGET" "mkdir -p ~/solar-bundles" 2>/dev/null
    if command -v rsync &>/dev/null; then
      rsync --partial --append --progress "$DEPLOY_TAR" "${DEPLOY_TARGET}:${LATEST_REMOTE}" 2>&1
      rsync --partial --append --progress "${DEPLOY_TAR}.sha256" "${DEPLOY_TARGET}:${LATEST_REMOTE}.sha256" 2>&1
    else
      scp $SSH_OPTS "$DEPLOY_TAR" "${DEPLOY_TARGET}:${LATEST_REMOTE}" 2>/dev/null
      scp $SSH_OPTS "${DEPLOY_TAR}.sha256" "${DEPLOY_TARGET}:${LATEST_REMOTE}.sha256" 2>/dev/null
    fi
    rm -rf "$BUNDLE_OUT"

    # Step 3: Remote import
    ok "Step 3/4: Remote import..."
    IMPORT_EXIT=0
    set +e
    ssh $SSH_OPTS "$DEPLOY_TARGET" "bash -lc 'solar-harness migrate import ~/solar-bundles/latest.tar'" 2>&1
    IMPORT_EXIT=$?
    set -e

    if [[ $IMPORT_EXIT -ne 0 ]]; then
      err "远程 import 失败 (exit=$IMPORT_EXIT)"
      exit 1
    fi

    # Step 4: Remote doctor
    ok "Step 4/4: Remote doctor..."
    DOCTOR_EXIT=0
    set +e
    ssh $SSH_OPTS "$DEPLOY_TARGET" "bash -lc 'solar-harness doctor'" 2>&1
    DOCTOR_EXIT=$?
    set -e

    if [[ $DOCTOR_EXIT -ne 0 ]]; then
      warn "远程 doctor 检查失败, 自动 rollback --diff..."
      ssh $SSH_OPTS "$DEPLOY_TARGET" "bash -lc 'solar-harness migrate rollback --diff --confirm'" 2>&1 || true
      err "部署失败: doctor 检查未通过, 已自动回滚"
      exit 1
    fi

    echo ""
    echo "──────────────────────────────────────────────────"
    ok "一键部署完成: $DEPLOY_TARGET"
    echo "──────────────────────────────────────────────────"
    echo ""
    ;;
  reload)
    # Sprint 20260423-062851 D3: 热加载 coordinator (kill + watchdog 拉新)
    if ! tmux_has_exact_session "solar-harness"; then
      err "tmux session solar-harness 不存在, 无法 reload"
      exit 1
    fi
    coord_pidfile="$HARNESS_DIR/.coordinator.pid"
    old_pid=""
    [[ -f "$coord_pidfile" ]] && old_pid=$(cat "$coord_pidfile" 2>/dev/null)
    if [[ -z "$old_pid" ]] || ! kill -0 "$old_pid" 2>/dev/null; then
      err "Coordinator 未运行 (PID=${old_pid:-empty})"
      exit 1
    fi
    old_md5=""
    old_md5=$(md5 -q "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 'unknown')
    ok "旧 Coordinator: PID=${old_pid}, md5=${old_md5}"
    kill -TERM "$old_pid" 2>/dev/null || true
    ok "已发送 SIGTERM, 等待 watchdog 拉起新实例..."
    waited=0
    new_pid=""
    while (( waited < 40 )); do
      sleep 1
      waited=$((waited + 1))
      [[ -f "$coord_pidfile" ]] && new_pid=$(cat "$coord_pidfile" 2>/dev/null)
      if [[ -n "$new_pid" ]] && kill -0 "$new_pid" 2>/dev/null && [[ "$new_pid" != "$old_pid" ]]; then
        break
      fi
      # exec 热加载 PID 不变, 但进程是新的 — 检查 md5 log
      if [[ "$new_pid" == "$old_pid" ]] && [[ -f "$HARNESS_DIR/.coordinator.log" ]]; then
        if tail -20 "$HARNESS_DIR/.coordinator.log" 2>/dev/null | grep -q "hot-reload\|coordinator.sh md5="; then
          break
        fi
      fi
    done
    if [[ -z "$new_pid" ]] || ! kill -0 "$new_pid" 2>/dev/null; then
      err "Watchdog 未能拉起新 coordinator (${waited}s), 请手动: bash $HARNESS_DIR/coordinator-watchdog.sh start"
      exit 1
    fi
    new_md5=""
    new_md5=$(md5 -q "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo 'unknown')
    ok "新 Coordinator: PID=${new_pid}, md5=${new_md5}"
    ;;
  update-contract)
    do_update_contract "$@"
    ;;
  context)
    shift
    _context_subcmd="${1:-inject}"; shift || true
    _context_py="$HARNESS_DIR/lib/solar-unified-context.py"
    if [[ ! -f "$_context_py" ]]; then
      err "solar-unified-context.py not found: $_context_py"
      exit 1
    fi
    case "$_context_subcmd" in
      inject)
        _query=""
        _format="hook"
        _json_requested="0"
        _args=()
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --query|-q)
              [[ -z "${2:-}" ]] && { err "--query requires text"; exit 1; }
              _query="$2"; shift 2 ;;
            --format)
              [[ -z "${2:-}" ]] && { err "--format requires hook|markdown"; exit 1; }
              _format="$2"; shift 2 ;;
            --json|--max-hits|--max-chars|--timeout-ms|--fail-open)
              [[ "$1" == "--json" ]] && _json_requested="1"
              _args+=("$1")
              if [[ "$1" != "--json" && "$1" != "--fail-open" ]]; then
                [[ -z "${2:-}" ]] && { err "$1 requires value"; exit 1; }
                _args+=("$2"); shift 2
              else
                shift
              fi ;;
            *)
              if [[ -z "$_query" ]]; then _query="$1"; else _args+=("$1"); fi
              shift ;;
          esac
        done
        [[ -n "$_query" ]] || { err "Usage: $0 context inject --query \"<text>\" [--format hook|markdown|--json]"; exit 2; }
        if [[ "$_format" != "hook" && "$_json_requested" != "1" ]]; then
          type solar_capability_prefix >/dev/null 2>&1 && solar_capability_prefix "knowledge" "context inject query=${_query:0:80}"
        fi
        python3 "$_context_py" --query "$_query" --format "$_format" --fail-open ${_args[@]+"${_args[@]}"}
        ;;
      status)
        python3 "$_context_py" --query "Solar Harness Obsidian QMD Mirage" --json --max-hits 3 --fail-open
        ;;
      *)
        err "Usage: $0 context [inject|status] --query \"<text>\""
        exit 2
        ;;
    esac
    ;;
  ragflow)
    shift
    _ragflow_adapter="$HARNESS_DIR/lib/ragflow_adapter.py"
    if [[ ! -f "$_ragflow_adapter" ]]; then
      err "RAGFlow adapter not found: $_ragflow_adapter"
      exit 1
    fi
    python3 "$_ragflow_adapter" "$@"
    ;;
  experience)
    # Solar Experience Memory Layer (sprint-20260509-205414)
    shift
    _exp_runner="$(dirname "$0")/lib/experience_runner.py"
    python3 "$_exp_runner" "$@"
    ;;
  help|--help|-h)
    echo "Solar Harness — multi-agent cockpit runtime"
    echo ""
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Cockpit & status:"
    echo "  $0 start [workdir] [--skip-doctor]   start the cockpit (tmux + selected runtime panes)"
    echo "  $0 2 [workdir]                        start the 2-pane cockpit"
    echo "  $0 status                            show cockpit status"
    echo "  $0 main-status                       main screen: runtime + assignment + artifact status"
    echo "  $0 lab-status                        lab pane: runtime + handoff artifact status"
    echo "  $0 runtime show                       show selected pane runtime"
    echo "  $0 runtime use codex|claude           persist repo-local pane runtime default"
    echo "  $0 actorhost-status [--json] [--host-type TYPE]  actor/host/lease taxonomy"
    echo "  $0 preflight                         check launch dependencies (does not start tmux/runtime panes)"
    echo "  $0 doctor                            environment self-check"
    echo "  $0 attach                            re-attach to the tmux session"
    echo "  $0 extend                            start the separate second quad-pane (solar-harness-lab)"
    echo "  $0 reload                            hot-reload the coordinator (kill + watchdog respawn)"
    echo "  $0 kill                              stop the cockpit"
    echo ""
    echo "Intake & sprint lifecycle:"
    echo "  $0 intake \"request\"                  main entry: create sprint/epic + raw record + trigger autopilot"
    echo "  $0 sprint \"request\"                  create a Sprint/Epic (no auto-dispatch; legacy-compatible)"
    echo "  $0 bg \"task\"                         run a task in a background tmux window (status/logs/attach/cancel)"
    echo "  $0 wake [sprint-id]                  list unfinished Sprints, or resume one (see: $0 wake --help)"
    echo "  $0 plan-verdict <sid> approve|reject [reason]   atomic plan approval"
    echo "  $0 eval-verdict <sid> pass|fail [reason]        atomic evaluation verdict"
    echo "  $0 parallel-integrate <sid> [repo-root]         integrate parallel builder worktrees"
    echo "  $0 verify-events <sid>               event-consistency check"
    echo "  $0 capsule show <sid>                show the State Capsule summary"
    echo "  $0 ledger show <sid>                 show the Bridge Ledger event stream"
    echo "  $0 update-contract <id> <section> <content>     update a contract"
    echo ""
    echo "Scheduling & multi-task:"
    echo "  $0 multi-task [screen|start|status|profiles|doctor|logs|attach|foreground|cancel]  background DAG worker pool"
    echo "  $0 monitor [--host HOST] [--apply|--dry-run] [--json|--loop]  multi-task monitor / safe-advance (optionally across hosts)"
    echo "  $0 monitor tui                       open the legacy tmux monitor window"
    echo "  $0 autopilot [status|apply|dispatch|loop|start|stop|service-status|queue]  auto-advance stalled sprints/panes"
    echo "  $0 symphony [status|dry-run|workspace <sid>]    Symphony scheduling"
    echo "  $0 graph-scheduler [validate|ready|batches|...|parent-check]  DAG parallel scheduling"
    echo "  $0 graph-dispatch [dispatch-ready|drain-queue]  DAG node-level pane dispatch"
    echo "  $0 workflow-guard route <sid> [--json]          PM->Planner->DAG-Builder gate"
    echo "  $0 architecture-guard validate --graph sprint.task_graph.json [--strict]  package-first architecture gate"
    echo ""
    echo "Servers & output:"
    echo "  $0 webhook [start|stop|status]                  manage the webhook server"
    echo "  $0 status-server [start|stop|restart|status]    manage the HTTP status panel (port 8765)"
    echo "  $0 tvs render < payload.json                    deterministic structured-output rendering (TVS)"
    echo "  $0 mermaid [--open] [file.mmd]                  open a Mermaid .mmd architecture diagram"
    echo ""
    echo "Knowledge & integrations (advanced):"
    echo "  $0 context inject --query \"q\" [--format hook|markdown|--json]  knowledge context injection"
    echo "  $0 wiki [install|status|query|ingest|...|help]  Obsidian wiki integration"
    echo "  $0 ragflow [doctor|config|search|evidence-pack|export-manifest]  RAGFlow retrieval adapter"
    echo "  $0 mirage [search|doctor|workspace|mounts|exec|provision]  Mirage unified virtual filesystem"
    echo "  $0 integrations status [--json]                 external integration health check"
    echo "  $0 verify-integrations                          end-to-end integration + dispatch verification"
    echo "  $0 everything-claude-code [doctor|inventory|report|install --dry-run]  ECC integration audit"
    echo "  $0 meta-harness [status|doctor|run|apply|history]  self-optimization outer loop (default dry-run)"
    echo ""
    echo "Cross-machine:"
    echo "  $0 migrate <export|import|verify|rollback|deploy|bootstrap>  cross-machine migration"
    echo "  $0 deploy <user@host> [--force]                 one-shot deploy to another machine"
    ;;
  mirage)
    # Mirage unified virtual filesystem — sprint-20260508-mirage-unified-vfs
    shift
    _mirage_wrapper="$HARNESS_DIR/lib/solar_mirage.py"
    if [[ ! -f "$_mirage_wrapper" ]]; then
      err "Mirage wrapper not found: $_mirage_wrapper"
      exit 1
    fi
    python3 "$_mirage_wrapper" "$@"
    ;;
  wiki)
    # Obsidian Wiki integration — sprint-20260507-obsidian-wiki
    shift
    _wiki_subcmd="${1:-help}"; shift || true
    _wiki_installer="$HARNESS_DIR/integrations/obsidian-wiki.sh"
    _wiki_exporter="$HARNESS_DIR/integrations/obsidian-wiki-export.sh"
    _wiki_bridge="$HARNESS_DIR/integrations/obsidian-wiki-bridge.sh"
    case "$_wiki_subcmd" in
      install)
        if [[ -f "$_wiki_installer" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_installer"
          cmd_wiki_install "$@"
        else
          err "Wiki installer not found: $_wiki_installer"
          err "Integration may not be fully deployed yet."
          exit 1
        fi
        ;;
      status)
        if [[ -f "$_wiki_installer" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_installer"
          cmd_wiki_status "$@"
        else
          err "Wiki installer not found: $_wiki_installer"
          exit 1
        fi
        ;;
      export-sprint)
        if [[ -f "$_wiki_exporter" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_exporter"
          cmd_wiki_export_sprint "$@"
        elif [[ -f "$_wiki_installer" ]]; then
          # fallback: export may be embedded in installer
          source "$_wiki_installer"
          cmd_wiki_export_sprint "$@"
        else
          err "Wiki export module not found: $_wiki_exporter"
          exit 1
        fi
        ;;
      update)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_update "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      query)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_query "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      ingest)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_ingest "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      knowledge-ingest)
        _knowledge_ingest="${HARNESS_DIR}/lib/knowledge_ingest_dispatcher.py"
        if [[ ! -f "$_knowledge_ingest" ]]; then
          err "knowledge ingest dispatcher not found: $_knowledge_ingest"
          exit 1
        fi
        python3 "$_knowledge_ingest" "$@"
        ;;
      chatgpt-import|import-chatgpt)
        _chatgpt_importer="${HARNESS_DIR}/lib/chatgpt-conversation-ingest.py"
        if [[ ! -f "$_chatgpt_importer" ]]; then
          err "ChatGPT importer not found: $_chatgpt_importer"
          exit 1
        fi
        python3 "$_chatgpt_importer" "$@"
        ;;
      vault-status)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_vault_status "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      lint)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_lint "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      rebuild)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_rebuild "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      export-graph)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_export_graph "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      colorize)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_colorize "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      history)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_history "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      run-dispatch)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_run_dispatch "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      dispatch-watch)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_dispatch_watch "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      dispatch-maintenance|dispatch-doctor)
        _dispatch_maint="${HARNESS_DIR}/lib/wiki-dispatch-maintenance.py"
        if [[ ! -f "$_dispatch_maint" ]]; then
          err "wiki dispatch maintenance not found: $_dispatch_maint"
          exit 1
        fi
        python3 "$_dispatch_maint" "$@"
        ;;
      import-solar-db)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_import_solar_db "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      capture-server)
        if [[ -f "$_wiki_bridge" ]]; then
          # shellcheck disable=SC1090
          source "$_wiki_bridge"
          cmd_wiki_capture_server "$@"
        else
          err "Wiki bridge not found: $_wiki_bridge"
          exit 1
        fi
        ;;
      sync-vault)
        # S2.5: Index ~/Knowledge (or --vault PATH) into Solar DB
        _indexer="${HARNESS_DIR}/lib/obsidian-vault-indexer.py"
        _sv_vault="${OBSIDIAN_VAULT_PATH:-$HOME/Knowledge}"
        _sv_args=()
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --vault) [[ -z "${2:-}" ]] && { err "--vault requires a path"; exit 1; }
                     _sv_vault="$2"; shift 2 ;;
            --once|--dry-run|--json) _sv_args+=("$1"); shift ;;
            --max-files) _sv_args+=("$1" "${2:?}"); shift 2 ;;
            *) err "unknown sync-vault arg: $1"; exit 1 ;;
          esac
        done
        if [[ ! -f "$_indexer" ]]; then
          err "obsidian-vault-indexer not found: $_indexer"
          exit 1
        fi
        python3 "$_indexer" --vault "$_sv_vault" --once "${_sv_args[@]}"
        ;;
      audit-uploads)
        # B3: Audit a file-upload batch for vault/qmd/DB coverage
        _auditor="${HARNESS_DIR}/lib/wiki-upload-audit.py"
        if [[ ! -f "$_auditor" ]]; then
          err "wiki-upload-audit not found: $_auditor"
          exit 1
        fi
        python3 "$_auditor" "$@"
        ;;
      backfill-uploads)
        # B3: Backfill qmd/vault/DB for a file-upload batch
        _backfill="${HARNESS_DIR}/lib/wiki-upload-backfill.py"
        if [[ ! -f "$_backfill" ]]; then
          err "wiki-upload-backfill not found: $_backfill"
          exit 1
        fi
        if python3 "$_backfill" "$@"; then
          if printf ' %s ' "$*" | grep -q ' --repair '; then
            _quality_gate="${HARNESS_DIR}/lib/wiki-quality-gate.py"
            if [[ -f "$_quality_gate" ]]; then
              warn "running post-backfill quality gate; low-quality stubs will be quarantined"
              python3 "$_quality_gate" --apply --json
            fi
          fi
        else
          exit $?
        fi
        ;;
      quality-gate)
        # Quarantine low-quality PDF/stub pages before they pollute default KB retrieval.
        _quality_gate="${HARNESS_DIR}/lib/wiki-quality-gate.py"
        if [[ ! -f "$_quality_gate" ]]; then
          err "wiki-quality-gate not found: $_quality_gate"
          exit 1
        fi
        python3 "$_quality_gate" "$@"
        ;;
      reingest-quarantine)
        # Create deep paper reingest dispatches for quarantined PDF/stub pages.
        _reingest_quarantine="${HARNESS_DIR}/lib/wiki-reingest-quarantine.py"
        if [[ ! -f "$_reingest_quarantine" ]]; then
          err "wiki-reingest-quarantine not found: $_reingest_quarantine"
          exit 1
        fi
        python3 "$_reingest_quarantine" "$@"
        ;;
      reingest-scheduler)
        _reingest_scheduler="${HARNESS_DIR}/lib/wiki-reingest-scheduler.sh"
        _reingest_session="${SOLAR_REINGEST_SESSION_NAME:-solar-wiki-reingest-scheduler}"
        if [[ ! -x "$_reingest_scheduler" ]]; then
          err "wiki-reingest-scheduler not executable: $_reingest_scheduler"
          exit 1
        fi
        case "${1:-status}" in
          start)
            _interval="${2:-60}"
            if tmux_has_exact_session "$_reingest_session"; then
              ok "wiki reingest scheduler already running ($_reingest_session)"
            else
              _reingest_panes="${SOLAR_REINGEST_PANES:-}"
              if [[ -n "$_reingest_panes" ]]; then
                tmux new-session -d -s "$_reingest_session" "SOLAR_REINGEST_PANES=$(printf '%q' "$_reingest_panes") $_reingest_scheduler loop '$_interval'"
              else
                tmux new-session -d -s "$_reingest_session" "$_reingest_scheduler loop '$_interval'"
              fi
              ok "wiki reingest scheduler started ($_reingest_session, interval=${_interval}s)"
            fi
            ;;
          stop)
            tmux kill-session -t "$_reingest_session" 2>/dev/null || true
            ok "wiki reingest scheduler stopped ($_reingest_session)"
            ;;
          run-once)
            "$_reingest_scheduler" run-once
            ;;
          status)
            if tmux_has_exact_session "$_reingest_session"; then
              ok "wiki reingest scheduler running ($_reingest_session)"
            else
              warn "wiki reingest scheduler not running ($_reingest_session)"
            fi
            "$_reingest_scheduler" status
            ;;
          *)
            err "Usage: $0 wiki reingest-scheduler [start [interval]|stop|status|run-once]"
            exit 2
            ;;
        esac
        ;;
      qmd-repair|mineru-repair)
        _qmd_repair="${HARNESS_DIR}/lib/qmd-launcher-repair.sh"
        [[ -x "$_qmd_repair" ]] || { err "qmd launcher repair not found: $_qmd_repair"; exit 1; }
        "$_qmd_repair" "$@"
        ;;
      qmd-status|mineru-status)
        _QMD_BIN="$(solar_qmd_bin_or_empty)"
        [[ -n "$_QMD_BIN" ]] || { err "qmd not found; install mineru-document-explorer"; exit 1; }
        solar_export_qmd_runtime_path "$_QMD_BIN"
        _qmd_status_out=""
        _qmd_status_rc=0
        _qmd_repair="${HARNESS_DIR}/lib/qmd-launcher-repair.sh"
        set +e
        _qmd_status_out="$("$_QMD_BIN" status "$@" 2>&1)"
        _qmd_status_rc=$?
        set -e
        if [[ "$_qmd_status_rc" != "0" ]] && printf '%s\n' "$_qmd_status_out" | grep -Eiq 'NODE_MODULE_VERSION|ERR_DLOPEN_FAILED|better-sqlite3' && [[ -x "$_qmd_repair" ]]; then
          warn "qmd native-module ABI error detected; attempting launcher repair"
          "$_qmd_repair" --apply >&2 || true
          set +e
          _qmd_status_out="$("$_QMD_BIN" status "$@" 2>&1)"
          _qmd_status_rc=$?
          set -e
        fi
        printf '%s\n' "$_qmd_status_out"
        exit "$_qmd_status_rc"
        ;;
      qmd-search|mineru-search)
        _QMD_BIN="$(solar_qmd_bin_or_empty)"
        [[ -n "$_QMD_BIN" ]] || { err "qmd not found; install mineru-document-explorer"; exit 1; }
        solar_export_qmd_runtime_path "$_QMD_BIN"
        if [[ $# -lt 1 ]]; then
          err "Usage: $0 wiki qmd-search \"<query>\" [qmd search args]"
          exit 2
        fi
        "$_QMD_BIN" search "$1" -c "${QMD_WIKI_COLLECTION:-solar-wiki}" "${@:2}"
        ;;
      qmd-update|mineru-update)
        _QMD_BIN="$(solar_qmd_bin_or_empty)"
        [[ -n "$_QMD_BIN" ]] || { err "qmd not found; install mineru-document-explorer"; exit 1; }
        solar_export_qmd_runtime_path "$_QMD_BIN"
        "$_QMD_BIN" update "$@"
        ;;
      qmd-mcp|mineru-mcp)
        _QMD_BIN="$(solar_qmd_bin_or_empty)"
        [[ -n "$_QMD_BIN" ]] || { err "qmd not found; install mineru-document-explorer"; exit 1; }
        solar_export_qmd_runtime_path "$_QMD_BIN"
        _QMD_PROXY="${HARNESS_DIR}/lib/qmd-ipv4-proxy.py"
        _QMD_PROXY_PID="${HARNESS_DIR}/run/qmd-mcp-ipv4-proxy.pid"
        _QMD_PROXY_SESSION="solar-qmd-mcp-proxy"
        _qmd_mcp_hosts() {
          python3 - <<'PY'
import socket
hosts=["127.0.0.1","::1","localhost"]
open_hosts=[]
for h in hosts:
    try:
        s=socket.create_connection((h,8181),timeout=0.4)
        s.close()
        open_hosts.append(h)
    except OSError:
        pass
print(",".join(open_hosts))
PY
        }
        _qmd_proxy_start() {
          [[ -f "$_QMD_PROXY" ]] || { err "qmd IPv4 proxy missing: $_QMD_PROXY"; return 1; }
          mkdir -p "$HARNESS_DIR/run"
          if tmux_has_exact_session "$_QMD_PROXY_SESSION"; then
            return 0
          fi
          if [[ -f "$_QMD_PROXY_PID" ]]; then
            _proxy_pid="$(cat "$_QMD_PROXY_PID" 2>/dev/null || true)"
            if [[ -n "$_proxy_pid" ]] && kill -0 "$_proxy_pid" 2>/dev/null; then
              return 0
            fi
            rm -f "$_QMD_PROXY_PID"
          fi
          tmux new-session -d -s "$_QMD_PROXY_SESSION" "python3 '$_QMD_PROXY' \
            --listen-host 127.0.0.1 --listen-port 8181 \
            --target-host ::1 --target-port 8181 \
            --pid-file "$_QMD_PROXY_PID" \
            >> '$HARNESS_DIR/run/qmd-mcp-ipv4-proxy.log' 2>&1"
          sleep 0.4
        }
        _qmd_proxy_stop() {
          tmux kill-session -t "$_QMD_PROXY_SESSION" 2>/dev/null || true
          if [[ -f "$_QMD_PROXY_PID" ]]; then
            _proxy_pid="$(cat "$_QMD_PROXY_PID" 2>/dev/null || true)"
            [[ -n "$_proxy_pid" ]] && kill "$_proxy_pid" 2>/dev/null || true
            rm -f "$_QMD_PROXY_PID"
          fi
        }
        case "${1:-status}" in
          status)
            _qmd_mcp_probe="$(_qmd_mcp_hosts)"
            if [[ -n "$_qmd_mcp_probe" ]]; then
              if [[ "$_qmd_mcp_probe" == *"127.0.0.1"* ]]; then
                ok "qmd MCP running → http://127.0.0.1:8181/mcp (hosts: $_qmd_mcp_probe)"
              else
                warn "qmd MCP running, but not on 127.0.0.1 (hosts: $_qmd_mcp_probe). Use localhost/[::1] or restart if a strict IPv4 client requires it."
              fi
              lsof -nP -iTCP:8181 -sTCP:LISTEN | tail -1 || true
            else
              err "qmd MCP not listening on 8181"
              exit 1
            fi
            ;;
          start)
            _qmd_mcp_probe="$(_qmd_mcp_hosts)"
            if [[ -z "$_qmd_mcp_probe" ]]; then
              "$_QMD_BIN" mcp --http --daemon
              sleep 1
              _qmd_mcp_probe="$(_qmd_mcp_hosts)"
            fi
            if [[ "$_qmd_mcp_probe" == *"127.0.0.1"* ]]; then
              ok "qmd MCP already reachable on 127.0.0.1:8181"
              exit 0
            fi
            if [[ "$_qmd_mcp_probe" == *"::1"* || "$_qmd_mcp_probe" == *"localhost"* ]]; then
              _qmd_proxy_start
              _qmd_mcp_probe="$(_qmd_mcp_hosts)"
              if [[ "$_qmd_mcp_probe" == *"127.0.0.1"* ]]; then
                ok "qmd MCP IPv4 proxy running → 127.0.0.1:8181 -> ::1:8181"
                exit 0
              fi
            fi
            err "qmd MCP failed to become reachable on 127.0.0.1:8181"
            exit 1
            ;;
          stop-proxy)
            _qmd_proxy_stop
            ok "qmd MCP IPv4 proxy stopped"
            ;;
          *)
            err "Usage: $0 wiki qmd-mcp [status|start|stop-proxy]"
            exit 2
            ;;
        esac
        ;;
      qmd-embed|mineru-embed)
        _embed_runner="${HARNESS_DIR}/lib/qmd-embed-runner.sh"
        _embed_plist="$HOME/Library/LaunchAgents/com.solar.qmd-mineru-embed.plist"
        _embed_status="${HARNESS_DIR}/state/qmd-embed-status.json"
        _embed_lock="${HARNESS_DIR}/run/qmd-embed.lockdir"
        _embed_lock_pid="${_embed_lock}/pid"
        _embed_label="com.solar.qmd-mineru-embed"
        case "${1:-status}" in
          start)
            [[ -x "$_embed_runner" ]] || { err "qmd embed runner not executable: $_embed_runner"; exit 1; }
            launchctl bootout "gui/$(id -u)" "$_embed_plist" >/dev/null 2>&1 || true
            launchctl bootstrap "gui/$(id -u)" "$_embed_plist"
            mkdir -p "$(dirname "$_embed_status")"
            cat > "$_embed_status" <<EOF
{
  "state": "scheduled",
  "collection": "solar-wiki",
  "mode": "gentle",
  "updated_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "detail": "launchd loaded; gentle background mode uses low priority, load guard, and time slices",
  "log": "${HARNESS_DIR}/run/qmd-embed.log"
}
EOF
            ok "qmd embedding gentle scheduler loaded ($_embed_label); low priority, load guarded"
            ;;
          run-once)
            [[ -x "$_embed_runner" ]] || { err "qmd embed runner not executable: $_embed_runner"; exit 1; }
            "$_embed_runner"
            ;;
          run-idle)
            [[ -x "$_embed_runner" ]] || { err "qmd embed runner not executable: $_embed_runner"; exit 1; }
            SOLAR_QMD_EMBED_MODE=idle "$_embed_runner"
            ;;
          run-gentle)
            [[ -x "$_embed_runner" ]] || { err "qmd embed runner not executable: $_embed_runner"; exit 1; }
            SOLAR_QMD_EMBED_MODE=gentle "$_embed_runner"
            ;;
          run-now)
            [[ -x "$_embed_runner" ]] || { err "qmd embed runner not executable: $_embed_runner"; exit 1; }
            SOLAR_QMD_EMBED_MODE=force SOLAR_QMD_EMBED_FORCE=1 "$_embed_runner"
            ;;
          stop)
            launchctl bootout "gui/$(id -u)" "$_embed_plist" >/dev/null 2>&1 || true
            pkill -f 'qmd embed -c solar-wiki' >/dev/null 2>&1 || true
            mkdir -p "$(dirname "$_embed_status")"
            cat > "$_embed_status" <<EOF
{
  "state": "stopped",
  "collection": "solar-wiki",
  "mode": "stopped",
  "updated_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "detail": "launchd unloaded and active qmd embed process stopped",
  "log": "${HARNESS_DIR}/run/qmd-embed.log"
}
EOF
            ok "qmd embedding background job stopped ($_embed_label)"
            ;;
          status)
            if launchctl print "gui/$(id -u)/$_embed_label" >/dev/null 2>&1; then
              ok "qmd embedding launchd loaded ($_embed_label)"
            else
              warn "qmd embedding launchd not loaded"
            fi
            if [[ -f "$_embed_status" ]] && grep -Eq '"state"[[:space:]]*:[[:space:]]*"(running|locked)"' "$_embed_status"; then
              _lock_pid="$(cat "$_embed_lock_pid" 2>/dev/null || true)"
              if [[ -z "$_lock_pid" || ! "$_lock_pid" =~ ^[0-9]+$ || ! -d "/proc/$_lock_pid" ]]; then
                # macOS has no /proc; kill -0 is the portable live-pid check.
                if [[ -z "$_lock_pid" || ! "$_lock_pid" =~ ^[0-9]+$ ]] || ! kill -0 "$_lock_pid" 2>/dev/null; then
                  _pending_after="$("$0" wiki qmd-status 2>/dev/null | awk '/Pending:/ {print $2; found=1; exit} END {if (!found) print "0"}')"
                  mkdir -p "$(dirname "$_embed_status")"
                  cat > "$_embed_status" <<EOF
{
  "state": "error",
  "collection": "solar-wiki",
  "mode": "stale",
  "updated_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "pending_before": "",
  "pending_after": "${_pending_after}",
  "detail": "stale qmd embed status/lock detected; no live runner pid (${_lock_pid:-N/A})",
  "log": "${HARNESS_DIR}/run/qmd-embed.log"
}
EOF
                  rm -f "$_embed_lock_pid" 2>/dev/null || true
                  rmdir "$_embed_lock" 2>/dev/null || true
                  warn "stale qmd embed lock/status repaired"
                fi
              fi
            fi
            if [[ -f "$_embed_status" ]]; then
              cat "$_embed_status"
            else
              warn "no qmd embed status yet: $_embed_status"
            fi
            ;;
          *)
            err "Usage: $0 wiki qmd-embed [start|status|stop|run-once|run-idle|run-gentle|run-now]"
            exit 2
            ;;
        esac
        ;;
      mineru-doctor)
        # sprint-20260509-mineru-mirage-closeout S1: doctor per design §2.1
        _md_py="$HARNESS_DIR/lib/mineru_doctor.py"
        if [[ ! -f "$_md_py" ]]; then err "mineru_doctor.py not found: $_md_py"; exit 1; fi
        python3 "$_md_py" "$@"
        ;;
      export-accepted)
        # sprint-20260508-accepted-artifact-knowledge: export PASS-only sprint artifact
        _aae="$HARNESS_DIR/lib/accepted-artifact-export.py"
        if [[ ! -f "$_aae" ]]; then
          err "accepted-artifact-export.py not found: $_aae"
          exit 1
        fi
        python3 "$_aae" export "$@"
        ;;
      backfill-accepted)
        # sprint-20260508-accepted-artifact-knowledge: backfill passed sprints (default dry-run)
        _aae="$HARNESS_DIR/lib/accepted-artifact-export.py"
        if [[ ! -f "$_aae" ]]; then
          err "accepted-artifact-export.py not found: $_aae"
          exit 1
        fi
        python3 "$_aae" backfill "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Harness Wiki — Obsidian LLM Wiki integration"
        echo ""
        echo "Usage:"
        echo "  $0 wiki install --vault <path> [--repo <path>] [--refresh]"
        echo "  $0 wiki status [--json]"
        echo "  $0 wiki export-sprint <sid> [--redact|--full]"
        echo "  $0 wiki update [--project <path>] [--mode append|full]"
        echo "  $0 wiki query \"<question>\" [--quick]"
        echo "  $0 wiki ingest [--source <path>] [--mode append|full|raw] [--project <name>]"
        echo "  $0 wiki knowledge-ingest <status|migrate|submit-event|discover-raw|discover-sources|discover-vault|process-queue|run-pipeline|reconcile|import-legacy-extracted|dashboard|coverage-report|drain-retry|drain-skip|discover-youtube|discover-github|discover-pdf|discover-accepted|discover-solar> [args]"
        echo "  $0 wiki chatgpt-import [--browser-all [auto|chrome|arc|edge|brave|safari]|--browser [auto|chrome|arc|edge|brave|safari]|--source <conversations.json|transcript.md|dir|->|--clipboard] [--no-dispatch] [--limit N]"
        echo "  $0 wiki vault-status [--insights]"
        echo "  $0 wiki lint [--fix]"
        echo "  $0 wiki rebuild [--mode archive-only|archive-rebuild|restore] [--archive <name>]"
        echo "  $0 wiki export-graph [--all|--public]"
        echo "  $0 wiki colorize [--mode by-tag|by-category|by-visibility|combined|custom]"
        echo "  $0 wiki history [--target claude|codex|copilot|hermes|openclaw|auto] [--query <topic>]"
        echo "  $0 wiki run-dispatch <dispatch.md> [--lab-builder 1|2|3|4|--main-builder|--pane <target>] [--dry-run]"
        echo "  $0 wiki dispatch-watch [--once|--loop] [--limit N] [--interval seconds] [--dry-run]"
        echo "  $0 wiki dispatch-maintenance [status|repair --apply] [--json]"
        echo "  $0 wiki import-solar-db [--scope solar|all] [--per-table-limit N] [--no-dispatch]"
        echo "  $0 wiki capture-server [start|stop|restart|status] [--port N] [--open]"
        echo "  $0 wiki sync-vault [--vault PATH] [--once] [--dry-run] [--json]"
        echo "  $0 wiki audit-uploads --batch <batch_id> [--json]"
        echo "  $0 wiki backfill-uploads --batch <batch_id> [--repair] [--json]"
        echo "  $0 wiki quality-gate [--apply] [--json] [--vault PATH]"
        echo "  $0 wiki reingest-quarantine [--manifest PATH] [--limit N] [--json] [--dry-run]"
        echo "  $0 wiki reingest-scheduler [start [interval]|stop|status|run-once]"
        echo "  $0 wiki qmd-status"
        echo "  $0 wiki qmd-repair [--check|--apply] [--json]"
        echo "  $0 wiki qmd-search \"<query>\" [-n N|--json|--files]"
        echo "  $0 wiki qmd-update"
        echo "  $0 wiki qmd-mcp [status|start|stop-proxy]"
        echo "  $0 wiki qmd-embed [start|status|stop|run-once|run-idle|run-gentle|run-now]"
        echo "  $0 wiki ai-influence-digest [run|status|doctor|send-test|schedule|help]"
        echo "  $0 wiki tech-hotspot-radar [status|plan-ai-influence-reports|run-ai-influence-planned-reports|validate-ai-influence-planned-reports|process-transcripts|help]"
        echo ""
        echo "Examples:"
        echo "  $0 wiki install --vault ~/Documents/SolarWiki"
        echo "  $0 wiki status --json"
        echo "  $0 wiki export-sprint sprint-20260507-symphony3 --redact"
        echo "  $0 wiki update --mode append"
        echo "  $0 wiki query \"What did sprint symphony1 achieve?\""
        echo "  $0 wiki ingest --source ~/Downloads/paper.pdf --mode append"
        echo "  $0 wiki chatgpt-import --browser-all      # preferred: capture all open ChatGPT conversation tabs"
        echo "  $0 wiki chatgpt-import --browser          # preferred: capture active ChatGPT tab"
        echo "  $0 wiki chatgpt-import --source ~/Downloads/conversations.json --limit 50"
        echo "  pbpaste | $0 wiki chatgpt-import --source -"
        echo "  $0 wiki history --target codex --query \"rust ownership\""
        echo "  $0 wiki colorize --mode by-category"
        echo "  $0 wiki run-dispatch \"\$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/wiki-ingest-<ts>.md\" --lab-builder 1"
        echo "  $0 wiki dispatch-watch --once --limit 4"
        echo "  $0 wiki import-solar-db --scope solar --per-table-limit 25"
        echo "  $0 wiki capture-server start --open"
        echo "  $0 wiki qmd-search \"Solar Harness Obsidian\" -n 5 --json"
        echo "  $0 wiki audit-uploads --batch 20260508T122047Z --json"
        echo "  $0 wiki backfill-uploads --batch 20260508T122047Z --repair --json"
        echo "  $0 wiki quality-gate --apply --json"
        echo "  $0 wiki reingest-quarantine --limit 8 --json"
        echo "  $0 wiki reingest-scheduler start 60"
        echo "  $0 wiki tech-hotspot-radar validate-ai-influence-planned-reports --date 2026-05-25 --require-project-archive"
        ;;
      tech-hotspot-radar)
        _thr_script="$HARNESS_DIR/scripts/tech_hotspot_radar.py"
        if [[ ! -f "$_thr_script" ]]; then
          err "Tech Hotspot Radar script not found: $_thr_script"
          exit 1
        fi
        case "${1:-help}" in
          help|--help|-h|"")
            python3 "$_thr_script" --help
            ;;
          *)
            python3 "$_thr_script" "$@"
            ;;
        esac
        ;;
      ai-influence-digest)
        # sprint-20260522-ai-influence-digest-scan N5: AI Influence Digest CLI
        _ai_digest_script="$HARNESS_DIR/scripts/ai_influence_daily.py"
        _ai_digest_accounts="${HARNESS_DIR}/ai-influence-digest/references/accounts_extended.txt"
        _ai_digest_state_dir="$HARNESS_DIR/state/ai-influence-digest"
        _ai_digest_raw_dir="$HOME/Knowledge/_raw/ai-influence-daily-digest"
        _ai_digest_plist="$HOME/Library/LaunchAgents/com.solar.ai-influence-digest.plist"
        _ai_digest_label="com.solar.ai-influence-digest"
        _ai_digest_marker="$HARNESS_DIR/state/ai-influence-digest/schedule.loaded"
        _ai_digest_action="${1:-help}"; shift || true
        case "$_ai_digest_action" in
          run)
            mkdir -p "$_ai_digest_state_dir" "$_ai_digest_raw_dir"
            python3 "$_ai_digest_script" \
              --accounts "$_ai_digest_accounts" \
              --state-dir "$_ai_digest_state_dir" \
              --raw-dir "$_ai_digest_raw_dir" \
              "$@" \
              run
            ;;
          status)
            python3 "$_ai_digest_script" \
              --accounts "$_ai_digest_accounts" \
              --state-dir "$_ai_digest_state_dir" \
              status
            ;;
          doctor)
            python3 "$_ai_digest_script" \
              --accounts "$_ai_digest_accounts" \
              --state-dir "$_ai_digest_state_dir" \
              doctor
            ;;
          send-test)
            _ai_test_root="$(mktemp -d)"
            _ai_test_raw="$_ai_test_root/raw"
            _ai_test_state="$_ai_test_root/state"
            mkdir -p "$_ai_test_raw" "$_ai_test_state"
            echo "send-test isolated raw: $_ai_test_raw" >&2
            python3 "$_ai_digest_script" \
              --accounts "$_ai_digest_accounts" \
              --state-dir "$_ai_test_state" \
              --raw-dir "$_ai_test_raw" \
              --dry-run "$@" \
              run
            ;;
          schedule)
            _sched_act="${1:-status}"; shift || true
            case "$_sched_act" in
              start)
                mkdir -p "$(dirname "$_ai_digest_plist")" "$(dirname "$_ai_digest_marker")" "$HARNESS_DIR/run"
                cat > "$_ai_digest_plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${_ai_digest_label}</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>${HARNESS_DIR}/solar-harness.sh</string>
    <string>wiki</string>
    <string>ai-influence-digest</string>
    <string>run</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>17</integer>
  </dict>
  <key>StandardOutPath</key><string>${HARNESS_DIR}/run/ai-influence-digest.log</string>
  <key>StandardErrorPath</key><string>${HARNESS_DIR}/run/ai-influence-digest.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST
                launchctl bootout "gui/$(id -u)" "$_ai_digest_plist" >/dev/null 2>&1 || true
                if launchctl bootstrap "gui/$(id -u)" "$_ai_digest_plist" >/dev/null 2>&1; then
                  echo "launchctl" > "$_ai_digest_marker"
                else
                  echo "marker" > "$_ai_digest_marker"
                  warn "AI Influence Digest scheduler plist created; launchctl unavailable from this shell, marker recorded"
                fi
                ok "AI Influence Digest scheduler loaded ($_ai_digest_label, daily 07:17)"
                ;;
              stop)
                launchctl bootout "gui/$(id -u)" "$_ai_digest_plist" >/dev/null 2>&1 || true
                rm -f "$_ai_digest_marker"
                ok "AI Influence Digest scheduler stopped ($_ai_digest_label)"
                ;;
              status)
                if launchctl print "gui/$(id -u)/$_ai_digest_label" >/dev/null 2>&1 || [[ -f "$_ai_digest_marker" ]]; then
                  ok "AI Influence Digest schedule loaded ($_ai_digest_label, daily 07:17)"
                else
                  warn "AI Influence Digest schedule not loaded ($_ai_digest_label)"
                fi
                if [[ -f "$_ai_digest_plist" ]]; then
                  echo "  plist: $_ai_digest_plist"
                else
                  echo "  plist: not created yet (run 'schedule start')"
                fi
                ;;
              *)
                err "Usage: $0 wiki ai-influence-digest schedule [start|stop|status]"
                exit 2
                ;;
            esac
            ;;
          help|--help|-h|"")
            echo "Solar Harness Wiki — AI Influence Daily Digest"
            echo ""
            echo "Usage:"
            echo "  $0 wiki ai-influence-digest run [--date YYYY-MM-DD] [--dry-run]"
            echo "  $0 wiki ai-influence-digest status"
            echo "  $0 wiki ai-influence-digest doctor"
            echo "  $0 wiki ai-influence-digest send-test [--date YYYY-MM-DD]"
            echo "  $0 wiki ai-influence-digest schedule [start|stop|status]"
            echo ""
            echo "Schedule: daily at 07:17 local time. Disabled by default; use 'schedule start' to enable."
            echo "send-test writes to mktemp isolated raw/state dirs and never production raw."
            ;;
          *)
            err "Unknown ai-influence-digest action: $_ai_digest_action"
            echo "Run '$0 wiki ai-influence-digest help' for usage." >&2
            exit 1
            ;;
        esac
        ;;
      *)
        err "Unknown wiki subcommand: $_wiki_subcmd"
        echo "Run '$0 wiki help' for usage." >&2
        exit 1
        ;;
    esac
    ;;
  symphony)
    shift
    case "${1:-status}" in
      status)
        python3 "$HARNESS_DIR/lib/symphony/scheduler.py" --status
        ;;
      dry-run)
        python3 "$HARNESS_DIR/lib/symphony/scheduler.py" --dry-run
        ;;
      workspace)
        shift
        [[ -z "${1:-}" ]] && { err "Usage: $0 symphony workspace <sprint-id>"; exit 2; }
        bash "$HARNESS_DIR/lib/symphony/workspace-manager.sh" show "$1"
        ;;
      *)
        echo "Usage: $0 symphony [status|dry-run|workspace <sid>]" >&2
        exit 1
        ;;
    esac
    ;;
  product)
    # S0 snapshot/restore/verify — sprint-20260509-solar-product-platform
    shift
    _prod_py="$HARNESS_DIR/lib/product_snapshot.py"
    if [[ ! -f "$_prod_py" ]]; then
      err "product_snapshot.py not found: $_prod_py"; exit 1
    fi
    _prod_subcmd="${1:-help}"; shift || true
    case "$_prod_subcmd" in
      snapshot)
        python3 "$_prod_py" snapshot "$@"
        ;;
      verify)
        python3 "$_prod_py" verify "$@"
        ;;
      restore)
        python3 "$_prod_py" restore "$@"
        ;;
      list)
        python3 "$_prod_py" list "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Product Snapshot — S0 foundation"
        echo ""
        echo "Usage:"
        echo "  $0 product snapshot [--dry-run] [--scope minimal|full] [--out-dir DIR]"
        echo "  $0 product verify   (--latest | --id SNAP_ID) [--out-dir DIR]"
        echo "  $0 product restore  (--latest | --id SNAP_ID) [--dry-run] [--target-dir DIR]"
        echo "  $0 product list     [--out-dir DIR]"
        ;;
      *)
        err "Unknown product subcommand: $_prod_subcmd"; exit 2
        ;;
    esac
    ;;
  s6-autopilot)
    # S6 Control Plane — autopilot.py (three-state deadlock detection)
    shift
    _ap_py="$HARNESS_DIR/lib/autopilot.py"
    if [[ ! -f "$_ap_py" ]]; then
      err "autopilot.py not found: $_ap_py"; exit 1
    fi
    _ap_subcmd="${1:-status}"; shift || true
    case "$_ap_subcmd" in
      scan|status|fault-report|resolve-deadlock|drain-queue)
        python3 "$_ap_py" "$_ap_subcmd" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar S6 Autopilot — three-state deadlock detection"
        echo ""
        echo "Usage:"
        echo "  $0 s6-autopilot scan            [--sprint SID]"
        echo "  $0 s6-autopilot status          [--sprint SID]"
        echo "  $0 s6-autopilot fault-report    [--sprint SID]"
        echo "  $0 s6-autopilot drain-queue     --sprint SID"
        echo "  $0 s6-autopilot resolve-deadlock --pane P --sprint SID --dispatch-id DID"
        ;;
      *)
        err "Unknown s6-autopilot subcommand: $_ap_subcmd"; exit 2
        ;;
    esac
    ;;

  graph-scheduler)
    # Machine-executable sprint DAG scheduler
    shift
    _graph_py="$HARNESS_DIR/lib/graph_scheduler.py"
    if [[ ! -f "$_graph_py" ]]; then
      err "graph_scheduler.py not found: $_graph_py"; exit 1
    fi
    _graph_subcmd="${1:-help}"; shift || true
    case "$_graph_subcmd" in
      validate|topo|layers|critical-path|ready|batches|enrich-capabilities|enrich-backlog|assign|mark|parent-check|doctor|enqueue-ready)
        python3 "$_graph_py" "$_graph_subcmd" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Graph Scheduler — DAG planning and parallel dispatch"
        echo ""
        echo "Usage:"
        echo "  $0 graph-scheduler validate       --graph sprint.task_graph.json"
        echo "  $0 graph-scheduler topo           --graph sprint.task_graph.json"
        echo "  $0 graph-scheduler layers         --graph sprint.task_graph.json"
        echo "  $0 graph-scheduler critical-path  --graph sprint.task_graph.json"
        echo "  $0 graph-scheduler ready          --graph sprint.task_graph.json"
        echo "  $0 graph-scheduler batches        --graph sprint.task_graph.json [--max-parallel N] [--out dispatch_batches.json]"
        echo "  $0 graph-scheduler enrich-capabilities --graph sprint.task_graph.json [--source contract.md] [--in-place]"
        echo "  $0 graph-scheduler enrich-backlog [--sprints-dir DIR] [--dry-run]"
        echo "  $0 graph-scheduler assign         --graph sprint.task_graph.json --workers workers.json [--max-parallel N]"
        echo "  $0 graph-scheduler doctor         --graph sprint.task_graph.json [--repair --in-place]"
        echo "  $0 graph-scheduler enqueue-ready  --graph sprint.task_graph.json --workers workers.json [--lease] [--in-place]"
        echo "  $0 graph-scheduler mark           --graph sprint.task_graph.json --node S1 --status passed [--in-place]"
        echo "  $0 graph-scheduler parent-check   --graph sprint.task_graph.json"
        ;;
      *)
        err "Unknown graph-scheduler subcommand: $_graph_subcmd"; exit 2
        ;;
    esac
    ;;

  architecture-guard)
    # Package-first architecture guard: new capabilities must be plugin/package/skill/connector first.
    shift
    _arch_guard_py="$HARNESS_DIR/lib/architecture_guard.py"
    if [[ ! -f "$_arch_guard_py" ]]; then
      err "architecture_guard.py not found: $_arch_guard_py"; exit 1
    fi
    _arch_guard_subcmd="${1:-help}"; shift || true
    case "$_arch_guard_subcmd" in
      validate)
        python3 "$_arch_guard_py" validate "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Architecture Guard — package-first / plugin-first development gate"
        echo ""
        echo "Usage:"
        echo "  $0 architecture-guard validate --graph sprint.task_graph.json [--strict]"
        ;;
      *)
        err "Unknown architecture-guard subcommand: $_arch_guard_subcmd"; exit 2
        ;;
    esac
    ;;

  workflow-guard)
    # PM -> Planner -> task_graph -> Builder lifecycle gate
    shift
    _workflow_guard_py="$HARNESS_DIR/lib/workflow_guard.py"
    if [[ ! -f "$_workflow_guard_py" ]]; then
      err "workflow_guard.py not found: $_workflow_guard_py"; exit 1
    fi
    _workflow_guard_subcmd="${1:-help}"; shift || true
    case "$_workflow_guard_subcmd" in
      route)
        python3 "$_workflow_guard_py" route "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Workflow Guard — PM PRD → Planner design/plan/task_graph → DAG Builder"
        echo ""
        echo "Usage:"
        echo "  $0 workflow-guard route <sprint-id> [--json] [--field route_role|stage|violations]"
        ;;
      *)
        err "Unknown workflow-guard subcommand: $_workflow_guard_subcmd"; exit 2
        ;;
    esac
    ;;

  epic)
    # Epic Decomposer — large requirement -> child PRDs/contracts + parent DAG
    shift
    _epic_py="$HARNESS_DIR/lib/epic_decomposer.py"
    _epic_show_py="$HARNESS_DIR/lib/cli/epic_show_cmd.py"
    if [[ ! -f "$_epic_py" ]]; then
      err "epic_decomposer.py not found: $_epic_py"; exit 1
    fi
    _epic_subcmd="${1:-help}"; shift || true
    case "$_epic_subcmd" in
      create|validate|activate-ready|status)
        python3 "$_epic_py" "$_epic_subcmd" "$@"
        ;;
      show)
        if [[ ! -f "$_epic_show_py" ]]; then
          err "epic_show_cmd.py not found: $_epic_show_py"; exit 1
        fi
        python3 "$_epic_show_py" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Epic Decomposer — split large asks into linked PRDs/contracts/task graph"
        echo ""
        echo "Usage:"
        echo "  $0 epic create --title TITLE --request TEXT [--slug SLUG] [--activate-ready] [--json]"
        echo "  $0 epic create --title TITLE --request-file FILE [--slices 5] [--activate-ready]"
        echo "  $0 epic activate-ready EPIC_ID [--max N] [--json]"
        echo "  $0 epic validate EPIC_ID [--json]"
        echo "  $0 epic status [--latest] [--json]"
        echo "  $0 epic show EPIC_ID [--json]"
        ;;
      *)
        err "Unknown epic subcommand: $_epic_subcmd"; exit 2
        ;;
    esac
    ;;

  graph-dispatch)
    # DAG graph_node payload dispatcher
    shift
    _graph_dispatch_py="$HARNESS_DIR/lib/graph_node_dispatcher.py"
    if [[ ! -f "$_graph_dispatch_py" ]]; then
      err "graph_node_dispatcher.py not found: $_graph_dispatch_py"; exit 1
    fi
    _graph_dispatch_subcmd="${1:-help}"; shift || true
    case "$_graph_dispatch_subcmd" in
      dispatch-ready|drain-queue|dispatch-evals|node-verdict|resume-human-review|escalate-terminal-failure|approve-fixed-experiment)
        python3 "$_graph_dispatch_py" "$_graph_dispatch_subcmd" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Graph Dispatch — DAG node payload to pane dispatch"
        echo ""
        echo "Usage:"
        echo "  $0 graph-dispatch dispatch-ready --graph sprint.task_graph.json [--dry-run]"
        echo "  $0 graph-dispatch dispatch-evals --graph sprint.task_graph.json [--dry-run]"
        echo "  $0 graph-dispatch node-verdict --graph sprint.task_graph.json --node S1 --verdict pass|fail"
        echo "  $0 graph-dispatch resume-human-review --graph sprint.task_graph.json --node S1 --generation N --actor NAME --reason TEXT"
        echo "  $0 graph-dispatch escalate-terminal-failure --graph sprint.task_graph.json --node S1 --generation N --actor NAME --reason TEXT"
        echo "  $0 graph-dispatch approve-fixed-experiment --graph sprint.task_graph.json --generation N --actor NAME --statement TEXT --plan-sha256 SHA --scope-json JSON --capability NAME"
        echo "  $0 graph-dispatch drain-queue    --sprint SID [--dry-run] [--max-items N]"
        ;;
      *)
        err "Unknown graph-dispatch subcommand: $_graph_dispatch_subcmd"; exit 2
        ;;
    esac
    ;;

  actorhost-status)
    shift
    _actorhost_json="0"
    _actorhost_filter=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --json)
          _actorhost_json="1"; shift ;;
        --host-type)
          [[ -n "${2:-}" ]] || { err "--host-type requires value"; exit 1; }
          _actorhost_filter="$2"; shift 2 ;;
        --help|-h)
          echo "Usage: $0 actorhost-status [--json] [--host-type TYPE]"
          exit 0 ;;
        *)
          err "Unknown actorhost-status option: $1"; exit 1 ;;
      esac
    done
    python3 - "$HARNESS_DIR" "$_actorhost_json" "$_actorhost_filter" "$0" <<'PY'
import json
import sys
from pathlib import Path

harness_dir = Path(sys.argv[1])
as_json = sys.argv[2] == "1"
host_type_filter = sys.argv[3]
script_harness_dir = Path(sys.argv[4]).resolve().parent
for path in (harness_dir / "lib", script_harness_dir / "tools", script_harness_dir / "lib"):
    value = str(path)
    if value in sys.path:
        sys.path.remove(value)
    sys.path.insert(0, value)
from monitor_bridge import build_snapshot  # noqa: E402
from multi_task_status import CANONICAL_HOST_TYPES  # noqa: E402

snapshot = build_snapshot()
actors = snapshot.get("actor_fleet") if isinstance(snapshot.get("actor_fleet"), dict) else {}
if host_type_filter:
    actors = {
        aid: entry for aid, entry in actors.items()
        if str(entry.get("host_type") or "") == host_type_filter
    }
payload = {
    "schema": "solar.actorhost_status.v1",
    "observed_at": snapshot.get("observed_at"),
    "canonical_host_types": list(CANONICAL_HOST_TYPES),
    "actor_count": len(actors),
    "actor_lease_counts": snapshot.get("actor_lease_counts", {}),
    "actors": actors,
}
if as_json:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0)

print("Solar ActorHost Status")
print(f"canonical_host_types={','.join(payload['canonical_host_types'])}")
print("┌────────────────────────────────────┬────────────────────┬──────────────────────────┬─────────────┬────────────┐")
print("│ Actor                              │ Host               │ Host Type                │ Lease       │ Role       │")
print("├────────────────────────────────────┼────────────────────┼──────────────────────────┼─────────────┼────────────┤")
for aid, entry in sorted(actors.items()):
    print(
        "│ %-34s │ %-18s │ %-24s │ %-11s │ %-10s │" % (
            aid[:34],
            str(entry.get("host_id") or "N/A")[:18],
            str(entry.get("host_type") or "N/A")[:24],
            str(entry.get("lease_state") or "N/A")[:11],
            str(entry.get("role") or "N/A")[:10],
        )
    )
print("└────────────────────────────────────┴────────────────────┴──────────────────────────┴─────────────┴────────────┘")
PY
    ;;

  pm-fleet|builder-pool|concurrency)
    # PM dispatch / builder pool / unified concurrency knob
    _pm_entrypoint="$1"
    shift
    _pm_dispatch_py="$HARNESS_DIR/tools/pm_dispatch.py"
    if [[ ! -f "$_pm_dispatch_py" ]]; then
      err "pm_dispatch.py not found: $_pm_dispatch_py"; exit 1
    fi
    _pm_subcmd="${1:-status}"; shift || true
    case "$_pm_subcmd" in
      status|fleet-status)
        if [[ "$_pm_entrypoint" == "concurrency" ]]; then
          python3 "$_pm_dispatch_py" concurrency-status "$@"
        else
          python3 "$_pm_dispatch_py" fleet-status "$@"
        fi
        ;;
      builder-pool-status|pool|pool-status)
        python3 "$_pm_dispatch_py" builder-pool-status "$@"
        ;;
      concurrency-status|status-concurrency)
        python3 "$_pm_dispatch_py" concurrency-status "$@"
        ;;
      concurrency-set|set)
        python3 "$_pm_dispatch_py" concurrency-set "$@"
        ;;
      prune-rate-limits|prune|cleanup)
        python3 "$_pm_dispatch_py" prune-rate-limits "$@"
        ;;
      quota-refresh|refresh-quota|quota-status)
        python3 "$_pm_dispatch_py" quota-refresh "$@"
        ;;
      install-quota-refresh|install-quota-launchd)
        bash "$HARNESS_DIR/scripts/quota-refresh-daemon.sh" install "$@"
        ;;
      uninstall-quota-refresh|uninstall-quota-launchd)
        bash "$HARNESS_DIR/scripts/quota-refresh-daemon.sh" uninstall
        ;;
      quota-refresh-status|quota-launchd-status)
        bash "$HARNESS_DIR/scripts/quota-refresh-daemon.sh" status
        ;;
      install-rate-limit-pruner|install-prune-launchd)
        bash "$HARNESS_DIR/scripts/operator-rate-limit-pruner.sh" install "$@"
        ;;
      uninstall-rate-limit-pruner|uninstall-prune-launchd)
        bash "$HARNESS_DIR/scripts/operator-rate-limit-pruner.sh" uninstall "$@"
        ;;
      rate-limit-pruner-status|prune-launchd-status)
        bash "$HARNESS_DIR/scripts/operator-rate-limit-pruner.sh" status "$@"
        ;;
      inbox|result|complete|submit|compile-request|drain-builder-ready)
        python3 "$_pm_dispatch_py" "$_pm_subcmd" "$@"
        ;;
      help|--help|-h)
        echo "Solar PM Fleet / Builder Pool"
        echo ""
        echo "Usage:"
        echo "  $0 pm-fleet status"
        echo "  $0 pm-fleet builder-pool-status [--json]"
        echo "  $0 pm-fleet drain-builder-ready [--dry-run] [--max-items N]"
        echo "  $0 pm-fleet prune-rate-limits [--json]"
        echo "  $0 pm-fleet quota-refresh [--json] [--apply]"
        echo "  $0 pm-fleet install-quota-refresh [--interval SECONDS]"
        echo "  $0 pm-fleet quota-refresh-status"
        echo "  $0 pm-fleet install-rate-limit-pruner [--interval SECONDS]"
        echo "  $0 pm-fleet rate-limit-pruner-status"
        echo "  $0 pm-fleet uninstall-rate-limit-pruner"
        echo "  $0 concurrency concurrency-status [--json]"
        echo "  $0 concurrency set --level low|normal|high|burst"
        ;;
      *)
        err "Unknown pm-fleet subcommand: $_pm_subcmd"; exit 2
        ;;
    esac
    ;;

  runtime)
    # Managed Agent Runtime — session log, projection, activity, doctor
    shift
    _runtime_subcmd="${1:-doctor}"; shift || true
    _runtime_py_dir="$HARNESS_DIR/lib"
    case "$_runtime_subcmd" in
      show|selector|pane|use|set|select)
        do_runtime_selector_command "$_runtime_subcmd" "$@"
        ;;
      doctor)
        python3 "$_runtime_py_dir/runtime_doctor.py" "$@"
        ;;
      project)
        python3 "$_runtime_py_dir/projection_engine.py" "$@"
        ;;
      adopt|bridge)
        python3 "$_runtime_py_dir/runtime_bridge.py" adopt "$@"
        ;;
      audit-writes)
        python3 "$_runtime_py_dir/runtime_write_path_audit.py" "$@"
        ;;
      context)
        python3 "$_runtime_py_dir/context_projection.py" "$@"
        ;;
      status)
        _runtime_sid="${1:-}"; shift || true
        _runtime_status="${1:-}"; shift || true
        _runtime_event="${1:-state_transition}"; shift || true
        _runtime_actor="${1:-coordinator}"; shift || true
        _runtime_extra="${1:-}"; shift || true
        [[ -n "$_runtime_extra" ]] || _runtime_extra="{}"
        if [[ -z "$_runtime_sid" || -z "$_runtime_status" ]]; then
          err "用法: $0 runtime status <sid> <new_status> [event] [actor] [extra_json] [--bump-round]"
          exit 2
        fi
        python3 "$_runtime_py_dir/runtime_status.py" "$SPRINTS_DIR/${_runtime_sid}.status.json" "$_runtime_status" "$_runtime_event" "$_runtime_actor" "$_runtime_extra" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Managed Agent Runtime"
        echo ""
        echo "Usage:"
        echo "  $0 runtime show"
        echo "  $0 runtime use codex|claude"
        echo "  $0 runtime doctor [sprint_id] [--json] [--all]"
        echo "  $0 runtime project <sprint_id> [--write-cache] [--json]"
        echo "  $0 runtime adopt  <sprint_id>|--all [--write-cache] [--json]"
        echo "  $0 runtime context <sprint_id> [--query text] [--record] [--format json|markdown]"
        echo "  $0 runtime audit-writes [--json] [--strict]"
        echo "  $0 runtime status <sid> <new_status> [event] [actor] [extra_json] [--bump-round]"
        ;;
      *)
        err "Unknown runtime subcommand: $_runtime_subcmd"; exit 2
        ;;
    esac
    ;;

  leases)
    # S6 Control Plane — pane_lease.py
    shift
    _lease_py="$HARNESS_DIR/lib/pane_lease.py"
    if [[ ! -f "$_lease_py" ]]; then
      err "pane_lease.py not found: $_lease_py"; exit 1
    fi
    _lease_subcmd="${1:-list}"; shift || true
    case "$_lease_subcmd" in
      check|state|acquire|release|reap|list)
        python3 "$_lease_py" "$_lease_subcmd" "$@"
        ;;
      help|--help|-h|"")
        echo "Solar Pane Leases — S6 Control Plane"
        echo ""
        echo "Usage:"
        echo "  $0 leases list"
        echo "  $0 leases state  --pane PANE"
        echo "  $0 leases check  --pane PANE"
        echo "  $0 leases acquire --pane P --sprint SID --dispatch-id DID [--ttl N]"
        echo "  $0 leases release --pane P --dispatch-id DID [--reason R]"
        echo "  $0 leases reap"
        ;;
      *)
        err "Unknown leases subcommand: $_lease_subcmd"; exit 2
        ;;
    esac
    ;;

  *)
    # Unknown command -> error and exit. (Previously a directory-shaped arg
    # here silently launched tmux + 3 Claude panes, so a typo that happened to
    # name a directory burned quota. An explicit work dir goes to `start <dir>`.)
    err "未知命令: $1"; log "运行 '$0 help'"; exit 2
    ;;
esac

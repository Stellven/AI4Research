#!/bin/bash
# ================================================================
# Solar Harness — Pane 启动器 (无交互阻塞, 统一配置)
#
# D1: 配置统一到 lib/persona-config.sh (sprint-20260502-191700)
# D2: 无 read -r 阻塞, 直接启动
# D4: 无明文 token
#
# @module solar-farm/harness/pane-launcher
# ================================================================
set -eu

PERSONA="${1:?Usage: $0 <planner|builder|evaluator> [workdir]}"
WORK_DIR="${2:-.}"
ORIGINAL_WORK_DIR="$WORK_DIR"
HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
export HARNESS_DIR
PANE_RUNTIME="${SOLAR_PANE_RUNTIME:-claude}"
case "$PANE_RUNTIME" in
  claude|codex) ;;
  *) echo "ERROR: unsupported SOLAR_PANE_RUNTIME='$PANE_RUNTIME' (expected claude|codex)" >&2; exit 64 ;;
esac
export SOLAR_PANE_RUNTIME="$PANE_RUNTIME"

prepare_harness_cli_path() {
  local runtime_bin="$HARNESS_DIR/run/bin"
  local runtime_cli="$runtime_bin/solar-harness"
  mkdir -p "$runtime_bin" 2>/dev/null || return 0
  if [[ -f "$HARNESS_DIR/solar-harness.sh" ]]; then
    [[ -L "$runtime_cli" ]] && rm -f "$runtime_cli"
    if {
      printf '%s\n' '#!/usr/bin/env bash'
      printf 'export HARNESS_DIR=%q\n' "$HARNESS_DIR"
      printf '%s\n' 'export SOLAR_HARNESS_DIR="${SOLAR_HARNESS_DIR:-$HARNESS_DIR}"'
      printf 'exec %q "$@"\n' "$HARNESS_DIR/solar-harness.sh"
    } > "$runtime_cli" 2>/dev/null; then
      chmod +x "$runtime_cli" 2>/dev/null || true
    fi
  fi
  case ":$PATH:" in
    *":$runtime_bin:"*) ;;
    *) export PATH="$runtime_bin:$PATH" ;;
  esac
}
prepare_harness_cli_path

# sprint-20260502-191700 follow-up: --print-config 必须**前置** (同 start-incarnation.sh)
if [[ "$PERSONA" == "--print-config" ]]; then
  bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "${2:?missing persona arg}"
  exit $?
fi

PERSONA_FILE="$HARNESS_DIR/personas/${PERSONA}.md"
[[ -f "$PERSONA_FILE" ]] || { echo "ERROR: Persona not found: $PERSONA_FILE"; exit 1; }
[[ -d "$WORK_DIR" ]] || { echo "ERROR: Dir not found: $WORK_DIR"; exit 1; }

# 加载共享配置
source "$HARNESS_DIR/lib/persona-config.sh"
source "$HARNESS_DIR/lib/capability-prefix.sh"

# 解析配置
CONFIG=$(get_persona_config "$PERSONA")
eval "$CONFIG"  # 设置 CN, MODEL_FLAG, TOOL_FLAG, DISPLAY_MODEL, STARTUP_TOKEN, PROXY_CHECK, EXTRA_FLAGS

if [[ "$PANE_RUNTIME" == "codex" ]]; then
  # Persona model config is Claude/Anthropic-gateway policy. Codex uses its own
  # CLI config and optional SOLAR_CODEX_MODEL, while persona instructions still
  # come from the shared persona file.
  LAUNCH_ERROR=""
  MODEL_FLAG=""
  TOOL_FLAG=""
  EXTRA_FLAGS=""
  DISPLAY_MODEL="Codex"
  [[ -n "${SOLAR_CODEX_MODEL:-}" ]] && DISPLAY_MODEL="Codex (${SOLAR_CODEX_MODEL})"
fi

if [[ -n "${LAUNCH_ERROR:-}" ]]; then
  echo "FATAL: $LAUNCH_ERROR" >&2
  echo "Refusing to start an Anthropic Claude fallback for persona=$PERSONA." >&2
  exit 78
fi

# 设置环境变量
if [[ "$PANE_RUNTIME" == "claude" ]]; then
  apply_persona_env "$PERSONA"
fi

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; B='\033[0;34m'; N='\033[0m'

clear
echo -e "${C}══════════════════════════════════════${N}"
echo -e "${B}  Solar Harness — ${CN}化身${N}"
echo -e "  Persona: ${PERSONA}"
echo -e "  模型: ${Y}${DISPLAY_MODEL}${N}"
echo -e "  工作目录: ${WORK_DIR}"
echo -e "${C}══════════════════════════════════════${N}"
echo ""
solar_capability_legend
echo ""

# Git worktree 隔离: builder
WORKTREE_DIR=""
if [[ "$PERSONA" == "builder" || "$PERSONA" == "lab-builder" || "$PERSONA" == "second-builder" ]]; then
  source "$HARNESS_DIR/lib/worktree.sh"
  WORKTREE_DIR=$(setup_builder_worktree "$WORK_DIR")
  if [[ -n "$WORKTREE_DIR" ]]; then
    echo -e "  ${G}Git worktree:${N} $WORKTREE_DIR"
    WORK_DIR="$WORKTREE_DIR"
  fi
fi

cd "$WORK_DIR"

# D2: poll 就绪提示符后发送启动 token
TMUX_PANE="${TMUX_PANE:-$(tmux display-message -p '#{pane_id}' 2>/dev/null || true)}"
send_ready_token() {
  local pane="$1" token="$2"
  [[ -z "$pane" ]] && return
  local max_attempts=60 attempt=0
  local bypass_accepted=0
  while (( attempt < max_attempts )); do
    local content
    content=$(tmux capture-pane -t "$pane" -p 2>/dev/null | tail -30)
    if (( bypass_accepted == 0 )) && echo "$content" | grep -qiE 'Bypass Permissions mode|1\. No, exit|2\. Yes, I accept'; then
      tmux send-keys -t "$pane" "2" Enter
      bypass_accepted=1
      sleep 1
      attempt=$((attempt + 1))
      continue
    fi
    if (( bypass_accepted == 0 )) && echo "$content" | grep -qiE 'Yes, and make it my default mode|Yes, enable auto mode|enable auto mode'; then
      tmux send-keys -t "$pane" Enter
      bypass_accepted=1
      sleep 1
      attempt=$((attempt + 1))
      continue
    fi
    if echo "$content" | grep -qiE 'Detected a custom API key in your environment|Do you want to use this API key'; then
      tmux send-keys -t "$pane" "1" Enter
      sleep 1
      attempt=$((attempt + 1))
      continue
    fi
    if echo "$content" | grep -qiE 'Files with errors are skipped|Continue without these settings|Exit and fix manually'; then
      tmux send-keys -t "$pane" "2" Enter
      sleep 1
      attempt=$((attempt + 1))
      continue
    fi
    if echo "$content" | grep -qiE '(quick safety check|yes, i trust this folder|trust.*folder|enter to confirm)'; then
      tmux send-keys -t "$pane" "1" Enter
      sleep 1
      attempt=$((attempt + 1))
      continue
    fi
    if echo "$content" | grep -qiE '(╭──|allow.*permission|bypass permissions)'; then
      sleep 1
      if [[ -n "$token" ]]; then
        tmux send-keys -t "$pane" "$token" Enter
      else
        tmux send-keys -t "$pane" Enter
      fi
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
}
if [[ "$PANE_RUNTIME" == "claude" && -n "$TMUX_PANE" ]]; then
  send_ready_token "$TMUX_PANE" "$STARTUP_TOKEN" &>/dev/null &
  AUTO_PID=$!
fi

# 构建启动命令。部分机器同时安装多个 Claude CLI；旧版不支持
# --bare，会让第三方网关兼容模式直接失败。需要按能力选择。
find_claude_bin() {
  local need_bare=0 c
  [[ " ${EXTRA_FLAGS:-} " == *" --bare "* ]] && need_bare=1
  local candidates=()
  [[ -n "${SOLAR_CLAUDE_BIN:-}" ]] && candidates+=("$SOLAR_CLAUDE_BIN")
  candidates+=("$HOME/.npm-global/bin/claude" "$HOME/bin/claude" "$HOME/n/bin/claude")
  c="$(command -v claude 2>/dev/null || true)"
  [[ -n "$c" ]] && candidates+=("$c")

  for c in "${candidates[@]}"; do
    [[ -x "$c" ]] || continue
    if (( need_bare == 1 )) && ! "$c" --help 2>&1 | grep -q -- '--bare'; then
      continue
    fi
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

find_codex_bin() {
  local c
  local candidates=()
  [[ -n "${SOLAR_CODEX_BIN:-}" ]] && candidates+=("$SOLAR_CODEX_BIN")
  candidates+=("$HOME/.npm-global/bin/codex" "$HOME/bin/codex" "$HOME/n/bin/codex")
  c="$(command -v codex 2>/dev/null || true)"
  [[ -n "$c" ]] && candidates+=("$c")

  for c in "${candidates[@]}"; do
    [[ -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

SELECTED_RUNTIME_BIN=""
if [[ "$PANE_RUNTIME" == "codex" ]]; then
  CODEX_BIN="$(find_codex_bin)" || {
    echo "FATAL: no Codex CLI found on PATH (SOLAR_PANE_RUNTIME=codex)" >&2
    exit 78
  }
  SELECTED_RUNTIME_BIN="$CODEX_BIN"
else
  CLAUDE_BIN="$(find_claude_bin)" || {
    echo "FATAL: no Claude CLI found with required capabilities for EXTRA_FLAGS='${EXTRA_FLAGS:-}'" >&2
    exit 78
  }
  SELECTED_RUNTIME_BIN="$CLAUDE_BIN"
fi

write_runtime_marker() {
  local marker_dir="$HARNESS_DIR/run/pane-env"
  local pane_safe="${TMUX_PANE:-unknown}"
  pane_safe="${pane_safe//[^A-Za-z0-9_.-]/_}"
  mkdir -p "$marker_dir" 2>/dev/null || return 0
  python3 - "$marker_dir/$pane_safe.json" <<'PY' 2>/dev/null || true
import json, os, sys, time

def present(name):
    return bool(os.environ.get(name))

def host(value):
    if not value:
        return ""
    return value.split("//", 1)[-1].split("/", 1)[0]

record = {
    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "pane": os.environ.get("TMUX_PANE", ""),
    "persona": os.environ.get("SOLAR_PERSONA", ""),
    "builder_slot": os.environ.get("SOLAR_BUILDER_SLOT", ""),
    "pane_runtime": os.environ.get("SOLAR_PANE_RUNTIME", "claude"),
    "runtime_bin": os.environ.get("SOLAR_SELECTED_RUNTIME_BIN", ""),
    "claude_bin": os.environ.get("SOLAR_SELECTED_CLAUDE_BIN", ""),
    "codex_bin": os.environ.get("SOLAR_SELECTED_CODEX_BIN", ""),
    "auth_source": os.environ.get("SOLAR_AUTH_SOURCE", ""),
    "base_url_host": host(os.environ.get("ANTHROPIC_BASE_URL", "")),
    "has_anthropic_auth_token": present("ANTHROPIC_AUTH_TOKEN"),
    "has_anthropic_api_key": present("ANTHROPIC_API_KEY"),
    "zhipu_token_source": os.environ.get("ZHIPU_TOKEN_SOURCE", ""),
    "default_opus_model": os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", ""),
    "default_sonnet_model": os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", ""),
    "model_flag": os.environ.get("SOLAR_MODEL_FLAG", ""),
    "extra_flags": os.environ.get("SOLAR_EXTRA_FLAGS", ""),
    "settings_file": os.environ.get("SOLAR_CLAUDE_SETTINGS_FILE", ""),
    "setting_sources": os.environ.get("SOLAR_CLAUDE_SETTING_SOURCES", ""),
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

prepare_sanitized_claude_settings() {
  local persona="$1"
  local settings_dir="$HARNESS_DIR/run/claude-settings"
  local pane_safe="${TMUX_PANE:-unknown}"
  pane_safe="${pane_safe//[^A-Za-z0-9_.-]/_}"
  local out="$settings_dir/${pane_safe}-${persona}.json"
  mkdir -p "$settings_dir"
  python3 - "$HOME/.claude/settings.json" "$out" "$HARNESS_DIR" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
harness_dir = Path(sys.argv[3])

data = {}
if src.exists():
    data = json.loads(src.read_text(encoding="utf-8"))

# Solar-Harness owns provider routing per pane. Global Claude settings may
# contain a proxy/base-url env for another workflow; carrying it into native
# Claude panes silently turns "Opus" into a gateway request and breaks routing.
data.pop("env", None)

# Do not inherit host-level hook entries: malformed global UserPromptSubmit
# hooks can abort pane startup before Solar can accept the TUI prompt.
hooks = {}
data["hooks"] = hooks

def append_hook(event_name, phase):
    entries = hooks.setdefault(event_name, [])
    command = f"python3 {harness_dir}/lib/claude_hook_event_bridge.py {phase}"
    for entry in entries:
        for hook in entry.get("hooks") or []:
            if hook.get("command") == command:
                return
    entries.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": command}],
    })

append_hook("PreToolUse", "pre-tool")
append_hook("PostToolUse", "post-tool")

out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  printf '%s\n' "$out"
}

export SOLAR_PERSONA="$PERSONA"
export SOLAR_SELECTED_RUNTIME_BIN="$SELECTED_RUNTIME_BIN"
if [[ "$PANE_RUNTIME" == "codex" ]]; then
  export SOLAR_SELECTED_CODEX_BIN="$CODEX_BIN"
else
  export SOLAR_SELECTED_CLAUDE_BIN="$CLAUDE_BIN"
fi
export SOLAR_AUTH_SOURCE="${AUTH_SOURCE:-}"
export SOLAR_MODEL_FLAG="${MODEL_FLAG:-}"
export SOLAR_EXTRA_FLAGS="${EXTRA_FLAGS:-}"
export SOLAR_RUNTIME_SESSION_ID="${SOLAR_RUNTIME_SESSION_ID:-pane-${TMUX_PANE:-unknown}}"
if [[ "$PANE_RUNTIME" == "claude" ]]; then
  CLAUDE_SETTINGS_FILE="$(prepare_sanitized_claude_settings "$PERSONA")"
  export SOLAR_CLAUDE_SETTINGS_FILE="$CLAUDE_SETTINGS_FILE"
  export SOLAR_CLAUDE_SETTING_SOURCES="local"
fi
write_runtime_marker

record_pane_model_session() {
  local event="${1:-}" exit_code="${2:-}"
  local recorder="$HARNESS_DIR/lib/model_call_runtime.py"
  [[ -f "$recorder" ]] || return 0
  local session_id="${SOLAR_RUNTIME_SESSION_ID:-pane-${TMUX_PANE:-unknown}}"
  session_id="${session_id//[^A-Za-z0-9_.:-]/_}"
  local args=("$recorder" "$event" "--session-id" "$session_id" "--pane" "${TMUX_PANE:-}" "--dispatch-id" "pane-session-${PERSONA}" "--actor" "pane-launcher" "--status" "$event")
  [[ -n "$exit_code" ]] && args+=("--exit-code" "$exit_code")
  python3 "${args[@]}" >/dev/null 2>&1 || true
}

prepare_codex_role_file() {
  local persona="$1"
  local role_dir="$HARNESS_DIR/run/pane-codex"
  mkdir -p "$role_dir"
  {
    printf '%s\n\n%s\n\n' "$_runtime_policy" "$_prefix_policy"
    cat "$PERSONA_FILE"
    printf '%s\n' "$_whisper"
  } > "$role_dir/${persona}.md" 2>/dev/null || true
  printf '%s\n' "$role_dir/${persona}.md"
}

# 退出信号捕获 → pane-exit.jsonl
EXIT_LOG="$HARNESS_DIR/logs/pane-exit.jsonl"
mkdir -p "$(dirname "$EXIT_LOG")" 2>/dev/null || true

set +e
_runtime_policy=$(inject_runtime_policy "$PERSONA")
_whisper=$(inject_whisper "$PERSONA")
_prefix_policy=$(inject_prefix_policy "$PERSONA")
record_pane_model_session "session-started" ""
if [[ "$PANE_RUNTIME" == "codex" ]]; then
  CODEX_CMD="$CODEX_BIN"
  SOLAR_CODEX_BYPASS="${SOLAR_CODEX_BYPASS:-1}"
  if [[ "$SOLAR_CODEX_BYPASS" == "1" ]]; then
    CODEX_CMD="$CODEX_CMD --dangerously-bypass-approvals-and-sandbox"
  fi
  # Solar dispatches into long-lived Codex panes. Interactive update prompts
  # steal the first Enter during clean/dispatch and can drop the pane back to
  # shell, so managed panes disable the startup check by default. Operators can
  # still run `codex update` manually outside the cockpit.
  if [[ "${SOLAR_CODEX_CHECK_FOR_UPDATE_ON_STARTUP:-0}" != "1" ]]; then
    CODEX_CMD="$CODEX_CMD -c check_for_update_on_startup=false"
  fi
  [[ -n "${SOLAR_CODEX_MODEL:-}" ]] && CODEX_CMD="$CODEX_CMD --model ${SOLAR_CODEX_MODEL}"
  [[ -n "${SOLAR_CODEX_EXTRA_FLAGS:-}" ]] && CODEX_CMD="$CODEX_CMD ${SOLAR_CODEX_EXTRA_FLAGS}"
  CODEX_ROLE_FILE="$(prepare_codex_role_file "$PERSONA")"
  echo -e "${Y}[${PERSONA}] Codex runtime selected${N}"
  echo -e "  Role instructions: ${CODEX_ROLE_FILE}"
  echo -e "  Starting Codex idle; dispatcher prompts will include role + task files."
  $CODEX_CMD
  RUNTIME_EXIT=$?
else
  CLAUDE_CMD="$CLAUDE_BIN"
  SOLAR_CLAUDE_BYPASS="${SOLAR_CLAUDE_BYPASS:-1}"
  if [[ "$SOLAR_CLAUDE_BYPASS" == "1" ]]; then
    CLAUDE_CMD="$CLAUDE_BIN --dangerously-skip-permissions --permission-mode ${SOLAR_CLAUDE_PERMISSION_MODE:-bypassPermissions}"
  fi
  [[ -n "$MODEL_FLAG" ]] && CLAUDE_CMD="$CLAUDE_CMD $MODEL_FLAG"
  [[ -n "$TOOL_FLAG" ]] && CLAUDE_CMD="$CLAUDE_CMD $TOOL_FLAG"
  [[ -n "${EXTRA_FLAGS:-}" ]] && CLAUDE_CMD="$CLAUDE_CMD $EXTRA_FLAGS"
  CLAUDE_CMD="$CLAUDE_CMD --setting-sources ${SOLAR_CLAUDE_SETTING_SOURCES} --settings ${CLAUDE_SETTINGS_FILE}"
  $CLAUDE_CMD --append-system-prompt "$_runtime_policy
$_prefix_policy
$(cat "$PERSONA_FILE")$_whisper"
  RUNTIME_EXIT=$?
fi
record_pane_model_session "session-ended" "$RUNTIME_EXIT"
set -e

# 写退出记录。Pane 内容可能含引号、反引号、控制字符；通过 stdin/env
# 传给 Python，避免把捕获文本插进 shell 字符串导致启动器语法崩溃。
LAST_LINES=""
if [[ -n "$TMUX_PANE" ]]; then
  LAST_LINES=$(tmux capture-pane -t "$TMUX_PANE" -p -S -30 2>/dev/null | tail -30 | head -c 2000 || true)
fi
PANE_EXIT_LOG="$EXIT_LOG" PANE_EXIT_CODE="$RUNTIME_EXIT" PANE_EXIT_TMUX="${TMUX_PANE:-}" PANE_EXIT_PERSONA="$PERSONA" PANE_EXIT_RUNTIME="$PANE_RUNTIME" PANE_EXIT_LAST_LINES="$LAST_LINES" python3 - <<'PY' 2>/dev/null || true
import datetime
import json
import os

exit_code = int(os.environ.get("PANE_EXIT_CODE", "0") or 0)
record = {
    "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "pane": os.environ.get("PANE_EXIT_TMUX", ""),
    "persona": os.environ.get("PANE_EXIT_PERSONA", ""),
    "pane_runtime": os.environ.get("PANE_EXIT_RUNTIME", "claude"),
    "exit_code": exit_code,
    "signal": "normal" if exit_code < 128 else f"signal_{exit_code - 128}",
    "last_30_lines": os.environ.get("PANE_EXIT_LAST_LINES", "")[:2000],
}
with open(os.environ["PANE_EXIT_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
PY

[[ -n "${AUTO_PID:-}" ]] && kill "$AUTO_PID" 2>/dev/null || true

# 清理 worktree
if [[ -n "$WORKTREE_DIR" ]]; then
  source "$HARNESS_DIR/lib/worktree.sh"
  cleanup_builder_worktree "$WORKTREE_DIR" "$ORIGINAL_WORK_DIR"
fi

exec "${SHELL:-/bin/zsh}"

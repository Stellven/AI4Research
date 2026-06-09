#!/bin/bash
# ================================================================
# Solar Harness — Incarnation 自动启动器 (无交互, watchdog 用)
#
# D1: 配置统一到 lib/persona-config.sh (sprint-20260502-191700)
# D3: builder worktree 支持
#
# @module solar-farm/harness/start-incarnation
# ================================================================
set -eu

# sprint-20260502-200424 D2: PATH 保底 — watchdog respawn 后 tmux env 不含用户 profile 路径
# claude 在 ~/n/bin, node 在 ~/n/bin 或 /opt/homebrew/bin, git 在 /opt/homebrew/bin 或 /usr/bin
for _p in /opt/homebrew/bin /usr/local/bin "$HOME/n/bin" "$HOME/.local/bin" "$HOME/.npm-global/bin" "$HOME/.bun/bin"; do
  [[ -d "$_p" ]] && case ":${PATH}:" in *":$_p:"*) ;; *) export PATH="$_p:${PATH}" ;; esac
done

PERSONA="${1:?Usage: $0 <planner|builder|evaluator> [workdir]}"
WORK_DIR="${2:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="${HARNESS_DIR:-$SCRIPT_DIR}"
export HARNESS_DIR

# sprint-20260502-191700 follow-up: --print-config 必须**前置**
# 旧 bug: 先 [[ -f PERSONA_FILE ]] || exit 1 → "--print-config" 当 PERSONA 找文件失败 → 永远进不到 --print-config 分支
# 修复: 把 CLI 接口拦截放最前面
if [[ "$PERSONA" == "--print-config" ]]; then
  bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "${2:?missing persona arg}"
  exit $?
fi

# Legacy compatibility: Solar panes now launch through pane-launcher, which
# owns the Codex/Claude runtime switch. Keep this file as a stable old entry.
if [[ -x "$HARNESS_DIR/pane-launcher.sh" ]]; then
  exec bash "$HARNESS_DIR/pane-launcher.sh" "$PERSONA" "$WORK_DIR"
fi

PERSONA_FILE="$HARNESS_DIR/personas/${PERSONA}.md"
[[ -f "$PERSONA_FILE" ]] || { echo "ERROR: Persona not found: $PERSONA_FILE"; exit 1; }
[[ -d "$WORK_DIR" ]] || { echo "ERROR: Dir not found: $WORK_DIR"; exit 1; }

# 加载共享配置
source "$HARNESS_DIR/lib/persona-config.sh"

# 解析配置
CONFIG=$(get_persona_config "$PERSONA")
eval "$CONFIG"

# 设置环境变量
apply_persona_env "$PERSONA"

# Git worktree 隔离: builder
WORKTREE_DIR=""
ORIGINAL_WORK_DIR="$WORK_DIR"
if [[ "$PERSONA" == "builder" || "$PERSONA" == "lab-builder" || "$PERSONA" == "second-builder" ]]; then
  source "$HARNESS_DIR/lib/worktree.sh"
  WORKTREE_DIR=$(setup_builder_worktree "$WORK_DIR")
  if [[ -n "$WORKTREE_DIR" ]]; then
    WORK_DIR="$WORKTREE_DIR"
  fi
fi

cd "$WORK_DIR"

clear
echo "══════════════════════════════════════"
echo "  Solar Harness — ${CN}化身"
echo "  Persona: ${PERSONA}"
echo "  工作目录: ${WORK_DIR}"
echo "══════════════════════════════════════"
echo ""

# Poll 就绪提示符后发送启动 token
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
if [[ -n "$TMUX_PANE" ]]; then
  send_ready_token "$TMUX_PANE" "$STARTUP_TOKEN" &>/dev/null &
  AUTO_PID=$!
fi

# 构建启动命令
if [[ -n "${SOLAR_CLAUDE_BIN:-}" ]]; then
  CLAUDE_BIN="$SOLAR_CLAUDE_BIN"
else
  CLAUDE_BIN="$(command -v claude || true)"
  [[ -n "$CLAUDE_BIN" ]] || CLAUDE_BIN="$HOME/.npm-global/bin/claude"
fi

CLAUDE_CMD="$CLAUDE_BIN"
SOLAR_CLAUDE_BYPASS="${SOLAR_CLAUDE_BYPASS:-1}"
if [[ "$SOLAR_CLAUDE_BYPASS" == "1" ]]; then
  SOLAR_CLAUDE_PERMISSION_MODE="${SOLAR_CLAUDE_PERMISSION_MODE:-bypassPermissions}"
  case "$SOLAR_CLAUDE_PERMISSION_MODE" in
    acceptEdits|bypassPermissions|default|delegate|dontAsk|plan) ;;
    auto)
      # Claude Code 2.x removed "auto"; keep legacy env/config usable.
      SOLAR_CLAUDE_PERMISSION_MODE="bypassPermissions"
      ;;
    *)
      echo "WARN: invalid SOLAR_CLAUDE_PERMISSION_MODE=$SOLAR_CLAUDE_PERMISSION_MODE; using bypassPermissions" >&2
      SOLAR_CLAUDE_PERMISSION_MODE="bypassPermissions"
      ;;
  esac
  SOLAR_CLAUDE_SKIP_PERMISSIONS="${SOLAR_CLAUDE_SKIP_PERMISSIONS:-1}"
  if [[ "$SOLAR_CLAUDE_SKIP_PERMISSIONS" == "1" ]]; then
    CLAUDE_CMD="$CLAUDE_BIN --dangerously-skip-permissions --permission-mode ${SOLAR_CLAUDE_PERMISSION_MODE}"
  else
    CLAUDE_CMD="$CLAUDE_BIN --permission-mode ${SOLAR_CLAUDE_PERMISSION_MODE}"
  fi
fi
[[ -n "$MODEL_FLAG" ]] && CLAUDE_CMD="$CLAUDE_CMD $MODEL_FLAG"
[[ -n "$TOOL_FLAG" ]] && CLAUDE_CMD="$CLAUDE_CMD $TOOL_FLAG"
[[ -n "${EXTRA_FLAGS:-}" ]] && CLAUDE_CMD="$CLAUDE_CMD $EXTRA_FLAGS"

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

CLAUDE_SETTINGS_FILE="$(prepare_sanitized_claude_settings "$PERSONA")"
export SOLAR_CLAUDE_SETTINGS_FILE="$CLAUDE_SETTINGS_FILE"
export SOLAR_CLAUDE_SETTING_SOURCES="local"
CLAUDE_CMD="$CLAUDE_CMD --setting-sources ${SOLAR_CLAUDE_SETTING_SOURCES} --settings ${CLAUDE_SETTINGS_FILE}"

# 退出信号捕获 → pane-exit.jsonl
EXIT_LOG="$HARNESS_DIR/logs/pane-exit.jsonl"
mkdir -p "$(dirname "$EXIT_LOG")" 2>/dev/null || true

set +e
_runtime_policy=$(inject_runtime_policy "$PERSONA")
_prefix_policy=$(inject_prefix_policy "$PERSONA")
_whisper=$(inject_whisper "$PERSONA")
$CLAUDE_CMD --append-system-prompt "$_runtime_policy
$_prefix_policy
$(cat "$PERSONA_FILE")$_whisper"
CLAUDE_EXIT=$?
set -e

# 写退出记录。Pane 内容可能含引号、反引号、控制字符；通过 stdin/env
# 传给 Python，避免把捕获文本插进 shell 字符串导致启动器语法崩溃。
LAST_LINES=""
if [[ -n "$TMUX_PANE" ]]; then
  LAST_LINES=$(tmux capture-pane -t "$TMUX_PANE" -p -S -30 2>/dev/null | tail -30 | head -c 2000 || true)
fi
PANE_EXIT_LOG="$EXIT_LOG" PANE_EXIT_CODE="$CLAUDE_EXIT" PANE_EXIT_TMUX="${TMUX_PANE:-}" PANE_EXIT_PERSONA="$PERSONA" PANE_EXIT_LAST_LINES="$LAST_LINES" python3 - <<'PY' 2>/dev/null || true
import datetime
import json
import os

exit_code = int(os.environ.get("PANE_EXIT_CODE", "0") or 0)
record = {
    "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "pane": os.environ.get("PANE_EXIT_TMUX", ""),
    "persona": os.environ.get("PANE_EXIT_PERSONA", ""),
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

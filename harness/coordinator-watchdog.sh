#!/usr/bin/env bash
# ================================================================
# Solar Harness — Coordinator Watchdog
#
# 每 30 秒检查 coordinator PID 是否存活
# 死了自动 wake → 连续 3 次失败则熔断报警
#
# 用法:
#   coordinator-watchdog.sh start    启动守护 (后台)
#   coordinator-watchdog.sh stop     停止守护
#   coordinator-watchdog.sh status   查看状态
#   coordinator-watchdog.sh check    单次检查 (手动)
#
# @module solar-farm/harness/watchdog
# ================================================================
set -Eeu

# Bash 4+ 版本守卫
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  echo "ERROR: watchdog 需要 bash 4+ (当前: ${BASH_VERSION:-unknown})" >&2
  echo "修复: brew install bash" >&2
  exit 1
fi

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
export HARNESS_DIR SPRINTS_DIR
SESSION_NAME="solar-harness"
LAB_SESSION_NAME="solar-harness-lab"
WATCHDOG_PID_FILE="$HARNESS_DIR/.watchdog.pid"
WATCHDOG_STATE="$HARNESS_DIR/.watchdog-state"
COORD_PID_FILE="$HARNESS_DIR/.coordinator.pid"
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"
WATCHDOG_MANAGE_LAB="${SOLAR_WATCHDOG_MANAGE_LAB:-0}"

# 熔断阈值
MAX_CONSECUTIVE_FAILURES=3
CHECK_INTERVAL=30

# D5: 死 pane 自愈配置
PANE_CHECK_INTERVAL=10
PANE_DEAD_THRESHOLD=30
# sprint-20260502-172945 D4: 熔断窗口 60s→300s, 阈值 2→3 (合约要求 5min/3 次)
PANE_RESTART_COOLDOWN=300
PANE_MAX_RESTARTS=3
PANE_RESTART_STATE="$HARNESS_DIR/.pane-restart-state"
SESSION_RECOVERY_MARKER="$HARNESS_DIR/.watchdog-session-recovered-at"
SESSION_START_GRACE_SECS="${SESSION_START_GRACE_SECS:-90}"
# sprint-20260503-100705 D5: 熔断自动恢复秒数 (默认 600, 可环境变量覆盖)
AUTO_RECOVER_SECS="${AUTO_RECOVER_SECS:-600}"
# sprint-20260503-100705 D4: 熔断通知限频 (同一 pane 5 分钟窗口最多 1 条)
_last_cb_notify_ts=0

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[Watchdog]${N} $(date '+%H:%M:%S') $*"; }
ok()   { echo -e "${G}[Watchdog]${N} $*"; }
warn() { echo -e "${Y}[Watchdog]${N} $*"; }
err()  { echo -e "${R}[Watchdog]${N} $*"; }

live_coordinator_pids() {
  ps ax -o pid= -o args= | awk -v script="$HARNESS_DIR/coordinator.sh" '
    $0 ~ "^[[:space:]]*[0-9]+[[:space:]]+([^[:space:]]*/)?bash[[:space:]]+" script "([[:space:]]|$)" { print $1 }
  '
}

heal_coord_pidfile_from_process_table() {
  local real_pids real_pid
  real_pids=$(live_coordinator_pids || true)
  [[ -n "$real_pids" ]] || return 1

  real_pid=$(echo "$real_pids" | head -1)
  echo "$real_pid" > "$COORD_PID_FILE"
  warn "Coordinator pidfile stale/missing; healed from process table (PID=${real_pid})"
  return 0
}

log_unexpected_error() {
  local status="$1"
  local line="$2"
  err "unexpected exit status=${status} line=${line} cmd=${BASH_COMMAND}"
}

# --- D4: 终态 sprint 过滤 (Sprint 20260422-211820) ---
is_actionable_state() {
  case "$1" in
    drafting|active|reviewing|approved) return 0 ;;
    *) return 1 ;;
  esac
}

# --- 读取连续失败计数 ---
get_failure_count() {
  if [[ -f "$WATCHDOG_STATE" ]]; then
    cat "$WATCHDOG_STATE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('consecutive_failures',0))" 2>/dev/null || echo 0
  else
    echo 0
  fi
}

# --- 写入状态 ---
save_state() {
  local failures="$1"
  local last_check
  last_check=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{\"consecutive_failures\":${failures},\"last_check\":\"${last_check}\"}" > "$WATCHDOG_STATE"
}

# --- 单次检查 ---
do_check() {
  local coord_alive=false

  if [[ -f "$COORD_PID_FILE" ]]; then
    local pid
    pid=$(cat "$COORD_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      coord_alive=true
    fi
  fi

  if ! $coord_alive && heal_coord_pidfile_from_process_table; then
    coord_alive=true
  fi

  local failures
  failures=$(get_failure_count)

  if $coord_alive; then
    # Coordinator 存活 → 重置失败计数
    if [[ "$failures" -gt 0 ]]; then
      log "Coordinator 恢复正常 (PID: $(cat "$COORD_PID_FILE"))"
    fi
    save_state 0
    return 0
  fi

  # Coordinator 死了
  failures=$((failures + 1))
  save_state "$failures"

  if [[ "$failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]]; then
    err "熔断! Coordinator 连续 ${failures} 次启动失败，停止重启"
    err "手动恢复: bash $HARNESS_DIR/solar-harness.sh wake <sid>"
    # 写事件到活跃 sprint
    local sf
    sf=$(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null | head -1)
    if [[ -n "$sf" ]]; then
      local sid
      sid=$(python3 -c "import json; print(json.load(open('$sf')).get('id',''))" 2>/dev/null)
      if [[ -n "$sid" ]]; then
        bash "$HARNESS_DIR/session.sh" append "$sid" "{\"event\":\"watchdog_circuit_break\",\"by\":\"watchdog\",\"data\":{\"failures\":${failures}}}" 2>/dev/null || true
      fi
    fi
    return 1
  fi

  warn "Coordinator 已死! (失败 ${failures}/${MAX_CONSECUTIVE_FAILURES})，尝试重启..."

  # 找活跃 sprint 并 wake (D3: 只 wake 非终态 sprint)
  local active_sid=""
  if [[ -f "$HARNESS_DIR/.pane-assignments" ]]; then
    active_sid=$(sed -n 's/^solar-harness:0\.2=\([^:]*\):.*/\1/p' "$HARNESS_DIR/.pane-assignments" | head -1)
    if [[ -n "$active_sid" && -f "$SPRINTS_DIR/${active_sid}.status.json" ]]; then
      local assigned_st
      assigned_st=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${active_sid}.status.json')).get('status',''))" 2>/dev/null)
      is_actionable_state "$assigned_st" || active_sid=""
    else
      active_sid=""
    fi
  fi

  for f in $(ls -t "$SPRINTS_DIR"/*.status.json 2>/dev/null); do
    [[ -z "$active_sid" ]] || break
    [[ -f "$f" ]] || continue
    local st
    st=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
    if is_actionable_state "$st"; then
      active_sid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
      break
    fi
  done

  bash "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
  log "Coordinator 重启已触发 (spawn PID: $!, pidfile 由 coordinator 接管)"

  if [[ -n "$active_sid" ]]; then
    log "Wake Sprint: ${active_sid} (async)"
    (
      bash "$HARNESS_DIR/solar-harness.sh" wake "$active_sid" >> "$HARNESS_DIR/.watchdog.log" 2>&1 || true
    ) &
  else
    log "无非终态 sprint, 跳过 wake"
  fi

  # 记录 watchdog 事件
  if [[ -n "$active_sid" ]]; then
    bash "$HARNESS_DIR/session.sh" append "$active_sid" "{\"event\":\"watchdog_restart\",\"by\":\"watchdog\",\"data\":{\"failure_count\":${failures}}}" 2>/dev/null || true
  fi

  return 0
}

# --- D1: claude 活性检测 (递归 BFS 进程子树) ---
# sprint-20260503-100705: 重写为完整递归，不再限于两级
# 用 pgrep -P BFS 遍历 pane_pid 的整个子进程树，匹配 claude 可执行文件
is_claude_alive_in_pane() {
  local pane_pid="$1"
  local queue="$pane_pid" visited=""

  while [[ -n "$queue" ]]; do
    local next_queue=""
    for pid in $queue; do
      case " $visited " in *" $pid "*) continue ;; esac
      visited="$visited $pid"
      # macOS comm 可能返回完整路径 (/Users/.../.local/bin/claude)。
      local ccmd
      ccmd=$(ps -p "$pid" -o comm= 2>/dev/null) || continue
      case "$ccmd" in
        claude|*/claude) return 0 ;;
      esac
      # 也检查 args= 前缀 (处理 claude CLI 入口 node .../claude)
      local cargs
      cargs=$(ps -p "$pid" -o args= 2>/dev/null) || continue
      case "$cargs" in
        claude[[:space:]]*|claude|*/claude[[:space:]]*|*/claude) return 0 ;;
      esac
      # BFS: 收集子进程
      local children
      children=$(pgrep -P "$pid" 2>/dev/null) || true
      [[ -n "$children" ]] && next_queue="$next_queue $children"
    done
    queue="$next_queue"
  done

  return 1
}

is_harness_launcher_alive_in_pane() {
  local pane_pid="$1"
  local queue="$pane_pid" visited=""

  while [[ -n "$queue" ]]; do
    local next_queue=""
    for pid in $queue; do
      case " $visited " in *" $pid "*) continue ;; esac
      visited="$visited $pid"

      local cargs
      cargs=$(ps -p "$pid" -o args= 2>/dev/null) || continue
      case "$cargs" in
        *"/pane-launcher.sh "*|*" pane-launcher.sh "*|*"/start-incarnation.sh "*|*" start-incarnation.sh "*) return 0 ;;
      esac

      local children
      children=$(pgrep -P "$pid" 2>/dev/null) || true
      [[ -n "$children" ]] && next_queue="$next_queue $children"
    done
    queue="$next_queue"
  done

  return 1
}

pane_key() {
  local pane="$1"
  printf '%s' "$pane" | sed 's/[^A-Za-z0-9_.-]/_/g'
}

pane_host_role() {
  local pane="$1" title="${2:-}" registry="$HARNESS_DIR/run/pane-hygiene.json"
  if [[ -f "$registry" ]]; then
    local role
    role=$(python3 - "$registry" "$pane" <<'PY' 2>/dev/null || true
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
entry = data.get(sys.argv[2]) if isinstance(data, dict) else None
if isinstance(entry, dict):
    print(entry.get("pane_role", ""))
PY
)
    if [[ -n "$role" ]]; then
      printf '%s' "$role"
      return 0
    fi
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

# --- D5: 死 pane 检测 + 自动重启 ---
# Full tmux target → startup persona seed. Host role truth comes from
# pane-hygiene / pane title inference; startup still needs persona for
# start-incarnation compatibility.
declare -A PERSONA_PANES=(
  ["$SESSION_NAME:0.0"]="pm"
  ["$SESSION_NAME:0.1"]="planner"
  ["$SESSION_NAME:0.2"]="builder"
  ["$SESSION_NAME:0.3"]="evaluator"
)
if [[ "$WATCHDOG_MANAGE_LAB" == "1" || "$WATCHDOG_MANAGE_LAB" == "true" ]]; then
  PERSONA_PANES["$LAB_SESSION_NAME:0.0"]="architect"
  PERSONA_PANES["$LAB_SESSION_NAME:0.1"]="lab-builder"
  PERSONA_PANES["$LAB_SESSION_NAME:0.2"]="lab-evaluator"
  PERSONA_PANES["$LAB_SESSION_NAME:0.3"]="observer"
fi

_load_layout_panes() {
  local layout="$HARNESS_DIR/farm-layout.json"
  [[ -f "$layout" ]] || return 0
  local target role
  while IFS=$'\t' read -r target role; do
    [[ -z "$target" || -z "$role" ]] && continue
    if [[ "$target" == "$LAB_SESSION_NAME:"* && "$WATCHDOG_MANAGE_LAB" != "1" && "$WATCHDOG_MANAGE_LAB" != "true" ]]; then
      continue
    fi
    PERSONA_PANES["$target"]="$role"
  done < <(python3 -c "
import json
d=json.load(open('$layout'))
default_session=d.get('session_name','solar-harness')
for w in d.get('windows',[]):
    session=w.get('session') or default_session
    win=w.get('index',0)
    for p in w.get('panes',[]):
        print(f\"{session}:{win}.{p.get('pane_index')}\\t{p.get('persona') or p.get('role') or ''}\")
" 2>/dev/null || true)
}
_load_layout_panes

ensure_tmux_sessions() {
  local missing=0

  if ! tmux has-session -t "$SESSION_NAME" &>/dev/null; then
    warn "tmux session missing: ${SESSION_NAME}; rebuilding Product Delivery"
    TERM=dumb "$HARNESS_DIR/solar-harness.sh" --skip-doctor "$HOME" >> "$HARNESS_DIR/.watchdog-launchd.log" 2>&1 || true
    missing=1
  fi

  if [[ "$WATCHDOG_MANAGE_LAB" == "1" || "$WATCHDOG_MANAGE_LAB" == "true" ]]; then
    if ! tmux has-session -t "$LAB_SESSION_NAME" &>/dev/null; then
      warn "tmux session missing: ${LAB_SESSION_NAME}; rebuilding Strategy Lab"
      TERM=dumb "$HARNESS_DIR/solar-harness.sh" 扩展 "$HOME" >> "$HARNESS_DIR/.watchdog-launchd.log" 2>&1 || true
      missing=1
    fi
  fi

  if (( missing )); then
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    date +%s > "$SESSION_RECOVERY_MARKER"
    printf '%s\n' "- [ ] [${ts}] [WATCHDOG-SESSION-RECOVERED] tmux session missing; watchdog attempted harness rebuild" \
      >> "$HARNESS_DIR/PLANNER-INBOX.md"
    printf '%s\tsession_recovered\t\twatchdog rebuilt missing tmux session(s)\n' "$ts" \
      > "$HARNESS_DIR/.planner-last-notice"
  fi
}

check_panes() {
  local now
  now=$(date +%s)

  ensure_tmux_sessions

  if [[ -f "$SESSION_RECOVERY_MARKER" ]]; then
    local recovered_at grace_elapsed
    recovered_at=$(cat "$SESSION_RECOVERY_MARKER" 2>/dev/null || echo 0)
    grace_elapsed=$(( now - recovered_at ))
    if (( grace_elapsed >= 0 && grace_elapsed < SESSION_START_GRACE_SECS )); then
      log "Session recovery grace active (${grace_elapsed}/${SESSION_START_GRACE_SECS}s); skip pane restart checks"
      return 0
    fi
  fi

  # 读取 rate-limit 状态: pane_key:last_ts:count (取最后匹配行)
  declare -A pane_state
  if [[ -f "$PANE_RESTART_STATE" ]]; then
    while IFS=':' read -r pidx pts pcount; do
      pane_state["$pidx"]="${pts}:${pcount}"
    done < <(tail -r "$PANE_RESTART_STATE" 2>/dev/null | awk -F: '!seen[$1]++')
  fi

  local target
  for target in "${!PERSONA_PANES[@]}"; do
    local session="${target%%:*}"
    tmux has-session -t "$session" &>/dev/null || continue

    local pane_info pcmd pdead pane_pid
    pane_info=$(tmux display-message -p -t "$target" '#{pane_current_command} #{pane_dead} #{pane_pid}' 2>/dev/null) || continue
    read -r pcmd pdead pane_pid <<< "$pane_info"

    # remain-on-exit 死 pane 不重启 (用户可手动处理)
    [[ "$pdead" == "1" ]] && continue
    # D1: 只有 claude/node 在白名单 (合约: 非 claude/node → 走活性检测)
    case "$pcmd" in
      claude|node) continue ;;
    esac
    # D1: cmd 不是 claude/node → 递归 BFS 检查 claude 是否在子进程树中
    if [[ -n "$pane_pid" ]] && is_claude_alive_in_pane "$pane_pid"; then
      continue
    fi
    # 启动中/信任确认中的 pane 可能还是 bash/zsh，但 launcher 正常存活；不能误杀。
    if [[ -n "$pane_pid" ]] && is_harness_launcher_alive_in_pane "$pane_pid"; then
      continue
    fi

    local persona="${PERSONA_PANES[$target]}"
    local pane_title host_role
    pane_title=$(tmux display-message -p -t "$target" '#{pane_title}' 2>/dev/null || true)
    host_role="$(pane_host_role "$target" "$pane_title")"
    local pidx
    pidx="$(pane_key "$target")"

    # rate-limit 检查
    local last_ts=0 count=0
    if [[ -n "${pane_state[$pidx]:-}" ]]; then
      local parts
      IFS=':' read -r last_ts count <<< "${pane_state[$pidx]}"
    fi

    local elapsed=$(( now - last_ts ))
    # sprint-20260503-100705 D5: 熔断自动恢复 — 超过 AUTO_RECOVER_SECS 清零 count
    if (( elapsed >= AUTO_RECOVER_SECS )); then
      count=0
      echo "${pidx}:${now}:0" >> "$PANE_RESTART_STATE"
    fi
    if (( elapsed < PANE_RESTART_COOLDOWN && count >= PANE_MAX_RESTARTS )); then
      # 超限 → 写警告转人工
      local active_sid=""
      for f in "$SPRINTS_DIR"/*.status.json; do
        [[ -f "$f" ]] || continue
        local fst
        fst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
        case "$fst" in passed|done|failed|eval_pass|cancelled) continue ;; esac
        active_sid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
        break
      done
      if [[ -n "$active_sid" ]]; then
        bash "$HARNESS_DIR/session.sh" append "$active_sid" \
          "{\"event\":\"pane_restart_rate_limited\",\"by\":\"watchdog\",\"data\":{\"pane\":\"$target\",\"persona\":\"$persona\",\"host_role\":\"$host_role\",\"count\":$count}}" 2>/dev/null || true
      fi
      warn "Pane $target (host_role=$host_role, persona=$persona) rate-limited (${count}/${PANE_MAX_RESTARTS} in ${PANE_RESTART_COOLDOWN}s)"
      # sprint-20260503-100705 D4: 熔断通知限频 — 同一 pane 5 分钟窗口最多 1 条
      local cb_ts
      cb_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
      local cb_now
      cb_now=$(date +%s)
      if (( cb_now - _last_cb_notify_ts >= 300 )); then
        printf '%s\n' "- [ ] [${cb_ts}] [WATCHDOG-CIRCUIT-BREAKER] Pane ${target} (host_role=${host_role}, persona=${persona}) ${PANE_RESTART_COOLDOWN}s 内 restart ${count}/${PANE_MAX_RESTARTS} 次,已熔断,停止重启,需人工介入" \
          >> "$HARNESS_DIR/PLANNER-INBOX.md"
        printf '%s\tcircuit_breaker\t\twatchdog 熔断 pane=%s host_role=%s persona=%s count=%s window=%ss\n' \
          "$cb_ts" "$target" "$host_role" "$persona" "$count" "$PANE_RESTART_COOLDOWN" \
          > "$HARNESS_DIR/.planner-last-notice"
        _last_cb_notify_ts=$cb_now
      fi
      continue
    fi

    # 重启 pane
    log "Pane $target (host_role=$host_role, persona=$persona) 异常 (cmd=$pcmd)，重启..."
    tmux send-keys -t "$target" C-c 2>/dev/null || true
    sleep 0.5
    # D3/D5 sprint-20260502-191700: 传 work_dir + 路径转义
    local _respawn_workdir
    _respawn_workdir=$(tmux display-message -p -t "$target" '#{pane_current_path}' 2>/dev/null || echo "$HOME")
    [[ -d "$_respawn_workdir" ]] || _respawn_workdir="$HOME"
    local _esc_h _esc_w
    _esc_h=$(printf '%q' "$HARNESS_DIR")
    _esc_w=$(printf '%q' "$_respawn_workdir")
    # sprint-20260502-200424 D2: 用绝对路径 bash + 注入完整 PATH
    # 根因: tmux respawn-pane 不继承用户 shell profile, ~/n/bin/claude 找不到 → exit 127
    local _restart_bash
    _restart_bash=$(resolve_bash4 2>/dev/null || command -v bash 2>/dev/null || echo /bin/bash)
    local _user_path="${PATH}"
    for _p in /opt/homebrew/bin /usr/local/bin "$HOME/n/bin" "$HOME/.local/bin" "$HOME/.npm-global/bin" "$HOME/.bun/bin"; do
      [[ -d "$_p" ]] && case ":${_user_path}:" in *":$_p:"*) ;; *) _user_path="$_p:${_user_path}" ;; esac
    done
    local _pane_id
    _pane_id=$(tmux display-message -p -t "$target" '#{pane_id}' 2>/dev/null || true)
    # respawn start-incarnation: keep watchdog pane recovery on the non-interactive launcher.
    tmux respawn-pane -k -t "$target" \
      "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH HOME='${HOME}' PATH='${_user_path}' TMUX_PANE='${_pane_id}' ${_restart_bash} ${_esc_h}/start-incarnation.sh $persona ${_esc_w}" 2>/dev/null || {
      warn "respawn-pane 失败, 尝试 send-keys..."
      tmux send-keys -t "$target" \
        "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH PATH='${_user_path}' TMUX_PANE='${_pane_id}' ${_restart_bash} ${_esc_h}/start-incarnation.sh $persona ${_esc_w}" Enter 2>/dev/null || {
        warn "send-keys 失败, pane 不存在或不可写: $target; 跳过本 pane 恢复"
        continue
      }
    }
    # sprint-20260502-200424 D2: respawn 后 5 秒验证 pane 活性 (诊断, 不是重试)
    sleep 5
    local _post_respawn_dead
    _post_respawn_dead=$(tmux display-message -p -t "$target" '#{pane_dead}' 2>/dev/null || echo 1)
    if [[ "${_post_respawn_dead:-0}" == "1" ]]; then
      err "Pane $target (host_role=$host_role, persona=$persona) respawn 后立即死亡! (status 127 或其他)"
      echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"respawn_immediate_death\",\"pane\":\"$target\",\"persona\":\"$persona\",\"host_role\":\"$host_role\",\"path\":\"${_user_path}\"}" \
        >> "$HARNESS_DIR/logs/pane-exit.jsonl"
    fi

    # 更新 rate-limit
    local new_count=1
    if (( elapsed < PANE_RESTART_COOLDOWN )); then
      new_count=$(( count + 1 ))
    fi
    echo "${pidx}:${now}:${new_count}" >> "$PANE_RESTART_STATE"

    # 写事件
    local active_sid=""
    for f in "$SPRINTS_DIR"/*.status.json; do
      [[ -f "$f" ]] || continue
      local fst
      fst=$(python3 -c "import json; print(json.load(open('$f')).get('status',''))" 2>/dev/null)
      case "$fst" in passed|done|failed|eval_pass|cancelled) continue ;; esac
      active_sid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
      break
    done
    if [[ -n "$active_sid" ]]; then
        bash "$HARNESS_DIR/session.sh" append "$active_sid" \
        "{\"event\":\"pane_auto_restarted\",\"by\":\"watchdog\",\"data\":{\"pane\":\"$target\",\"persona\":\"$persona\",\"host_role\":\"$host_role\",\"restart_count\":$new_count}}" 2>/dev/null || true
    fi

    log "Pane $target (host_role=$host_role, persona=$persona) 已重启 (restart #${new_count})"
  done
}

# 清理 pane restart state (启动时)
clean_pane_restart_state() {
  if [[ -f "$PANE_RESTART_STATE" ]]; then
    local now
    now=$(date +%s)
    # 只保留最近 5 分钟的记录
    local tmpf
    tmpf=$(mktemp)
    while IFS=':' read -r pidx ts count; do
      local elapsed=$(( now - ts ))
      (( elapsed < 300 )) && echo "${pidx}:${ts}:${count}" >> "$tmpf"
    done < "$PANE_RESTART_STATE"
    mv "$tmpf" "$PANE_RESTART_STATE"
  fi
}

launchd_label() {
  printf '%s\n' "com.solar.watchdog"
}

launchd_domain() {
  printf 'gui/%s\n' "$(id -u)"
}

write_launchd_plist() {
  local plist_path="$1"
  local script_path="$HARNESS_DIR/coordinator-watchdog.sh"
  local bash_path
  bash_path=$(resolve_bash4 2>/dev/null || command -v bash 2>/dev/null || echo /bin/bash)
  mkdir -p "$(dirname "$plist_path")"
  cat > "$plist_path" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$(launchd_label)</string>
    <key>ProgramArguments</key>
    <array>
        <string>${bash_path}</string>
        <string>${script_path}</string>
        <string>run-daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${HARNESS_DIR}/.watchdog-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>${HARNESS_DIR}/.watchdog-launchd.log</string>
    <key>WorkingDirectory</key>
    <string>${HARNESS_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:${HOME}/n/bin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
PLIST_EOF
}

start_launchd_watchdog() {
  local plist_label
  plist_label="$(launchd_label)"
  local plist_path="$HOME/Library/LaunchAgents/${plist_label}.plist"
  local domain
  domain="$(launchd_domain)"

  write_launchd_plist "$plist_path"
  launchctl bootout "$domain" "$plist_path" 2>/dev/null || launchctl unload "$plist_path" 2>/dev/null || true
  launchctl bootstrap "$domain" "$plist_path" 2>/dev/null || launchctl load "$plist_path" 2>/dev/null
  launchctl kickstart -k "${domain}/${plist_label}" 2>/dev/null || true

  sleep 2
  local daemon_pid
  daemon_pid=$(pgrep -f "coordinator-watchdog.sh run-daemon" 2>/dev/null | head -1 || true)
  if [[ -z "$daemon_pid" ]]; then
    return 1
  fi
  echo "$daemon_pid" > "$WATCHDOG_PID_FILE"
  log "launchd plist: ${plist_path}"
  ok "Watchdog 已通过 launchd 常驻 (PID: ${daemon_pid})"
}

# --- 后台守护循环 ---
run_watchdog() {
  log "Watchdog 启动 (每 ${CHECK_INTERVAL}s 检查 coordinator, ${PANE_CHECK_INTERVAL}s 检查 panes)"
  save_state 0
  clean_pane_restart_state

  local coord_ticks=0
  local pane_ticks=0

  while true; do
    # Coordinator 检查 (每 CHECK_INTERVAL)
    if (( coord_ticks >= CHECK_INTERVAL )); then
      do_check || {
        err "Watchdog 因熔断退出"
        break
      }
      coord_ticks=0
    fi

    # D5: Pane 检查 (每 PANE_CHECK_INTERVAL)
    if (( pane_ticks >= PANE_CHECK_INTERVAL )); then
      check_panes
      pane_ticks=0
    fi

    sleep 1
    coord_ticks=$((coord_ticks + 1))
    pane_ticks=$((pane_ticks + 1))
  done
}

# --- 命令入口 ---
case "${1:-help}" in
  start)
    # D3: pidfile 自治 — 防多实例 (Sprint 20260422-222017)
    if [[ -f "$WATCHDOG_PID_FILE" ]]; then
      # [HOTFIX 1] removed `local wpid` (case branch, not function)
      wpid=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)
      if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
        ok "Watchdog 已在运行 (PID: ${wpid})"
        exit 0
      fi
      rm -f "$WATCHDOG_PID_FILE"
    fi
    log "启动 Watchdog..."
    if [[ "$(uname -s)" == "Darwin" && "${SOLAR_WATCHDOG_NO_LAUNCHD:-0}" != "1" ]] && command -v launchctl >/dev/null 2>&1; then
      if start_launchd_watchdog; then
        exit 0
      fi
      warn "launchd 启动失败，回退到后台进程模式"
    fi
    bash_path=$(resolve_bash4 2>/dev/null || command -v bash 2>/dev/null || echo /bin/bash)
    nohup "$bash_path" "$HARNESS_DIR/coordinator-watchdog.sh" run-daemon >> "$HARNESS_DIR/.watchdog.log" 2>&1 </dev/null &
    echo $! > "$WATCHDOG_PID_FILE"
    ok "Watchdog 启动完成 (PID: $!)"
    ;;
  stop)
    if [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
      plist_label="$(launchd_label)"
      plist_path="$HOME/Library/LaunchAgents/${plist_label}.plist"
      domain="$(launchd_domain)"
      launchctl bootout "$domain" "$plist_path" 2>/dev/null || launchctl unload "$plist_path" 2>/dev/null || true
    fi
    if [[ -f "$WATCHDOG_PID_FILE" ]]; then
      kill "$(cat "$WATCHDOG_PID_FILE")" 2>/dev/null || true
      rm -f "$WATCHDOG_PID_FILE"
      ok "Watchdog 已停止"
    else
      warn "Watchdog 未运行"
    fi
    ;;
  status)
    echo ""
    if [[ -f "$WATCHDOG_PID_FILE" ]] && kill -0 "$(cat "$WATCHDOG_PID_FILE")" 2>/dev/null; then
      ok "✅ 运行中 PID=$(cat "$WATCHDOG_PID_FILE")"
      # 检测运行模式
      if launchctl list 2>/dev/null | grep -q "com.solar.watchdog"; then
        log "模式: launchd 常驻"
      else
        log "模式: 后台进程"
      fi
    else
      # 检查 launchd 是否在管理
      if launchctl list 2>/dev/null | grep -q "com.solar.watchdog"; then
        warn "Watchdog launchd 已注册但进程未检测到"
      else
        warn "Watchdog 未运行"
      fi
    fi
    if [[ -f "$COORD_PID_FILE" ]]; then
      pid=$(cat "$COORD_PID_FILE")
      if kill -0 "$pid" 2>/dev/null; then
        ok "Coordinator 存活 (PID: ${pid})"
      elif heal_coord_pidfile_from_process_table; then
        ok "Coordinator 存活 (PID: $(cat "$COORD_PID_FILE"))"
      else
        err "Coordinator 已死 (PID: ${pid} 不存在)"
      fi
    else
      if heal_coord_pidfile_from_process_table; then
        ok "Coordinator 存活 (PID: $(cat "$COORD_PID_FILE"))"
      else
        warn "无 Coordinator PID 文件"
      fi
    fi
    failures=$(get_failure_count)
    echo "  连续失败: ${failures}/${MAX_CONSECUTIVE_FAILURES}"
    if [[ "$failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]]; then
      err "  状态: 熔断 (需手动恢复)"
    else
      ok "  状态: 正常"
    fi
    echo ""
    ;;
  check)
    do_check
    ;;
  install-launchd)
    # 互斥检查：如果已经在用后台 start 模式，先停掉
    if [[ -f "$WATCHDOG_PID_FILE" ]] && kill -0 "$(cat "$WATCHDOG_PID_FILE")" 2>/dev/null; then
      warn "Watchdog 后台模式运行中 (PID: $(cat "$WATCHDOG_PID_FILE"))，先停止..."
      kill "$(cat "$WATCHDOG_PID_FILE")" 2>/dev/null || true
      rm -f "$WATCHDOG_PID_FILE"
    fi

    plist_label="$(launchd_label)"
    plist_path="$HOME/Library/LaunchAgents/${plist_label}.plist"
    domain="$(launchd_domain)"

    write_launchd_plist "$plist_path"
    launchctl bootout "$domain" "$plist_path" 2>/dev/null || launchctl unload "$plist_path" 2>/dev/null || true
    launchctl bootstrap "$domain" "$plist_path" 2>/dev/null || launchctl load "$plist_path" 2>/dev/null
    launchctl kickstart -k "${domain}/${plist_label}" 2>/dev/null || true
    # 写 PID 文件（launchd 管理的进程 PID 需要等一下）
    sleep 1
    # 尝试获取 launchd 管理的 watchdog PID
    daemon_pid=""
    daemon_pid=$(pgrep -f "coordinator-watchdog.sh run-daemon" 2>/dev/null | head -1 || true)
    if [[ -n "$daemon_pid" ]]; then
      echo "$daemon_pid" > "$WATCHDOG_PID_FILE"
      ok "Watchdog 已通过 launchd 常驻 (PID: ${daemon_pid})"
    else
      ok "Watchdog launchd plist 已加载 (PID 将在首次 check 时写入)"
    fi
    log "plist: ${plist_path}"
    log "日志: ${HARNESS_DIR}/.watchdog-launchd.log"
    log "卸载: $0 uninstall-launchd"
    ;;
  uninstall-launchd)
    plist_label="$(launchd_label)"
    plist_path="$HOME/Library/LaunchAgents/${plist_label}.plist"
    domain="$(launchd_domain)"

    if [[ -f "$plist_path" ]]; then
      launchctl bootout "$domain" "$plist_path" 2>/dev/null || launchctl unload "$plist_path" 2>/dev/null || true
      rm -f "$plist_path"
      rm -f "$WATCHDOG_PID_FILE"
      ok "Watchdog launchd 已卸载，plist 已删除"
    else
      warn "无 launchd plist (${plist_path})"
    fi
    ;;
  run-daemon)
    # D3: pidfile 自治 + trap 清理 (Sprint 20260422-222017)
    cleanup_watchdog_pid() {
      local exit_status=$?
      log "Watchdog daemon 退出 (PID: $$, status=${exit_status})"
      if [[ "$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)" == "$$" ]]; then
        rm -f "$WATCHDOG_PID_FILE"
      fi
    }
    trap 'log_unexpected_error "$?" "$LINENO"' ERR
    trap 'cleanup_watchdog_pid' EXIT
    trap 'log "Watchdog daemon 收到 TERM"; exit 143' TERM
    trap 'log "Watchdog daemon 收到 HUP"; exit 129' HUP
    trap 'log "Watchdog daemon 收到 INT"; exit 130' INT
    echo "$$" > "$WATCHDOG_PID_FILE"
    log "Watchdog daemon 启动 (PID: $$, coord 每 ${CHECK_INTERVAL}s, panes 每 ${PANE_CHECK_INTERVAL}s)"
    save_state 0
    clean_pane_restart_state

    # Sprint 20260423-062851 D2: 启动时记录自身 md5 用于热加载自检
    INIT_MD5=""
    INIT_MD5=$(md5 -q "$0" 2>/dev/null || md5sum "$0" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')
    log "watchdog md5=${INIT_MD5}"

    coord_ticks=0
    pane_ticks=0
    daemon_loop_count=0

    while true; do
      if (( coord_ticks >= CHECK_INTERVAL )); then
        do_check || {
          err "Watchdog daemon 因熔断退出"
          rm -f "$WATCHDOG_PID_FILE"
          exit 1
        }
        coord_ticks=0
      fi
      if (( pane_ticks >= PANE_CHECK_INTERVAL )); then
        check_panes
        pane_ticks=0
      fi
      sleep 1
      coord_ticks=$((coord_ticks + 1))
      pane_ticks=$((pane_ticks + 1))
      daemon_loop_count=$((daemon_loop_count + 1))

      # Sprint 20260423-062851 D2: md5 自检热加载 (每 60 轮 ≈ 60 秒)
      hot_reload_tick=${HOT_RELOAD_TICK_OVERRIDE:-60}
      if (( daemon_loop_count % hot_reload_tick == 0 )); then
        current_md5=""
        current_md5=$(md5 -q "$0" 2>/dev/null || md5sum "$0" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')
        if [[ "$current_md5" != "$INIT_MD5" ]]; then
          log "[hot-reload] watchdog md5 changed: ${INIT_MD5} → ${current_md5}, exec restart"
          cleanup_watchdog_pid
          bash_path=$(resolve_bash4 2>/dev/null || command -v bash 2>/dev/null || echo /bin/bash)
          exec "$bash_path" "$HARNESS_DIR/coordinator-watchdog.sh" run-daemon
        fi
      fi
    done
    ;;
  help|--help|-h|"")
    echo "Solar Harness — Coordinator Watchdog"
    echo ""
    echo "用法:"
    echo "  $0 start             启动守护 (后台, 每 ${CHECK_INTERVAL}s 检查)"
    echo "  $0 stop              停止守护"
    echo "  $0 status            查看状态"
    echo "  $0 check             单次手动检查"
    echo "  $0 install-launchd   macOS launchd 常驻 (开机自启)"
    echo "  $0 uninstall-launchd 卸载 launchd 常驻"
    echo "  $0 run-daemon        前台守护模式 (由 launchd 管理)"
    echo ""
    echo "熔断: 连续 ${MAX_CONSECUTIVE_FAILURES} 次失败后停止重启"
    ;;
  *)
    err "未知命令: $1"
    exit 1
    ;;
esac

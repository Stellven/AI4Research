#!/usr/bin/env bash
# Targeted nightwatch for sprint-20260509-solar-product-platform.
# It does not implement product code. It only watches phase transitions and
# nudges the correct pane when the current G0 flow is ready or stale.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SID="sprint-20260509-solar-product-platform"
SPRINT_DIR="$HARNESS_DIR/sprints"
STATUS="$SPRINT_DIR/$SID.status.json"
S0_HANDOFF="$SPRINT_DIR/$SID.s0-handoff.md"
S0_DISPATCH="$SPRINT_DIR/$SID.s0-dispatch.md"
LOG="$HARNESS_DIR/run/product-platform-nightwatch.log"
STATE="$HARNESS_DIR/state/product-platform-nightwatch.state"
INTERVAL="${1:-120}"

mkdir -p "$HARNESS_DIR/run" "$HARNESS_DIR/state"

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG"
}

json_field() {
  python3 - "$STATUS" "$1" <<'PY'
import json, sys
p, key = sys.argv[1], sys.argv[2]
try:
    print(json.load(open(p)).get(key, ""))
except Exception:
    print("")
PY
}

pane_idle() {
  local pane="$1" tail
  tail="$(tmux capture-pane -p -t "$pane" -S -20 2>/dev/null | tail -20 || true)"
  if printf '%s\n' "$tail" | grep -qiE 'Actioning|Wrangling|Thinking|Running|Bash\\(|Read |Writing|Compacting conversation'; then
    return 1
  fi
  return 0
}

pane_role_matches() {
  local expected_role="$1" pane="$2"
  [[ "${SOLAR_ALLOW_NIGHTWATCH_ANY_PANE:-0}" == "1" ]] && return 0

  local meta session title
  meta="$(tmux display-message -p -t "$pane" '#{session_name}	#{pane_title}' 2>/dev/null)" || return 1
  session="${meta%%$'\t'*}"
  title="${meta#*$'\t'}"
  [[ "$session" == "${SOLAR_SESSION_NAME:-solar-harness}" ]] || return 1

  case "$expected_role" in
    builder)
      printf '%s\n' "$title" | grep -qiE 'Builder|建设者' || return 1
      printf '%s\n' "$title" | grep -qiE 'PM|产品经理|Planner|规划者|Evaluator|审判官' && return 1
      ;;
    evaluator)
      printf '%s\n' "$title" | grep -qiE 'Evaluator|审判官' || return 1
      printf '%s\n' "$title" | grep -qiE 'PM|产品经理|Planner|规划者|Builder|建设者' && return 1
      ;;
    *)
      return 1
      ;;
  esac

  return 0
}

send_once() {
  local key="$1" expected_role="$2" pane="$3" prompt="$4"
  if grep -qx "$key" "$STATE" 2>/dev/null; then
    return 0
  fi
  if ! pane_role_matches "$expected_role" "$pane"; then
    log "skip_send key=$key pane=$pane expected_role=$expected_role reason=role_mismatch"
    return 0
  fi
  if ! pane_idle "$pane"; then
    log "skip_send key=$key pane=$pane reason=busy"
    return 0
  fi
  tmux send-keys -t "$pane" C-u 2>/dev/null || true
  sleep 0.2
  tmux send-keys -t "$pane" "$prompt" 2>/dev/null || true
  sleep 0.2
  tmux send-keys -t "$pane" Enter 2>/dev/null || true
  printf '%s\n' "$key" >> "$STATE"
  log "sent key=$key pane=$pane"
}

while :; do
  phase="$(json_field phase)"
  handoff_to="$(json_field handoff_to)"
  log "tick phase=${phase:-N/A} handoff_to=${handoff_to:-N/A}"

  if [[ "$phase" == "s0_ready_for_eval" || ( -f "$S0_HANDOFF" && "$handoff_to" == "evaluator" ) ]]; then
    send_once \
      "s0_eval_dispatched" \
      "evaluator" \
      "solar-harness:0.3" \
      "读取并执行 G0 evaluator review：先读 ~/.solar/harness/sprints/sprint-20260509-solar-product-platform.s0-snapshot.contract.md 和 ${S0_HANDOFF}；验证 snapshot/restore/secret-exclusion/现有命令不破。通过则更新 parent status phase=g0_passed handoff_to=coordinator；失败则 phase=s0_failed_review handoff_to=builder_main 并写 eval。"
  fi

  for slice in s1 s2 s6; do
    handoff="$SPRINT_DIR/$SID.${slice}-handoff.md"
    if [[ -f "$handoff" ]]; then
      send_once \
        "${slice}_eval_dispatched" \
        "evaluator" \
        "solar-harness:0.3" \
        "读取并执行 ${slice^^} evaluator review：先读 $handoff、~/.solar/harness/sprints/sprint-20260509-solar-product-platform.contract.md 和 ~/.solar/harness/sprints/sprint-20260509-solar-product-platform.plan.md；只评估该 slice，不要把 parent sprint 标成 passed。通过则记录 ${slice}_eval_passed；失败则写明 blocker 并 handoff_to=builder_main。"
    fi
  done

  # If builder has not produced S0 handoff after 25 minutes, nudge once.
  if [[ "$phase" == "s0_dispatched" && ! -f "$S0_HANDOFF" ]]; then
    updated="$(json_field updated_at)"
    if [[ -n "$updated" ]]; then
      age="$(python3 - "$updated" <<'PY'
from datetime import datetime, timezone
import sys
try:
    t=datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))
    print(int((datetime.now(timezone.utc)-t).total_seconds()))
except Exception:
    print(0)
PY
)"
      if [[ "$age" -gt 1500 ]]; then
        send_once \
          "s0_builder_nudge" \
          "builder" \
          "solar-harness:0.2" \
          "S0 nightwatch 温和提醒：你正在执行 ~/.solar/harness/sprints/sprint-20260509-solar-product-platform.s0-dispatch.md。请继续完成 snapshot/restore foundation；如果遇到阻塞，写明 blocker 到 s0-handoff 并更新 status，不要停在无输出状态。"
      fi
    fi
  fi

  if [[ "$phase" == "s6_dispatched" && ! -f "$SPRINT_DIR/$SID.s6-handoff.md" ]]; then
    updated="$(json_field updated_at)"
    if [[ -n "$updated" ]]; then
      age="$(python3 - "$updated" <<'PY'
from datetime import datetime, timezone
import sys
try:
    t=datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))
    print(int((datetime.now(timezone.utc)-t).total_seconds()))
except Exception:
    print(0)
PY
)"
      if [[ "$age" -gt 1800 ]]; then
        send_once \
          "s6_builder_nudge" \
          "builder" \
          "solar-harness:0.2" \
          "S6 nightwatch 温和提醒：你正在执行 ~/.solar/harness/sprints/sprint-20260509-solar-product-platform.s6-control-plane-dispatch.md。请继续完成 control-plane slice；如果遇到阻塞，写明 blocker 到 s6-handoff 并更新 status，不要停在无输出状态。"
      fi
    fi
  fi

  sleep "$INTERVAL"
done

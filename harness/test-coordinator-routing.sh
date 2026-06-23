#!/usr/bin/env bash
# test-coordinator-routing.sh — Unit tests for discover_pane_by_persona routing fix
# Sprint: sprint-20260507-symphony3 / S7
#
# Strategy: since we can't spin up a real tmux session in a test environment,
# we test the routing logic by:
# TC1-TC3: env override path (SOLAR_PANE_EVALUATOR, SOLAR_PANE_BUILDER, SOLAR_PANE_PLANNER)
# TC4: no-tmux fallback path (tmux session absent → fallback returned)

set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
COORDINATOR_SH="${HARNESS_DIR}/coordinator.sh"
export COORDINATOR_SH

# ── Safety guards ──
[[ "${SESSION_NAME:-}" == "solar-harness" ]] && {
  echo "REFUSE: cannot run tests on live solar-harness session"; exit 1
}

# ── Extract discover_pane_by_persona and helpers from coordinator.sh ──
export TEST_TMP
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

# Stub dependencies so we can source coordinator functions in isolation
STUB_FILE="$TEST_TMP/stubs.sh"
cat > "$STUB_FILE" <<'EOF'
# Minimal stubs for coordinator internals needed by routing functions
SESSION_NAME="solar-harness"
LAB_SESSION_NAME="solar-lab"
PANE_NOTIFY="$SESSION_NAME:0.0"
PANE_PLANNER_DEFAULT="$SESSION_NAME:0.1"
PANE_PLANNER="$PANE_PLANNER_DEFAULT"
PANE_BUILDER_DEFAULT="$SESSION_NAME:0.2"
PANE_EVALUATOR_DEFAULT="$SESSION_NAME:0.3"
PANE_LAB_ARCHITECT="$LAB_SESSION_NAME:0.0"
PANE_LAB_BUILDER="$LAB_SESSION_NAME:0.1"
PANE_LAB_EVALUATOR="$LAB_SESSION_NAME:0.2"
PANE_LAB_OBSERVER="$LAB_SESSION_NAME:0.3"
COORD_LOG="$HARNESS_DIR/.coordinator.log"
R="" Y="" N="" G=""  # Color stubs

log() { true; }
pane_key() { echo "${1##*.}"; }
pane_session() { echo "${1%%:*}"; }
pane_process_persona() { return 1; }
pane_title_persona() { return 1; }
ensure_lab_session() { return 0; }
EOF

# Extract the functions we need from coordinator.sh
python3 - <<'PYEOF'
import re, sys

with open(__import__('os').environ["COORDINATOR_SH"]) as f:
    src = f.read()

# Extract discover_pane_by_persona, choose_* functions and pane_title_persona
funcs_to_extract = [
    "pane_is_idle_snapshot",
    "pane_has_processing_snapshot",
    "pane_has_prompt_snapshot",
    "pane_prompt_input_snapshot",
    "ensure_ack_contract",
    "pane_title_persona",
    "discover_pane_by_persona",
    "choose_builder_pane",
    "choose_pm_pane",
    "choose_planner_pane",
    "choose_evaluator_pane",
    "choose_architect_pane",
]

import os
out_path = os.environ.get("TEST_TMP", "/tmp") + "/extracted.sh"
lines = src.split("\n")
extracted = []
in_func = False
brace_depth = 0
current_func = None

for line in lines:
    # detect function start
    func_match = re.match(r'^(\w+)\(\)\s*\{?\s*$', line)
    if func_match and func_match.group(1) in funcs_to_extract:
        in_func = True
        current_func = func_match.group(1)
        brace_depth = line.count("{") - line.count("}")
        extracted.append(line)
        continue
    if in_func:
        extracted.append(line)
        brace_depth += line.count("{") - line.count("}")
        if brace_depth <= 0:
            in_func = False
            extracted.append("")

with open(out_path, "w") as f:
    f.write("\n".join(extracted))
func_lines = [l for l in extracted if "()" in l]
print(f"Extracted {len(func_lines)} functions to {out_path}")
PYEOF

# ── Test framework ──
PASS=0
FAIL=0

assert() {
  local desc="$1" expr="$2"
  if eval "$expr" 2>/dev/null; then
    echo "  ✅ PASS: $desc"
    (( PASS++ )) || true
  else
    echo "  ❌ FAIL: $desc"
    (( FAIL++ )) || true
  fi
}

# Source stubs + extracted functions
source "$STUB_FILE"
source "$TEST_TMP/extracted.sh"

echo "=== test-coordinator-routing.sh ==="
echo ""

# ── TC1: SOLAR_PANE_EVALUATOR env override routes to correct pane ──
echo "TC1: SOLAR_PANE_EVALUATOR env override returns correct pane (not fallback)"
export SOLAR_PANE_EVALUATOR="solar-harness:0.3"
RESULT=$(choose_evaluator_pane 2>/dev/null)
assert "choose_evaluator_pane returns env override value" '[[ "$RESULT" == "solar-harness:0.3" ]]'
assert "result is not planner pane (0.0)" '[[ "$RESULT" != "solar-harness:0.0" ]]'
unset SOLAR_PANE_EVALUATOR
echo ""

# ── TC2: SOLAR_PANE_BUILDER env override routes correctly ──
echo "TC2: SOLAR_PANE_BUILDER env override returns correct pane"
export SOLAR_PANE_BUILDER="solar-harness:0.2"
RESULT=$(choose_builder_pane 2>/dev/null)
assert "choose_builder_pane returns env override" '[[ "$RESULT" == "solar-harness:0.2" ]]'
unset SOLAR_PANE_BUILDER
echo ""

# ── TC3: SOLAR_PANE_PLANNER env override routes correctly ──
echo "TC3: SOLAR_PANE_PLANNER env override routes planner"
export SOLAR_PANE_PLANNER="solar-harness:0.1"
RESULT=$(choose_planner_pane 2>/dev/null)
assert "choose_planner_pane returns env override" '[[ "$RESULT" == "solar-harness:0.1" ]]'
unset SOLAR_PANE_PLANNER
echo ""

# ── TC4: No tmux session → fallback returned (not crash) ──
echo "TC4: No tmux session → discover_pane_by_persona returns fallback"
# Ensure no live session matches
unset SOLAR_PANE_EVALUATOR SOLAR_PANE_BUILDER SOLAR_PANE_PLANNER 2>/dev/null || true
RESULT=$(discover_pane_by_persona "no-such-session-xyz" 0 "evaluator" "fallback-pane" 2>/dev/null)
assert "returns fallback when tmux session absent" '[[ "$RESULT" == "fallback-pane" ]]'
echo ""

# ── TC5: Regex anchoring — content with 'evaluator' not at line start does NOT match ──
echo "TC5: Strict regex — 'Persona: evaluator' only matches exact line format"
# We test the grep pattern directly (without tmux)
TEST_CONTENT="Some random evaluator mention here
Persona: planner
This line has evaluator-pending in it"
PATTERN="^Persona:[[:space:]]*evaluator[[:space:]]*$"
assert "random 'evaluator' text does not match strict pattern" \
  '! printf "%s\n" "$TEST_CONTENT" | grep -qE "$PATTERN"'
TEST_EXACT="Persona: evaluator"
assert "exact 'Persona: evaluator' line matches strict pattern" \
  'printf "%s\n" "$TEST_EXACT" | grep -qE "$PATTERN"'
TEST_WITH_SUFFIX="Persona: evaluator-pending"
assert "'evaluator-pending' does not match strict pattern" \
  '! printf "%s\n" "$TEST_WITH_SUFFIX" | grep -qE "$PATTERN"'
echo ""

# ── TC6: Coordinator honors custom tmux session env ──
echo "TC6: coordinator.sh session defaults honor custom-session env"
assert "SESSION_NAME reads SOLAR_HARNESS_SESSION" \
  'grep -qF '\''SESSION_NAME="${SOLAR_HARNESS_SESSION:-solar-harness}"'\'' "$COORDINATOR_SH"'
assert "LAB_SESSION_NAME derives from custom session unless explicitly set" \
  'grep -qF '\''LAB_SESSION_NAME="${SOLAR_HARNESS_LAB_SESSION:-${SESSION_NAME}-lab}"'\'' "$COORDINATOR_SH"'
echo ""

# ── TC7: Codex idle composer is dispatchable ──
echo "TC7: Codex idle composer is treated as idle, slash residue is not"
CODEX_IDLE_SNAPSHOT=$'╭────────────────────────╮\n│ >_ OpenAI Codex       │\n│ permissions: YOLO mode│\n╰────────────────────────╯\n\n› Find and fix a bug in @filename\n\n  gpt-5.5 xhigh fast · /tmp/repo'
CODEX_SLASH_SNAPSHOT=$'╭────────────────────────╮\n│ >_ OpenAI Codex       │\n│ permissions: YOLO mode│\n╰────────────────────────╯\n\n› /clear\n\n  gpt-5.5 xhigh fast · /tmp/repo'
assert "Codex suggestion composer is idle" \
  'pane_is_idle_snapshot "$CODEX_IDLE_SNAPSHOT"'
assert "Codex slash residue is not idle" \
  '! pane_is_idle_snapshot "$CODEX_SLASH_SNAPSHOT"'
assert "Codex prompt glyph is detected" \
  'pane_has_prompt_snapshot "$CODEX_IDLE_SNAPSHOT"'
PROMPT_INPUT="$(pane_prompt_input_snapshot "$CODEX_IDLE_SNAPSHOT")"
assert "Codex default suggestion is not treated as typed residue" \
  '[[ -z "$PROMPT_INPUT" ]]'
SLASH_INPUT="$(pane_prompt_input_snapshot "$CODEX_SLASH_SNAPSHOT")"
assert "Codex slash residue remains visible to quarantine logic" \
  '[[ "$SLASH_INPUT" == "/clear" ]]'
echo ""

# ── TC8: Codex processing markers satisfy coordinator direct-dispatch verification ──
echo "TC8: Codex processing markers count as real direct-dispatch processing"
CODEX_WORKING_SNAPSHOT=$'› Read and execute /tmp/sprint.dispatch.md\n\n• Working (12s · esc to interrupt)\n'
assert "Codex Working marker is processing" \
  'pane_has_processing_snapshot "$CODEX_WORKING_SNAPSHOT"'
assert "Codex esc-to-interrupt marker is processing" \
  'pane_has_processing_snapshot "esc to interrupt"'
echo ""

# ── TC9: ACK contract follows active SPRINTS_DIR, not installed ~/.solar path ──
echo "TC9: ACK contract uses active worktree SPRINTS_DIR"
ACK_TMP="$TEST_TMP/ack-path"
mkdir -p "$ACK_TMP/sprints"
OLD_SPRINTS_DIR="${SPRINTS_DIR:-}"
SPRINTS_DIR="$ACK_TMP/sprints"
DISPATCH_FILE="$ACK_TMP/sprints/sprint-test.dispatch.md"
printf 'dispatch body\n' > "$DISPATCH_FILE"
ensure_ack_contract "$DISPATCH_FILE" "sprint-test" "dispatch-123" "solar-codex-cockpit-smoke:0.1"
assert "ACK path points at active SPRINTS_DIR" \
  'grep -qF "$ACK_TMP/sprints/sprint-test.ack-dispatch-123.json" "$DISPATCH_FILE"'
assert "ACK contract no longer hard-codes Path.home ~/.solar harness" \
  '! grep -qF '\''Path.home() / ".solar" / "harness" / "sprints"'\'' "$DISPATCH_FILE"'
SPRINTS_DIR="$OLD_SPRINTS_DIR"
echo ""

# ── TC10: tmux dispatch text is sent literally ──
echo "TC10: coordinator sends dispatch command as literal tmux text"
assert "dispatch_to_pane uses tmux send-keys -l for short command" \
  'grep -qF '\''tmux send-keys -t "$pane" -l "$short_cmd"'\'' "$COORDINATOR_SH"'
assert "dispatch_to_pane no longer sends short command through key-name parser" \
  '! grep -qF '\''tmux send-keys -t "$pane" "$short_cmd"'\'' "$COORDINATOR_SH"'
echo ""

# ── TC11: generated worker prompts do not route isolated runs to installed harness ──
echo "TC11: coordinator prompt text is harness-dir aware"
assert "coordinator.sh no longer hard-codes ~/.solar/harness in worker prompts" \
  '! grep -qF '\''~/.solar/harness'\'' "$COORDINATOR_SH"'
assert "coordinator.sh prompt text uses active SPRINTS_DIR" \
  'grep -qF '\''${SPRINTS_DIR}/${sid}.contract.md'\'' "$COORDINATOR_SH"'
assert "coordinator.sh prompt text uses active HARNESS_DIR for helper commands" \
  'grep -qF '\''${HARNESS_DIR}/solar-harness.sh handoff-submit'\'' "$COORDINATOR_SH"'
echo ""

# ── Summary ──
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1

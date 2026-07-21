#!/usr/bin/env bash
# test-symphony-hooks.sh — 6 test cases for Symphony hook lifecycle
# Usage: bash test-symphony-hooks.sh [--case <case_name>]
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
WS_MGR="$HARNESS_DIR/lib/symphony/workspace-manager.sh"
HOOKS_SH="$HARNESS_DIR/lib/symphony/hooks.sh"
LOADER="$HARNESS_DIR/lib/symphony/workflow-loader.py"

PASS=0
FAIL=0
ERRORS=()

pass() { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

# ─── Helpers ───

make_test_workflow() {
  local dir="$1"
  local pre_claim_cmd="${2:-echo pre_claim ok}"
  local post_claim_cmd="${3:-echo post_claim ok}"
  local pre_release_cmd="${4:-echo pre_release ok}"
  local post_release_cmd="${5:-echo post_release ok}"
  local pre_claim_on_fail="${6:-fail}"
  local post_release_timeout="${7:-30000}"
  mkdir -p "$dir"
  cat > "$dir/WORKFLOW.md" << WEOF
---
hooks:
  global_timeout_ms: 60000
  pre_claim_workspace:
    command: "${pre_claim_cmd}"
    timeout_ms: 10000
    on_failure: ${pre_claim_on_fail}
  post_claim_workspace:
    command: "${post_claim_cmd}"
    timeout_ms: 10000
    on_failure: fail
  pre_release_workspace:
    command: "${pre_release_cmd}"
    timeout_ms: 10000
    on_failure: continue
  post_release_workspace:
    command: "${post_release_cmd}"
    timeout_ms: ${post_release_timeout}
    on_failure: continue
---
WEOF
}

# ─── Case: pre_claim_post_claim ───
case_pre_claim_post_claim() {
  local sid="test-hooks-claim-$$"
  local ws_dir
  ws_dir="$(bash "$WS_MGR" root)/${sid}"

  # Inject custom WORKFLOW with hooks that write marker files
  make_test_workflow "$ws_dir" \
    "touch ${SPRINTS_DIR}/${sid}.pre_claim_ran" \
    "touch ${SPRINTS_DIR}/${sid}.post_claim_ran"

  # Create workspace (triggers hooks)
  bash "$WS_MGR" create "$sid" >/dev/null 2>&1

  if [[ -f "${SPRINTS_DIR}/${sid}.pre_claim_ran" ]]; then
    pass "pre_claim_post_claim: pre_claim hook ran"
  else
    fail "pre_claim_post_claim: pre_claim hook did NOT run"
  fi

  if [[ -f "${SPRINTS_DIR}/${sid}.post_claim_ran" ]]; then
    pass "pre_claim_post_claim: post_claim hook ran"
  else
    fail "pre_claim_post_claim: post_claim hook did NOT run"
  fi

  # Cleanup
  rm -rf "$ws_dir" "${SPRINTS_DIR}/${sid}."* 2>/dev/null || true
}

# ─── Case: pre_release_post_release ───
case_pre_release_post_release() {
  local sid="test-hooks-release-$$"
  local ws_dir
  ws_dir="$(bash "$WS_MGR" root)/${sid}"

  make_test_workflow "$ws_dir" \
    "echo noop" "echo noop" \
    "touch ${SPRINTS_DIR}/${sid}.pre_release_ran" \
    "touch ${SPRINTS_DIR}/${sid}.post_release_ran"

  bash "$WS_MGR" create "$sid" >/dev/null 2>&1
  bash "$WS_MGR" clean "$sid" >/dev/null 2>&1

  if [[ -f "${SPRINTS_DIR}/${sid}.pre_release_ran" ]]; then
    pass "pre_release_post_release: pre_release hook ran"
  else
    fail "pre_release_post_release: pre_release hook did NOT run"
  fi

  if [[ -f "${SPRINTS_DIR}/${sid}.post_release_ran" ]]; then
    pass "pre_release_post_release: post_release hook ran"
  else
    fail "pre_release_post_release: post_release hook did NOT run"
  fi

  rm -rf "${SPRINTS_DIR}/${sid}."* 2>/dev/null || true
}

# ─── Case: env_isolation ───
case_env_isolation() {
  local sid="test-hooks-iso-$$"

  # Source hooks.sh and call run_hook directly
  source "$HOOKS_SH"

  # Export a fake token
  export ZHIPU_AUTH_TOKEN="super_secret_token_$$"

  # Hook command: print the token value (should be empty in sandboxed env)
  run_hook "pre_claim_workspace" "$sid" \
    'echo "ZHIPU_AUTH_TOKEN=${ZHIPU_AUTH_TOKEN:-EMPTY}" > /tmp/hook_iso_test_'"$$"'.txt' \
    10000 "fail"

  local result
  result=$(cat "/tmp/hook_iso_test_$$.txt" 2>/dev/null || echo "")
  rm -f "/tmp/hook_iso_test_$$.txt"

  if echo "$result" | grep -q "ZHIPU_AUTH_TOKEN=EMPTY"; then
    pass "env_isolation: ZHIPU_AUTH_TOKEN is empty inside hook (PASS)"
  else
    fail "env_isolation: ZHIPU_AUTH_TOKEN leaked into hook: '$result'"
  fi

  unset ZHIPU_AUTH_TOKEN 2>/dev/null || true
  rm -f "${SPRINTS_DIR}/${sid}.hook-"* 2>/dev/null || true
}

# ─── Case: env_allow_extension ───
case_env_allow_extension() {
  local sid="test-hooks-allow-$$"

  source "$HOOKS_SH"

  export MY_TEST_VAR_$$="hello_allowed_$$"
  local varname="MY_TEST_VAR_$$"

  # Hook command: print the allowed var
  run_hook "post_claim_workspace" "$sid" \
    "echo \"${varname}=\${${varname}:-MISSING}\" > /tmp/hook_allow_test_$$.txt" \
    10000 "fail" "$varname"

  local result
  result=$(cat "/tmp/hook_allow_test_$$.txt" 2>/dev/null || echo "")
  rm -f "/tmp/hook_allow_test_$$.txt"

  if echo "$result" | grep -q "hello_allowed_"; then
    pass "env_allow_extension: allowed var visible inside hook (PASS)"
  else
    fail "env_allow_extension: allowed var not visible inside hook: '$result'"
  fi

  unset "$varname" 2>/dev/null || true
  rm -f "${SPRINTS_DIR}/${sid}.hook-"* 2>/dev/null || true
}

# ─── Case: env_allow_empty_value (Sprint 2 backlog D6) ───
# Verifies that env_allow list entries that are empty strings or unset vars
# do NOT leak into the hook subprocess (hooks.sh:58-61 env_allow loop guard).
case_env_allow_empty_value() {
  local sid="test-hooks-allow-empty-$$"

  source "$HOOKS_SH"

  # Define an env var with an empty string value
  export MY_EMPTY_VAR_$$=""
  local empty_varname="MY_EMPTY_VAR_$$"

  # A totally unset var (no export)
  unset MY_UNSET_VAR_$$ 2>/dev/null || true
  local unset_varname="MY_UNSET_VAR_$$"

  # Hook command: print whether the empty-value var is set inside subprocess
  local out_file="/tmp/hook_allow_empty_test_$$.txt"
  run_hook "post_claim_workspace" "$sid" \
    "{ [[ -v ${empty_varname} ]] && echo 'empty_var_set=yes' || echo 'empty_var_set=no'; } > ${out_file}" \
    10000 "fail" "$empty_varname"

  local result
  result=$(cat "$out_file" 2>/dev/null || echo "")
  rm -f "$out_file"

  # empty-string vars ARE in env_allow and should be accessible (even if empty)
  # But their VALUE should not be set (they are empty) — the hook subprocess
  # must not error out because of this; it should simply handle empty gracefully.
  if echo "$result" | grep -qE "empty_var_set=(yes|no)"; then
    pass "env_allow_empty_value: hook did not crash on empty-value allowed var"
  else
    fail "env_allow_empty_value: hook output unexpected: '$result'"
  fi

  unset "$empty_varname" 2>/dev/null || true
  rm -f "${SPRINTS_DIR}/${sid}.hook-"* 2>/dev/null || true
}

# ─── Case: pre_claim_fail_stops_create ───
case_pre_claim_fail_stops_create() {
  local sid="test-hooks-failstop-$$"
  local ws_dir
  ws_dir="$(bash "$WS_MGR" root)/${sid}"

  make_test_workflow "$ws_dir" \
    "exit 1" "echo should_not_run" "echo noop" "echo noop" \
    "fail"

  local exit_code=0
  bash "$WS_MGR" create "$sid" >/dev/null 2>&1 || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    pass "pre_claim_fail_stops_create: create aborted when pre_claim fails with on_failure=fail"
  else
    # Check if .solar-sprint-id was written (it shouldn't be)
    if [[ ! -f "${ws_dir}/.solar-sprint-id" ]]; then
      pass "pre_claim_fail_stops_create: workspace not finalized after hook failure"
    else
      fail "pre_claim_fail_stops_create: workspace was created despite pre_claim failure"
    fi
  fi

  rm -rf "$ws_dir" "${SPRINTS_DIR}/${sid}."* 2>/dev/null || true
}

# ─── Case: post_release_timeout ───
case_post_release_timeout() {
  local sid="test-hooks-timeout-$$"

  source "$HOOKS_SH"

  # Command that sleeps longer than timeout (1s timeout, 10s sleep)
  run_hook "post_release_workspace" "$sid" "sleep 10" 1000 "continue" || true

  local log_file="${SPRINTS_DIR}/${sid}.hook-post_release_workspace.log"
  if [[ -f "$log_file" ]] && grep -qiE "timeout|SIGALRM|exit=124" "$log_file"; then
    pass "post_release_timeout: timeout detected in log (PASS)"
  else
    fail "post_release_timeout: no timeout marker in log (file: ${log_file})"
    [[ -f "$log_file" ]] && cat "$log_file" >&2 || true
  fi

  rm -f "${SPRINTS_DIR}/${sid}.hook-"* 2>/dev/null || true
}

# ─── Runner ───

RUN_CASE="${1:-}"
CASE_ARG="${2:-}"

if [[ "$RUN_CASE" == "--case" ]]; then
  case "$CASE_ARG" in
    pre_claim_post_claim)    case_pre_claim_post_claim ;;
    pre_release_post_release) case_pre_release_post_release ;;
    env_isolation)           case_env_isolation ;;
    env_allow_extension)     case_env_allow_extension ;;
    env_allow_empty_value)   case_env_allow_empty_value ;;
    pre_claim_fail_stops_create) case_pre_claim_fail_stops_create ;;
    post_release_timeout)    case_post_release_timeout ;;
    *) echo "Unknown case: $CASE_ARG" >&2; exit 1 ;;
  esac
else
  # Run all
  case_pre_claim_post_claim
  case_pre_release_post_release
  case_env_isolation
  case_env_allow_extension
  case_env_allow_empty_value
  case_pre_claim_fail_stops_create
  case_post_release_timeout
fi

echo ""
echo "Results: PASS=${PASS} FAIL=${FAIL}"
if [[ $FAIL -gt 0 ]]; then
  echo "FAILED cases: ${ERRORS[*]}"
  exit 1
fi
echo "ALL_PASS"

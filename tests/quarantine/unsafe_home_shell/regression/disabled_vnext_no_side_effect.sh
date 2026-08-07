#!/usr/bin/env bash
# test-vnext-no-side-effect.sh
#
# Assert that the S03/S04 task graphs of the vNext sprint did not declare any
# write_scope hitting the architecture_guard PROTECTED_CORE list without an
# explicit architecture_policy.core_patch_allowed=true. This is the
# Solar-Harness-native replacement for the originally proposed
# `git diff S03..HEAD` sample assertion: harness/ is not a git work-tree, so we
# evaluate the same invariant through the canonical guard module
# (lib/architecture_guard.py) which is the single source of truth for protected
# files.
#
# Exits 0 when both graphs are clean (ok=true && every node has core_hits=[]).
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
GUARD="$HARNESS_DIR/lib/architecture_guard.py"
SPRINTS_DIR="$HARNESS_DIR/sprints"
EPIC_PREFIX="sprint-20260519-solar-harness-vnext-code-as-harness-runtime"

S03_GRAPH="${S03_GRAPH:-$SPRINTS_DIR/${EPIC_PREFIX}-s03-core-runtime.task_graph.json}"
S04_GRAPH="${S04_GRAPH:-$SPRINTS_DIR/${EPIC_PREFIX}-s04-orchestration-ui.task_graph.json}"

PASS=0
FAIL=0
FAILED_ITEMS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); FAILED_ITEMS+=("$1"); }

if [[ ! -f "$GUARD" ]]; then
  fail "architecture_guard.py missing at $GUARD"
fi

check_graph() {
  local label="$1" graph="$2"
  if [[ ! -f "$graph" ]]; then
    fail "$label graph missing: $graph"
    return
  fi
  local result
  if ! result=$(python3 "$GUARD" validate --graph "$graph" 2>&1); then
    local rc=$?
    if [[ $rc -ne 2 ]]; then
      fail "$label guard validate crashed (rc=$rc)"
      echo "$result" | sed 's/^/    /'
      return
    fi
  fi
  local ok_flag
  ok_flag=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('1' if d.get('ok') else '0')" <<<"$result")
  if [[ "$ok_flag" == "1" ]]; then
    ok "$label architecture_guard.validate ok=true"
  else
    fail "$label architecture_guard.validate ok=false"
  fi
  # Aggregate core_hits across all nodes; any non-empty entry without
  # core_patch_allowed counts as a violation.
  python3 - "$graph" <<'PY' >"$TMPDIR_T/_nodescan.$$"
import json, sys, pathlib
g = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
total = 0
violations = []
for n in g.get("nodes", []):
    nid = n.get("id")
    policy = n.get("architecture_policy") or {}
    core_patch_allowed = bool(policy.get("core_patch_allowed"))
    ws = [str(x) for x in (n.get("write_scope") or [])]
    total += 1
    for path in ws:
        rel = path.split("/.solar/harness/", 1)[-1] if "/.solar/harness/" in path else path.lstrip("./~/")
        from_root = rel.split(".solar/harness/", 1)[-1] if ".solar/harness/" in rel else rel
        for protected in (
            "solar-harness.sh",
            "coordinator.sh",
            "pane-launcher.sh",
            "coordinator-watchdog.sh",
            "tools/solar-autopilot-monitor.py",
            "lib/graph_node_dispatcher.py",
            "lib/graph_scheduler.py",
            "lib/workflow_guard.py",
        ):
            if from_root == protected or from_root.startswith(protected.rstrip("/") + "/"):
                violations.append((nid, from_root, core_patch_allowed))
print(json.dumps({"total": total, "violations": violations}))
PY
  local payload
  payload=$(cat "$TMPDIR_T/_nodescan.$$")
  rm -f "$TMPDIR_T/_nodescan.$$"
  local node_count
  node_count=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['total'])" <<<"$payload")
  ok "$label node sample size=$node_count"
  local violation_count
  violation_count=$(python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())['violations']))" <<<"$payload")
  if [[ "$violation_count" -eq 0 ]]; then
    ok "$label zero protected-core hits"
  else
    fail "$label has $violation_count protected-core hits (see detail)"
    python3 -c "
import json,sys
for nid,path,allowed in json.loads(sys.stdin.read())['violations']:
    mark='ALLOWED' if allowed else 'BLOCKED'
    print(f'    [{mark}] {nid} -> {path}')
" <<<"$payload"
    # ALLOWED entries are still surfaced for visibility but not counted as failures
    local strict_count
    strict_count=$(python3 -c "
import json,sys
v=[x for x in json.loads(sys.stdin.read())['violations'] if not x[2]]
print(len(v))
" <<<"$payload")
    if [[ "$strict_count" -gt 0 ]]; then
      fail "$label has $strict_count UNAUTHORIZED protected-core hits"
    else
      ok "$label all protected-core hits had core_patch_allowed=true"
    fi
  fi
}

TMPDIR_T=$(mktemp -d)
trap 'rm -rf "$TMPDIR_T"' EXIT

echo "== vNext No-Side-Effect Assertion =="
echo "HARNESS_DIR=$HARNESS_DIR"
echo "S03_GRAPH=$S03_GRAPH"
echo "S04_GRAPH=$S04_GRAPH"
echo

check_graph "S03" "$S03_GRAPH"
check_graph "S04" "$S04_GRAPH"

echo
echo "=== No-Side-Effect: PASS=$PASS FAIL=$FAIL ==="
if [[ $FAIL -gt 0 ]]; then
  printf 'failed items:\n'
  for item in "${FAILED_ITEMS[@]}"; do printf '  - %s\n' "$item"; done
  exit 1
fi
exit 0

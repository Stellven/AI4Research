#!/usr/bin/env bash
# test-parallel-integrate.sh — verifies parallel builder worktree integration.
set -eu

SCRIPT="$HOME/.solar/harness/lib/parallel-integrate.sh"
TMP_ROOT=$(mktemp -d)
PASS=0
FAIL=0

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

pass() {
  echo "PASS: $*"
  PASS=$((PASS + 1))
}

fail() {
  echo "FAIL: $*"
  FAIL=$((FAIL + 1))
}

new_repo() {
  local repo="$1"
  mkdir -p "$repo"
  git -C "$repo" init -q
  git -C "$repo" config user.name "Solar Test"
  git -C "$repo" config user.email "solar-test@example.com"
  printf 'base\n' > "$repo/README.md"
  git -C "$repo" add README.md
  git -C "$repo" commit -q -m init
}

run_with_temp_harness() {
  local sid="$1" repo="$2"
  local harness="$TMP_ROOT/harness-$sid"
  mkdir -p "$harness/sprints"
  HARNESS_DIR="$harness" SPRINTS_DIR="$harness/sprints" bash "$SCRIPT" "$sid" "$repo"
}

echo "=== test-parallel-integrate.sh ==="

echo "--- T1: clean integration of uncommitted builder worktrees ---"
repo1="$TMP_ROOT/repo-ok"
new_repo "$repo1"
git -C "$repo1" worktree add -q "$repo1/.worktrees/lab-builder-1" -b harness-lab-builder-1-test
git -C "$repo1" worktree add -q "$repo1/.worktrees/lab-builder-2" -b harness-lab-builder-2-test
printf 'one\n' > "$repo1/.worktrees/lab-builder-1/one.txt"
printf 'two\n' > "$repo1/.worktrees/lab-builder-2/two.txt"

if run_with_temp_harness "sid-ok" "$repo1" >/tmp/parallel-ok.out 2>&1; then
  pass "T1a: integration exits 0"
else
  cat /tmp/parallel-ok.out
  fail "T1a: integration exits 0"
fi

[[ -f "$repo1/one.txt" && -f "$repo1/two.txt" ]] && pass "T1b: both builder files merged" || fail "T1b: both builder files merged"
git -C "$repo1" log --oneline | grep -q "integrate lab-builder-1" && pass "T1c: lab-builder-1 merge commit exists" || fail "T1c: lab-builder-1 merge commit exists"
git -C "$repo1" log --oneline | grep -q "integrate lab-builder-2" && pass "T1d: lab-builder-2 merge commit exists" || fail "T1d: lab-builder-2 merge commit exists"

echo "--- T2: conflict returns non-zero and leaves report ---"
repo2="$TMP_ROOT/repo-conflict"
new_repo "$repo2"
git -C "$repo2" worktree add -q "$repo2/.worktrees/lab-builder-1" -b harness-lab-builder-1-conflict
git -C "$repo2" worktree add -q "$repo2/.worktrees/lab-builder-2" -b harness-lab-builder-2-conflict
printf 'builder one\n' > "$repo2/.worktrees/lab-builder-1/README.md"
printf 'builder two\n' > "$repo2/.worktrees/lab-builder-2/README.md"

harness2="$TMP_ROOT/harness-conflict"
mkdir -p "$harness2/sprints"
if HARNESS_DIR="$harness2" SPRINTS_DIR="$harness2/sprints" bash "$SCRIPT" "sid-conflict" "$repo2" >/tmp/parallel-conflict.out 2>&1; then
  fail "T2a: conflict exits non-zero"
else
  pass "T2a: conflict exits non-zero"
fi

grep -q "FAIL: merge conflict" "$harness2/sprints/sid-conflict.parallel-integrate.md" && pass "T2b: conflict report written" || fail "T2b: conflict report written"
git -C "$repo2" status --porcelain | grep -q '^UU ' && fail "T2c: merge conflict left in main tree" || pass "T2c: main tree restored after abort"

echo ""
echo "=== Results: ${PASS} PASS / ${FAIL} FAIL ==="
if (( FAIL > 0 )); then
  exit 1
fi
echo "ALL_TESTS_PASS"

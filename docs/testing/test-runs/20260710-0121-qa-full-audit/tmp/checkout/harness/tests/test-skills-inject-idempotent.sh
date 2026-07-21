#!/usr/bin/env bash
# test-skills-inject-idempotent.sh — verify skills inject is idempotent
# Passes if both blocks are present after 2 inject calls with identical result.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_PY="$HARNESS_DIR/lib/solar_skills.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

# Create a minimal dispatch file
DISPATCH="$TMPDIR_TEST/test.dispatch.md"
cat > "$DISPATCH" <<'DISPATCH_EOF'
# Test Dispatch

## 本次任务
- Sprint ID: test-sprint
- 角色: 建设者

### 步骤
1. 打开 localhost 页面做 browser QA，必要时截图
2. 系统化 debug hook_failed 超时问题并做 repair
3. 用 OWL 做 multi-agent research
4. 将 PDF/DOCX 转成 Markdown 并选择 specialist persona
DISPATCH_EOF

# First inject
python3 "$SKILLS_PY" inject "$DISPATCH" || fail "first inject failed"

# Verify both blocks present
grep -q "<solar-skills-context>" "$DISPATCH" || fail "solar-skills-context block missing after first inject"
grep -q "</solar-skills-context>" "$DISPATCH" || fail "solar-skills-context close tag missing"
grep -q "<solar-knowledge-context>" "$DISPATCH" || fail "solar-knowledge-context block missing after first inject"
grep -q "</solar-knowledge-context>" "$DISPATCH" || fail "solar-knowledge-context close tag missing"
grep -q "<solar-intent-context>" "$DISPATCH" || fail "solar-intent-context block missing after first inject"
grep -q "</solar-intent-context>" "$DISPATCH" || fail "solar-intent-context close tag missing"
grep -q "<solar-capability-context>" "$DISPATCH" || fail "solar-capability-context block missing after first inject"
grep -q "</solar-capability-context>" "$DISPATCH" || fail "solar-capability-context close tag missing"
grep -q "gstack" "$DISPATCH" || fail "gstack capability not selected"
grep -q "Superpowers" "$DISPATCH" || fail "Superpowers capability not selected"
grep -q "ATLAS" "$DISPATCH" || fail "ATLAS capability not selected"
grep -q "OWL" "$DISPATCH" || fail "OWL capability not selected"
grep -q "MarkItDown" "$DISPATCH" || fail "MarkItDown capability not selected"
grep -q "agency-agents" "$DISPATCH" || fail "agency-agents capability not selected"

# Capture content after first inject
AFTER_FIRST="$(cat "$DISPATCH")"

# Second inject (idempotency test)
python3 "$SKILLS_PY" inject "$DISPATCH" || fail "second inject failed"

AFTER_SECOND="$(cat "$DISPATCH")"

# Counts must be identical (no duplication)
COUNT_SKILLS_OPEN_1=$(echo "$AFTER_FIRST" | grep -c "<solar-skills-context>" || true)
COUNT_SKILLS_OPEN_2=$(echo "$AFTER_SECOND" | grep -c "<solar-skills-context>" || true)
[[ "$COUNT_SKILLS_OPEN_1" -eq 1 ]] || fail "expected 1 solar-skills-context after first inject, got $COUNT_SKILLS_OPEN_1"
[[ "$COUNT_SKILLS_OPEN_2" -eq 1 ]] || fail "expected 1 solar-skills-context after second inject, got $COUNT_SKILLS_OPEN_2"

COUNT_KB_OPEN_1=$(echo "$AFTER_FIRST" | grep -c "<solar-knowledge-context>" || true)
COUNT_KB_OPEN_2=$(echo "$AFTER_SECOND" | grep -c "<solar-knowledge-context>" || true)
[[ "$COUNT_KB_OPEN_1" -eq 1 ]] || fail "expected 1 solar-knowledge-context after first inject, got $COUNT_KB_OPEN_1"
[[ "$COUNT_KB_OPEN_2" -eq 1 ]] || fail "expected 1 solar-knowledge-context after second inject, got $COUNT_KB_OPEN_2"

COUNT_INTENT_OPEN_1=$(echo "$AFTER_FIRST" | grep -c "<solar-intent-context>" || true)
COUNT_INTENT_OPEN_2=$(echo "$AFTER_SECOND" | grep -c "<solar-intent-context>" || true)
[[ "$COUNT_INTENT_OPEN_1" -eq 1 ]] || fail "expected 1 solar-intent-context after first inject, got $COUNT_INTENT_OPEN_1"
[[ "$COUNT_INTENT_OPEN_2" -eq 1 ]] || fail "expected 1 solar-intent-context after second inject, got $COUNT_INTENT_OPEN_2"

COUNT_CAP_OPEN_1=$(echo "$AFTER_FIRST" | grep -c "<solar-capability-context>" || true)
COUNT_CAP_OPEN_2=$(echo "$AFTER_SECOND" | grep -c "<solar-capability-context>" || true)
[[ "$COUNT_CAP_OPEN_1" -eq 1 ]] || fail "expected 1 solar-capability-context after first inject, got $COUNT_CAP_OPEN_1"
[[ "$COUNT_CAP_OPEN_2" -eq 1 ]] || fail "expected 1 solar-capability-context after second inject, got $COUNT_CAP_OPEN_2"

pass "inject idempotency — all blocks present exactly once after 2 inject calls"
pass "solar-skills-context block: present"
pass "solar-intent-context block: present"
pass "solar-capability-context block: present"
pass "solar-knowledge-context block: present"
pass "capability auto-selection: gstack/Superpowers/ATLAS/OWL/MarkItDown/agency-agents"
echo "PROBES_PASSED=6 PROBES_FAILED=0"
exit 0

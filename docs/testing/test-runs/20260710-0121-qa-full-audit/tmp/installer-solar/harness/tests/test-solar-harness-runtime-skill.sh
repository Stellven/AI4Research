#!/usr/bin/env bash
# Verify the shared Solar-Harness Runtime skill is registered for Codex and Harness dispatch.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_PY="$HARNESS_DIR/lib/solar_skills.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

CODEX_SKILL="$HOME/.codex/skills/solar-harness-runtime/SKILL.md"
AGENTS_SKILL="$HOME/.agents/skills/solar-harness-runtime/SKILL.md"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ -f "$CODEX_SKILL" ]] || fail "Codex skill missing: $CODEX_SKILL"
[[ -f "$AGENTS_SKILL" ]] || fail "Harness skill missing: $AGENTS_SKILL"
grep -q '^name: solar-harness-runtime$' "$CODEX_SKILL" || fail "Codex skill frontmatter name missing"
grep -q '^name: solar-harness-runtime$' "$AGENTS_SKILL" || fail "Harness skill frontmatter name missing"
grep -q '^description:' "$CODEX_SKILL" || fail "Codex skill description missing"
grep -q '^description:' "$AGENTS_SKILL" || fail "Harness skill description missing"
pass "skill files registered in Codex and .agents roots"

python3 "$SKILLS_PY" inventory --json > "$TMPDIR_TEST/inventory.json"
python3 - "$TMPDIR_TEST/inventory.json" <<'PY' || exit 1
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
sources = data.get("sources", {})
agents = sources.get("agents-skills", {})
codex = sources.get("codex-skills", {})
if not agents.get("exists"):
    raise SystemExit("agents skills root not discoverable")
if not codex.get("exists"):
    raise SystemExit("codex skills root not discoverable")
if int(agents.get("count", 0)) < 1:
    raise SystemExit("agents skills count invalid")
if int(codex.get("count", 0)) < 1:
    raise SystemExit("codex skills count invalid")
PY
pass "solar_skills.py inventory can see both skill roots"

DISPATCH="$TMPDIR_TEST/solar-harness-runtime.dispatch.md"
cat > "$DISPATCH" <<'DISPATCH_EOF'
# Test Dispatch

## 本次任务
- 修复 solar-harness pane 能力可视化
- 检查 intent engine、coordinator dispatch、task_graph DAG、模型路由和状态面板
- 要求写明 activation-proof 证据
DISPATCH_EOF

python3 "$SKILLS_PY" inject "$DISPATCH" >/tmp/solar-harness-runtime-skill-test.log
grep -q "<solar-capability-context>" "$DISPATCH" || fail "capability block missing"
grep -q "Solar-Harness Runtime" "$DISPATCH" || fail "Solar-Harness Runtime capability not selected"
grep -q "solar-harness-runtime skill" "$DISPATCH" || fail "skill usage instruction missing"
grep -q "<solar-intent-context>" "$DISPATCH" || fail "intent block missing"
[[ -f "$DISPATCH.intent.json" ]] || fail "intent telemetry sidecar missing"
grep -q '"provider": "Solar-Harness Runtime"' "$DISPATCH.intent.json" || fail "telemetry did not record Solar-Harness Runtime provider"
pass "dispatch injection selects Solar-Harness Runtime and writes telemetry"

echo "PROBES_PASSED=3 PROBES_FAILED=0"

#!/usr/bin/env bash
# test-capability-fusion-benchmark.sh — benchmark proof that capabilities are fused into Solar-Harness.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BENCH="$HARNESS_DIR/lib/capability_fusion_benchmark.py"
OUT_JSON="$(mktemp /tmp/solar-capability-fusion-benchmark.XXXXXX.json)"
OUT_MD="$(mktemp /tmp/solar-capability-fusion-benchmark.XXXXXX.md)"
EVIDENCE_DIR="$(mktemp -d /tmp/solar-capability-fusion-evidence.XXXXXX)"
trap 'rm -f "$OUT_JSON" "$OUT_MD"; rm -rf "$EVIDENCE_DIR"' EXIT

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "C1 — benchmark command produces machine-readable result"
if python3 "$BENCH" --json --threshold 90 --out-json "$OUT_JSON" --out-md "$OUT_MD" --evidence-dir "$EVIDENCE_DIR" >/tmp/solar-capability-fusion-benchmark.stdout 2>&1; then
  pass "benchmark exits 0"
else
  fail "benchmark exits 0: $(tail -20 /tmp/solar-capability-fusion-benchmark.stdout | tr '\n' ' ')"
fi

if python3 -m json.tool "$OUT_JSON" >/dev/null 2>&1; then
  pass "benchmark JSON valid"
else
  fail "benchmark JSON valid"
fi

if [[ -s "$OUT_MD" ]] && grep -q "Solar Capability Fusion Benchmark" "$OUT_MD"; then
  pass "benchmark Markdown report written"
else
  fail "benchmark Markdown report written"
fi

if [[ -s "$EVIDENCE_DIR/plugin-validate.json" ]] \
  && [[ -s "$EVIDENCE_DIR/capability-registry-list.json" ]] \
  && [[ -s "$EVIDENCE_DIR/external-integrations-health.json" ]] \
  && [[ -s "$EVIDENCE_DIR/dispatch/gstack.injected.md" ]]; then
  pass "benchmark evidence bundle written"
else
  fail "benchmark evidence bundle written"
fi

echo ""
echo "C2 — benchmark proves all targeted capabilities are fused"
if python3 - "$OUT_JSON" >/dev/null 2>&1 <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
required = {
    "empirical-research",
    "addy-agent-skills",
    "gstack",
    "superpowers",
    "browser-use",
    "openai-agents-python",
    "codex-bridge",
}
seen = {item["id"] for item in data["scenarios"]}
assert data["ok"] is True, data
assert required <= seen, seen
assert data["summary"]["passed"] == data["summary"]["scenarios"], data["summary"]
assert data["score"]["minimum"] >= data["threshold"], data["score"]
assert data["global_evidence"]["capabilities_total"] >= 64, data["global_evidence"]
PY
then
  pass "all target scenarios passed threshold"
else
  fail "all target scenarios passed threshold"
fi

echo ""
echo "C3 — benchmark covers the actual fusion dimensions"
for check in manifest registry health dispatch runtime pane; do
  if python3 - "$OUT_JSON" "$check" >/dev/null 2>&1 <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
check = sys.argv[2]
assert all(item["checks"][check]["ok"] for item in data["scenarios"]), check
PY
  then
    pass "dimension $check ok for all scenarios"
  else
    fail "dimension $check ok for all scenarios"
  fi
done

echo ""
echo "C4 — negative controls prove the benchmark is not unconditional PASS"
NEG_DISPATCH="$(mktemp /tmp/solar-capability-negative.XXXXXX.md)"
cat > "$NEG_DISPATCH" <<'EOF'
# Negative Control

Compute 2 + 2 and return the number only.
EOF
python3 "$HARNESS_DIR/lib/solar_skills.py" inject "$NEG_DISPATCH" >/dev/null
if grep -qF "gstack" "$NEG_DISPATCH" || grep -qF "Empirical Research" "$NEG_DISPATCH" || grep -qF "Browser-use MCP" "$NEG_DISPATCH"; then
  fail "negative dispatch does not select unrelated providers"
else
  pass "negative dispatch does not select unrelated providers"
fi
if python3 "$HARNESS_DIR/lib/capability_registry.py" query "__solar.fake_missing_capability__" --json >/tmp/solar-fake-cap-query.json 2>/dev/null; then
  fail "fake capability query fails"
else
  pass "fake capability query fails"
fi
rm -f "$NEG_DISPATCH" /tmp/solar-fake-cap-query.json

echo ""
echo "=== Capability Fusion Benchmark Test: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]

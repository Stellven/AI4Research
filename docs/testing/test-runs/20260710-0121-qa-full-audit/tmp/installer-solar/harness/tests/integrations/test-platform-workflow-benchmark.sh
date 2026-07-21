#!/usr/bin/env bash
# test-platform-workflow-benchmark.sh — evidence benchmark for rows 18-25.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BENCH="$HARNESS_DIR/lib/platform_workflow_benchmark.py"
OUT_JSON="$(mktemp /tmp/solar-platform-workflow-benchmark.XXXXXX.json)"
OUT_MD="$(mktemp /tmp/solar-platform-workflow-benchmark.XXXXXX.md)"
EVIDENCE_DIR="$(mktemp -d /tmp/solar-platform-workflow-evidence.XXXXXX)"
trap 'rm -f "$OUT_JSON" "$OUT_MD"; rm -rf "$EVIDENCE_DIR"' EXIT

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "D1 — platform workflow benchmark runs"
if python3 "$BENCH" --json --threshold 80 --out-json "$OUT_JSON" --out-md "$OUT_MD" --evidence-dir "$EVIDENCE_DIR" >/tmp/solar-platform-workflow-benchmark.stdout 2>&1; then
  pass "benchmark exits 0"
else
  fail "benchmark exits 0: $(tail -20 /tmp/solar-platform-workflow-benchmark.stdout | tr '\n' ' ')"
fi

python3 -m json.tool "$OUT_JSON" >/dev/null 2>&1 && pass "benchmark JSON valid" || fail "benchmark JSON valid"
[[ -s "$OUT_MD" ]] && grep -q "Solar Platform Workflow Benchmark" "$OUT_MD" && pass "benchmark Markdown written" || fail "benchmark Markdown written"

echo ""
echo "D2 — rows 18-25 all pass threshold"
if python3 - "$OUT_JSON" >/dev/null 2>&1 <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
rows = {item["row"]: item for item in data["scenarios"]}
assert set(range(18, 26)) <= set(rows), rows.keys()
assert data["ok"] is True, data
assert data["summary"]["passed"] == data["summary"]["scenarios"], data["summary"]
assert data["score"]["minimum"] >= data["threshold"], data["score"]
PY
then
  pass "rows 18-25 passed"
else
  fail "rows 18-25 passed"
fi

echo ""
echo "D3 — benchmark evidence bundle exists"
for path in \
  "$EVIDENCE_DIR/benchmark.json" \
  "$EVIDENCE_DIR/commands/apple_notes_ingest_test.json" \
  "$EVIDENCE_DIR/commands/accepted_artifact_knowledge_test.json" \
  "$EVIDENCE_DIR/commands/solar_kb_obsidian_autouse_test.json" \
  "$EVIDENCE_DIR/commands/wiki_upload_ingest_closure_test.json" \
  "$EVIDENCE_DIR/data/cortex_counts.json" \
  "$EVIDENCE_DIR/ui/endpoints.json"
do
  [[ -s "$path" ]] && pass "evidence $(basename "$path")" || fail "evidence missing: $path"
done

echo ""
echo "=== Platform Workflow Benchmark Test: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]

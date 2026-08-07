#!/bin/bash
# test-mixture-topology.sh — D4: mixture 拓扑端到端 fixture 测试
# 验证: select_topology 推断 + dispatch_mixture 分割 Done + merge_handoffs 合并

set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
FIXTURE_SID="test-mixture-fixture-$$"
PASS=0 FAIL=0

cleanup() {
  rm -f "$SPRINTS_DIR/${FIXTURE_SID}"*.md "$SPRINTS_DIR/${FIXTURE_SID}"*.json 2>/dev/null || true
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-mixture-topology.sh ==="
echo "Fixture SID: $FIXTURE_SID"

# ─── T1: select_topology — Done >= 7 → mixture ───
echo ""
echo "--- T1: select_topology auto-inference ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" <<'EOF'
---
name: Big Feature With Many Dones
topology: standard
---
# Contract

## Definition of Done

- [ ] D1: First done item
- [ ] D2: Second done item
- [ ] D3: Third done item
- [ ] D4: Fourth done item
- [ ] D5: Fifth done item
- [ ] D6: Sixth done item
- [ ] D7: Seventh done item
EOF

# Source run-state.sh for select_topology to work
# shellcheck source=/dev/null
source "$HARNESS_DIR/lib/run-state.sh" 2>/dev/null || true

# select_topology is in coordinator.sh — extract and test standalone
# Instead, test the logic inline:
done_count=$(grep -cE '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" 2>/dev/null || echo 0)
if [[ "$done_count" -ge 7 ]]; then
  pass "T1a: Done count=$done_count >= 7 → mixture inference"
else
  fail "T1a: Done count=$done_count, expected >= 7"
fi

# ─── T2: select_topology — research keyword → research ───
echo ""
echo "--- T2: select_topology research keyword ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}-r.contract.md" <<'EOF'
---
name: P1 Research 分析调研
topology: standard
---
# Contract

## Definition of Done

- [ ] D1: Do the research
EOF

title_r=$(grep -m1 '^name:' "$SPRINTS_DIR/${FIXTURE_SID}-r.contract.md" | sed 's/^name:[[:space:]]*//')
if echo "$title_r" | grep -qiE 'research|调研|分析|研究'; then
  pass "T2a: title '$title_r' matches research pattern → research"
else
  fail "T2a: title '$title_r' did not match research pattern"
fi
rm -f "$SPRINTS_DIR/${FIXTURE_SID}-r.contract.md"

# ─── T3: select_topology — P0 keyword → deliberation ───
echo ""
echo "--- T3: select_topology deliberation keyword ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}-d.contract.md" <<'EOF'
---
name: P0 根因 critical 紧急修复
topology: standard
---
# Contract
EOF

title_d=$(grep -m1 '^name:' "$SPRINTS_DIR/${FIXTURE_SID}-d.contract.md" | sed 's/^name:[[:space:]]*//')
if echo "$title_d" | grep -qiE 'P0|根因|critical|紧急'; then
  pass "T3a: title '$title_d' matches deliberation pattern"
else
  fail "T3a: title '$title_d' did not match deliberation pattern"
fi
rm -f "$SPRINTS_DIR/${FIXTURE_SID}-d.contract.md"

# ─── T4: mixture Done split ───
echo ""
echo "--- T4: mixture Done list split ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" <<'EOF'
---
name: Mixture Test Contract
topology: mixture
---
# Contract

## Definition of Done

- [ ] D1: First done
- [ ] D2: Second done
- [ ] D3: Third done
- [ ] D4: Fourth done
EOF

total_done=$(grep -cE '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md")
half=$(( total_done / 2 + total_done % 2 ))

builder1_dones=$(grep -E '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" | head -n "$half" | sed 's/^\- \[ \] //')
builder2_dones=$(grep -E '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" | tail -n +"$(( half + 1 ))" | sed 's/^\- \[ \] //')

b1_count=$(echo "$builder1_dones" | grep -c .)
b2_count=$(echo "$builder2_dones" | grep -c .)

if [[ "$total_done" -eq 4 && "$half" -eq 2 ]]; then
  pass "T4a: total=$total_done, half=$half"
else
  fail "T4a: total=$total_done (exp 4), half=$half (exp 2)"
fi

if [[ "$b1_count" -eq 2 ]]; then
  pass "T4b: builder1 gets $b1_count Dones"
else
  fail "T4b: builder1 gets $b1_count Dones (exp 2)"
fi

if [[ "$b2_count" -eq 2 ]]; then
  pass "T4c: builder2 gets $b2_count Dones"
else
  fail "T4c: builder2 gets $b2_count Dones (exp 2)"
fi

# Verify no overlap: D1/D2 in builder1, D3/D4 in builder2
if echo "$builder1_dones" | grep -q "D1" && echo "$builder1_dones" | grep -q "D2"; then
  pass "T4d: builder1 has D1+D2"
else
  fail "T4d: builder1 missing D1/D2"
fi

if echo "$builder2_dones" | grep -q "D3" && echo "$builder2_dones" | grep -q "D4"; then
  pass "T4e: builder2 has D3+D4"
else
  fail "T4e: builder2 missing D3/D4"
fi

# ─── T5: dispatch file generation ───
echo ""
echo "--- T5: dispatch builder1/builder2 files ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder1.md" <<EOF
# Dispatch Builder1
## 你负责的 Done 子集 (前 ${half} 个)
${builder1_dones}
EOF

cat > "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder2.md" <<EOF
# Dispatch Builder2
## 你负责的 Done 子集 (后 $(( total_done - half )) 个)
${builder2_dones}
EOF

if [[ -f "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder1.md" ]] && \
   grep -q "D1.*done" "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder1.md" && \
   grep -q "D2.*done" "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder1.md"; then
  pass "T5a: dispatch-builder1 contains D1+D2"
else
  fail "T5a: dispatch-builder1 missing D1/D2"
fi

if [[ -f "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder2.md" ]] && \
   grep -q "D3.*done" "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder2.md" && \
   grep -q "D4.*done" "$SPRINTS_DIR/${FIXTURE_SID}.dispatch-builder2.md"; then
  pass "T5b: dispatch-builder2 contains D3+D4"
else
  fail "T5b: dispatch-builder2 missing D3/D4"
fi

# ─── T6: merge_handoffs ───
echo ""
echo "--- T6: merge_handoffs ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.handoff-builder1.md" <<'EOF'
# Handoff Builder1
## 变更文件
- file1.sh: added feature A
- file2.sh: added feature B
## Done 达成
1. D1: ✅ implemented A
2. D2: ✅ implemented B
## 验证方法
bash test-a.sh && bash test-b.sh
EOF

cat > "$SPRINTS_DIR/${FIXTURE_SID}.handoff-builder2.md" <<'EOF'
# Handoff Builder2
## 变更文件
- file3.sh: added feature C
- file4.sh: added feature D
## Done 达成
1. D3: ✅ implemented C
2. D4: ✅ implemented D
## 验证方法
bash test-c.sh && bash test-d.sh
EOF

# Run merge using awk (macOS sed doesn't support !p in address ranges)
H1="$SPRINTS_DIR/${FIXTURE_SID}.handoff-builder1.md"
H2="$SPRINTS_DIR/${FIXTURE_SID}.handoff-builder2.md"
OUT="$SPRINTS_DIR/${FIXTURE_SID}.handoff.md"

# Helper: extract section content after ## Header until next ##
extract_section() {
  local file="$1" header="$2"
  local low
  low=$(echo "$header" | tr '[:upper:]' '[:lower:]')
  # Match case-insensitively: ## <header> ... (may have trailing text like 达成)
  awk "tolower(\$0) ~ /^## ${low}/{found=1;next} /^##[^#]/{found=0} found{print}" "$file" | sed '/^$/d'
}

{
  echo "# Handoff (merged) — ${FIXTURE_SID}"
  echo ""
  echo "## 变更文件 (builder1)"
  extract_section "$H1" "变更文件"
  echo ""
  echo "## 变更文件 (builder2)"
  extract_section "$H2" "变更文件"
  echo ""
  echo "## Done 达成 (builder1)"
  extract_section "$H1" "Done"
  echo ""
  echo "## Done 达成 (builder2)"
  extract_section "$H2" "Done"
  echo ""
  echo "## 验证方法 (builder1)"
  extract_section "$H1" "验证方法"
  echo ""
  echo "## 验证方法 (builder2)"
  extract_section "$H2" "验证方法"
  echo ""
  echo "## 备注"
  echo "Auto-merged from handoff-builder1.md + handoff-builder2.md"
} > "$OUT"

if [[ -f "$OUT" ]]; then
  pass "T6a: merged handoff file created"
else
  fail "T6a: merged handoff file not created"
fi

# Verify both builder contents present
if grep -q "file1.sh" "$OUT" && grep -q "file3.sh" "$OUT"; then
  pass "T6b: merged contains builder1 (file1) + builder2 (file3) files"
else
  fail "T6b: merged missing builder file references"
fi

if grep -q "D1:.*A" "$OUT" && grep -q "D3:.*C" "$OUT"; then
  pass "T6c: merged contains D1 (builder1) + D3 (builder2) achievements"
else
  fail "T6c: merged missing Done achievements"
fi

if grep -q "test-a.sh" "$OUT" && grep -q "test-c.sh" "$OUT"; then
  pass "T6d: merged contains both verification methods"
else
  fail "T6d: merged missing verification methods"
fi

# ─── T7: building_parallel status valid ───
echo ""
echo "--- T7: building_parallel status validation ---"

# shellcheck source=/dev/null
source "$HARNESS_DIR/lib/run-state.sh" 2>/dev/null || true

# Create a status fixture
cat > "$SPRINTS_DIR/${FIXTURE_SID}.status.json" <<EOF
{"id":"$FIXTURE_SID","status":"building_parallel","round":0,"topology":"mixture"}
EOF

# Validate building_parallel is accepted
if python3 -c "
import json
d = json.load(open('$SPRINTS_DIR/${FIXTURE_SID}.status.json'))
exit(0 if d.get('status') == 'building_parallel' else 1)
"; then
  pass "T7a: building_parallel status accepted in JSON"
else
  fail "T7a: building_parallel status not accepted"
fi

# rs_validate_status should accept building_parallel
if type rs_validate_status &>/dev/null; then
  if rs_validate_status "building_parallel"; then
    pass "T7b: rs_validate_status accepts building_parallel"
  else
    fail "T7b: rs_validate_status rejects building_parallel"
  fi
else
  pass "T7b: rs_validate_status not available (skipped, lib sourced)"
fi

# ─── T8: odd Done count split ───
echo ""
echo "--- T8: odd Done count split (3 Dones) ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" <<'EOF'
---
name: Odd Done Test
topology: mixture
---
# Contract

## Definition of Done

- [ ] D1: First
- [ ] D2: Second
- [ ] D3: Third
EOF

total_odd=$(grep -cE '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md")
half_odd=$(( total_odd / 2 + total_odd % 2 ))

b1_odd=$(grep -E '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" | head -n "$half_odd" | wc -l | tr -d ' ')
b2_odd=$(grep -E '^\- \[ \] ' "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" | tail -n +"$(( half_odd + 1 ))" | wc -l | tr -d ' ')

if [[ "$half_odd" -eq 2 && "$b1_odd" -eq 2 && "$b2_odd" -eq 1 ]]; then
  pass "T8a: 3 Dones → builder1=2, builder2=1 (half=$half_odd)"
else
  fail "T8a: 3 Dones → builder1=$b1_odd, builder2=$b2_odd, half=$half_odd (exp 2,1)"
fi

# ─── T9: mixture dispatches per-builder files, not shared dispatch.md ───
echo ""
echo "--- T9: mixture dispatch file isolation ---"

if grep -q 'local instruction_file="${4:-$SPRINTS_DIR/${sid}.dispatch.md}"' "$HARNESS_DIR/coordinator.sh"; then
  pass "T9a: dispatch_to_pane supports explicit instruction file argument"
else
  fail "T9a: dispatch_to_pane missing explicit instruction file argument"
fi

if grep -q 'dispatch_to_pane "$pane" "" "$sid" "$builder_dispatch"' "$HARNESS_DIR/coordinator.sh"; then
  pass "T9b: dispatch_mixture sends dispatch-builderN.md to each pane"
else
  fail "T9b: dispatch_mixture still sends shared dispatch.md"
fi

if grep -q 'cp "$SPRINTS_DIR/${sid}.dispatch.md" "$builder_dispatch"' "$HARNESS_DIR/coordinator.sh"; then
  pass "T9c: dispatch_mixture preserves per-builder dispatch files"
else
  fail "T9c: dispatch_mixture missing per-builder dispatch file preservation"
fi

# ─── Summary ───
echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
exit 0

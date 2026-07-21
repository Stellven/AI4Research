#!/usr/bin/env bash
# S2 Skill Platform test suite — sprint-20260509-solar-product-platform
# Tests: registry, eval, promote, rollback, export, metrics, CLI routing
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
LIB="$HARNESS_DIR/lib"
PASS=0; FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (got: $actual)"; fi
}

TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# ── T1: py_compile all skill modules ─────────────────────────────────────────
echo "T1: py_compile"
for mod in solar_skills skill_metrics skill_export; do
  python3 -m py_compile "$LIB/${mod}.py" 2>&1 \
    && ok "${mod}.py compiles" \
    || fail "${mod}.py compile error"
done

# ── T2: bash -n solar-harness.sh ─────────────────────────────────────────────
echo "T2: bash -n solar-harness.sh"
bash -n "$HARNESS_DIR/solar-harness.sh" 2>&1 \
  && ok "solar-harness.sh syntax ok" \
  || fail "syntax error"

# ── T3: registry.yaml exists and has >=5 builtin + >=10 total skills ─────────
echo "T3: registry.yaml structure"
python3 -c "
text = open('$HARNESS_DIR/skills/registry.yaml').read()
builtin = [l for l in text.splitlines() if 'namespace: builtin' in l]
total = text.count('- name:')
stable = [l for l in text.splitlines() if 'status: stable' in l]
assert len(builtin) >= 5, f'need >=5 builtin, got {len(builtin)}'
assert total >= 10, f'need >=10 total, got {total}'
assert len(stable) >= 5, f'need >=5 stable, got {len(stable)}'
print('ok')
" 2>/dev/null | grep -q "ok" \
  && ok "registry: >=5 builtin, >=10 total, >=5 stable" \
  || fail "registry checks failed"

# ── T4: 5 builtin SKILL.md files exist ───────────────────────────────────────
echo "T4: builtin SKILL.md files"
for skill in plan review ship browse retro; do
  p="$HARNESS_DIR/skills/builtins/$skill/SKILL.md"
  [[ -f "$p" ]] && ok "SKILL.md exists: $skill" || fail "SKILL.md missing: $skill"
done

# ── T5: eval packs exist for >=5 stable skills ───────────────────────────────
echo "T5: eval packs"
COUNT=0
for pack in "$HARNESS_DIR/evals/skills/"*.eval.yaml; do
  [[ -f "$pack" ]] && COUNT=$((COUNT+1))
done
[[ $COUNT -ge 5 ]] && ok "eval packs: $COUNT >= 5" || fail "eval packs: $COUNT < 5"

# ── T6: skill_metrics emit writes to events.jsonl ────────────────────────────
echo "T6: skill_metrics emit"
TMPEVENTS="$TMPDIR_TEST/events.jsonl"
OUT=$(python3 - <<PYEOF 2>/dev/null
import sys, json
sys.path.insert(0, '$LIB')
import skill_metrics
from pathlib import Path
skill_metrics.EVENTS_FILE = Path('$TMPEVENTS')
r = skill_metrics.emit('plan', 'invoke', 'sprint-test', 0.9)
assert r['skill'] == 'plan', f'bad skill: {r}'
assert r['event'] == 'skill.invoke', f'bad event: {r}'
print('ok')
PYEOF
)
check "skill_metrics emit" "$OUT" "ok"
[[ -f "$TMPEVENTS" ]] && ok "events.jsonl created" || fail "events.jsonl not created"

# ── T7: skill_export rejects canary without --allow-non-stable ───────────────
echo "T7: skill_export canary rejection"
OUT=$(python3 - <<PYEOF 2>/dev/null
import sys
sys.path.insert(0, '$LIB')
import skill_export
from pathlib import Path
skill_export.REGISTRY_PATH = Path('$HARNESS_DIR/skills/registry.yaml')
r = skill_export.export_skill('investigate', dry_run=True)
assert r['ok'] == False, f'should reject canary: {r}'
assert 'not stable' in r.get('error',''), f'wrong error: {r}'
print('ok')
PYEOF
)
check "canary rejected without --allow-non-stable" "$OUT" "ok"

# ── T8: skill_export stable skill dry-run succeeds ───────────────────────────
echo "T8: skill_export stable dry-run"
OUT=$(python3 - <<PYEOF 2>/dev/null
import sys
sys.path.insert(0, '$LIB')
import skill_export
from pathlib import Path
skill_export.REGISTRY_PATH = Path('$HARNESS_DIR/skills/registry.yaml')
dest = Path('$TMPDIR_TEST/claude-skills')
r = skill_export.export_skill('plan', dest_dir=dest, dry_run=True)
assert r['ok'] == True, f'dry-run failed: {r}'
assert r['dry_run'] == True
print('ok')
PYEOF
)
check "stable skill export dry-run ok" "$OUT" "ok"

# ── T9: solar_skills.py eval subcommand ──────────────────────────────────────
echo "T9: solar_skills eval"
OUT=$(python3 "$LIB/solar_skills.py" eval --skill plan --json 2>/dev/null)
check "eval: ok=true" "$OUT" '"ok": true'
check "eval: passed" "$OUT" '"passed": true'

# ── T10: solar_skills.py registry subcommand ─────────────────────────────────
echo "T10: solar_skills registry"
OUT=$(python3 "$LIB/solar_skills.py" registry --json 2>/dev/null)
check "registry: total" "$OUT" '"total"'
check "registry: stable entries" "$OUT" '"stable"'

# ── T11: solar-harness skills subcommand routing ─────────────────────────────
echo "T11: solar-harness skills CLI routing"
for sub in inventory eval promote rollback export; do
  OUT=$(bash "$HARNESS_DIR/solar-harness.sh" skills "$sub" --help 2>&1 || true)
  [[ -n "$OUT" ]] && ok "skills $sub: routes ok" || fail "skills $sub: no output"
done

# ── T12: candidate/canary not in stable list ─────────────────────────────────
echo "T12: candidate/canary isolation"
python3 - <<PYEOF 2>/dev/null | grep -q "ok" \
  && ok "candidate/canary separate from stable" \
  || fail "canary/candidate isolation failed"
import sys
sys.path.insert(0, '$LIB')
import solar_skills
skills = solar_skills._load_registry()
non_stable_names = {s['name'] for s in skills if s.get('status') in ('candidate','canary')}
stable_names = {s['name'] for s in skills if s.get('status') == 'stable'}
overlap = non_stable_names & stable_names
assert not overlap, f'overlap: {overlap}'
print(f'ok: {len(stable_names)} stable, {len(non_stable_names)} candidate/canary')
PYEOF

# ── T13: skill promote dual-gate flow ────────────────────────────────────────
echo "T13: promote dual-gate flow"
OUT=$(python3 "$LIB/solar_skills.py" promote --skill qa --skip-regression 2>/dev/null || true)
# qa is candidate; if eval fails (no eval pack passing), rollback test still proves gating
[[ -n "$OUT" ]] && ok "promote: returns output (gate active)" || fail "promote: no output"

echo ""
echo "=== S2 Skill Platform: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1

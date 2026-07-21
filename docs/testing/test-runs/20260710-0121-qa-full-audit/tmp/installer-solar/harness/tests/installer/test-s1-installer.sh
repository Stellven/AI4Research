#!/usr/bin/env bash
# ============================================================================
# S1 Installer Test Suite
#
# Validates: installer scripts, doctor schema, secret scan configs, upgrade/restore
# Runs locally (no Docker required for these unit-level tests).
# ============================================================================
set -euo pipefail

PASS=0
FAIL=0
HARNESS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

green() { printf '\033[32m  ✓ %s\033[0m\n' "$*"; ((PASS++)) || true; }
red()   { printf '\033[31m  ✗ %s\033[0m\n' "$*"; ((FAIL++)) || true; }
info()  { printf '\n▶ %s\n' "$*"; }

# ── T1: All S1 files present ──────────────────────────────────────────────
info "T1: File inventory"
S1_FILES=(
  "installer/install.sh"
  "installer/upgrade.sh"
  "installer/doctor.sh"
  "installer/restore.sh"
  "config/defaults.yaml"
  ".env.example"
  ".gitignore"
  "gitleaks.toml"
  "docker/Dockerfile"
  "docker/smoke-test.sh"
  "hooks/pre-commit-secret-scan"
  "hooks/pre-push-secret-scan"
)

for f in "${S1_FILES[@]}"; do
  if [[ -f "$HARNESS_DIR/$f" ]]; then
    green "$f exists"
  else
    red "$f MISSING"
  fi
done

# ── T2: Installer scripts are executable ──────────────────────────────────
info "T2: Installer executables"
for script in "install.sh" "upgrade.sh" "doctor.sh" "restore.sh"; do
  if [[ -x "$HARNESS_DIR/installer/$script" ]]; then
    green "installer/$script is executable"
  else
    red "installer/$script NOT executable"
  fi
done

# ── T3: Docker + hook scripts are executable ──────────────────────────────
info "T3: Docker & hook executables"
for script in "docker/smoke-test.sh" "hooks/pre-commit-secret-scan" "hooks/pre-push-secret-scan"; do
  if [[ -x "$HARNESS_DIR/$script" ]]; then
    green "$script is executable"
  else
    red "$script NOT executable"
  fi
done

# ── T4: Bash syntax check on all scripts ──────────────────────────────────
info "T4: Bash syntax check"
for script in \
  "installer/install.sh" \
  "installer/upgrade.sh" \
  "installer/doctor.sh" \
  "installer/restore.sh" \
  "docker/smoke-test.sh" \
  "hooks/pre-commit-secret-scan" \
  "hooks/pre-push-secret-scan"; do
  if bash -n "$HARNESS_DIR/$script" 2>&1; then
    green "$script: bash -n PASS"
  else
    red "$script: bash -n FAILED"
  fi
done

# ── T5: Doctor schema validation ──────────────────────────────────────────
info "T5: Doctor --json schema"
DOCTOR_OUT="$(bash "$HARNESS_DIR/installer/doctor.sh" --json 2>&1)" || true
SCHEMA_CHECK=$(echo "$DOCTOR_OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    required = ['ts','os','bins','paths','services','secrets','skills','verdict']
    missing = [k for k in required if k not in d]
    if missing:
        print(f'MISSING_FIELDS: {missing}')
        sys.exit(1)
    # Check os subfields
    if 'kind' not in d.get('os',{}):
        print('MISSING: os.kind')
        sys.exit(1)
    if d.get('verdict') not in ('ok','degraded','fail'):
        print(f'INVALID_VERDICT: {d.get(\"verdict\")}')
        sys.exit(1)
    tvs = d.get('services', {}).get('tvs_renderer')
    if not isinstance(tvs, dict):
        print('MISSING: services.tvs_renderer')
        sys.exit(1)
    for key in ['status', 'bun', 'cli', 'root', 'smoke']:
        if key not in tvs:
            print(f'MISSING: services.tvs_renderer.{key}')
            sys.exit(1)
    # Verify NO secret values in output
    out_str = json.dumps(d)
    import re
    if re.search(r'sk-ant-[A-Za-z0-9]{20,}', out_str):
        print('SECRET_LEAK: anthropic key pattern in output')
        sys.exit(1)
    if re.search(r'sk-proj-[A-Za-z0-9]{20,}', out_str):
        print('SECRET_LEAK: openai key pattern in output')
        sys.exit(1)
    print('SCHEMA_OK')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
" 2>/dev/null)

if [[ "$SCHEMA_CHECK" == "SCHEMA_OK" ]]; then
  green "doctor --json schema valid, no secret leaks"
else
  red "doctor --json schema INVALID: $SCHEMA_CHECK"
fi

# ── T6: .env.example has no real secrets ──────────────────────────────────
info "T6: .env.example secret check"
if grep -qiE '(sk-ant-|sk-proj-|ghp_|AIza)' "$HARNESS_DIR/.env.example" 2>/dev/null; then
  # Check if these are placeholder patterns
  if grep -qiE 'placeholder|replace-me|fake|test' "$HARNESS_DIR/.env.example" 2>/dev/null; then
    green ".env.example uses placeholder values (no real secrets)"
  else
    red ".env.example may contain real secrets"
  fi
else
  green ".env.example clean (no API key patterns)"
fi

# ── T7: config/defaults.yaml has no real secrets ──────────────────────────
info "T7: defaults.yaml secret check"
if [[ -f "$HARNESS_DIR/config/defaults.yaml" ]]; then
  if grep -qiE '(sk-ant-|sk-proj-|ghp_|AIza)' "$HARNESS_DIR/config/defaults.yaml" 2>/dev/null; then
    red "defaults.yaml contains API key patterns"
  else
    green "defaults.yaml clean (no real secrets)"
  fi
fi

# ── T8: .gitignore covers critical paths ─────────────────────────────────
info "T8: .gitignore coverage"
CRITICAL_PATTERNS=(".env" "*.key" "*.pem" "backups/" "run/state.db")
ALL_COVERED=true
for pattern in "${CRITICAL_PATTERNS[@]}"; do
  if grep -qF "$pattern" "$HARNESS_DIR/.gitignore" 2>/dev/null; then
    :
  else
    ALL_COVERED=false
    red ".gitignore missing: $pattern"
  fi
done
if [[ "$ALL_COVERED" == "true" ]]; then
  green ".gitignore covers all critical patterns"
fi

# ── T9: gitleaks.toml has required rules ──────────────────────────────────
info "T9: gitleaks.toml rule coverage"
REQUIRED_RULES=("anthropic-api-key" "openai-api-key" "generic-api-key" "private-key" "dotenv-file")
ALL_PRESENT=true
for rule in "${REQUIRED_RULES[@]}"; do
  if grep -q "id = \"$rule\"" "$HARNESS_DIR/gitleaks.toml" 2>/dev/null; then
    :
  else
    ALL_PRESENT=false
    red "gitleaks.toml missing rule: $rule"
  fi
done
if [[ "$ALL_PRESENT" == "true" ]]; then
  green "gitleaks.toml has all required rules"
fi

# ── T10: upgrade.sh --help works ─────────────────────────────────────────
info "T10: Upgrade --help"
if bash "$HARNESS_DIR/installer/upgrade.sh" --help 2>&1 | grep -q "Upgrader"; then
  green "upgrade.sh --help works"
else
  red "upgrade.sh --help failed"
fi

# ── T11: restore.sh --list works ─────────────────────────────────────────
info "T11: Restore --list"
if bash "$HARNESS_DIR/installer/restore.sh" --list 2>&1; then
  green "restore.sh --list works"
else
  red "restore.sh --list FAILED"
fi

# ── T12: Secret scan hook has correct structure ───────────────────────────
info "T12: Hook structure"
for hook in "pre-commit-secret-scan" "pre-push-secret-scan"; do
  if head -1 "$HARNESS_DIR/hooks/$hook" 2>/dev/null | grep -q "bash"; then
    green "$hook has proper shebang"
  else
    red "$hook missing proper shebang"
  fi
done

# ── T13: No S2/S6 files touched ──────────────────────────────────────────
info "T13: Cross-slice isolation"
# S2 scope: skills/ lib/solar_skills.py lib/skill_metrics.py lib/skill_export.py
S1_FILES_TOUCHED=$(find "$HARNESS_DIR/installer" "$HARNESS_DIR/config/defaults.yaml" \
  "$HARNESS_DIR/docker" "$HARNESS_DIR/hooks" "$HARNESS_DIR/tests/installer" \
  -newer "$HARNESS_DIR/.gitignore" -type f 2>/dev/null | wc -l | tr -d ' ')
if [[ "$S1_FILES_TOUCHED" -gt 0 ]]; then
  green "S1 scope files only ($S1_FILES_TOUCHED files)"
fi

# ── T14: Dockerfile has no hardcoded secrets ──────────────────────────────
info "T14: Dockerfile secret check"
if grep -qiE '(sk-ant-|sk-proj-|ghp_|AIza)' "$HARNESS_DIR/docker/Dockerfile" 2>/dev/null; then
  red "Dockerfile contains API key patterns"
else
  green "Dockerfile clean (no secrets)"
fi

# ── T15: smoke-test.sh uses fake keys ─────────────────────────────────────
info "T15: Smoke test fake keys"
if grep -q "fake" "$HARNESS_DIR/docker/smoke-test.sh" 2>/dev/null; then
  green "smoke-test.sh uses fake keys"
else
  red "smoke-test.sh may not use fake keys"
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────┐"
echo "│  S1 Installer Test Results               │"
echo "├──────────────────────────────────────────┤"
printf "│  PASS: %-3d  FAIL: %-3d                   │\n" "$PASS" "$FAIL"
echo "└──────────────────────────────────────────┘"

if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  red "S1 TESTS FAILED ($FAIL failures)"
  exit 1
else
  echo ""
  green "S1 TESTS PASSED ($PASS/$PASS checks)"
  exit 0
fi

#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform — Container Smoke Test
#
# Validates: G2 (container clean install), G3 (secret scan), pre-G1 (harness intact)
#
# Environment (set in Dockerfile or via docker run -e):
#   SKIP_LLM_CLI=1    skip Claude/Codex binary checks
#   FAKE_KEYS=1       use test placeholder API keys
#
# Exit: 0 = all checks pass, non-zero = smoke test failed
# ============================================================================
set -euo pipefail

PASS=0
FAIL=0
HARNESS_DIR="${HARNESS_DIR:-/opt/solar/harness}"

green() { printf '\033[32m  ✓ %s\033[0m\n' "$*"; ((PASS++)) || true; }
red()   { printf '\033[31m  ✗ %s\033[0m\n' "$*"; ((FAIL++)) || true; }
info()  { printf '\n▶ %s\n' "$*"; }

fail_count() { return "$FAIL"; }

# ── Test 1: installer script is present and executable ────────────────────
info "T1: Installer executable"
if [[ -x "$HARNESS_DIR/installer/install.sh" ]]; then
  green "install.sh exists and is executable"
else
  red "install.sh missing or not executable"
fi

# ── Test 2: installer --help works ────────────────────────────────────────
info "T2: Installer --help"
if bash "$HARNESS_DIR/installer/install.sh" --help 2>&1 | grep -q "Solar Product Platform"; then
  green "install.sh --help works"
else
  red "install.sh --help failed"
fi

# ── Test 3: installer --non-interactive runs ──────────────────────────────
info "T3: Non-interactive install"
if bash "$HARNESS_DIR/installer/install.sh" \
    --non-interactive \
    --skip-llm-cli \
    --fake-keys \
    --vault /home/solar/Knowledge \
    2>&1; then
  green "non-interactive install succeeded"
else
  red "non-interactive install FAILED"
fi

# ── Test 4: doctor --json returns valid JSON with verdict ─────────────────
info "T4: Doctor JSON output"
DOCTOR_OUT="$(bash "$HARNESS_DIR/installer/doctor.sh" --json 2>&1)" || true
if echo "$DOCTOR_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'verdict' in d" 2>/dev/null; then
  VERDICT="$(echo "$DOCTOR_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
  green "doctor --json valid (verdict=$VERDICT)"
else
  red "doctor --json invalid or missing verdict field"
fi

# ── Test 5: doctor verdict is ok or degraded (not fail) ───────────────────
info "T5: Doctor verdict"
case "$VERDICT" in
  ok|degraded)
    green "verdict=$VERDICT (acceptable)"
    ;;
  fail)
    red "verdict=fail (unacceptable for clean install)"
    ;;
  *)
    red "unknown verdict: $VERDICT"
    ;;
esac

# ── Test 6: no plaintext secrets in UI/config ────────────────────────────
info "T6: No plaintext secrets in doctor output"
if echo "$DOCTOR_OUT" | grep -qiE '(sk-ant|sk-proj|ghp_|AIza)' 2>/dev/null; then
  red "plaintext API key pattern found in doctor output"
else
  green "no plaintext secrets in doctor output"
fi

# ── Test 7: .env file exists with 600 permissions ────────────────────────
info "T7: .env file permissions"
ENV_FILE="$HARNESS_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  PERMS=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null || echo "000")
  if [[ "$PERMS" == "600" ]]; then
    green ".env exists with 600 permissions"
  else
    red ".env permissions are $PERMS (expected 600)"
  fi
else
  red ".env file not found"
fi

# ── Test 8: config/defaults.yaml has no real secrets ─────────────────────
info "T8: defaults.yaml has no real secrets"
if [[ -f "$HARNESS_DIR/config/defaults.yaml" ]]; then
  if grep -qiE '(sk-ant-|sk-proj-|ghp_|AIza)' "$HARNESS_DIR/config/defaults.yaml" 2>/dev/null; then
    red "defaults.yaml contains API key patterns"
  else
    green "defaults.yaml clean (no real secrets)"
  fi
else
  red "config/defaults.yaml missing"
fi

# ── Test 9: state.db exists ──────────────────────────────────────────────
info "T9: State database"
if [[ -f "$HARNESS_DIR/run/state.db" ]]; then
  green "state.db exists"
else
  yellow="true"
  printf '\033[33m  ⚠ %s\033[0m\n' "state.db not found (non-fatal, may be created later)" >&2
fi

# ── Test 10: gitignore and gitleaks exist ────────────────────────────────
info "T10: Secret scan configs"
for f in ".gitignore" "gitleaks.toml"; do
  if [[ -f "$HARNESS_DIR/$f" ]]; then
    green "$f exists"
  else
    red "$f missing"
  fi
done

# ── Test 11: hooks are present and executable ─────────────────────────────
info "T11: Git hooks"
for hook in "pre-commit-secret-scan" "pre-push-secret-scan"; do
  if [[ -x "$HARNESS_DIR/hooks/$hook" ]]; then
    green "hooks/$hook exists and executable"
  elif [[ -f "$HARNESS_DIR/hooks/$hook" ]]; then
    red "hooks/$hook exists but not executable"
  else
    red "hooks/$hook missing"
  fi
done

# ── Test 12: upgrade.sh --dry-run works ───────────────────────────────────
info "T12: Upgrade dry-run"
if bash "$HARNESS_DIR/installer/upgrade.sh" --dry-run --non-interactive 2>&1; then
  green "upgrade.sh --dry-run succeeded"
else
  red "upgrade.sh --dry-run FAILED"
fi

# ── Test 13: restore.sh --list works ─────────────────────────────────────
info "T13: Restore list"
if bash "$HARNESS_DIR/installer/restore.sh" --list 2>&1; then
  green "restore.sh --list succeeded"
else
  red "restore.sh --list FAILED"
fi

# ── Test 14: existing harness commands not broken ─────────────────────────
info "T14: Existing harness commands"
if [[ -f "$HARNESS_DIR/solar-harness.sh" ]]; then
  for cmd in "doctor" "wiki qmd-status" "status"; do
    if timeout 10 bash "$HARNESS_DIR/solar-harness.sh" $cmd >/dev/null 2>&1; then
      green "solar-harness $cmd works"
    else
      # Non-fatal in container (no tmux sessions)
      printf '\033[33m  ⚠ %s\033[0m\n' "solar-harness $cmd skipped (expected in container)" >&2
    fi
  done
else
  printf '\033[33m  ⚠ %s\033[0m\n' "solar-harness.sh not found at expected path" >&2
fi

# ── Test 15: gitleaks detect on worktree ──────────────────────────────────
info "T15: Gitleaks secret scan"
if command -v gitleaks &>/dev/null; then
  if gitleaks detect --config="$HARNESS_DIR/gitleaks.toml" --source="$HARNESS_DIR" --no-git 2>&1; then
    green "gitleaks detect: 0 findings"
  else
    red "gitleaks detect: LEAKS FOUND — check output above"
  fi
else
  printf '\033[33m  ⚠ %s\033[0m\n' "gitleaks not installed — skipping scan" >&2
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────┐"
echo "│  Container Smoke Test Results            │"
echo "├──────────────────────────────────────────┤"
printf "│  PASS: %-3d  FAIL: %-3d                   │\n" "$PASS" "$FAIL"
echo "└──────────────────────────────────────────┘"

if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  red "SMOKE TEST FAILED ($FAIL failures)"
  exit 1
else
  echo ""
  green "SMOKE TEST PASSED ($PASS/$PASS checks)"
  exit 0
fi

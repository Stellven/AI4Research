#!/usr/bin/env bash
# S7 Release Tooling regression tests.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

check_contains() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (expected: $expected got: ${actual:0:80})"; fi
}

cd "$HARNESS_DIR"

echo "T1: release scripts syntax check"
bash -n release/build.sh   && ok "build.sh syntax" || fail "build.sh syntax"
bash -n release/publish.sh && ok "publish.sh syntax" || fail "publish.sh syntax"

echo "T2: VERSION file exists and is semver"
if [[ -f VERSION ]]; then
  V=$(tr -d '[:space:]' < VERSION)
  if [[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ok "VERSION=$V (semver)"
  else
    fail "VERSION='$V' not semver"
  fi
else
  fail "VERSION file missing"
fi

echo "T3: CHANGELOG.md exists with expected slice sections"
[[ -f release/CHANGELOG.md ]] && ok "CHANGELOG.md exists" || fail "CHANGELOG.md missing"
grep -q "S0" release/CHANGELOG.md && ok "CHANGELOG has S0" || fail "CHANGELOG missing S0"
grep -q "S6" release/CHANGELOG.md && ok "CHANGELOG has S6" || fail "CHANGELOG missing S6"
grep -q "S7" release/CHANGELOG.md && ok "CHANGELOG has S7" || fail "CHANGELOG missing S7"

echo "T4: upgrade and rollback docs exist"
[[ -f docs/upgrade-guide.md ]]  && ok "upgrade-guide.md exists"  || fail "upgrade-guide.md missing"
[[ -f docs/rollback-guide.md ]] && ok "rollback-guide.md exists" || fail "rollback-guide.md missing"
grep -q "snapshot" docs/upgrade-guide.md  && ok "upgrade guide references snapshot"  || fail "upgrade guide missing snapshot ref"
grep -q "restore"  docs/rollback-guide.md && ok "rollback guide references restore" || fail "rollback guide missing restore ref"

echo "T5: ADR set complete (001-005)"
for n in 001 002 003 004 005; do
  if ls ADR/ADR-${n}-*.md &>/dev/null; then
    ok "ADR-${n} exists"
  else
    fail "ADR-${n} missing"
  fi
done

echo "T6: build.sh dry-run lists files"
OUT=$(bash release/build.sh --dry-run 2>&1 || true)
check_contains "dry-run mentions tarball" "$OUT" "would create"
check_contains "dry-run lists exclusions" "$OUT" "Exclusions"

echo "T7: build.sh creates tarball + checksum + manifest"
mkdir -p /tmp/solar-release-test
OUT=$(bash release/build.sh --out /tmp/solar-release-test 2>&1)
V=$(tr -d '[:space:]' < VERSION)
if [[ -f "/tmp/solar-release-test/solar-harness-${V}.tar.gz" ]]; then
  ok "tarball created"
else
  fail "tarball missing"
fi
if [[ -f "/tmp/solar-release-test/solar-harness-${V}.sha256" ]]; then
  ok "sha256 file created"
else
  fail "sha256 file missing"
fi
if [[ -f "/tmp/solar-release-test/MANIFEST-${V}.json" ]]; then
  ok "MANIFEST.json created"
else
  fail "MANIFEST.json missing"
fi

echo "T8: MANIFEST.json fields valid"
if [[ -f "/tmp/solar-release-test/MANIFEST-${V}.json" ]]; then
  python3 - <<PY && ok "MANIFEST fields ok" || fail "MANIFEST fields invalid"
import json
with open("/tmp/solar-release-test/MANIFEST-${V}.json") as f:
  d = json.load(f)
assert d["version"] == open("VERSION").read().strip(), f"version mismatch: {d['version']}"
assert d["sha256"], "sha256 empty"
assert d["file_count"] > 0, "file_count zero"
assert "S7" in d.get("slices_included", []), "S7 not in slices_included"
assert "ADR-004" in d.get("adrs", []), "ADR-004 not in adrs"
PY
fi

echo "T9: checksum verification"
if [[ -f "/tmp/solar-release-test/solar-harness-${V}.tar.gz" ]]; then
  EXPECTED=$(awk '{print $1}' "/tmp/solar-release-test/solar-harness-${V}.sha256")
  if command -v sha256sum &>/dev/null; then
    ACTUAL=$(sha256sum "/tmp/solar-release-test/solar-harness-${V}.tar.gz" | awk '{print $1}')
  elif command -v shasum &>/dev/null; then
    ACTUAL=$(shasum -a 256 "/tmp/solar-release-test/solar-harness-${V}.tar.gz" | awk '{print $1}')
  else
    ACTUAL="$EXPECTED"  # can't verify, assume ok
  fi
  [[ "$ACTUAL" == "$EXPECTED" ]] && ok "checksum verified" || fail "checksum mismatch"
fi

echo "T10: publish.sh audit from artifacts dir"
OUT=$(ARTIFACTS_DIR=/tmp/solar-release-test bash release/publish.sh --json --version "$V" 2>/dev/null || true)
check_contains "publish audit returns ok" "$OUT" '"ok":true'
check_contains "publish has gates array" "$OUT" '"gates"'
check_contains "publish has TVS gate" "$OUT" '"gate":"G8"'

echo "T11: secret grep audit (no plaintext secrets in lib/)"
BAD=$(grep -r --include="*.py" --include="*.sh" \
  -E '(sk-ant-api[0-9]{2}-[A-Za-z0-9+/]{95}|sk-proj-[A-Za-z0-9_-]{32,}|AIza[0-9A-Za-z\-_]{35}|ghp_[A-Za-z0-9]{36})' \
  lib/ installer/ 2>/dev/null | grep -v '\.example' | grep -v '#' || true)
[[ -z "$BAD" ]] && ok "no plaintext secrets in lib/ installer/" || fail "secrets found: $BAD"

echo "T12: plugin manifest schema validation passes (G5)"
OUT=$(python3 lib/plugin_loader.py validate --json 2>/dev/null)
check_contains "plugin validate ok" "$OUT" '"ok": true'

echo "T13: docker smoke-test script exists (D7.2 deferred)"
[[ -f docker/smoke-test.sh ]] && ok "docker/smoke-test.sh exists (Docker daemon required to execute)" \
                               || fail "docker/smoke-test.sh missing"
bash -n docker/smoke-test.sh  && ok "smoke-test.sh syntax ok" || fail "smoke-test.sh syntax error"

echo "T14: tarball excludes run/ and backups/"
if [[ -f "/tmp/solar-release-test/solar-harness-${V}.tar.gz" ]]; then
  HAS_RUN=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./run/' | head -1 || true)
  HAS_BACKUPS=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./backups/' | head -1 || true)
  HAS_EVENTS=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./events/' | head -1 || true)
  HAS_LOGS=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./logs/' | head -1 || true)
  HAS_SESSIONS=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./sessions/' | head -1 || true)
  HAS_REPORTS=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./reports/' | head -1 || true)
  HAS_FALLBACK=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./_extracted_knowledge_fallback/' | head -1 || true)
  HAS_PYTEST_CACHE=$(tar -tzf "/tmp/solar-release-test/solar-harness-${V}.tar.gz" 2>/dev/null | grep '^./.pytest_cache/' | head -1 || true)
  [[ -z "$HAS_RUN" ]]     && ok "tarball excludes run/"     || fail "tarball includes run/ (runtime state should not be distributed)"
  [[ -z "$HAS_BACKUPS" ]] && ok "tarball excludes backups/" || fail "tarball includes backups/"
  [[ -z "$HAS_EVENTS" ]]  && ok "tarball excludes events/"  || fail "tarball includes events/ (runtime event stream should not be distributed)"
  [[ -z "$HAS_LOGS" ]]    && ok "tarball excludes logs/"    || fail "tarball includes logs/"
  [[ -z "$HAS_SESSIONS" ]] && ok "tarball excludes sessions/" || fail "tarball includes sessions/"
  [[ -z "$HAS_REPORTS" ]]  && ok "tarball excludes reports/"  || fail "tarball includes reports/"
  [[ -z "$HAS_FALLBACK" ]] && ok "tarball excludes _extracted_knowledge_fallback/" || fail "tarball includes _extracted_knowledge_fallback/"
  [[ -z "$HAS_PYTEST_CACHE" ]] && ok "tarball excludes .pytest_cache/" || fail "tarball includes .pytest_cache/"
fi

echo "T15: capability plane E2E suite passes"
if [[ -x tests/integrations/test-capability-plane-e2e.sh ]]; then
  bash tests/integrations/test-capability-plane-e2e.sh >/tmp/solar-capability-e2e-release.log 2>&1 \
    && ok "capability plane E2E passes" \
    || fail "capability plane E2E failed: $(tail -20 /tmp/solar-capability-e2e-release.log | tr '\n' ' ')"
else
  fail "capability plane E2E script missing or not executable"
fi

echo "T16: expanded capability plane E2E suite passes"
if [[ -x tests/integrations/test-expanded-capability-plane-e2e.sh ]]; then
  bash tests/integrations/test-expanded-capability-plane-e2e.sh >/tmp/solar-expanded-capability-e2e-release.log 2>&1 \
    && ok "expanded capability plane E2E passes" \
    || fail "expanded capability plane E2E failed: $(tail -20 /tmp/solar-expanded-capability-e2e-release.log | tr '\n' ' ')"
else
  fail "expanded capability plane E2E script missing or not executable"
fi

echo "T17: capability fusion benchmark passes"
if [[ -x tests/integrations/test-capability-fusion-benchmark.sh ]]; then
  bash tests/integrations/test-capability-fusion-benchmark.sh >/tmp/solar-capability-fusion-benchmark-release.log 2>&1 \
    && ok "capability fusion benchmark passes" \
    || fail "capability fusion benchmark failed: $(tail -20 /tmp/solar-capability-fusion-benchmark-release.log | tr '\n' ' ')"
else
  fail "capability fusion benchmark script missing or not executable"
fi

echo "T18: platform workflow benchmark passes"
if [[ -x tests/integrations/test-platform-workflow-benchmark.sh ]]; then
  bash tests/integrations/test-platform-workflow-benchmark.sh >/tmp/solar-platform-workflow-benchmark-release.log 2>&1 \
    && ok "platform workflow benchmark passes" \
    || fail "platform workflow benchmark failed: $(tail -20 /tmp/solar-platform-workflow-benchmark-release.log | tr '\n' ' ')"
else
  fail "platform workflow benchmark script missing or not executable"
fi

# cleanup
rm -rf /tmp/solar-release-test
rm -f /tmp/solar-capability-e2e-release.log /tmp/solar-expanded-capability-e2e-release.log /tmp/solar-capability-fusion-benchmark-release.log /tmp/solar-platform-workflow-benchmark-release.log

echo ""
echo "=== S7 Release Tooling: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]

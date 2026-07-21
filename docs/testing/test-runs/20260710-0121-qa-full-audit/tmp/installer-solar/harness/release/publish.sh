#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform — Pre-Publish Audit
#
# Runs all release gates before marking an artifact as publish-ready.
# Does NOT push to any external registry — it is a local audit gate only.
#
# Usage:
#   release/publish.sh                          # audit latest artifact
#   release/publish.sh --version 1.0.0          # audit specific version
#   release/publish.sh --json                    # machine-readable output
#
# Gates:
#   G1: VERSION file present and semver-valid
#   G2: tarball + sha256 + manifest exist
#   G3: SHA256 checksum matches tarball
#   G4: gitleaks scan passes (or gitleaks not installed → warn)
#   G5: plugin manifest schema validation passes
#   G6: python3 lib/ compile check
#   G7: CHANGELOG.md has current version entry
#   G8: TVS renderer bridge + Bun + TVS root + smoke pass
# ============================================================================
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$HARNESS_DIR/release/artifacts}"

AS_JSON=0
VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)    AS_JSON=1; shift ;;
    --version) VERSION="$2"; shift 2 ;;
    --help|-h)
      cat <<'EOF'
Solar Harness Release Audit

Usage:
  release/publish.sh [--json] [--version VERSION]

Required TVS environment:
  bun              JavaScript runtime for TVS smoke checks
  SOLAR_TVS_ROOT   TVS checkout path containing index.ts

Gates:
  G1 VERSION semver
  G2 tarball + sha256 + manifest present
  G3 SHA256 matches
  G4 secret scan
  G5 plugin manifests validate
  G6 python compile
  G7 CHANGELOG entry
  G8 TVS renderer bridge + Bun + TVS root + smoke pass
EOF
      exit 0
      ;;
    *) printf '[publish] unknown arg: %s\n' "$1" >&2; exit 1 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  VERSION=$(tr -d '[:space:]' < "$HARNESS_DIR/VERSION" 2>/dev/null || echo "")
fi
[[ -z "$VERSION" ]] && { printf '[publish] ERROR: no VERSION\n' >&2; exit 1; }

TARBALL="$ARTIFACTS_DIR/solar-harness-${VERSION}.tar.gz"
CHECKSUM_FILE="$ARTIFACTS_DIR/solar-harness-${VERSION}.sha256"
MANIFEST="$ARTIFACTS_DIR/MANIFEST-${VERSION}.json"

PASS=0
FAIL=0
WARN=0
declare -a RESULTS=()

record() {
  local gate="$1" status="$2" msg="$3"
  RESULTS+=("{\"gate\":\"$gate\",\"status\":\"$status\",\"msg\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$msg")}")
  case "$status" in
    pass) PASS=$((PASS+1)) ;;
    fail) FAIL=$((FAIL+1)) ;;
    warn) WARN=$((WARN+1)) ;;
  esac
}

cd "$HARNESS_DIR"

# G1: VERSION valid
if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  record G1 pass "VERSION=$VERSION (semver ok)"
else
  record G1 fail "VERSION='$VERSION' not semver"
fi

# G2: artifacts exist
if [[ -f "$TARBALL" && -f "$CHECKSUM_FILE" && -f "$MANIFEST" ]]; then
  record G2 pass "tarball + sha256 + manifest present"
else
  MISSING=""
  [[ -f "$TARBALL" ]]       || MISSING="$MISSING tarball"
  [[ -f "$CHECKSUM_FILE" ]] || MISSING="$MISSING sha256"
  [[ -f "$MANIFEST" ]]      || MISSING="$MANIFEST manifest"
  record G2 fail "missing:$MISSING"
fi

# G3: checksum matches (only if tarball exists)
if [[ -f "$TARBALL" && -f "$CHECKSUM_FILE" ]]; then
  EXPECTED=$(awk '{print $1}' "$CHECKSUM_FILE")
  if command -v sha256sum &>/dev/null; then
    ACTUAL=$(sha256sum "$TARBALL" | awk '{print $1}')
  elif command -v shasum &>/dev/null; then
    ACTUAL=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
  else
    ACTUAL=""
  fi
  if [[ -n "$ACTUAL" && "$ACTUAL" == "$EXPECTED" ]]; then
    record G3 pass "SHA256 matches"
  elif [[ -z "$ACTUAL" ]]; then
    record G3 warn "sha256sum/shasum not available, skipping checksum verify"
  else
    record G3 fail "SHA256 mismatch: expected=$EXPECTED actual=$ACTUAL"
  fi
else
  record G3 warn "tarball or checksum file missing, skipped"
fi

# G4: gitleaks
if command -v gitleaks &>/dev/null; then
  if gitleaks detect --config="$HARNESS_DIR/gitleaks.toml" --source="$HARNESS_DIR" --no-git 2>/dev/null; then
    record G4 pass "gitleaks: 0 secrets found"
  else
    record G4 fail "gitleaks: secrets detected — STOP"
  fi
else
  # Fallback: grep for common secret patterns in lib/
  BAD=$(grep -r --include="*.py" --include="*.sh" \
    -E '(sk-ant-api|sk-proj-|AIza[A-Za-z0-9]{35}|ghp_[A-Za-z0-9]{36})' \
    lib/ installer/ 2>/dev/null | grep -v '\.example' | grep -v '#' || true)
  if [[ -z "$BAD" ]]; then
    record G4 warn "gitleaks not installed; fallback grep found 0 secrets"
  else
    record G4 fail "gitleaks not installed; fallback grep found secrets: $BAD"
  fi
fi

# G5: plugin manifest schema validation
PL_OUT=$(python3 lib/plugin_loader.py validate --json 2>/dev/null || true)
if echo "$PL_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)" 2>/dev/null; then
  record G5 pass "plugin manifests schema-valid"
else
  record G5 fail "plugin manifest validation failed: $PL_OUT"
fi

# G6: python compile
COMPILE_FAIL=""
for f in lib/*.py; do
  python3 -m py_compile "$f" 2>/dev/null || COMPILE_FAIL="$COMPILE_FAIL $f"
done
if [[ -z "$COMPILE_FAIL" ]]; then
  record G6 pass "all lib/*.py compile clean"
else
  record G6 fail "compile errors:$COMPILE_FAIL"
fi

# G7: CHANGELOG has current version
if grep -q "^## v${VERSION}" release/CHANGELOG.md 2>/dev/null; then
  record G7 pass "CHANGELOG.md has v${VERSION} entry"
else
  record G7 fail "CHANGELOG.md missing v${VERSION} entry"
fi

# G8: TVS renderer bridge and smoke
if [[ ! -f "lib/tvs_render_cli.ts" ]]; then
  record G8 fail "TVS renderer bridge missing: lib/tvs_render_cli.ts"
elif [[ ! -f "solar-harness.sh" ]]; then
  record G8 fail "solar-harness.sh missing; cannot validate TVS entrypoint"
elif ! command -v bun &>/dev/null; then
  record G8 fail "bun not installed; TVS renderer is a required release dependency"
else
  TVS_ROOT_CANDIDATE="${SOLAR_TVS_ROOT:-}"
  if [[ -z "$TVS_ROOT_CANDIDATE" ]]; then
    for d in "$HARNESS_DIR/../../TVS" "$HOME/TVS" "$HOME/Solar/../TVS"; do
      if [[ -f "$d/index.ts" ]]; then
        TVS_ROOT_CANDIDATE="$(cd "$d" && pwd)"
        break
      fi
    done
  fi
  if [[ -z "$TVS_ROOT_CANDIDATE" || ! -f "$TVS_ROOT_CANDIDATE/index.ts" ]]; then
    record G8 fail "TVS root not found; set SOLAR_TVS_ROOT to a checkout containing index.ts"
  else
    TVS_OUT=$(SOLAR_TVS_ROOT="$TVS_ROOT_CANDIDATE" HARNESS_DIR="$HARNESS_DIR" bash "$HARNESS_DIR/solar-harness.sh" tvs render --width 44 --colors off <<'JSON' 2>/dev/null || true
{"canvas":{"width":44},"style":"solar_default","root":{"type":"card","header":"TVS Publish","sections":[{"type":"kv","items":[{"key":"Status","value":"ok"}]}]}}
JSON
)
    if [[ "$TVS_OUT" == *"TVS Publish"* && "$TVS_OUT" == *"Powered by TVS"* ]]; then
      record G8 pass "TVS renderer entrypoint smoke passed"
    else
      record G8 fail "TVS renderer entrypoint smoke did not produce expected output"
    fi
  fi
fi

# ── output ──────────────────────────────────────────────────────────────────
OK=$([[ $FAIL -eq 0 ]] && echo true || echo false)

if [[ $AS_JSON -eq 1 ]]; then
  printf '{"ok":%s,"version":"%s","pass":%d,"fail":%d,"warn":%d,"gates":[%s]}\n' \
    "$OK" "$VERSION" "$PASS" "$FAIL" "$WARN" "$(IFS=,; echo "${RESULTS[*]}")"
else
  printf '\n[publish] Release Audit — solar-harness v%s\n' "$VERSION"
  printf '  PASS=%d  FAIL=%d  WARN=%d\n' "$PASS" "$FAIL" "$WARN"
  [[ $OK == true ]] && printf '  ✅ AUDIT PASS — artifact is publish-ready\n' \
                    || printf '  ❌ AUDIT FAIL — do not publish\n'
fi

[[ $FAIL -eq 0 ]]

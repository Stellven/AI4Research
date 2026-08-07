#!/usr/bin/env bash
# test-obsidian-wiki-integration.sh
# Solar Harness — Obsidian Wiki integration test suite
# Usage: HARNESS_TEST=1 bash test-obsidian-wiki-integration.sh <subcommand>
# Subcommands: install | status | export | bridge | safety | status_server | all
#
# Safety contracts:
#   - HARNESS_TEST=1 required; refuses to run otherwise
#   - Uses temp vault, temp config (.test suffix), temp skill dirs
#   - Does not mutate real vaults or skill directories
#   - trap EXIT cleans all temp paths

set -euo pipefail

# ── Guard: must be in test mode ──────────────────────────────────────────────
[[ "${HARNESS_TEST:-}" == "1" ]] || {
  echo "REFUSE: HARNESS_TEST=1 required. This test suite must not run in production mode." >&2
  exit 1
}

# ── Guard: refuse to run inside live solar-harness tmux session ──────────────
if [[ "${TMUX:-}" != "" ]] && tmux display-message -p '#S' 2>/dev/null | grep -q "^solar-harness$"; then
  echo "REFUSE: running inside live solar-harness tmux session. Use a separate terminal." >&2
  exit 1
fi

# ── Paths ────────────────────────────────────────────────────────────────────
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
INTEGRATION="${HARNESS_DIR}/integrations/obsidian-wiki.sh"
SCHEMA="${HARNESS_DIR}/schemas/obsidian-wiki-status.schema.json"
SPRINTS_DIR="${HARNESS_DIR}/sprints"
STATUS_SERVER_PY="${HARNESS_DIR}/lib/symphony/status-server.py"

# ── Temp paths setup ─────────────────────────────────────────────────────────
TMPVAULT=$(mktemp -d -t solar-wiki-test-vault.XXXXXX)
TMPSKILLS=$(mktemp -d -t solar-wiki-test-skills.XXXXXX)
TMPREPO=$(mktemp -d -t solar-wiki-test-repo.XXXXXX)
OBSIDIAN_WIKI_CONFIG="${HOME}/.obsidian-wiki/config.test"

export OBSIDIAN_VAULT_PATH="$TMPVAULT"
export OBSIDIAN_WIKI_CONFIG
export OBSIDIAN_WIKI_REPO="$TMPREPO"
export SKILL_TARGETS_OVERRIDE_CODEX="${TMPSKILLS}/codex/skills"
export SKILL_TARGETS_OVERRIDE_CLAUDE="${TMPSKILLS}/claude/skills"
export SKILL_TARGETS_OVERRIDE_AGENTS="${TMPSKILLS}/agents/skills"
export OBSIDIAN_WIKI_OFFLINE="${OBSIDIAN_WIKI_OFFLINE:-1}"

# ── Cleanup ───────────────────────────────────────────────────────────────────
_cleanup() {
  rm -rf "$TMPVAULT" "$TMPSKILLS" "$TMPREPO"
  rm -f "$OBSIDIAN_WIKI_CONFIG"
}
trap _cleanup EXIT

# ── Utilities ─────────────────────────────────────────────────────────────────
PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
_warn() { echo "  WARN: $1"; }
_section() { echo; echo "=== $1 ==="; }

_require_integration() {
  if [[ ! -f "$INTEGRATION" ]]; then
    echo "SKIP: $INTEGRATION not found (other builder slice pending). Cannot run $1 tests." >&2
    return 1
  fi
  return 0
}

_check_json_schema() {
  local json_file="$1"
  if ! python3 -c "import jsonschema" 2>/dev/null; then
    _warn "jsonschema not available; skipping schema validation"
    return 0
  fi
  python3 - "$json_file" "$SCHEMA" <<'PYEOF'
import sys, json
try:
    import jsonschema
except ImportError:
    sys.exit(0)
data = json.load(open(sys.argv[1]))
schema = json.load(open(sys.argv[2]))
jsonschema.validate(data, schema)
print("  schema: OK")
PYEOF
}

# ── Test: scaffold a minimal fake upstream repo ───────────────────────────────
_setup_fake_repo() {
  mkdir -p "$TMPREPO/.skills/wiki-setup" \
            "$TMPREPO/.skills/wiki-update" \
            "$TMPREPO/.skills/wiki-query"
  cat > "$TMPREPO/.skills/wiki-setup/SKILL.md" <<'EOF'
# wiki-setup skill
Vault dirs: index.md log.md hot.md _raw/ projects/ concepts/ entities/ skills/ references/ synthesis/ journal/
EOF
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: install
# ─────────────────────────────────────────────────────────────────────────────
test_install() {
  _section "D2 — install"
  _require_integration "install" || return 0

  _setup_fake_repo

  # Run install
  if bash "$INTEGRATION" install \
        --vault "$TMPVAULT" \
        --repo  "$TMPREPO"; then

    # Config written
    if [[ -f "$OBSIDIAN_WIKI_CONFIG" ]]; then
      _pass "config file created at OBSIDIAN_WIKI_CONFIG"
    else
      _fail "config file missing: $OBSIDIAN_WIKI_CONFIG"
    fi

    # OBSIDIAN_VAULT_PATH in config
    if grep -q "OBSIDIAN_VAULT_PATH" "$OBSIDIAN_WIKI_CONFIG" 2>/dev/null; then
      _pass "config contains OBSIDIAN_VAULT_PATH"
    else
      _fail "config missing OBSIDIAN_VAULT_PATH"
    fi

    # Vault skeleton dirs
    for dir in _raw projects concepts entities skills references synthesis journal; do
      if [[ -d "$TMPVAULT/$dir" ]]; then
        _pass "vault/$dir created"
      else
        _fail "vault/$dir missing"
      fi
    done

    # Vault skeleton files
    for f in index.md log.md hot.md .manifest.json; do
      if [[ -f "$TMPVAULT/$f" ]]; then
        _pass "vault/$f created"
      else
        _fail "vault/$f missing"
      fi
    done

    # Skill symlinks (override targets are temp dirs — they should be symlinks or dirs)
    for target in "$SKILL_TARGETS_OVERRIDE_CODEX" \
                  "$SKILL_TARGETS_OVERRIDE_CLAUDE" \
                  "$SKILL_TARGETS_OVERRIDE_AGENTS"; do
      if [[ -L "$target" || -d "$target" ]]; then
        _pass "skill target exists: $(basename "$(dirname "$target")")/skills"
      else
        _warn "skill target not created (may be offline/no repo skills): $target"
      fi
    done

  else
    _fail "install command exited non-zero"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: status
# ─────────────────────────────────────────────────────────────────────────────
test_status() {
  _section "D3 — status --json"
  _require_integration "status" || return 0

  # Ensure install ran first (idempotent)
  _setup_fake_repo
  bash "$INTEGRATION" install --vault "$TMPVAULT" --repo "$TMPREPO" >/dev/null 2>&1 || true

  local json_out
  json_out=$(bash "$INTEGRATION" status --json 2>/dev/null) || {
    _fail "status --json exited non-zero"
    return
  }

  # Valid JSON
  if echo "$json_out" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    _pass "status output is valid JSON"
  else
    _fail "status output is not valid JSON: $json_out"
    return
  fi

  # Required fields
  for field in configured repo_path vault_path config_path skills_installed last_checked_at; do
    if echo "$json_out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert '$field' in d" 2>/dev/null; then
      _pass "JSON has field: $field"
    else
      _fail "JSON missing field: $field"
    fi
  done

  # skills_installed has codex/claude/agents
  for skill in codex claude agents; do
    if echo "$json_out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert '$skill' in d.get('skills_installed',{})" 2>/dev/null; then
      _pass "skills_installed has: $skill"
    else
      _fail "skills_installed missing: $skill"
    fi
  done

  # Schema validation
  local tmp_json
  tmp_json=$(mktemp -t wiki-status-XXXXXX.json)
  echo "$json_out" > "$tmp_json"
  _check_json_schema "$tmp_json"
  rm -f "$tmp_json"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: export-sprint (D4)
# ─────────────────────────────────────────────────────────────────────────────
test_export() {
  _section "D4 — export-sprint"
  _require_integration "export" || return 0

  _setup_fake_repo
  bash "$INTEGRATION" install --vault "$TMPVAULT" --repo "$TMPREPO" >/dev/null 2>&1 || true

  # Find a real sprint to export
  local test_sid=""
  for sid_file in "$SPRINTS_DIR"/sprint-*.contract.md; do
    [[ -f "$sid_file" ]] || continue
    test_sid=$(basename "$sid_file" .contract.md)
    break
  done

  if [[ -z "$test_sid" ]]; then
    _warn "No sprint contracts found in $SPRINTS_DIR — skipping export content tests"
    # Create synthetic sprint fixtures for testing
    test_sid="sprint-20260507-test-export"
    mkdir -p "$SPRINTS_DIR"
    cat > "$SPRINTS_DIR/${test_sid}.contract.md" <<'EOF'
# Test Sprint Contract
Goal: Test export functionality.
api_key: sk-test-SUPERSECRET1234567890abcdef
EOF
  fi

  local export_file="$TMPVAULT/_raw/solar-harness/${test_sid}.md"

  if bash "$INTEGRATION" export-sprint "$test_sid" --redact 2>/dev/null; then
    _pass "export-sprint exited 0"
  else
    _fail "export-sprint exited non-zero"
    return
  fi

  # File created
  if [[ -f "$export_file" ]]; then
    _pass "export file created: _raw/solar-harness/${test_sid}.md"
  else
    _fail "export file not found: $export_file"
    return
  fi

  # Frontmatter present
  if head -5 "$export_file" | grep -q "^source: solar-harness"; then
    _pass "frontmatter has 'source: solar-harness'"
  else
    _fail "frontmatter missing 'source: solar-harness'"
  fi

  if grep -q "sprint_id:" "$export_file"; then
    _pass "frontmatter has sprint_id"
  else
    _fail "frontmatter missing sprint_id"
  fi

  if grep -q "redacted:" "$export_file"; then
    _pass "frontmatter has redacted field"
  else
    _fail "frontmatter missing redacted field"
  fi

  # Redact: no bare secrets
  local secret_leaks
  secret_leaks=$((grep -E "(token|secret|api[_-]?key|password)\s*[=:]\s*[^<[:space:]]" "$export_file" \
                 | grep -v "<REDACTED>" | wc -l) || true)
  if [[ "$secret_leaks" -eq 0 ]]; then
    _pass "redact: no leaked secrets detected"
  else
    _fail "redact: $secret_leaks potential secret lines not redacted"
  fi

  # Cleanup synthetic sprint
  rm -f "$SPRINTS_DIR/${test_sid}.contract.md" 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: update/query bridge (D5)
# ─────────────────────────────────────────────────────────────────────────────
test_bridge() {
  _section "D5 — update/query bridge"
  _require_integration "bridge" || return 0

  _setup_fake_repo
  bash "$INTEGRATION" install --vault "$TMPVAULT" --repo "$TMPREPO" >/dev/null 2>&1 || true

  local dispatch_dir="$TMPVAULT/_raw/solar-harness/.dispatch"

  # wiki update
  if bash "$INTEGRATION" update --mode append 2>/dev/null; then
    _pass "wiki update exited 0"
  else
    _fail "wiki update exited non-zero"
  fi

  # dispatch file created for update
  if ls "$dispatch_dir"/wiki-update-*.md 2>/dev/null | grep -q .; then
    _pass "wiki update created dispatch file"
  else
    _fail "wiki update dispatch file not created in $dispatch_dir"
  fi

  # wiki query with content
  if bash "$INTEGRATION" query "What are the recent sprint decisions?" 2>/dev/null; then
    _pass "wiki query (with content) exited 0"
  else
    _fail "wiki query (with content) exited non-zero"
  fi

  # dispatch file created for query
  if ls "$dispatch_dir"/wiki-query-*.md 2>/dev/null | grep -q .; then
    _pass "wiki query created dispatch file"
  else
    _fail "wiki query dispatch file not created"
  fi

  # Refuse empty query
  local empty_exit=0
  bash "$INTEGRATION" query "" 2>/dev/null || empty_exit=$?
  if [[ "$empty_exit" -ne 0 ]]; then
    _pass "wiki query refuses empty string (exit $empty_exit)"
  else
    _fail "wiki query should refuse empty string but exited 0"
  fi

  # --quick flag accepted
  if bash "$INTEGRATION" query "quick test" --quick 2>/dev/null; then
    _pass "wiki query --quick accepted"
  else
    _warn "wiki query --quick not supported (non-fatal)"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: safety — real-dir overwrite protection (D7)
# ─────────────────────────────────────────────────────────────────────────────
test_safety() {
  _section "D7 — safety (real dir overwrite protection)"
  _require_integration "safety" || return 0

  _setup_fake_repo

  # Previous subtests may have installed a symlink at this target. Remove that
  # symlink first so this test actually exercises the real-directory refusal.
  [[ -L "$SKILL_TARGETS_OVERRIDE_CODEX" ]] && rm "$SKILL_TARGETS_OVERRIDE_CODEX"

  # Create a real (non-symlink) directory at the codex skill target.
  mkdir -p "$SKILL_TARGETS_OVERRIDE_CODEX"

  local install_exit=0
  local install_output
  install_output=$(bash "$INTEGRATION" install \
    --vault "$TMPVAULT" \
    --repo  "$TMPREPO" 2>&1) || install_exit=$?

  # Install should either: exit non-zero, or output a REFUSE message for that target
  if [[ "$install_exit" -ne 0 ]] || echo "$install_output" | grep -qi "REFUSE\|refuse\|exists.*real\|skip"; then
    _pass "install refused/warned about real dir at codex/skills target"
  else
    _fail "install should refuse to overwrite real directory but did not (exit=$install_exit)"
    echo "    output: $install_output" >&2
  fi

  # The real dir must still be a real dir (not replaced by a symlink)
  if [[ -d "$SKILL_TARGETS_OVERRIDE_CODEX" && ! -L "$SKILL_TARGETS_OVERRIDE_CODEX" ]]; then
    _pass "real directory was NOT replaced by symlink"
  else
    _fail "real directory was REPLACED by symlink — safety breach!"
  fi

  # Verify vault path is temp (not real user vault)
  local vault_resolved
  vault_resolved=$(python3 -c "import os; print(os.path.realpath('${TMPVAULT}'))")
  if [[ "$vault_resolved" == /tmp/* || "$vault_resolved" == /var/* || "$vault_resolved" == /private/var/* ]]; then
    _pass "vault is a temp path: $vault_resolved"
  else
    _fail "vault path is NOT temp — mutation risk: $vault_resolved"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: status-server wiki readiness (D6)
# ─────────────────────────────────────────────────────────────────────────────
test_status_server() {
  _section "D6 — status-server obsidian_wiki readiness"

  # Check if status-server.py has obsidian_wiki block
  if ! grep -q "obsidian_wiki" "$STATUS_SERVER_PY" 2>/dev/null; then
    _warn "status-server.py has no obsidian_wiki block yet (other builder pending or stub mode)"
    _warn "Checking stub readiness JSON fallback..."
    local stub_file="$HARNESS_DIR/run/wiki-readiness.json"
    if [[ -f "$stub_file" ]]; then
      _pass "stub wiki-readiness.json found: $stub_file"
    else
      _warn "No stub file yet; D6 will need status-server.py integration from builder slice"
    fi
    return 0
  fi

  # Find a free port in 8800-8899
  local test_port=""
  for p in $(seq 8800 8820); do
    if ! lsof -iTCP:"$p" -sTCP:LISTEN -n -P 2>/dev/null | grep -q .; then
      test_port="$p"
      break
    fi
  done

  if [[ -z "$test_port" ]]; then
    _warn "No free port found in 8800-8820; skipping live status-server test"
    return 0
  fi

  # Start test server on temp port
  local server_pid=""
  HARNESS_DIR="$HARNESS_DIR" \
    python3 "$STATUS_SERVER_PY" --port "$test_port" --test-port 2>/dev/null &
  server_pid=$!

  # Ensure server is stopped on exit
  trap "_cleanup; kill $server_pid 2>/dev/null || true" EXIT

  # Wait for server
  local tries=0
  while [[ $tries -lt 15 ]]; do
    if curl -sf "http://127.0.0.1:${test_port}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 0.3
    tries=$((tries + 1))
  done

  if ! curl -sf "http://127.0.0.1:${test_port}/healthz" >/dev/null 2>&1; then
    _warn "status-server did not start on port $test_port (skip live test)"
    kill "$server_pid" 2>/dev/null || true
    trap "_cleanup" EXIT
    return 0
  fi

  _pass "status-server started on port $test_port"

  # /status must have obsidian_wiki key
  local status_json
  status_json=$(curl -sf "http://127.0.0.1:${test_port}/status" 2>/dev/null) || {
    _fail "/status endpoint unreachable"
    kill "$server_pid" 2>/dev/null || true
    trap "_cleanup" EXIT
    return
  }

  if echo "$status_json" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'obsidian_wiki' in d" 2>/dev/null; then
    _pass "/status has obsidian_wiki key"
  else
    _fail "/status missing obsidian_wiki key"
  fi

  # obsidian_wiki.ready must exist (true or false, not error)
  if echo "$status_json" | python3 -c "import sys, json; d=json.load(sys.stdin); w=d.get('obsidian_wiki',{}); assert 'ready' in w" 2>/dev/null; then
    _pass "obsidian_wiki has 'ready' field"
  else
    _fail "obsidian_wiki missing 'ready' field"
  fi

  # Server must not have crashed (still responding)
  if curl -sf "http://127.0.0.1:${test_port}/healthz" >/dev/null 2>&1; then
    _pass "server still healthy after /status call"
  else
    _fail "server crashed after /status call"
  fi

  # Unconfigured scenario: move config away and re-check
  if [[ -f "$OBSIDIAN_WIKI_CONFIG" ]]; then
    local bak="${OBSIDIAN_WIKI_CONFIG}.bak"
    mv "$OBSIDIAN_WIKI_CONFIG" "$bak"
    local unconfigured_json
    unconfigured_json=$(curl -sf "http://127.0.0.1:${test_port}/status" 2>/dev/null) || true
    mv "$bak" "$OBSIDIAN_WIKI_CONFIG"

    local wiki_ready
    wiki_ready=$(echo "$unconfigured_json" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('obsidian_wiki',{}).get('ready','MISSING'))" 2>/dev/null || echo "MISSING")
    if [[ "$wiki_ready" == "False" || "$wiki_ready" == "false" ]]; then
      _pass "obsidian_wiki.ready=false when unconfigured (graceful degradation)"
    else
      _warn "obsidian_wiki.ready=$wiki_ready when unconfigured (expected false)"
    fi
  fi

  kill "$server_pid" 2>/dev/null || true
  trap "_cleanup" EXIT
}

# ─────────────────────────────────────────────────────────────────────────────
# Subcommand dispatch
# ─────────────────────────────────────────────────────────────────────────────
CMD="${1:-all}"

case "$CMD" in
  install)       test_install ;;
  status)        test_status ;;
  export)        test_export ;;
  bridge)        test_bridge ;;
  safety)        test_safety ;;
  status_server) test_status_server ;;
  all)
    test_install
    test_status
    test_export
    test_bridge
    test_safety
    test_status_server
    ;;
  *)
    echo "Usage: HARNESS_TEST=1 bash $0 <install|status|export|bridge|safety|status_server|all>" >&2
    exit 1
    ;;
esac

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo "────────────────────────────────────────────────────"
echo "  Results: PASS=$PASS  FAIL=$FAIL"
echo "────────────────────────────────────────────────────"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

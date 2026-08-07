#!/usr/bin/env bash
# S4 Extension Framework regression tests.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="${BIN:-$HOME/.solar/bin/solar-harness}"
PASS=0
FAIL=0
PROBE_PLUGIN="$HARNESS_DIR/plugins/s4_probe"

ok() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
check_contains() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (expected: $expected)"; fi
}

cleanup() {
  rm -rf "$PROBE_PLUGIN"
}
trap cleanup EXIT

cd "$HARNESS_DIR"

echo "T1: syntax and schema files"
python3 -m py_compile lib/plugin_loader.py lib/capability_registry.py lib/solar_mirage.py lib/external-integrations-health.py \
  && ok "python modules compile" || fail "python modules compile"
python3 - <<'PY' && ok "plugin/capability schemas parse" || fail "plugin/capability schemas parse"
import json
for path in ("schemas/plugin.schema.json", "schemas/capability.schema.json"):
    json.load(open(path))
PY

echo "T2: plugin manifests validate and declare safety metadata"
OUT=$(python3 lib/plugin_loader.py validate --json)
check_contains "validate ok" "$OUT" '"ok": true'
printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["checked"] >= 5, d["checked"]' \
  && ok "at least five manifests checked" || fail "manifest count < 5"
python3 - <<'PY' && ok "all manifests include commands/background/eval/rollback" || fail "manifest safety metadata missing"
import sys
sys.path.insert(0, "lib")
import plugin_loader
plugins = plugin_loader.load_all_plugins()
assert len(plugins) >= 5
for item in plugins:
    assert item.get("commands"), item["id"]
    assert item.get("background_safety"), item["id"]
    assert item.get("eval_packs"), item["id"]
    assert item.get("rollback"), item["id"]
PY

echo "T3: four-level integrations status"
OUT=$("$BIN" integrations plugins --json)
check_contains "plugin status ok" "$OUT" '"ok": true'
check_contains "closed_loop bucket" "$OUT" '"closed_loop"'
check_contains "default_usable bucket" "$OUT" '"default_usable"'
check_contains "basic_usable bucket" "$OUT" '"basic_usable"'
OUT=$("$BIN" integrations status --json --refresh)
check_contains "external status has integration_levels" "$OUT" '"integration_levels"'
check_contains "external status has dead_end" "$OUT" '"dead_end"'

echo "T4: capability registry persists to state DB"
OUT=$("$BIN" integrations sync-caps --json)
check_contains "sync ok" "$OUT" '"ok": true'
OUT=$("$BIN" integrations capabilities query vfs.search --json)
check_contains "vfs.search found" "$OUT" '"found": true'
check_contains "vfs.search provider mirage" "$OUT" '"provider": "mirage"'

echo "T5: scope guard allows declared writes and rejects overreach"
mkdir -p "$HARNESS_DIR/state/obsidian"
OUT=$(python3 lib/plugin_loader.py check-scope --plugin obsidian --path "$HARNESS_DIR/state/obsidian/test.json" --json)
check_contains "declared scope allowed" "$OUT" '"allowed": true'
set +e
DENY=$(python3 lib/plugin_loader.py check-scope --plugin obsidian --path "$HARNESS_DIR/solar-harness.sh" --json)
DENY_RC=$?
set -e
[[ $DENY_RC -ne 0 ]] && ok "overreach returns nonzero" || fail "overreach returns nonzero"
check_contains "overreach rejected" "$DENY" '"allowed": false'
check_contains "overreach alert" "$DENY" 'scope_violation_rejected'
grep -q '"event": "plugin.scope_violation"' "$HARNESS_DIR/events/all.jsonl" \
  && ok "scope violation event emitted" || fail "scope violation event missing"

echo "T6: install/disable/list CLI works on temporary candidate plugin"
mkdir -p "$PROBE_PLUGIN"
cat > "$PROBE_PLUGIN/manifest.yaml" <<'YAML'
---
id: s4_probe
name: "S4 Probe Plugin"
version: "1.0.0"
description: "Temporary plugin used by S4 tests."
status: candidate
write_scope:
  - "state/s4_probe"
read_scope:
  - "state/s4_probe"
capabilities:
  - "probe.s4"
commands:
  - "solar-harness integrations list"
background_safety:
  mode: none
  idle_only: false
  rate_limit: "none"
eval_packs:
  - "tests/plugins/test-s4-extension-framework.sh"
rollback:
  strategy: disable
  commands:
    - "solar-harness integrations disable s4_probe"
integration_level: basic_usable
entry: "noop"
events:
  - "probe.s4"
depends_on: []
tags:
  - "test"
YAML
OUT=$("$BIN" integrations list --json)
check_contains "probe appears in list" "$OUT" '"id": "s4_probe"'
OUT=$("$BIN" integrations install s4_probe --json)
check_contains "probe install ok" "$OUT" '"new_status": "enabled"'
OUT=$("$BIN" integrations disable s4_probe --json)
check_contains "probe disable ok" "$OUT" '"new_status": "disabled"'

echo "T7: Mirage mount contract matches S3/S4 required names"
OUT=$(python3 lib/solar_mirage.py mounts --json)
printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
paths = {m["path"] for m in d["mounts"]}
required = {"/knowledge", "/raw", "/sources", "/papers", "/qmd", "/solar-db", "/cortex", "/sprints", "/drive"}
missing = required - paths
assert not missing, missing
assert "/projects" not in paths, paths
assert "/solar" not in paths, paths
' && ok "required Mirage mounts present" || fail "required Mirage mounts missing"

echo ""
echo "=== S4 Extension Framework: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]

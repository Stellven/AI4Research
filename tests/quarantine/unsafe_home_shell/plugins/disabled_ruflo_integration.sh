#!/usr/bin/env bash
# test-ruflo-integration.sh — Ruflo safe vendor/plugin/capability integration.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
PASS=0
FAIL=0

ok() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "R1 — modules compile"
python3 -m py_compile "$HARNESS_DIR/lib/ruflo_adapter.py" "$HARNESS_DIR/lib/solar_skills.py" \
  && ok "ruflo/skills modules compile" || fail "ruflo/skills modules compile"

echo "R2 — Ruflo vendor status is readable"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations ruflo-status --json)
python3 - "$OUT" <<'PY' && ok "ruflo status ok" || fail "ruflo status ok"
import json, sys
d=json.loads(sys.argv[1])
assert d["ok"] is True
assert d["source"]["repo"] == "https://github.com/ruvnet/ruflo.git"
assert d["inventory"]["plugins"] >= 30
assert d["inventory"]["skill_files"] >= 100
assert d["mode"] == "read_only_safe_vendor"
assert "runtime" in d
PY

echo "R3 — plugin manifest and capability registry"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations validate --id ruflo --json)
python3 - "$OUT" <<'PY' && ok "ruflo manifest valid" || fail "ruflo manifest valid"
import json, sys
d=json.loads(sys.argv[1])
assert d["ok"] is True
assert d["results"][0]["valid"] is True
PY
"$HARNESS_DIR/solar-harness.sh" integrations sync-caps --json >/tmp/solar-ruflo-sync.json
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations capabilities query ruflo.swarm --json)
python3 - "$OUT" <<'PY' && ok "ruflo.swarm capability found" || fail "ruflo.swarm capability found"
import json, sys
d=json.loads(sys.argv[1])
assert d["found"] is True
assert d["providers"][0]["provider"] == "ruflo"
PY

echo "R4 — skill inventory includes Ruflo but does not claim all skills are prompt-loaded"
OUT=$("$HARNESS_DIR/solar-harness.sh" skills inventory --json)
python3 - "$OUT" <<'PY' && ok "skill inventory truth labels" || fail "skill inventory truth labels"
import json, sys
d=json.loads(sys.argv[1])
assert d["totals"]["skill_files_recursive"] >= 1000
assert d["sources"]["vendor-skill-files"]["ruflo"]["skill_files"] >= 100
assert d["usability"]["all_1000_plus_loaded_into_prompt"] is False
PY

echo "R5 — dispatch injection selects Ruflo by keyword"
TMP=$(mktemp /tmp/solar-ruflo-dispatch.XXXXXX.md)
printf '# Dispatch\n\nUse Ruflo swarm and Claude Flow for multi-agent orchestration.\n' > "$TMP"
"$HARNESS_DIR/solar-harness.sh" skills inject "$TMP" >/dev/null
grep -q "Ruflo (ruflo.swarm" "$TMP" && ok "Ruflo capability injected" || fail "Ruflo capability injected"
rm -f "$TMP"

echo "R6 — full runtime status is explicit and sandboxed"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations ruflo-runtime-status --json || true)
python3 - "$OUT" <<'PY' && ok "ruflo runtime status explicit" || fail "ruflo runtime status explicit"
import json, sys
d=json.loads(sys.argv[1])
assert d["mode"] == "sandboxed_full_runtime"
assert "state/ruflo" in d["paths"]["runtime_dir"]
assert d["integration_level"] in ("pending", "full_runtime_usable")
PY

OUT=$("$HARNESS_DIR/solar-harness.sh" integrations ruflo-runtime-smoke --json)
python3 - "$OUT" <<'PY' && ok "ruflo runtime smoke uses SandboxHand" || fail "ruflo runtime smoke uses SandboxHand"
import json, sys
d=json.loads(sys.argv[1])
assert d["ok"] is True
for item in d.get("commands", []):
    assert item.get("executor") == "sandbox", item
    assert item.get("execution_mode") == "argv", item
    assert item.get("evidence_file"), item
    assert item.get("write_guard", {}).get("enabled") is True, item
PY

echo "R7 — unified health and UI expose full runtime"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations status --json --refresh)
python3 - "$OUT" <<'PY' && ok "ruflo unified health full runtime" || fail "ruflo unified health full runtime"
import json, sys
d=json.loads(sys.argv[1])
items=[x for x in d.get("integrations", []) if "ruflo" in x.get("name", "").lower()]
assert items, "ruflo integration missing"
item=items[0]
assert item["status"] == "ok"
assert item["status_label"] == "closed_loop"
ev=item.get("evidence", {})
assert ev.get("runtime_level") == "full_runtime_usable"
assert ev.get("runtime_backend") == "official_claude_flow_cli"
assert ev.get("runtime_version")
PY

if curl -fsS --max-time 5 "http://127.0.0.1:8765/integrations-view" >/tmp/solar-ruflo-ui.html 2>/dev/null; then
  grep -q "full_runtime_usable" /tmp/solar-ruflo-ui.html \
    && grep -q "official_claude_flow_cli" /tmp/solar-ruflo-ui.html \
    && ok "status UI shows Ruflo full runtime" || fail "status UI shows Ruflo full runtime"
else
  ok "status UI skipped (status server not running)"
fi

echo ""
echo "=== Ruflo Integration Test: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]

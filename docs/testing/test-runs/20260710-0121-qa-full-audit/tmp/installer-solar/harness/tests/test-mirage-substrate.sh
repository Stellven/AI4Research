#!/usr/bin/env bash
# test-mirage-substrate.sh — Mirage boundary + functionality probes.
# S1: Verifies security boundaries and positive data access.
# Usage: bash tests/test-mirage-substrate.sh [--json]
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="${HARNESS_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
JSON_OUT="${1:-}"

PROBES_PASSED=0
PROBES_FAILED=0
RESULTS=()

pass_probe() {
  local name="$1"
  PROBES_PASSED=$((PROBES_PASSED+1))
  RESULTS+=("{\"probe\":\"$name\",\"result\":\"pass\"}")
  [[ "$JSON_OUT" != "--json" ]] && echo "PASS: $name"
}

fail_probe() {
  local name="$1"; local reason="$2"
  PROBES_FAILED=$((PROBES_FAILED+1))
  local esc="${reason//\"/\\\"}"
  RESULTS+=("{\"probe\":\"$name\",\"result\":\"fail\",\"reason\":\"$esc\"}")
  [[ "$JSON_OUT" != "--json" ]] && echo "FAIL: $name — $reason"
}

# ── Helper: run mirage exec and get JSON output ──────────────────────────────
mirage_exec_json() {
  solar-harness mirage exec --json -- "$1" 2>/dev/null
}

# ── P1: Denied host absolute reads ───────────────────────────────────────────

OUT=$(mirage_exec_json 'cat ~/.zshrc')
if echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d and "host path not allowed" in d["error"]' 2>/dev/null; then
  pass_probe "P1-deny-tilde-zshrc"
else
  fail_probe "P1-deny-tilde-zshrc" "expected blocked, got: $(echo "$OUT" | head -1)"
fi

OUT=$(mirage_exec_json 'cat /etc/passwd')
if echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d and "host path not allowed" in d["error"]' 2>/dev/null; then
  pass_probe "P1-deny-etc-passwd"
else
  fail_probe "P1-deny-etc-passwd" "expected blocked, got: $(echo "$OUT" | head -1)"
fi

OUT=$(mirage_exec_json 'cat ~/.solar/secrets/openai.key')
if echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d and ("host path not allowed" in d["error"] or "blocked" in d["error"])' 2>/dev/null; then
  pass_probe "P1-deny-credential-path"
else
  fail_probe "P1-deny-credential-path" "expected blocked, got: $(echo "$OUT" | head -1)"
fi

# ── P2: Denied writes to read-only mounts ────────────────────────────────────

for mp in /knowledge /sources /papers /solar-db /cortex /sprints; do
  OUT=$(solar-harness mirage exec --json -- "echo x > ${mp}/_write_test.txt" 2>/dev/null)
  if echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d or d.get("exit_code",0)!=0' 2>/dev/null; then
    pass_probe "P2-deny-write-${mp#/}"
  else
    fail_probe "P2-deny-write-${mp#/}" "write to ro mount succeeded: $mp"
  fi
done

# /drive not configured → path not found, also blocked
OUT=$(solar-harness mirage exec --json -- "echo x > /drive/_write_test.txt" 2>/dev/null)
if echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d' 2>/dev/null; then
  pass_probe "P2-deny-write-drive"
else
  fail_probe "P2-deny-write-drive" "write to /drive should be blocked"
fi

# ── P3: Positive probe — /raw write then read ────────────────────────────────

TODAY=$(date +%Y-%m-%d)
RAW_PROBE_PATH="/raw/${TODAY}/_mirage_probe_$$.md"
PHYS_RAW_DIR="$HOME/Knowledge/_raw/${TODAY}"
mkdir -p "$PHYS_RAW_DIR"

WRITE_OUT=$(solar-harness mirage exec --json -- "echo mirage_probe_${TODAY} > ${RAW_PROBE_PATH}" 2>/dev/null)
if echo "$WRITE_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("exit_code",1)==0' 2>/dev/null; then
  pass_probe "P3-raw-write"
else
  fail_probe "P3-raw-write" "$(echo "$WRITE_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error",d.get("stderr","")))' 2>/dev/null || echo "$WRITE_OUT")"
fi

READ_OUT=$(solar-harness mirage exec --json -- "cat ${RAW_PROBE_PATH}" 2>/dev/null)
if echo "$READ_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "mirage_probe_" in d.get("stdout","")' 2>/dev/null; then
  pass_probe "P3-raw-read"
else
  fail_probe "P3-raw-read" "$(echo "$READ_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("stderr",d.get("error","")))' 2>/dev/null)"
fi

# Cleanup probe file
rm -f "${PHYS_RAW_DIR}/_mirage_probe_$$.md" 2>/dev/null || true

# ── P4: mirage search returns sourced bounded hits ───────────────────────────

SEARCH_OUT=$(solar-harness mirage search "Solar Harness" --json 2>/dev/null)
if echo "$SEARCH_OUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
hits=d.get("hits",[])
assert len(hits)>0, "no hits"
sources=set(h.get("source_type","") for h in hits)
assert len(sources)>=1, "no source_type"
' 2>/dev/null; then
  pass_probe "P4-search-returns-hits"
else
  fail_probe "P4-search-returns-hits" "$(echo "$SEARCH_OUT" | head -1)"
fi

# Multi-source check (at least mirage_path or qmd)
if echo "$SEARCH_OUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
hits=d.get("hits",[])
types=set(h.get("source_type","") for h in hits)
assert "mirage_path" in types or "qmd" in types, f"expected mirage_path or qmd, got: {types}"
' 2>/dev/null; then
  pass_probe "P4-search-source-type"
else
  fail_probe "P4-search-source-type" "unexpected source types"
fi

# ── P5: doctor returns structured health ─────────────────────────────────────

DOCTOR_OUT=$(solar-harness mirage doctor --json 2>/dev/null)
if echo "$DOCTOR_OUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert "enabled" in d
assert "mounts" in d
ready=[m for m in d["mounts"] if m.get("ready")]
assert len(ready)>0, "no ready mounts"
' 2>/dev/null; then
  pass_probe "P5-doctor-healthy"
else
  fail_probe "P5-doctor-healthy" "$(echo "$DOCTOR_OUT" | head -1)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

if [[ "$JSON_OUT" == "--json" ]]; then
  python3 -c "
import json
results = [$(IFS=,; echo "${RESULTS[*]:-}")]
print(json.dumps({
  'probes_passed': $PROBES_PASSED,
  'probes_failed': $PROBES_FAILED,
  'total': $((PROBES_PASSED+PROBES_FAILED)),
  'ok': $PROBES_FAILED == 0,
  'results': results,
}, indent=2))
"
else
  echo ""
  echo "═══════════════════════════════════════════"
  echo "PROBES_PASSED=$PROBES_PASSED PROBES_FAILED=$PROBES_FAILED"
  echo "═══════════════════════════════════════════"
fi

[[ $PROBES_FAILED -eq 0 ]]

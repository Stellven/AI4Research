#!/usr/bin/env bash
# test-solar-kb-qmd-fallback.sh — Regression tests for solar-knowledge-context qmd fallback
# Coverage: A1-A6 from sprint contract + A3 fail-open + A4 disable flag + A5 max-chars
set -euo pipefail

SCRIPT="$HOME/.solar/harness/lib/solar-knowledge-context.py"
HOOK="$HOME/.claude/hooks/solar-knowledge-context.sh"
PASS=0; FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

echo "=== test-solar-kb-qmd-fallback.sh ==="

# T1 — DB miss + qmd hit: query known to exist only in qmd solar-wiki
t1_hits=$(python3 "$SCRIPT" --query '大模型热力学' --json --fail-open \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["hits"]))' 2>/dev/null)
if [ "${t1_hits:-0}" -ge 1 ]; then
  pass "T1 qmd hit count=$t1_hits for '大模型热力学'"
else
  fail "T1" "expected ≥1 hit, got ${t1_hits:-error}"
fi

# T2 — hit schema: source/title/snippet/path all present
schema_ok=$(python3 "$SCRIPT" --query '大模型热力学' --json --fail-open \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
h=d["hits"][0] if d["hits"] else {}
ok = all(k in h for k in ["source","title","snippet","path"])
print("ok" if ok else "missing:"+str([k for k in ["source","title","snippet","path"] if k not in h]))
' 2>/dev/null)
if [ "$schema_ok" = "ok" ]; then
  pass "T2 hit schema has required fields"
else
  fail "T2" "schema check: $schema_ok"
fi

# T3 — qmd unavailable → fail-open, valid JSON, hits may be empty
t3_out=$(QMD_BIN=/tmp/no-such-qmd python3 "$SCRIPT" \
  --query '大模型热力学' --json --fail-open 2>/dev/null)
if echo "$t3_out" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  pass "T3 qmd missing → fail-open valid JSON"
else
  fail "T3" "invalid JSON or exception when qmd missing"
fi

# T4 — SOLAR_KB_CONTEXT=0 disables hook injection
t4_out=$(printf '{"user_prompt":"大模型热力学"}' \
  | SOLAR_KB_CONTEXT=0 "$HOOK" 2>/dev/null)
if [ -z "$t4_out" ]; then
  pass "T4 SOLAR_KB_CONTEXT=0 → empty hook output"
else
  fail "T4" "hook output not empty with SOLAR_KB_CONTEXT=0"
fi

# T5 — max-chars budget respected
t5_chars=$(python3 "$SCRIPT" --query '大模型热力学' --json --max-chars 500 --fail-open \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("total_chars",0))' 2>/dev/null)
if [ "${t5_chars:-9999}" -le 500 ]; then
  pass "T5 max-chars=500 respected (total_chars=${t5_chars})"
else
  fail "T5" "total_chars=${t5_chars} exceeds 500"
fi

# T6 — valid JSON output always
t6_valid=$(python3 "$SCRIPT" --query '大模型热力学' --json --fail-open \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok")' 2>/dev/null)
if [ "$t6_valid" = "ok" ]; then
  pass "T6 output is valid JSON"
else
  fail "T6" "invalid JSON output"
fi

# T7 — hook emits <solar-knowledge-context> for matching prompt
t7_tag=$(printf '{"user_prompt":"帮我基于大模型热力学分析注意力机制"}' \
  | "$HOOK" 2>/dev/null | grep -c '<solar-knowledge-context>' || true)
if [ "${t7_tag:-0}" -ge 1 ]; then
  pass "T7 hook emits <solar-knowledge-context>"
else
  fail "T7" "hook did not emit <solar-knowledge-context>"
fi

# T8 — hit deduplication: no duplicate ids for same query
t8_dedup=$(python3 "$SCRIPT" --query '大模型热力学' --json --fail-open \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
ids=[h.get("id","") for h in d["hits"]]
print("ok" if len(ids)==len(set(ids)) else "dups:"+str(ids))
' 2>/dev/null)
if [ "$t8_dedup" = "ok" ]; then
  pass "T8 no duplicate hits"
else
  fail "T8" "$t8_dedup"
fi

# T9 — qmd_adapter status routes through SandboxHand (R1 of
# sprint-20260513-tool-plane-sandbox-default-routing)
echo "T9: qmd_adapter status sandbox routing"
t9_out=$(python3 "$HOME/.solar/harness/lib/qmd_adapter.py" status --json 2>/dev/null)
t9_eval=$(printf '%s' "$t9_out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("parse-error:" + str(e))
    sys.exit(0)
executor = d.get("executor", "")
mode = d.get("execution_mode", "")
ev = d.get("evidence_file", "")
if executor != "sandbox":
    print("not-sandbox:" + executor)
elif mode != "argv":
    print("not-argv:" + mode)
elif not ev:
    print("no-evidence")
else:
    print("ok:" + ev)
' 2>/dev/null)
case "$t9_eval" in
  ok:*) pass "T9 qmd status routed through SandboxHand (${t9_eval})" ;;
  *)    fail "T9" "$t9_eval" ;;
esac

# T10 — evidence file actually exists and records argv mode
if [ "${t9_eval#ok:}" != "$t9_eval" ]; then
  ev_path="${t9_eval#ok:}"
  if [ -f "$ev_path" ] && python3 -c "
import json, sys
d = json.load(open('$ev_path'))
assert d.get('execution_mode') == 'argv', d.get('execution_mode')
assert d.get('command_name') == 'qmd-status', d.get('command_name')
print('ok')
" 2>/dev/null | grep -q '^ok$'; then
    pass "T10 sandbox evidence file written with argv mode"
  else
    fail "T10" "evidence missing or wrong schema at $ev_path"
  fi
fi

# T11 — mirage_search.search_qmd routes through SandboxHand (R1 extension of
# sprint-20260513-tool-plane-sandbox-default-routing)
echo "T11: mirage_search.search_qmd sandbox routing"
t11_eval=$(python3 - <<'PY' 2>/dev/null
import os, json, importlib.util, sys
spec = importlib.util.spec_from_file_location("mirage_search", os.path.expanduser("~/.solar/harness/lib/mirage_search.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["mirage_search"] = m
spec.loader.exec_module(m)
m.search_qmd("sandbox routing smoke", max_hits=1)
r = m.LAST_QMD_ROUTE or {}
if r.get("executor") != "sandbox":
    print("not-sandbox:" + str(r.get("executor")))
elif r.get("execution_mode") != "argv":
    print("not-argv:" + str(r.get("execution_mode")))
elif not r.get("evidence_file") or not os.path.exists(r.get("evidence_file","")):
    print("no-evidence:" + str(r.get("evidence_file")))
else:
    print("ok:" + r.get("evidence_file"))
PY
)
case "$t11_eval" in
  ok:*) pass "T11 mirage_search.search_qmd routed through SandboxHand (${t11_eval})" ;;
  *)    fail "T11" "$t11_eval" ;;
esac

# T12 — evidence file from T11 records argv mode and qmd-search command name
if [ "${t11_eval#ok:}" != "$t11_eval" ]; then
  ev_path="${t11_eval#ok:}"
  if [ -f "$ev_path" ] && python3 -c "
import json
d = json.load(open('$ev_path'))
assert d.get('execution_mode') == 'argv', d.get('execution_mode')
assert d.get('command_name') == 'qmd-search', d.get('command_name')
print('ok')
" 2>/dev/null | grep -q '^ok$'; then
    pass "T12 qmd-search evidence file written with argv mode"
  else
    fail "T12" "evidence missing or wrong schema at $ev_path"
  fi
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

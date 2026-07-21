#!/usr/bin/env bash
# Test suite for sprint-20260508-accepted-artifact-knowledge
# Acceptance criteria A1-A8

set -euo pipefail
HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPORTER="$HARNESS_DIR/lib/accepted-artifact-export.py"
SPRINTS_DIR="$HARNESS_DIR/sprints"
PASS=0; FAIL=0; SKIP=0

_ok()   { echo "  ✅ $*"; PASS=$((PASS+1)); }
_fail() { echo "  ❌ $*"; FAIL=$((FAIL+1)); }
_skip() { echo "  ⏭  $*"; SKIP=$((SKIP+1)); }

# --case filter
CASE_FILTER="${1:-}"
[[ "$CASE_FILTER" == "--case" ]] && CASE_FILTER="${2:-}"

run_case() {
  local name="$1"
  if [[ -n "$CASE_FILTER" && "$CASE_FILTER" != "$name" ]]; then
    return
  fi
  echo ""
  echo "=== Case: $name ==="
  "_test_$name"
}

# ─── Fixture helpers ─────────────────────────────────────────────────────────

_make_sprint() {
  local vault="$1" sid="$2" status="${3:-passed}"
  local sd="$vault/.sprints"
  mkdir -p "$sd"
  local title="Test Sprint ${sid##sprint-}"
  # status.json
  cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"$title","status":"$status","round":2,"created_at":"2026-05-01T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  # contract
  cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
## Done 定义
1. Feature X works correctly.
## 约束
- No secrets in output.
MD
  # handoff
  cat > "$sd/${sid}.handoff.md" <<MD
# Handoff — $sid
Builder: 建设者化身
Round: 2

## 变更文件
- lib/feature.py (NEW)

## Done 定义达成
1. Feature X: ✅ tested and working

## 验证方法
\`\`\`bash
python3 -c "print('ok')"
\`\`\`
MD
  # eval
  cat > "$sd/${sid}.eval.md" <<MD
# Eval — $sid
Verdict: PASS
All items passed.
MD
  cat > "$sd/${sid}.eval.json" <<JSON
{"verdict":"PASS","sprint_id":"$sid","items":[],"score":10}
JSON
  cat > "$sd/${sid}.prd.html" <<HTML
<!doctype html><html><head><style>.x{color:red}</style></head><body><h1>PRD Visual Summary</h1><script>ignored()</script><p>Human readable PRD card for ${sid}.</p></body></html>
HTML
  cat > "$sd/${sid}.design.html" <<HTML
<!doctype html><html><body><h1>Design Visual Summary</h1><p>Architecture view, stack binding, and interfaces for ${sid}.</p></body></html>
HTML
  cat > "$sd/${sid}.planning.html" <<HTML
<!doctype html><html><body><h1>Planning Visual Summary</h1><p>DAG, write scope, validation commands, and stop rules for ${sid}.</p></body></html>
HTML
}

# ─── A1: pass-only ───────────────────────────────────────────────────────────

_test_pass-only() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  # passed sprint → should export
  local sid_pass="sprint-20260501-passtest"
  cat > "$sd/${sid_pass}.status.json" <<JSON
{"sprint_id":"$sid_pass","title":"Pass Test","status":"passed","round":2,"created_at":"2026-05-01T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  cat > "$sd/${sid_pass}.contract.md" <<MD
# Contract — $sid_pass
## Done 定义
1. Something.
MD

  # reviewing sprint → must NOT export
  local sid_rev="sprint-20260502-revtest"
  cat > "$sd/${sid_rev}.status.json" <<JSON
{"sprint_id":"$sid_rev","title":"Reviewing Test","status":"reviewing","round":1,"created_at":"2026-05-02T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON

  # Test passed sprint exports
  local out
  out=$(python3 "$EXPORTER" export --sid "$sid_pass" \
    --vault "$vault" --sprints-dir "$sd" --dry-run --json 2>&1 || true)
  if echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('dry_run')==True" 2>/dev/null; then
    _ok "pass-only: passed sprint accepted in dry-run"
  else
    _fail "pass-only: passed sprint dry-run failed; output=$out"
  fi

  # Test reviewing sprint rejected
  out=$(python3 "$EXPORTER" export --sid "$sid_rev" \
    --vault "$vault" --sprints-dir "$sd" --dry-run --json 2>&1 || true)
  if echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok')==False" 2>/dev/null; then
    _ok "pass-only: non-passed sprint rejected"
  else
    _fail "pass-only: non-passed sprint was not rejected; output=$out"
  fi
}

# ─── A2: artifact-schema ─────────────────────────────────────────────────────

_test_artifact-schema() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault"
  _make_sprint "$tmpdir" "sprint-20260503-schematest" "passed"
  cp -r "$tmpdir/.sprints/." "$sd/" 2>/dev/null || true
  mkdir -p "$sd"
  _make_sprint "$tmpdir" "sprint-20260503-schematest" "passed"
  # move sprints
  rm -rf "$sd"
  mv "$tmpdir/.sprints" "$sd"

  local sid="sprint-20260503-schematest"
  local out
  out=$(python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json 2>&1)

  if echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok')==True" 2>/dev/null; then
    _ok "artifact-schema: export succeeded"
  else
    _fail "artifact-schema: export failed; output=$out"
    return
  fi

  # Check output file exists and has required frontmatter keys
  local outfile
  outfile=$(echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',d.get('path','')))" 2>/dev/null || true)
  if [[ -z "$outfile" || ! -f "$outfile" ]]; then
    _fail "artifact-schema: output file not found: $outfile"
    return
  fi

  local required_keys=("source: solar-harness" "artifact_type: accepted_sprint_knowledge" "sprint_id:" "status: passed" "redacted: true" "visibility: internal" "provenance: accepted-by-evaluator" "source_files:" "prd_html: true" "design_html: true" "planning_html: true")
  local all_ok=1
  for key in "${required_keys[@]}"; do
    if grep -q "$key" "$outfile"; then
      true
    else
      _fail "artifact-schema: missing frontmatter key: $key"
      all_ok=0
    fi
  done
  [[ $all_ok -eq 1 ]] && _ok "artifact-schema: all required frontmatter keys present"

  # Check body sections
  local required_sections=("## Executive Summary" "## Human-readable HTML Artifacts" "## Source Artifact Index")
  for section in "${required_sections[@]}"; do
    if grep -q "$section" "$outfile"; then
      true
    else
      _fail "artifact-schema: missing section: $section"
      all_ok=0
    fi
  done
  [[ $all_ok -eq 1 ]] && _ok "artifact-schema: required body sections present"

  if grep -q "Design Visual Summary" "$outfile" && grep -q "Planning Visual Summary" "$outfile" && grep -q "Human readable PRD card" "$outfile"; then
    _ok "artifact-schema: HTML artifacts extracted into accepted knowledge"
  else
    _fail "artifact-schema: HTML artifacts missing from accepted knowledge"
  fi
}

# ─── A3: redaction ───────────────────────────────────────────────────────────

_test_redaction() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  local sid="sprint-20260504-redacttest"
  cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"Redact Test","status":"passed","round":1,"created_at":"2026-05-04T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  # Contract with embedded secrets
  cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
API_KEY=sk-abc123secretkey
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.secret
ANTHROPIC_AUTH_TOKEN=sk-ant-secret
ZHIPU_AUTH_TOKEN=zhipu-secret-token
DEEPSEEK_API_KEY=dsk-secret-key
api_key=mysecretapikey
token=mysecrettoken
## Done 定义
1. Feature works.
MD

  local out
  out=$(python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json 2>&1)

  if ! echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok')==True" 2>/dev/null; then
    _fail "redaction: export failed; output=$out"
    return
  fi

  local outfile
  outfile=$(echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',d.get('path','')))" 2>/dev/null || true)

  # Verify no raw secrets in output
  local leaked=0
  for pattern in "sk-abc123" "eyJhbGciOiJSUzI1NiJ9.secret" "zhipu-secret-token" "dsk-secret-key" "mysecretapikey" "mysecrettoken"; do
    if grep -q "$pattern" "$outfile" 2>/dev/null; then
      _fail "redaction: secret leaked in output: $pattern"
      leaked=1
    fi
  done
  [[ $leaked -eq 0 ]] && _ok "redaction: no raw secrets in output"

  # Verify [REDACTED] markers present
  if grep -q "\[REDACTED" "$outfile" 2>/dev/null; then
    _ok "redaction: [REDACTED] markers present in output"
  else
    _fail "redaction: no [REDACTED] markers found in output"
  fi
}

# ─── A4: idempotent ──────────────────────────────────────────────────────────

_test_idempotent() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  local sid="sprint-20260505-idemptest"
  cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"Idempotency Test","status":"passed","round":1,"created_at":"2026-05-05T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
## Done 定义
1. Feature idempotent.
MD

  # First export
  local out1
  out1=$(python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json 2>&1)

  if ! echo "$out1" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok')==True" 2>/dev/null; then
    _fail "idempotent: first export failed; output=$out1"
    return
  fi

  local path1
  path1=$(echo "$out1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',d.get('path','')))" 2>/dev/null || true)

  # Second export (same content, should skip or return same path)
  local out2
  out2=$(python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json 2>&1)

  local skipped
  skipped=$(echo "$out2" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('skipped',False))" 2>/dev/null || echo "False")

  if [[ "$skipped" == "True" ]]; then
    _ok "idempotent: second export correctly skipped (hash match)"
  else
    # Also acceptable: ok=True and same path
    local path2
    path2=$(echo "$out2" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',d.get('path','')))" 2>/dev/null || true)
    if [[ "$path1" == "$path2" ]]; then
      _ok "idempotent: second export returned same path"
    else
      _fail "idempotent: second export not idempotent; path1=$path1 path2=$path2 out2=$out2"
    fi
  fi

  # --force flag bypasses idempotency check
  local out3
  out3=$(python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --force --json 2>&1)
  if echo "$out3" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok')==True and not d.get('skipped')" 2>/dev/null; then
    _ok "idempotent: --force bypasses hash check"
  else
    _fail "idempotent: --force did not bypass hash check; output=$out3"
  fi
}

# ─── A5: status-events ───────────────────────────────────────────────────────

_test_status-events() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  local sid="sprint-20260506-statustest"
  cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"Status Events Test","status":"passed","round":1,"created_at":"2026-05-06T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
## Done 定义
1. Status fields updated.
MD
  touch "$sd/${sid}.events.jsonl"

  python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json > /dev/null 2>&1 || true

  # Check status.json has knowledge_export_status field
  local kstatus
  kstatus=$(python3 -c "import json; d=json.load(open('$sd/${sid}.status.json')); print(d.get('knowledge_export_status','MISSING'))" 2>/dev/null || echo "MISSING")

  if [[ "$kstatus" != "MISSING" && "$kstatus" != "" ]]; then
    _ok "status-events: knowledge_export_status set to '$kstatus'"
  else
    _fail "status-events: knowledge_export_status not set in status.json"
  fi

  # Check events.jsonl has accepted_artifact_exported event
  if [[ -f "$sd/${sid}.events.jsonl" ]] && grep -q "accepted_artifact" "$sd/${sid}.events.jsonl" 2>/dev/null; then
    _ok "status-events: accepted_artifact event emitted to events.jsonl"
  else
    _fail "status-events: no accepted_artifact event in events.jsonl"
  fi

  # Verify knowledge_export_path and knowledge_exported_at also set
  local kpath
  kpath=$(python3 -c "import json; d=json.load(open('$sd/${sid}.status.json')); print(d.get('knowledge_export_path','MISSING'))" 2>/dev/null || echo "MISSING")
  if [[ "$kpath" != "MISSING" && "$kpath" != "" ]]; then
    _ok "status-events: knowledge_export_path set"
  else
    _fail "status-events: knowledge_export_path not set"
  fi
}

# ─── A6: ingest-dispatch ─────────────────────────────────────────────────────

_test_ingest-dispatch() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  local sid="sprint-20260507-dispatchtest"
  cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"Ingest Dispatch Test","status":"passed","round":2,"created_at":"2026-05-07T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
  cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
## Done 定义
1. Dispatch created.
MD

  python3 "$EXPORTER" export --sid "$sid" \
    --vault "$vault" --sprints-dir "$sd" --json > /dev/null 2>&1 || true

  # Check dispatch file created under Knowledge/_raw/solar-harness/.dispatch/
  local dispatch_dir="$vault/_raw/solar-harness/.dispatch"
  if [[ -d "$dispatch_dir" ]]; then
    local dispatch_files
    dispatch_files=$(ls "$dispatch_dir"/*.md 2>/dev/null | wc -l || echo "0")
    if [[ "$dispatch_files" -gt 0 ]]; then
      _ok "ingest-dispatch: dispatch file created under $dispatch_dir"
    else
      _fail "ingest-dispatch: dispatch dir exists but no .md files"
    fi
  else
    _fail "ingest-dispatch: dispatch dir not created: $dispatch_dir"
  fi

  # Check dispatch file has safe content (no executable code, just wiki ingest instruction)
  local dispatch_file
  dispatch_file=$(ls "$dispatch_dir"/*.md 2>/dev/null | head -1 || true)
  if [[ -n "$dispatch_file" && -f "$dispatch_file" ]]; then
    if grep -q "$sid" "$dispatch_file"; then
      _ok "ingest-dispatch: dispatch file references sprint_id"
    else
      _fail "ingest-dispatch: dispatch file does not reference sprint_id"
    fi
    # knowledge_ingest_dispatch field updated
    local kdisp
    kdisp=$(python3 -c "import json; d=json.load(open('$sd/${sid}.status.json')); print(d.get('knowledge_ingest_dispatch','MISSING'))" 2>/dev/null || echo "MISSING")
    if [[ "$kdisp" != "MISSING" && "$kdisp" != "" ]]; then
      _ok "ingest-dispatch: knowledge_ingest_dispatch field set in status.json"
    else
      _fail "ingest-dispatch: knowledge_ingest_dispatch not set in status.json"
    fi
  fi
}

# ─── A7: backfill-dry-run ────────────────────────────────────────────────────

_test_backfill-dry-run() {
  local tmpdir; tmpdir=$(mktemp -d)
  trap "rm -rf $tmpdir" RETURN

  local vault="$tmpdir/vault"
  local sd="$tmpdir/sprints"
  mkdir -p "$vault" "$sd"

  # Create 4 passed sprints
  for i in 1 2 3 4; do
    local sid="sprint-2026050${i}-bftest${i}"
    cat > "$sd/${sid}.status.json" <<JSON
{"sprint_id":"$sid","title":"BF Test $i","status":"passed","round":1,"created_at":"2026-05-0${i}T00:00:00Z","updated_at":"2026-05-09T00:00:00Z"}
JSON
    cat > "$sd/${sid}.contract.md" <<MD
# Contract — $sid
## Done 定义
1. Backfill test $i.
MD
  done

  # Dry-run backfill with limit 3
  local out
  out=$(python3 "$EXPORTER" backfill \
    --vault "$vault" --sprints-dir "$sd" --limit 3 --dry-run --json 2>&1)

  if echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('dry_run')==True and len(d.get('candidates',[]))>=1" 2>/dev/null; then
    _ok "backfill-dry-run: dry-run returned candidates list"
  else
    _fail "backfill-dry-run: unexpected output; out=$out"
    return
  fi

  # Verify --limit honored (at most 3 candidates)
  local cnt
  cnt=$(echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('candidates',[])))" 2>/dev/null || echo "0")
  if [[ "$cnt" -le 3 ]]; then
    _ok "backfill-dry-run: --limit 3 honored (got $cnt candidates)"
  else
    _fail "backfill-dry-run: --limit 3 not honored (got $cnt candidates)"
  fi

  # Verify no files written during dry-run
  local accepted_dir="$vault/_raw/solar-harness/accepted"
  local written=0
  if [[ -d "$accepted_dir" ]]; then
    written=$(find "$accepted_dir" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [[ "$written" -eq 0 ]]; then
    _ok "backfill-dry-run: no files written during dry-run"
  else
    _fail "backfill-dry-run: files written during dry-run ($written files)"
  fi
}

# ─── Run all cases ────────────────────────────────────────────────────────────

echo "Sprint sprint-20260508-accepted-artifact-knowledge — Regression Suite"
echo "Exporter: $EXPORTER"

run_case "pass-only"
run_case "artifact-schema"
run_case "redaction"
run_case "idempotent"
run_case "status-events"
run_case "ingest-dispatch"
run_case "backfill-dry-run"

echo ""
echo "─────────────────────────────────────────"
echo "PASS=$PASS  FAIL=$FAIL  SKIP=$SKIP"
if [[ $FAIL -gt 0 ]]; then
  echo "RESULT: ❌ FAIL"
  exit 1
else
  echo "RESULT: ✅ PASS"
  exit 0
fi

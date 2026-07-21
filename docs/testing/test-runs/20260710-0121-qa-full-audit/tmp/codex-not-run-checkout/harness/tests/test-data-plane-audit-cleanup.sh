#!/usr/bin/env bash
# Regression coverage for data-plane audit cleanup:
# - sys_resources uses the real registry/usage schema, not old access_count columns
# - legacy KB tables become dormant when the current vault+FTS index is fresh
# - refresh-ledger updates metadata without pretending dormant tables are active
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AUDIT="$HARNESS_DIR/lib/data_plane_audit.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

DB="$TMPDIR_TEST/solar.db"

python3 - "$DB" <<'PY'
import sqlite3
import sys

db = sys.argv[1]
conn = sqlite3.connect(db)
conn.executescript(
    """
    CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO state VALUES ('ok', '{"status":"ok"}');

    CREATE TABLE sys_data_ledger (
      ledger_id TEXT PRIMARY KEY,
      source_type TEXT,
      source_name TEXT,
      record_count INTEGER,
      status TEXT,
      last_checked TEXT,
      updated_at TEXT,
      notes TEXT
    );
    INSERT INTO sys_data_ledger VALUES
      ('ledger-kb', 'table', 'solar_kb_entries', 0, 'active', '2026-02-01 00:00:00', '2026-02-01 00:00:00', ''),
      ('ledger-resource', 'table', 'sys_resources', 0, 'active', '2026-02-01 00:00:00', '2026-02-01 00:00:00', '');

    CREATE TABLE sys_resources (
      resource_id TEXT PRIMARY KEY,
      resource_type TEXT NOT NULL,
      name TEXT NOT NULL,
      version TEXT DEFAULT '1.0',
      status TEXT DEFAULT 'active',
      description TEXT,
      config JSON,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      layer TEXT DEFAULT 'local',
      executor TEXT DEFAULT 'shell',
      command_template TEXT,
      cost_type TEXT DEFAULT 'free',
      cost_per_call REAL DEFAULT 0,
      latency_ms INTEGER DEFAULT 100,
      keywords TEXT,
      availability TEXT DEFAULT 'available',
      source TEXT DEFAULT 'manual',
      last_verified DATETIME
    );
    INSERT INTO sys_resources VALUES
      ('tool:existing-a:1.0', 'tool', 'existing-a', '1.0', 'active', NULL, '{}', '2026-05-12T00:00:00Z', '2026-05-12T00:00:00Z', 'local', 'shell', NULL, 'free', 0, 100, '[]', 'available', 'test', NULL),
      ('tool:existing-b:1.0', 'tool', 'existing-b', '1.0', 'active', NULL, '{}', '2026-05-12T00:00:00Z', '2026-05-12T00:00:00Z', 'local', 'shell', NULL, 'free', 0, 100, '[]', 'available', 'test', NULL);

    CREATE TABLE sys_resource_usage (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      resource_id TEXT NOT NULL,
      called_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      intent TEXT,
      input_summary TEXT,
      success INTEGER DEFAULT 1,
      latency_ms INTEGER,
      cost_actual REAL,
      output_summary TEXT,
      error TEXT,
      user_feedback TEXT
    );

    CREATE TABLE cortex_sources (id TEXT PRIMARY KEY, created_at TEXT);
    INSERT INTO cortex_sources VALUES ('src1', '2026-05-12T00:00:00Z');

    CREATE TABLE cortex_passages (id TEXT PRIMARY KEY, created_at TEXT);
    INSERT INTO cortex_passages VALUES ('cp1', '2026-02-01T00:00:00Z');

    CREATE TABLE solar_kb_entries (id TEXT PRIMARY KEY, created_at TEXT);
    INSERT INTO solar_kb_entries VALUES ('kb1', '2026-02-01T00:00:00Z');

    CREATE TABLE knowledge_records (id TEXT PRIMARY KEY, created_at TEXT);
    INSERT INTO knowledge_records VALUES ('kr1', '2026-02-01T00:00:00Z');

    CREATE TABLE obsidian_vault_index (
      file_path TEXT PRIMARY KEY,
      title TEXT,
      indexed_at TEXT,
      deleted_at TEXT
    );
    INSERT INTO obsidian_vault_index VALUES
      ('/tmp/vault/_raw/solar-harness/accepted/sprint-test.accepted.md', 'Accepted Test', '2026-05-12T00:00:00Z', NULL),
      ('/tmp/vault/concepts/current.md', 'Current', '2026-05-12T00:00:00Z', NULL);

    CREATE TABLE fts_unified_search (
      doc_id TEXT,
      doc_type TEXT,
      title TEXT,
      content TEXT,
      tags TEXT,
      metadata TEXT
    );
    INSERT INTO fts_unified_search VALUES
      ('d1', 'obsidian', 'Accepted Test', 'body', '', '{}'),
      ('d2', 'obsidian', 'Current', 'body', '', '{}');
    """
)
conn.commit()
conn.close()
PY
pass "fixture database created"

python3 -m py_compile "$AUDIT" || fail "data_plane_audit.py does not compile"
bash -n "$HARNESS_DIR/solar-harness.sh" || fail "solar-harness.sh syntax failed"
pass "syntax checks"

set +e
SOLAR_DB="$DB" python3 "$AUDIT" audit --json > "$TMPDIR_TEST/audit-before.json" 2>"$TMPDIR_TEST/audit-before.err"
before_rc=$?
set -e
[[ "$before_rc" -ne 0 ]] || fail "pre-refresh audit should warn on stale sys_data_ledger"

python3 - "$TMPDIR_TEST/audit-before.json" <<'PY' || exit 1
import json
import sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {c["name"]: c for c in d["checks"]}
if checks["sys_data_ledger"]["status"] != "stale":
    raise SystemExit(f"expected stale ledger before refresh, got {checks['sys_data_ledger']}")
if checks["sys_resources"]["status"] != "dormant":
    raise SystemExit(f"expected dormant sys_resources, got {checks['sys_resources']}")
for name in ("cortex_passages", "solar_kb_entries", "knowledge_records"):
    item = checks[name]
    if item["status"] != "dormant":
        raise SystemExit(f"expected dormant {name}, got {item}")
    if item.get("replacement") != "obsidian_vault_index+fts_unified_search":
        raise SystemExit(f"missing replacement evidence for {name}: {item}")
PY
pass "audit classifies legacy tables and resource registry honestly"

SOLAR_DB="$DB" "$HARNESS_DIR/solar-harness.sh" data-plane refresh-ledger --json > "$TMPDIR_TEST/refresh.json"
python3 - "$TMPDIR_TEST/refresh.json" <<'PY' || exit 1
import json
import sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
if d.get("status") != "ok":
    raise SystemExit(d)
if int(d.get("updated", 0)) < 2:
    raise SystemExit(f"expected at least 2 ledger updates, got {d}")
PY
pass "solar-harness data-plane refresh-ledger route works"

SOLAR_DB="$DB" python3 "$AUDIT" audit --json > "$TMPDIR_TEST/audit-after.json"
python3 - "$TMPDIR_TEST/audit-after.json" <<'PY' || exit 1
import json
import sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {c["name"]: c for c in d["checks"]}
if d.get("overall_status") != "ok":
    raise SystemExit(f"expected overall ok after refresh, got {d.get('overall_status')}")
if checks["sys_data_ledger"]["status"] != "ok":
    raise SystemExit(f"ledger not ok after refresh: {checks['sys_data_ledger']}")
if checks["solar_kb_entries"]["status"] != "dormant":
    raise SystemExit(f"legacy table should remain dormant, not active: {checks['solar_kb_entries']}")
if checks["resource_usage"]["status"] != "dormant":
    raise SystemExit(f"resource usage should be dormant without telemetry: {checks['resource_usage']}")
PY
pass "post-refresh audit is ok while dormant layers stay explicit"

SOLAR_DB="$DB" PYTHONPATH="$HARNESS_DIR/lib" python3 - <<'PY' || exit 1
from resource_telemetry import record_usage
from capability_effects import scan_effect
from pathlib import Path
import json
import tempfile

ok = record_usage(
    "tool",
    "test-runtime-telemetry",
    intent="test.runtime",
    input_summary="fixture dispatch",
    output_summary="fixture output",
    description="test resource",
    keywords=["test"],
)
if not ok:
    raise SystemExit("record_usage returned false")

td = Path(tempfile.mkdtemp())
dispatch = td / "dispatch.md"
dispatch.write_text("# Dispatch\n", encoding="utf-8")
sidecar = td / "dispatch.md.intent.json"
sidecar.write_text(json.dumps({
    "dispatch_file": str(dispatch),
    "capabilities": [{
        "provider": "Browser-use MCP",
        "capabilities": ["browser.browse", "browser.localhost_test"],
        "scorecard": {"provider_id": "browser-use"},
    }],
    "effect": {"status": "pending_worker_evidence", "worker_used": False},
}), encoding="utf-8")
handoff = td / "handoff.md"
handoff.write_text("Used Browser-use MCP to verify localhost browser QA.", encoding="utf-8")
eval_json = td / "eval.json"
eval_json.write_text('{"verdict":"PASS"}', encoding="utf-8")
result = scan_effect(dispatch, handoff_file=handoff, eval_json_file=eval_json, record_db=True)
if result.get("effect", {}).get("status") != "eval_passed_with_worker_evidence":
    raise SystemExit(result)
PY

SOLAR_DB="$DB" python3 "$AUDIT" audit --json > "$TMPDIR_TEST/audit-active.json"
python3 - "$TMPDIR_TEST/audit-active.json" <<'PY' || exit 1
import json
import sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {c["name"]: c for c in d["checks"]}
if checks["resource_usage"]["status"] != "ok":
    raise SystemExit(f"resource usage should become active after telemetry: {checks['resource_usage']}")
if checks["sys_resources"]["status"] != "ok":
    raise SystemExit(f"sys_resources should become active after telemetry: {checks['sys_resources']}")
PY
pass "runtime telemetry turns resource usage from dormant to active"

echo "PROBES_PASSED=6 PROBES_FAILED=0"

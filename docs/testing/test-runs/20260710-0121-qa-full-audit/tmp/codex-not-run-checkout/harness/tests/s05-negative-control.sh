#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$HARNESS_DIR/tests/s05-negctl-results.json}"
PYTEST_LOG="$(mktemp)"

set +e
python3 -m pytest -q "$HARNESS_DIR/tests/runtime/test_compat_mapping.py" >"$PYTEST_LOG" 2>&1
PYTEST_RC=$?
set -e

python3 - "$HARNESS_DIR" "$OUT" "$PYTEST_LOG" "$PYTEST_RC" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

harness_dir = Path(sys.argv[1])
out = Path(sys.argv[2])
pytest_log = Path(sys.argv[3])
pytest_rc = int(sys.argv[4])


def check(name, passed, evidence):
    return {"name": name, "status": "passed" if passed else "failed", "evidence": evidence}


physical = json.loads((harness_dir / "config" / "physical-operators.json").read_text(encoding="utf-8"))
schema = json.loads((harness_dir / "config" / "physical-operators.schema.json").read_text(encoding="utf-8"))
operators = physical.get("operators", {})
deprecated_missing = [op_id for op_id, cfg in operators.items() if cfg.get("deprecated") is not True]
compat_missing = [op_id for op_id, cfg in operators.items() if not cfg.get("compat_maps_to")]
compat_mismatch = [
    op_id
    for op_id, cfg in operators.items()
    if cfg.get("compat_maps_to", {}).get("host_type") != cfg.get("compat_alias_for")
]
pytest_output = pytest_log.read_text(encoding="utf-8", errors="replace")

checks = [
    check("physical_registry_meta_read_only", physical.get("_meta", {}).get("transition_status") == "read_only", {
        "meta": physical.get("_meta", {}),
    }),
    check("physical_schema_marks_read_only", schema.get("properties", {}).get("transition_status", {}).get("const") == "read_only", {
        "transition_status": schema.get("properties", {}).get("transition_status", {}),
    }),
    check("all_physical_operators_deprecated", not deprecated_missing, {
        "operator_count": len(operators),
        "deprecated_missing": deprecated_missing[:20],
    }),
    check("all_physical_operators_have_compat_map", not compat_missing and not compat_mismatch, {
        "compat_missing": compat_missing[:20],
        "compat_mismatch": compat_mismatch[:20],
    }),
    check("compat_mapping_pytest_passes", pytest_rc == 0, {
        "exit_code": pytest_rc,
        "output": pytest_output[-2000:],
    }),
]

payload = {
    "schema": "solar.s05.negative_control_results.v1",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "checks": checks,
    "summary": {
        "total": len(checks),
        "passed": sum(1 for item in checks if item["status"] == "passed"),
        "failed": sum(1 for item in checks if item["status"] == "failed"),
    },
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload["summary"], ensure_ascii=False))
sys.exit(0 if payload["summary"]["failed"] == 0 else 1)
PY

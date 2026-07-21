#!/usr/bin/env bash
set -euo pipefail

ROOT="${HARNESS_DIR:-$HOME/.solar/harness}"
REPORT_ROOT="$ROOT/reports/remote-dispatch-productization"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$REPORT_ROOT/$RUN_ID"
mkdir -p "$OUT_DIR"

JSON_REPORT="$OUT_DIR/report.json"
MD_REPORT="$OUT_DIR/report.md"
LOG_FILE="$OUT_DIR/pytest.log"

status="ok"
pytest_rc=0

{
  echo "== remote dispatch productization pytest =="
  python3 -m pytest \
    "$ROOT/tests/remote/test_remote_dispatch_core.py" \
    "$ROOT/tests/remote/test_remote_dispatch_cli.py" \
    "$ROOT/tests/graph/test_graph_dispatch_submit.py" \
    "$ROOT/tests/graph/test_parent_ready_closeout.py" \
    -q
} >"$LOG_FILE" 2>&1 || pytest_rc=$?

if [[ "$pytest_rc" -ne 0 ]]; then
  status="error"
fi

python3 - "$JSON_REPORT" "$status" "$pytest_rc" "$LOG_FILE" "$OUT_DIR" <<'PY'
import datetime
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
status = sys.argv[2]
pytest_rc = int(sys.argv[3])
log_file = Path(sys.argv[4])
out_dir = Path(sys.argv[5])

payload = {
    "status": status,
    "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "pytest_returncode": pytest_rc,
    "coverage": {
        "remote_core": True,
        "bash_cli_doctor": True,
        "fake_transport": True,
        "checksum_mismatch": True,
        "duplicate_dispatch": True,
        "pull_reconcile": True,
        "pane_submit_failure": True,
        "parent_ready_check": True,
    },
    "artifacts": {
        "log": str(log_file),
        "out_dir": str(out_dir),
    },
}
report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

cat >"$MD_REPORT" <<EOF
# Remote Dispatch Productization Integration Report

- status: $status
- checked_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- pytest_returncode: $pytest_rc
- log: $LOG_FILE
- json: $JSON_REPORT

## Coverage

- remote core config/doctor/manifest/checksum
- bash CLI doctor JSON subprocess
- fake ssh/rsync transport paths
- checksum mismatch / missing / timeout failures
- duplicate dispatch / forced redispatch record
- pull reconcile source-host marker
- pane submit failure lease release
- parent_ready_check closeout guard
EOF

cat "$MD_REPORT"
exit "$pytest_rc"

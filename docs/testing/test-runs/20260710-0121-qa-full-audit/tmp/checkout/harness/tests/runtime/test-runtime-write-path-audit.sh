#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${HOME}/.solar/harness"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/lib" "$TMP/tools" "$TMP/reports"

cat > "$TMP/lib/events.sh" <<'SH'
emit_event() {
  echo "$json_line" >> "$HARNESS_DIR/sprints/${sid}.events.jsonl"
  python3 "$HARNESS_DIR/lib/runtime_bridge.py" event "$sid" "$event" "$actor" "$payload" --quiet
}
SH

cat > "$TMP/lib/good_writer.py" <<'PY'
from runtime_bridge import record_legacy_event
event_file = "sprint-x.events.jsonl"
with open(event_file, "a") as f:
    f.write("{}\n")
record_legacy_event("sprint-x", "sample", "test", {})
PY

cat > "$TMP/tools/bad_status.py" <<'PY'
import json
sf = "sprint-x.status.json"
with open(sf, "w") as f:
    json.dump({"status": "passed"}, f)
PY

cat > "$TMP/tools/bad_event.py" <<'PY'
event_file = "sprint-x.events.jsonl"
with open(event_file, "a") as f:
    f.write("{}\n")
PY

cat > "$TMP/reports/ignored.py" <<'PY'
open("ignored.status.json", "w").write("{}")
PY

set +e
out="$(python3 "$REAL_HARNESS/lib/runtime_write_path_audit.py" --root "$TMP" --json)"
rc=$?
set -e

[[ "$rc" -eq 1 ]] || { echo "FAIL expected nonzero with direct status write, got $rc"; echo "$out"; exit 1; }

python3 - "$out" <<'PY'
import json
import sys

d = json.loads(sys.argv[1])
assert d["counts"]["error"] == 1, d
assert d["counts"]["warn"] == 1, d
assert d["counts"]["ok"] == 1, d
paths = {f["path"]: f for f in d["findings"]}
assert "tools/bad_status.py" in paths, paths
assert "tools/bad_event.py" in paths, paths
assert "lib/good_writer.py" in paths, paths
assert "reports/ignored.py" not in paths, paths
print("PASS runtime write-path audit classifies ok/warn/error")
PY

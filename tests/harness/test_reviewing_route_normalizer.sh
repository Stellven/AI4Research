#!/usr/bin/env bash
set -euo pipefail

ROOT="${HARNESS_DIR:-$HOME/.solar/harness}"
TMP="$(mktemp -d /tmp/solar-review-route.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

status="$TMP/sprint-route.status.json"
cat >"$status" <<'JSON'
{
  "id": "sprint-route",
  "status": "reviewing",
  "phase": "implementation_complete",
  "handoff_to": "builder",
  "target_role": "builder",
  "history": []
}
JSON

out="$(python3 "$ROOT/lib/reviewing_route_normalizer.py" "$status")"
[[ "$out" == "normalized" ]]

python3 - "$status" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d["handoff_to"] == "evaluator"
assert d["target_role"] == "evaluator"
assert any(h.get("event") == "review_route_normalized" for h in d.get("history", []))
PY

stable="$TMP/sprint-stable.status.json"
cat >"$stable" <<'JSON'
{
  "id": "sprint-stable",
  "status": "reviewing",
  "phase": "implementation_complete",
  "handoff_to": "evaluator",
  "target_role": "evaluator",
  "history": []
}
JSON
out="$(python3 "$ROOT/lib/reviewing_route_normalizer.py" "$stable")"
[[ "$out" == "unchanged" ]]

echo "reviewing route normalizer: PASS"

#!/usr/bin/env bash
# Regression: installer doctor exposes TVS renderer readiness and smoke result.
set -euo pipefail

HARNESS_DIR_REAL="$(cd "$(dirname "$0")/../.." && pwd)"
TVS_ROOT="${SOLAR_TVS_ROOT:-$HOME/TVS}"

if [[ ! -f "$TVS_ROOT/index.ts" ]]; then
  echo "SKIP: TVS root not found at $TVS_ROOT"
  exit 0
fi

JSON_OUT="$(HARNESS_DIR="$HARNESS_DIR_REAL" SOLAR_TVS_ROOT="$TVS_ROOT" bash "$HARNESS_DIR_REAL/installer/doctor.sh" --json)"
JSON_OUT="$JSON_OUT" python3 - <<'PY'
import json
import os

d = json.loads(os.environ["JSON_OUT"])
tvs = d.get("services", {}).get("tvs_renderer")
assert isinstance(tvs, dict), "services.tvs_renderer missing"
assert tvs.get("bun") == "ok", tvs
assert tvs.get("cli") == "ok", tvs
assert tvs.get("root") == "ok", tvs
assert tvs.get("smoke") == "ok", tvs
assert tvs.get("status") == "ok", tvs
PY

SUMMARY_OUT="$(HARNESS_DIR="$HARNESS_DIR_REAL" SOLAR_TVS_ROOT="$TVS_ROOT" bash "$HARNESS_DIR_REAL/installer/doctor.sh" --summary)"
grep -q "TVS:" <<<"$SUMMARY_OUT" || { echo "FAIL: summary missing TVS line"; exit 1; }
grep -q "smoke=ok" <<<"$SUMMARY_OUT" || { echo "FAIL: summary missing TVS smoke ok"; exit 1; }

BAD_ROOT="$(mktemp -d)"
trap 'rm -rf "$BAD_ROOT"' EXIT
# doctor.sh now exits nonzero on a failing verdict (this BAD_ROOT case is a
# deliberate "fail"); tolerate that so we can still inspect the JSON body.
BAD_JSON="$(HARNESS_DIR="$HARNESS_DIR_REAL" SOLAR_TVS_ROOT="$BAD_ROOT" bash "$HARNESS_DIR_REAL/installer/doctor.sh" --json || true)"
BAD_JSON="$BAD_JSON" python3 - <<'PY'
import json
import os

d = json.loads(os.environ["BAD_JSON"])
tvs = d.get("services", {}).get("tvs_renderer", {})
assert d.get("verdict") == "fail", d
assert tvs.get("status") == "missing", tvs
assert tvs.get("root") == "missing", tvs
assert tvs.get("smoke") == "not_run", tvs
PY

echo "PASS: installer doctor exposes TVS renderer readiness"

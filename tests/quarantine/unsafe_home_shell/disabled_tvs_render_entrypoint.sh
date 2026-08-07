#!/usr/bin/env bash
# Regression: `solar-harness tvs render` routes structured JSON into TVS.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v bun >/dev/null 2>&1 || { echo "SKIP: bun not found"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP"/lib

cp solar-harness.sh "$TMP/solar-harness.sh"
cp lib/run-state.sh "$TMP/lib/run-state.sh"
cp lib/events.sh "$TMP/lib/events.sh"
cp lib/tvs_render_cli.ts "$TMP/lib/tvs_render_cli.ts"

python3 - "$TMP/solar-harness.sh" "$TMP" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
tmp = sys.argv[2]
s = p.read_text()
s = s.replace('HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"', f'HARNESS_DIR="${{HARNESS_DIR:-{tmp}}}"', 1)
p.write_text(s)
PY
chmod +x "$TMP/solar-harness.sh"

cat > "$TMP/v1.json" <<'JSON'
{
  "canvas": {"width": 52},
  "style": "solar_default",
  "root": {
    "type": "card",
    "header": "Harness TVS",
    "sections": [
      {
        "type": "kv",
        "items": [
          {"key": "Status", "value": "OK", "status": "success"},
          {"key": "Route", "value": "solar-harness tvs render"}
        ]
      }
    ]
  }
}
JSON

SOLAR_TVS_ROOT="${SOLAR_TVS_ROOT:-$HOME/TVS}" \
  HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" tvs render --width 52 --colors off < "$TMP/v1.json" > "$TMP/v1.out"
grep -q "Harness TVS" "$TMP/v1.out" || { echo "FAIL: v1 title not rendered"; exit 1; }
grep -q "Status" "$TMP/v1.out" || { echo "FAIL: v1 kv not rendered"; exit 1; }
grep -q "Powered by TVS" "$TMP/v1.out" || { echo "FAIL: TVS footer missing"; exit 1; }

cat > "$TMP/v2.json" <<'JSON'
{
  "canvas": {"width": 52},
  "style": "enterprise_minimal",
  "layout": {
    "type": "card",
    "sections": [
      {"type": "header", "text": "TVS V2"},
      {"type": "divider"},
      {
        "type": "kv",
        "items": [
          {"key": "Mode", "value": "v2"},
          {"key": "Status", "value": "OK", "status": "success"}
        ]
      }
    ]
  }
}
JSON

SOLAR_TVS_ROOT="${SOLAR_TVS_ROOT:-$HOME/TVS}" \
  HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" tvs render --mode v2 --width 52 < "$TMP/v2.json" > "$TMP/v2.out"
grep -q "TVS V2" "$TMP/v2.out" || { echo "FAIL: v2 title not rendered"; exit 1; }
grep -q "Mode" "$TMP/v2.out" || { echo "FAIL: v2 kv not rendered"; exit 1; }

if printf '{bad json' | SOLAR_TVS_ROOT="${SOLAR_TVS_ROOT:-$HOME/TVS}" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" tvs render >"$TMP/bad.out" 2>"$TMP/bad.err"; then
  echo "FAIL: invalid JSON should fail"
  exit 1
fi
grep -q "invalid JSON" "$TMP/bad.err" || { echo "FAIL: invalid JSON error not surfaced"; exit 1; }

echo "PASS: solar-harness tvs render routes structured JSON into TVS"

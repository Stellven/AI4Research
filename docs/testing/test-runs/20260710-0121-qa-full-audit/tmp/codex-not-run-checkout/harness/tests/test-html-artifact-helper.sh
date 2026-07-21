#!/usr/bin/env bash
# Regression: HTML artifacts are registered/opened fail-open and never become a workflow gate.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HELPER="$HARNESS_DIR_REAL/lib/html_artifact.py"
GUARD="$HARNESS_DIR_REAL/lib/workflow_guard.py"

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

export HARNESS_DIR="$TMPDIR_TEST/harness"
export SPRINTS_DIR="$HARNESS_DIR/sprints"
mkdir -p "$SPRINTS_DIR"

SID="sprint-html-artifact-test"
STATUS="$SPRINTS_DIR/${SID}.status.json"
HTML="$SPRINTS_DIR/${SID}.prd.html"
PLANNING_HTML="$SPRINTS_DIR/${SID}.planning.html"
OPEN_LOG="$TMPDIR_TEST/open.log"
OPEN_MOCK="$TMPDIR_TEST/open-mock.sh"

cat > "$STATUS" <<JSON
{
  "id": "$SID",
  "status": "drafting",
  "phase": "spec",
  "handoff_to": "pm",
  "artifacts": {}
}
JSON

cat > "$HTML" <<'HTML'
<!doctype html><html><body><h1>PRD</h1></body></html>
HTML

cat > "$OPEN_MOCK" <<'SH'
#!/usr/bin/env bash
echo "$1" >> "$OPEN_LOG"
SH
chmod +x "$OPEN_MOCK"
export OPEN_LOG

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "PASS: $*"; }

SOLAR_HTML_AUTO_OPEN=0 python3 "$HELPER" register --sid "$SID" --kind prd_html --path "$HTML" --json >/tmp/solar-html-helper-register.json \
  || fail "helper register returned non-zero"

SOLAR_HTML_OPEN_CMD="$OPEN_MOCK" python3 "$HELPER" register --sid "$SID" --kind prd_html --path "$HTML" --json >/tmp/solar-html-helper-open.json \
  || fail "helper open returned non-zero"

python3 - "$STATUS" <<'PY' || fail "prd_html not registered as sprints-relative artifact"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["artifacts"]["prd_html"].endswith("sprint-html-artifact-test.prd.html")
assert d["artifacts"]["prd_html"].startswith("sprints/")
PY
ok "registers prd_html in status artifacts"

grep -Fq "$HTML" "$OPEN_LOG" || fail "mock open did not receive html path"
ok "opens HTML when enabled"

cat > "$PLANNING_HTML" <<'HTML'
<!doctype html><html><body><h1>Planning</h1></body></html>
HTML

before_count="$(wc -l < "$OPEN_LOG" | tr -d ' ')"
SOLAR_HTML_AUTO_OPEN=0 SOLAR_HTML_OPEN_CMD="$OPEN_MOCK" \
  python3 "$HELPER" register --sid "$SID" --kind planning_html --path "$PLANNING_HTML" --json >/tmp/solar-html-helper-disabled.json \
  || fail "helper disabled-open returned non-zero"
after_count="$(wc -l < "$OPEN_LOG" | tr -d ' ')"
[[ "$before_count" == "$after_count" ]] || fail "SOLAR_HTML_AUTO_OPEN=0 still opened browser"
ok "respects SOLAR_HTML_AUTO_OPEN=0"

python3 - "$STATUS" <<'PY' || fail "planning_html not registered"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["artifacts"]["planning_html"] == "sprints/sprint-html-artifact-test.planning.html"
PY
ok "registers planning_html in status artifacts"

python3 "$HELPER" register --sid "$SID" --kind prd_html --path "$SPRINTS_DIR/missing.html" --json >/tmp/solar-html-helper-missing.json \
  || fail "missing html should fail-open with zero exit"
ok "missing HTML is fail-open"

printf '# PRD\n' > "$SPRINTS_DIR/${SID}.prd.md"
printf '# Design\n' > "$SPRINTS_DIR/${SID}.design.md"
printf '# Plan\n' > "$SPRINTS_DIR/${SID}.plan.md"
cat > "$SPRINTS_DIR/${SID}.task_graph.json" <<'JSON'
{
  "sprint_id": "sprint-html-artifact-test",
  "nodes": [
    {
      "id": "S1",
      "goal": "test",
      "depends_on": [],
      "write_scope": ["harness/example"],
      "read_scope": ["harness"],
      "required_skills": ["bash"],
      "preferred_model": "sonnet",
      "gate": "G1",
      "acceptance": ["ok"],
      "estimated_cost": 1
    }
  ]
}
JSON

rm -f "$PLANNING_HTML"
route_json="$(python3 "$GUARD" route "$SID" --json)"
python3 - "$route_json" <<'PY' || fail "workflow_guard routed away from builder when planning_html missing"
import json, sys
d = json.loads(sys.argv[1])
assert d["route_role"] == "builder_main", d
assert d["artifacts"]["planning_html"] is False
PY
ok "missing planning_html does not block builder route"

echo "PASS"

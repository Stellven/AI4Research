#!/usr/bin/env bash
set -euo pipefail

ROOT="${HARNESS_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
RENDER="$ROOT/lib/render_sprint_html.py"
HELPER="$ROOT/lib/html_artifact.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "PASS: $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SID="sprint-html-anything-test"
SPRINTS="$TMP/sprints"
mkdir -p "$SPRINTS"

cat > "$SPRINTS/${SID}.status.json" <<JSON
{
  "id": "$SID",
  "title": "HTML Anything Default Renderer Test",
  "status": "drafting",
  "phase": "planning_complete",
  "handoff_to": "builder_main",
  "priority": "P0",
  "lane_hint": "html-rendering",
  "artifacts": {}
}
JSON

cat > "$SPRINTS/${SID}.prd.md" <<'MD'
# Product

## Goal

- Switch Solar default HTML rendering to html-anything.
MD

cat > "$SPRINTS/${SID}.contract.md" <<'MD'
## Contract

- self-contained html
- default renderer must not be legacy
MD

cat > "$SPRINTS/${SID}.design.md" <<'MD'
## Architecture

- adapter layer
- design_html support
MD

cat > "$SPRINTS/${SID}.plan.md" <<'MD'
## Plan

1. render prd
2. render planning
3. render design
MD

cat > "$SPRINTS/${SID}.task_graph.json" <<'JSON'
{
  "nodes": [
    {
      "id": "N1",
      "goal": "adapter",
      "preferred_model": "builder",
      "required_skills": ["rendering"],
      "gate": "G_DEFAULT",
      "depends_on": [],
      "write_scope": ["harness/lib"],
      "acceptance": ["default renderer"]
    }
  ]
}
JSON

python3 -m py_compile "$RENDER" "$HELPER" "$ROOT/lib/html_anything_adapter.py" || fail "python syntax"

for kind in prd planning design; do
  SOLAR_HTML_AUTO_OPEN=0 HARNESS_DIR="$ROOT" SPRINTS_DIR="$SPRINTS" \
    python3 "$RENDER" render --sid "$SID" --kind "$kind" --register --json > "$TMP/$kind.json" || fail "render $kind"
  OUT="$SPRINTS/${SID}.${kind}.html"
  [[ -f "$OUT" ]] || fail "missing output $OUT"
  grep -Fq 'meta name="x-solar-renderer" content="html-anything"' "$OUT" || fail "$kind missing html-anything marker"
  ! grep -Eiq 'href="https?://|src="https?://|<link[^>]+stylesheet' "$OUT" || fail "$kind not self-contained"
done
ok "renders prd/planning/design via html-anything adapter"

python3 - "$SPRINTS/${SID}.status.json" <<'PY' || fail "status artifacts missing registrations"
import json, sys
data = json.load(open(sys.argv[1]))
arts = data["artifacts"]
assert arts["prd_html"].endswith(".prd.html")
assert arts["planning_html"].endswith(".planning.html")
assert arts["design_html"].endswith(".design.html")
PY
ok "registers prd_html planning_html design_html"

SOLAR_USE_LEGACY_RENDERER=1 SOLAR_HTML_AUTO_OPEN=0 HARNESS_DIR="$ROOT" SPRINTS_DIR="$SPRINTS" \
  python3 "$RENDER" render --sid "$SID" --kind prd --json > "$TMP/legacy.json" || fail "legacy render"
python3 - "$TMP/legacy.json" <<'PY' || fail "legacy override not reflected"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["renderer"] == "legacy"
PY
ok "legacy override remains available"

echo "PASS"

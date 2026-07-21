#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HARNESS_DIR="$ROOT"
export SOLAR_MULTI_TASK_OPERATORS="$ROOT/config/physical-operators.json"

python3 -m py_compile "$ROOT/lib/multi_task_runner.py"
python3 -m json.tool "$ROOT/config/physical-operators.json" >/dev/null

ROOT="$ROOT" python3 - <<'PY'
import os
import sys
from pathlib import Path

root = Path(os.environ["ROOT"])
sys.path.insert(0, str(root / "lib"))
import multi_task_runner as m

cases = [
    (
        {"id": "impl", "role": "builder", "operator_selector": {"task_type": "implementation"}},
        "builder",
    ),
    (
        {"id": "kb", "role": "builder", "operator_selector": {"task_type": "knowledge-extraction"}},
        "knowledge-extractor",
    ),
    (
        {"id": "plan", "preferred_operator": "mini-claude-opus-planner"},
        "planner",
    ),
]

for node, profile_name in cases:
    selected = m.select_profile(node)
    assert selected.get("operator_id"), (node, selected)
    assert selected.get("role") == profile_name or selected.get("name") == profile_name, (node, selected)

legacy = m.select_profile({"id": "legacy", "role": "builder"})
assert legacy.get("name") == "builder", legacy
assert legacy.get("operator_id") in (None, ""), legacy

disabled = m.select_profile({"id": "agy", "preferred_operator": "mini-antigravity-gemini35-flash-high"})
assert disabled.get("name") == "builder", disabled
assert "preferred_operator_unavailable" in disabled.get("operator_fallback_reason", ""), disabled

image_op = m.resolve_operator("mini-antigravity-gemini35-flash-image")
ok, reason = m.operator_dispatchable(image_op)
assert not ok, (ok, reason)
assert "image" not in image_op.get("input_modalities", []), image_op
assert image_op.get("disabled_reason"), image_op
assert image_op.get("command"), image_op

diagram = m.select_profile({
    "id": "diagram",
    "role": "builder",
    "operator_selector": {"task_type": "technology-diagram"},
    "goal": "generate a technology architecture diagram",
})
assert diagram.get("name") == "browser-agent", diagram
assert diagram.get("operator_id") == "technology-diagram-painter", diagram

diagram_op = m.resolve_operator("technology-diagram-painter")
ok, reason = m.operator_dispatchable(diagram_op)
assert ok, (ok, reason)
assert "image" in diagram_op.get("output_modalities", []), diagram_op
assert "technology_diagram_painter_operator.py" in diagram_op.get("command", ""), diagram_op

assert not m.QUOTA_RE.search("quota cycle monthly; quota refresh unknown")
assert m.QUOTA_RE.search("API Error 429 quota exceeded")

print("physical_operator_registry_ok")
PY

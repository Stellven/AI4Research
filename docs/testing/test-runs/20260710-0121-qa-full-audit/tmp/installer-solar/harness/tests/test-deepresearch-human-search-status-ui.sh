#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
export HARNESS_DIR

python3 - <<'PY'
import importlib.util
import json
import os
import tempfile
from pathlib import Path

harness = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
routes_path = harness / "status-server" / "research_routes.py"
spec = importlib.util.spec_from_file_location("research_routes_human_search_status_smoke", routes_path)
routes = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(routes)  # type: ignore[union-attr]

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    handoff = root / "sprint-smoke.R2-human-search-handoff.md"
    results = root / "sprint-smoke.R2-human-search-results.md"
    graph = root / "sprint-smoke.task_graph.json"
    handoff.write_text("# handoff\n", encoding="utf-8")
    graph.write_text(json.dumps({
        "sprint_id": "sprint-smoke",
        "nodes": [{
            "id": "R2_external_search",
            "goal": "wait for human search",
            "status": "waiting_human_search",
            "human_search": {
                "status": "waiting",
                "provider": "human",
                "run_id": "sprint-smoke",
                "handoff_md": str(handoff),
                "results_md": str(results),
                "import_command": "solar-harness research import-search ..."
            }
        }]
    }), encoding="utf-8")

    data = routes.discover_human_search_waiting(root, "sprint-smoke")
    if data.get("status") != "waiting" or data.get("count") != 1:
        raise SystemExit(f"expected waiting/count=1, got {data}")
    item = data["items"][0]
    if item.get("node_id") != "R2_external_search":
        raise SystemExit(f"wrong node projected: {item}")
    if item.get("handoff_exists") is not True:
        raise SystemExit(f"handoff file was not projected as existing: {item}")
    if item.get("ready_to_import") is not False:
        raise SystemExit(f"results should not be ready before file exists: {item}")

    results.write_text("# results\n", encoding="utf-8")
    data = routes.discover_human_search_waiting(root, "sprint-smoke")
    item = data["items"][0]
    if item.get("results_exists") is not True or item.get("ready_to_import") is not True:
        raise SystemExit(f"results-ready state not projected: {item}")

    payload = routes.build_research_payload(root, "sprint-smoke")
    if payload.get("human_search", {}).get("count") != 1:
        raise SystemExit(f"build_research_payload lost human_search: {payload}")

    md = routes.generate_markdown_report(root, "sprint-smoke")
    if "Human Search Waiting" not in md or "R2_external_search" not in md:
        raise SystemExit("markdown report does not include human-search waiting section")

print(json.dumps({"ok": True, "feature": "deepresearch_human_search_status_ui"}, ensure_ascii=False))
PY

echo "PASS: DeepResearch human-search waiting state projects into status payloads"

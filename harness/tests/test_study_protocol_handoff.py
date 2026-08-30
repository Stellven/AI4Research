from __future__ import annotations

import sys
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
if str(HARNESS_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT / "lib"))

from lib import elastic_planner
from plugins.autosci.operators.scientific_lifecycle.action.delivery import (
    _render_study_protocol,
    _study_protocol_evidence,
)
from plugins.autosci.operators.scientific_lifecycle.evidence.operators import (
    _study_protocol,
)


LITERATURE_DISCOVERY = "schema:schemas/evidence/literature_discovery.v1.schema.json"
SCIENTIFIC_REPORT = "schema:schemas/evidence/scientific_report.v1.schema.json"
REPORT_PLAN_CAPSULES = {
    "cap.research-report-plan",
    "cap.research-method-aware-report-plan",
}


class _InlineContext:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    @staticmethod
    def input_artifact_refs() -> list[dict]:
        return []


def test_discovery_protocol_marks_missing_time_range_without_inventing_it() -> None:
    protocol = _study_protocol(
        {"query": "KV cache compression"},
        {},
        query="KV cache compression",
        mode="topic",
        candidates=[
            {
                "candidate_id": "paper-1",
                "title": "KV Cache Quantization",
                "source_channels": ["semantic-scholar"],
            }
        ],
    )

    assert protocol["protocol_status"] == "partially_resolved"
    assert protocol["time_range"]["status"] == "unresolved"
    assert protocol["time_range"]["start"] is None
    assert protocol["unresolved_fields"] == ["time_range"]
    assert "semantic-scholar" in protocol["search_strategy"]


def test_report_handoff_preserves_and_renders_discovery_protocol() -> None:
    protocol = _study_protocol(
        {"query": "KV cache", "year": 2025},
        {"year": 2025},
        query="KV cache",
        mode="topic",
        candidates=[
            {
                "candidate_id": "paper-1",
                "title": "KV Cache Quantization",
                "source_channels": ["arxiv"],
            }
        ],
    )
    context = _InlineContext(
        {
            "literature_discovery": {
                "schema": "literature_discovery.v1",
                "outputs": {
                    "query": "KV cache",
                    "candidates": [{"candidate_id": "paper-1"}],
                    "study_protocol": protocol,
                },
                "limitations": [],
            }
        }
    )

    carried, evidence_ids, limitations = _study_protocol_evidence(context)
    rendered = _render_study_protocol(carried)

    assert carried == protocol
    assert evidence_ids == ["paper-1"]
    assert limitations == []
    assert "Search strategy" in rendered
    assert "2025 to 2025 (resolved)" in rendered
    assert "Unresolved protocol fields: none" in rendered


def test_every_admitted_report_composition_routes_discovery_into_report_planning() -> None:
    catalog = elastic_planner.build_planning_catalog_snapshot()
    node = {
        "node_id": "synthesize_report",
        "requirement_ids": ["R1"],
        "consumes": [LITERATURE_DISCOVERY],
        "produces": [
            {
                "artifact_type": SCIENTIFIC_REPORT,
                "materialization": {"kind": "file", "path": "report.json"},
                "verifier_ids": [],
            }
        ],
        "operator_requirements": {
            "effects": ["read", "write", "execute", "network"],
            "network": "required",
            "execution_trust": "any",
        },
    }

    row = elastic_planner._node_composition_row(node, catalog)
    admitted = set(row["admitted_candidate_ids"])
    assert admitted
    candidates = {
        candidate["candidate_id"]: candidate
        for candidate in row["search"]["candidates"]
        if candidate["candidate_id"] in admitted
    }
    assert candidates
    for candidate in candidates.values():
        planning_steps = [
            step
            for step in candidate["steps"]
            if step["capsule_id"] in REPORT_PLAN_CAPSULES
        ]
        assert planning_steps
        assert all(LITERATURE_DISCOVERY in step["consumes"] for step in planning_steps)

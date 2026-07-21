"""Partial closeout for completed reviewing nodes in HF Paper Flow S02 architecture."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture"
NODE_IDS = (
    "A1_architecture",
    "A2_data_models",
    "A3_interfaces",
    "A4_open_questions_resolutions",
    "A5_traceability_handoff",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _contains_all(text: str, snippets: list[str]) -> bool:
    return all(snippet in text for snippet in snippets)


def build_eval_payloads(sprint_root: Path) -> dict[str, dict[str, Any]]:
    architecture_doc = sprint_root / f"{SPRINT_ID}.architecture.md"
    architecture_handoff = sprint_root / f"{SPRINT_ID}.A1_architecture-handoff.md"
    data_models_doc = sprint_root / f"{SPRINT_ID}.data_models.md"
    data_models_handoff = sprint_root / f"{SPRINT_ID}.A2_data_models-handoff.md"
    interfaces_doc = sprint_root / f"{SPRINT_ID}.interfaces.md"
    interfaces_handoff = sprint_root / f"{SPRINT_ID}.A3_interfaces-handoff.md"
    oq_doc = sprint_root / f"{SPRINT_ID}.open_questions_resolutions.md"
    oq_handoff = sprint_root / f"{SPRINT_ID}.A4_open_questions_resolutions-handoff.md"
    traceability_doc = sprint_root / f"{SPRINT_ID}.traceability.json"
    parent_handoff = sprint_root / f"{SPRINT_ID}.handoff.md"

    architecture_text = architecture_doc.read_text(encoding="utf-8") if architecture_doc.exists() else ""
    architecture_handoff_text = architecture_handoff.read_text(encoding="utf-8") if architecture_handoff.exists() else ""
    data_models_text = data_models_doc.read_text(encoding="utf-8") if data_models_doc.exists() else ""
    data_models_handoff_text = data_models_handoff.read_text(encoding="utf-8") if data_models_handoff.exists() else ""
    interfaces_text = interfaces_doc.read_text(encoding="utf-8") if interfaces_doc.exists() else ""
    interfaces_handoff_text = interfaces_handoff.read_text(encoding="utf-8") if interfaces_handoff.exists() else ""
    oq_text = oq_doc.read_text(encoding="utf-8") if oq_doc.exists() else ""
    oq_handoff_text = oq_handoff.read_text(encoding="utf-8") if oq_handoff.exists() else ""
    traceability = json.loads(traceability_doc.read_text(encoding="utf-8")) if traceability_doc.exists() else {}
    parent_handoff_text = parent_handoff.read_text(encoding="utf-8") if parent_handoff.exists() else ""

    a1_conditions = [
        ("architecture_doc_exists", architecture_doc.exists()),
        ("architecture_handoff_exists", architecture_handoff.exists()),
        ("architecture_has_10_sections", "## §10" in architecture_text),
        ("architecture_handoff_records_ac1_ac8", _contains_all(architecture_handoff_text, ["AC1:", "AC8:"])),
    ]
    a2_conditions = [
        ("data_models_doc_exists", data_models_doc.exists()),
        ("data_models_handoff_exists", data_models_handoff.exists()),
        ("data_models_has_6_sections", "## §6" in data_models_text),
        ("data_models_mentions_6_core_entities", _contains_all(data_models_text, ["PaperSnapshot", "PaperCanonical", "PaperEnrichment", "PaperTaxonomy", "PaperSignal", "PaperEvidencePacket"])),
        ("data_models_mentions_4_graph_tables", _contains_all(data_models_text, ["paper_signal_graph", "paper_route_graph", "paper_resonance_graph", "paper_claim_graph"])),
        ("data_models_handoff_records_ac1_ac7", _contains_all(data_models_handoff_text, ["AC1:", "AC7:"])),
    ]
    a3_conditions = [
        ("interfaces_doc_exists", interfaces_doc.exists()),
        ("interfaces_handoff_exists", interfaces_handoff.exists()),
        ("interfaces_has_7_sections", "## §7" in interfaces_text),
        ("interfaces_collector_methods_present", _contains_all(interfaces_text, ["fetch_daily_snapshot", "fetch_weekly_snapshot", "fetch_monthly_snapshot"])),
        ("interfaces_enricher_methods_present", _contains_all(interfaces_text, ["enrich_hf", "enrich_arxiv", "enrich_hf_assets", "enrich_semantic_scholar", "enrich_github"])),
        ("interfaces_reasoning_methods_present", _contains_all(interfaces_text, ["call_high_model", "insight_gate_check", "resonance_gate_check", "compile_research_judgment"])),
        ("interfaces_handoff_records_ac1_ac7", _contains_all(interfaces_handoff_text, ["AC1:", "AC7:"])),
    ]
    a4_conditions = [
        ("oq_doc_exists", oq_doc.exists()),
        ("oq_handoff_exists", oq_handoff.exists()),
        ("oq_doc_has_5_questions", _contains_all(oq_text, ["OQ-01", "OQ-02", "OQ-03", "OQ-04", "OQ-05"])),
        ("oq_handoff_records_ac1_ac8", _contains_all(oq_handoff_text, ["AC1:", "AC8:"])),
    ]
    a5_conditions = [
        ("traceability_exists", traceability_doc.exists()),
        ("parent_handoff_exists", parent_handoff.exists()),
        ("traceability_schema_version_ok", traceability.get("schema_version") == "solar.s02_architecture.traceability.v1"),
        ("traceability_decisions_count_5", len(traceability.get("decisions") or []) == 5),
        ("traceability_oq_count_5", len(traceability.get("oq_resolutions") or []) == 5),
        ("traceability_module_inventory_ge_10", len(traceability.get("module_inventory") or []) >= 10),
        ("traceability_data_schema_inventory_ge_6", len(traceability.get("data_schema_inventory") or []) >= 6),
        ("traceability_downstream_has_s03_s04_s05", _contains_all(json.dumps(traceability, ensure_ascii=False), ["S03", "S04", "S05"])),
        ("handoff_mentions_a1_to_a4", _contains_all(parent_handoff_text, ["A1", "A2", "A3", "A4"])),
        ("handoff_mentions_hf_ranking_guardrail", "HF ranking" in parent_handoff_text and "raw paper list" in parent_handoff_text),
    ]

    def pack(node_id: str, conditions: list[tuple[str, bool]], summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
        passed = [label for label, ok in conditions if ok]
        failed = [label for label, ok in conditions if not ok]
        return {
            "sprint_id": SPRINT_ID,
            "node_id": node_id,
            "round": 1,
            "verdict": "PASS" if not failed else "FAIL",
            "checked_at": _now(),
            "passed_conditions": passed,
            "failed_conditions": failed,
            "warnings": [],
            "evidence": evidence,
            "summary": summary,
        }

    return {
        "A1_architecture": pack(
            "A1_architecture",
            a1_conditions,
            "A1 architecture document and builder handoff evidence were present.",
            {"architecture_md": str(architecture_doc), "handoff_md": str(architecture_handoff)},
        ),
        "A2_data_models": pack(
            "A2_data_models",
            a2_conditions,
            "A2 data model document and builder handoff evidence were present.",
            {"data_models_md": str(data_models_doc), "handoff_md": str(data_models_handoff)},
        ),
        "A3_interfaces": pack(
            "A3_interfaces",
            a3_conditions,
            "A3 interface document and builder handoff evidence were present.",
            {"interfaces_md": str(interfaces_doc), "handoff_md": str(interfaces_handoff)},
        ),
        "A4_open_questions_resolutions": pack(
            "A4_open_questions_resolutions",
            a4_conditions,
            "A4 open-questions resolution document and builder handoff evidence were present.",
            {"open_questions_md": str(oq_doc), "handoff_md": str(oq_handoff)},
        ),
        "A5_traceability_handoff": pack(
            "A5_traceability_handoff",
            a5_conditions,
            "A5 traceability JSON and parent handoff evidence were present.",
            {"traceability_json": str(traceability_doc), "handoff_md": str(parent_handoff)},
        ),
    }


def auto_closeout_hf_s02_architecture(runtime_root: Path) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    payloads = build_eval_payloads(sprint_root)
    return auto_closeout_graph_nodes(
        graph_path=sprint_root / f"{SPRINT_ID}.task_graph.json",
        node_payloads=payloads,
        eval_json_paths={node_id: sprint_root / f"{SPRINT_ID}.{node_id}-eval.json" for node_id in NODE_IDS},
        reason="hf_s02_architecture_auto_closeout",
        actor="hf_s02_architecture_closeout",
        event="hf_s02_architecture_auto_closeout",
        dispatch_downstream=False,
    )

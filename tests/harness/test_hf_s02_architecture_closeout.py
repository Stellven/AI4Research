from pathlib import Path

from hf_s02_architecture_closeout import NODE_IDS, build_eval_payloads


def test_build_eval_payloads_from_docs_and_handoffs(tmp_path):
    sprint_root = tmp_path
    sid = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture"
    (sprint_root / f"{sid}.architecture.md").write_text("## §1\n...\n## §10\n", encoding="utf-8")
    (sprint_root / f"{sid}.A1_architecture-handoff.md").write_text("AC1:\n...\nAC8:\n", encoding="utf-8")
    (sprint_root / f"{sid}.data_models.md").write_text("PaperSnapshot\nPaperCanonical\nPaperEnrichment\nPaperTaxonomy\nPaperSignal\nPaperEvidencePacket\npaper_signal_graph\npaper_route_graph\npaper_resonance_graph\npaper_claim_graph\n## §6\n", encoding="utf-8")
    (sprint_root / f"{sid}.A2_data_models-handoff.md").write_text("AC1:\n...\nAC7:\n", encoding="utf-8")
    (sprint_root / f"{sid}.interfaces.md").write_text("fetch_daily_snapshot\nfetch_weekly_snapshot\nfetch_monthly_snapshot\nenrich_hf\nenrich_arxiv\nenrich_hf_assets\nenrich_semantic_scholar\nenrich_github\ncall_high_model\ninsight_gate_check\nresonance_gate_check\ncompile_research_judgment\n## §7\n", encoding="utf-8")
    (sprint_root / f"{sid}.A3_interfaces-handoff.md").write_text("AC1:\n...\nAC7:\n", encoding="utf-8")
    (sprint_root / f"{sid}.open_questions_resolutions.md").write_text("OQ-01\nOQ-02\nOQ-03\nOQ-04\nOQ-05\n", encoding="utf-8")
    (sprint_root / f"{sid}.A4_open_questions_resolutions-handoff.md").write_text("AC1:\n...\nAC8:\n", encoding="utf-8")
    (sprint_root / f"{sid}.traceability.json").write_text(
        '{"schema_version":"solar.s02_architecture.traceability.v1","decisions":[1,2,3,4,5],"oq_resolutions":[1,2,3,4,5],"module_inventory":[1,2,3,4,5,6,7,8,9,10],"data_schema_inventory":[1,2,3,4,5,6],"downstream_sprint_kickoff_package":{"S03":[],"S04":[],"S05":[]}}',
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.handoff.md").write_text("A1 A2 A3 A4 HF ranking raw paper list\n", encoding="utf-8")

    payloads = build_eval_payloads(sprint_root)

    assert set(payloads) == set(NODE_IDS)
    assert all(payload["verdict"] == "PASS" for payload in payloads.values())

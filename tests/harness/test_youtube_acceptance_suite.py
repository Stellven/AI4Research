import json
import sys
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parents[2] / 'harness') / "lib"))

from youtube.acceptance_suite import (
    REPORT_NAMES,
    NODE_IDS,
    auto_closeout_s03_runtime,
    build_closeout_eval_payloads,
    run_pollution_report,
    generate_acceptance_reports,
    generate_traceability_and_handoff,
)


def test_generate_reports_and_traceability(tmp_path):
    root = Path("~/Solar/harness")
    report_dir = tmp_path / "reports"
    reports = generate_acceptance_reports(root, report_dir)
    assert set(reports) == set(REPORT_NAMES)
    assert all((report_dir / f"{name}.json").exists() for name in REPORT_NAMES)
    traceability_path, handoff_path = generate_traceability_and_handoff(
        sprint_root=tmp_path,
        report_dir=report_dir,
        reports=reports,
        knowledge_context="test-context",
    )
    assert traceability_path.exists()
    assert handoff_path.exists()
    payload = json.loads(traceability_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "solar.s03_core_runtime.traceability.v1"
    assert "acceptance_reports" in payload


def test_build_closeout_eval_payloads_and_auto_closeout(monkeypatch, tmp_path):
    root = Path("~/Solar/harness")
    report_dir = tmp_path / "reports"
    reports = generate_acceptance_reports(root, report_dir)
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    sprint_root.mkdir(parents=True, exist_ok=True)
    graph_path = sprint_root / "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime.task_graph.json"
    status_path = sprint_root / "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime.status.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime",
                "nodes": [
                    {"id": "B3_phase3_application", "status": "worker_blocked", "depends_on": []},
                    {"id": "B4_phase4_interface", "status": "", "depends_on": ["B3_phase3_application"]},
                    {"id": "B5_acceptance_gates", "status": "", "depends_on": ["B4_phase4_interface"]},
                    {"id": "B6_traceability_handoff", "status": "", "depends_on": ["B5_acceptance_gates"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps({"id": "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime", "status": "active"}, ensure_ascii=False),
        encoding="utf-8",
    )
    traceability_path, handoff_path = generate_traceability_and_handoff(
        sprint_root=sprint_root,
        report_dir=report_dir,
        reports=reports,
        knowledge_context="test-context",
    )
    payloads = build_closeout_eval_payloads(
        root=root,
        report_dir=report_dir,
        sprint_root=sprint_root,
        traceability_path=traceability_path,
        handoff_path=handoff_path,
        reports=reports,
    )
    assert set(payloads) == set(NODE_IDS)
    assert all(payload["verdict"] == "PASS" for payload in payloads.values())

    verdict_calls = []

    def _fake_node_verdict(*, graph_path, node_id, eval_json_path, reason, dispatch_downstream):
        verdict_calls.append((str(graph_path), node_id, str(eval_json_path), reason, dispatch_downstream))
        return {"ok": True, "node": node_id, "status": "passed"}

    def _fake_status_sync(*, graph_path, actor, event):
        return {
            "ok": True,
            "status_path": str(graph_path).replace(".task_graph.json", ".status.json"),
            "actor": actor,
            "event": event,
        }

    monkeypatch.setattr("acceptance_closeout.invoke_node_verdict", _fake_node_verdict)
    monkeypatch.setattr("acceptance_closeout.invoke_status_sync", _fake_status_sync)

    closeout = auto_closeout_s03_runtime(
        root=root,
        runtime_root=runtime_root,
        report_dir=report_dir,
        traceability_path=traceability_path,
        handoff_path=handoff_path,
        reports=reports,
    )
    assert closeout["ok"] is True
    assert len(verdict_calls) == 4
    for node_id in NODE_IDS:
        eval_json = sprint_root / f"sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime.{node_id}-eval.json"
        assert eval_json.exists()


def test_run_pollution_report_uses_schema_aware_audit(tmp_path):
    root = Path("~/Solar/harness")
    report = run_pollution_report(root, tmp_path)
    assert report["ok"] is True
    assert report["seed_count"] == 165
    assert report["remaining_count"] == 0
    assert "pollution_types" in report

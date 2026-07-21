from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parent.parent
STATUS_SERVER = HARNESS_ROOT / "lib" / "symphony" / "status-server.py"


def load_status_server():
    spec = importlib.util.spec_from_file_location("solar_status_server_autoresearch_test", str(STATUS_SERVER))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_autoresearch_impact_summary_uses_status_artifact(tmp_path):
    mod = load_status_server()
    sid = "sprint-20260519-autoresearch-impact"
    (tmp_path / f"{sid}.prd.md").write_text(
        "# PRD\n\n## 目标\n\n让 Autoresearch 在失败评审后减少 Builder 返工轮次。\n",
        encoding="utf-8",
    )
    (tmp_path / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "status": "failed_review",
                "phase": "eval_failed",
                "artifacts": {
                    "autoresearch_optimizer": {
                        "recorded_at": "2026-05-19T20:10:00Z",
                        "canonical_role": "builder",
                        "recommended": True,
                        "trigger_level": "strong",
                        "telemetry": {
                            "round": 2,
                            "eval_verdict": "FAIL",
                            "failed_conditions": ["missing_evidence", "weak_stop_rule"],
                            "error_count": 1,
                            "warning_count": 0,
                        },
                        "quality_metrics": {
                            "expected_effect": ["reduce_repair_rounds"],
                            "must_measure": ["repair_round_delta", "eval_failure_recurrence"],
                        },
                        "execution_policy": {"replaces_builder": False},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mod.SPRINTS_DIR = tmp_path

    summary = mod._autoresearch_impact_summary()

    assert summary["status"] == "warn"
    assert summary["count"] == 1
    assert summary["strong_count"] == 1
    assert summary["fail_verdict_count"] == 1
    assert summary["trend"]["effect_status"] == "warn"
    assert summary["trend"]["pass_after_trigger"] == 0
    assert summary["trend"]["still_failing"] == 1
    assert summary["trend"]["fail_recurrence"] == 1
    assert summary["trend"]["avg_round"] == 2
    assert summary["roles"] == {"builder": 1}
    latest = summary["latest"]
    assert latest["sid"] == sid
    assert latest["task_description"] == "让 Autoresearch 在失败评审后减少 Builder 返工轮次。"
    assert latest["failed_conditions"] == ["missing_evidence", "weak_stop_rule"]
    assert latest["must_measure"] == ["repair_round_delta", "eval_failure_recurrence"]


def test_status_payload_includes_autoresearch_impact(monkeypatch, tmp_path):
    mod = load_status_server()
    sid = "sprint-20260519-autoresearch-payload"
    (tmp_path / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "status": "active",
                "phase": "implementation",
                "artifacts": {
                    "autoresearch_optimizer": {
                        "canonical_role": "planner",
                        "recommended": True,
                        "trigger_level": "recommended",
                        "telemetry": {"round": 1, "eval_verdict": "", "failed_conditions": []},
                        "quality_metrics": {"must_measure": ["evidence_gap_count"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    mod.SPRINTS_DIR = tmp_path
    monkeypatch.setattr(mod, "_pane_info", lambda: [])
    monkeypatch.setattr(mod, "_main_screen", lambda *args, **kwargs: {})
    monkeypatch.setattr(mod, "_lab_screen", lambda *args, **kwargs: {})
    monkeypatch.setattr(mod, "_read_jsonl", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod, "_kpi", lambda: {})
    monkeypatch.setattr(mod, "_obsidian_wiki_readiness", lambda: {})
    monkeypatch.setattr(mod, "_mirage_status", lambda: {})
    monkeypatch.setattr(mod, "_capability_health_summary", lambda runtime: {})
    monkeypatch.setattr(mod, "_solar_kb_status", lambda: {})
    monkeypatch.setattr(mod, "_obsidian_sync_status", lambda: {})
    monkeypatch.setattr(mod, "_apple_notes_ingest_status", lambda: {})
    monkeypatch.setattr(mod, "_evolution_status", lambda: {})
    monkeypatch.setattr(mod, "_runtime_interfaces_status", lambda sprint_id: {})
    monkeypatch.setattr(mod, "_human_search_waiting_status", lambda: {})
    monkeypatch.setattr(mod, "_research_status_summary", lambda: {})

    payload = mod._status_payload()

    assert "autoresearch_impact" in payload
    assert payload["autoresearch_impact"]["latest"]["role"] == "planner"
    assert payload["autoresearch_impact"]["latest"]["must_measure"] == ["evidence_gap_count"]
    assert payload["autoresearch_impact"]["trend"]["effect_status"] == "mixed"


def test_autoresearch_impact_trend_counts_pass_after_trigger(tmp_path):
    mod = load_status_server()
    fixtures = [
        ("sprint-20260519-ar-pass", "passed", "planning_complete", "planner", "recommended", "", 1),
        ("sprint-20260519-ar-fail", "failed_review", "eval_failed", "builder", "strong", "FAIL", 3),
        ("sprint-20260519-ar-active", "active", "implementation", "builder", "recommended", "", 2),
    ]
    for sid, status, phase, role, trigger, verdict, round_no in fixtures:
        (tmp_path / f"{sid}.status.json").write_text(
            json.dumps(
                {
                    "id": sid,
                    "status": status,
                    "phase": phase,
                    "artifacts": {
                        "autoresearch_optimizer": {
                            "canonical_role": role,
                            "recommended": True,
                            "trigger_level": trigger,
                            "telemetry": {
                                "round": round_no,
                                "eval_verdict": verdict,
                                "failed_conditions": ["regression"] if verdict else [],
                                "error_count": 1 if verdict else 0,
                            },
                            "quality_metrics": {"must_measure": ["repair_round_delta"]},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
    mod.SPRINTS_DIR = tmp_path

    summary = mod._autoresearch_impact_summary(limit=10)

    assert summary["count"] == 3
    assert summary["trend"]["effect_status"] == "mixed"
    assert summary["trend"]["pass_after_trigger"] == 1
    assert summary["trend"]["still_failing"] == 1
    assert summary["trend"]["fail_recurrence"] == 1
    assert summary["trend"]["avg_round"] == 2
    assert summary["trend"]["max_round"] == 3

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "planner_bounce_dispatch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("planner_bounce_dispatch_test", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _harness(tmp_path: Path, sid: str) -> Path:
    harness = tmp_path / "harness"
    (harness / "sprints").mkdir(parents=True)
    (harness / "tools").mkdir()
    (harness / "run" / "pm-inbox").mkdir(parents=True)
    (harness / "sprints" / f"{sid}.status.json").write_text(
        json.dumps({"id": sid, "status": "drafting", "phase": "prd_ready"}),
        encoding="utf-8",
    )
    (harness / "sprints" / f"{sid}.plan-compile-errors.json").write_text(
        json.dumps(
            {
                "bounce_count": 1,
                "graph_hash": "bad-graph-hash",
                "exhausted": False,
                "terminal": False,
                "errors": [{"code": "AUTOSCI_GRAPH_NODE_CONTRACT_MISMATCH"}],
            }
        ),
        encoding="utf-8",
    )
    return harness


def test_nonterminal_rejection_dispatches_one_bounded_planner_and_updates_claim(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    sid = "sprint-bounce-once"
    harness = _harness(tmp_path, sid)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "OK\n task_id = pm-sprint-bounce-once-N0-cafefeed\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    first = module.dispatch_planner_bounce(harness, sid)
    second = module.dispatch_planner_bounce(harness, sid)

    assert first["ok"] is True
    assert first["task_id"] == "pm-sprint-bounce-once-N0-cafefeed"
    assert second["ok"] is True
    assert second["dispatch"] == "already_claimed"
    assert len(calls) == 1
    objective = calls[0][calls[0].index("--objective") + 1]
    assert "[Solar planner bounce 1]" in objective
    assert "do not create or alter a plan certificate" in objective
    assert "do not dispatch Builder or Evaluator" in objective
    status = json.loads((harness / "sprints" / f"{sid}.status.json").read_text(encoding="utf-8"))
    claim = status["planner_dispatch_claim"]
    assert claim["owner"] == "operator_pool"
    assert claim["task_id"] == first["task_id"]
    assert claim["planner_bounce_count"] == 1


def test_terminal_or_exhausted_rejection_never_dispatches(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    sid = "sprint-no-more-bounces"
    harness = _harness(tmp_path, sid)
    errors_path = harness / "sprints" / f"{sid}.plan-compile-errors.json"
    errors = json.loads(errors_path.read_text(encoding="utf-8"))
    errors.update({"bounce_count": 2, "exhausted": True, "terminal": True})
    errors_path.write_text(json.dumps(errors), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("terminal plan rejection must not dispatch Planner")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    result = module.dispatch_planner_bounce(harness, sid)

    assert result["ok"] is False
    assert result["state"] == "refused"
    assert not (harness / "run" / "planner-bounces").exists()


def test_existing_bounce_task_is_recovered_without_duplicate_submit(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    sid = "sprint-recover-bounce"
    harness = _harness(tmp_path, sid)
    task_id = f"pm-{sid}-N0-deadbeef"
    (harness / "run" / "pm-inbox" / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "requested_role": "planner",
                "objective": "[Solar planner bounce 1] repair",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("existing bounce task must be reused")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    result = module.dispatch_planner_bounce(harness, sid)

    assert result["ok"] is True
    assert result["dispatch"] == "recovered"
    assert result["task_id"] == task_id

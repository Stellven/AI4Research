from __future__ import annotations

import json
import os
import sys
import importlib.util
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import write_json


def test_p22_071_human_review_lifecycle_resume(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    lib = repo_root / "harness" / "lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))

    spec = importlib.util.spec_from_file_location("phase22_graph_scheduler", lib / "graph_scheduler.py")
    assert spec and spec.loader
    gs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gs)

    approval_statement = os.environ.get(
        "PHASE22_J21_HUMAN_APPROVAL_STATEMENT",
        "我批准 J21 Phase 22 lifecycle handoff 继续，审批人是 j50058254，时间是 2026-08-12。",
    )
    actor = "j50058254"
    rec = JourneyRecorder(repo_root, "P22-071")
    harness_dir = tmp_path / "harness"
    sprints = harness_dir / "sprints"
    sprints.mkdir(parents=True)
    sprint_id = "phase22-j21-human-review-resume"
    node_id = "j21-lifecycle-handoff"
    graph_path = sprints / f"{sprint_id}.task_graph.json"

    graph = {
        "id": sprint_id,
        "sprint_id": sprint_id,
        "nodes": [
            {
                "id": node_id,
                "status": "pending",
                "depends_on": [],
                "gate": "phase22-lifecycle-human-review",
                "max_repair_attempts": 2,
            }
        ],
        "node_results": {},
        "gate_results": {"phase22-lifecycle-human-review": {"status": "blocked"}},
        "events": [],
    }
    block = gs.enter_node_human_review(
        graph,
        node_id,
        reason="J21 Phase 22 lifecycle handoff requires attributable human approval before resume.",
        next_action="Record the user approval statement and resume the lifecycle handoff.",
        writer="phase22-lifecycle-gate",
        author_type="policy",
    )
    gs.save_graph(graph_path, graph)

    approval_evidence = write_json(
        rec.artifact_dir / "j21-human-approval-statement.json",
        {
            "schema": "phase22_human_approval_statement.v1",
            "issue_id": "P22-REPAIR-071",
            "journey_reference": "P22-J21",
            "actor": actor,
            "statement": approval_statement,
            "approval_date": "2026-08-12",
            "approved_action": "Continue J21 Phase 22 lifecycle handoff.",
        },
    )
    resume_reason = (
        "Approved J21 Phase 22 lifecycle handoff continuation; "
        f"actor={actor}; date=2026-08-12; approval_evidence={approval_evidence.name}"
    )

    env = dict(os.environ)
    env.update(
        {
            "HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_DIR": str(harness_dir),
            "HARNESS_SPRINTS_DIR": str(sprints),
            "SOLAR_GATE_LEDGER": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    resume = rec.run(
        "human-review-resume",
        [
            phase22_python,
            str(lib / "graph_node_dispatcher.py"),
            "resume-human-review",
            "--graph",
            str(graph_path),
            "--node",
            node_id,
            "--generation",
            str(block["generation"]),
            "--actor",
            actor,
            "--reason",
            resume_reason,
        ],
        cwd=repo_root,
        env=env,
        timeout=60,
    )
    second_resume = rec.run(
        "human-review-resume-replay-rejected",
        [
            phase22_python,
            str(lib / "graph_node_dispatcher.py"),
            "resume-human-review",
            "--graph",
            str(graph_path),
            "--node",
            node_id,
            "--generation",
            str(block["generation"]),
            "--actor",
            actor,
            "--reason",
            resume_reason,
        ],
        cwd=repo_root,
        env=env,
        timeout=60,
    )

    resume_payload = json.loads(resume.stdout) if resume.stdout.strip() else {}
    second_payload = json.loads(second_resume.stdout) if second_resume.stdout.strip() else {}
    persisted = gs.load_graph(graph_path)
    node = next(item for item in persisted["nodes"] if item["id"] == node_id)
    ledger_path = sprints / f"{sprint_id}.gate-ledger.jsonl"
    ledger_rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    resume_rows = [
        row
        for row in ledger_rows
        if row.get("writer") == "resume_human_review" and row.get("human_actor") == actor
    ]

    rec.add_artifact(graph_path, "human_review_graph")
    rec.add_artifact(ledger_path, "human_review_gate_ledger")
    rec.add_artifact(approval_evidence, "human_approval_statement")
    rec.add_assertion("human_review_block_created", block.get("state") == "blocked" and block.get("generation") == 1, block)
    rec.add_assertion("human_resume_completed", resume.returncode == 0 and resume_payload.get("ok") is True and resume_payload.get("actor") == actor, resume_payload)
    node_result = persisted.get("node_results", {}).get(node_id, {})
    rec.add_assertion(
        "graph_reopened_after_human_resume",
        gs.node_status(persisted, node_id) == "pending"
        and node.get("repair_context", {}).get("trigger") == "explicit_human_resume"
        and node_result.get("human_review", {}).get("state") == "resumed",
        node,
    )
    rec.add_assertion("ledger_records_human_author", bool(resume_rows) and resume_rows[-1].get("author", {}).get("type") == "human", resume_rows[-1] if resume_rows else {})
    rec.add_assertion("resume_is_one_shot", second_resume.returncode == 2 and second_payload.get("reason") == "node_not_waiting_for_human_review", second_payload)
    rec.add_l2(
        "Foundation",
        "Lifecycle, Parity & Human Review Evaluator",
        "The lifecycle handoff entered needs_human_review, resumed only with the attributable j50058254 approval statement, recorded a human-authored ledger transition, and rejected replay.",
        ledger_path,
        True,
    )
    status = "PASS" if all(item["passed"] for item in rec.assertions) else "FAIL"
    rec.finalize(status, limitations=[])

    assert resume.returncode == 0, resume.stderr
    assert second_resume.returncode == 2
    assert all(item["passed"] for item in rec.assertions)

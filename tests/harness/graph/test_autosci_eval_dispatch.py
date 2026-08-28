#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
ADAPTER = HARNESS / "plugins" / "autosci" / "bin" / "autosci_eval_adapter.py"
SCIENTIFIC_FIXTURES = Path(__file__).resolve().parents[1] / "evaluators" / "scientific" / "fixtures"
PASS_EVIDENCE = SCIENTIFIC_FIXTURES / "pass" / "research_paper.json"
FAIL_EVIDENCE = SCIENTIFIC_FIXTURES / "fail" / "research_paper.json"

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))


def _prepare_isolated_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copytree(HARNESS / "config", harness_dir / "config")
    for name in (
        "capability-capsules",
        "evaluators",
        "lib",
        "personas",
        "plugins",
        "schemas",
        "templates",
        "tools",
        "workflows",
    ):
        link = harness_dir / name
        try:
            link.symlink_to(HARNESS / name, target_is_directory=True)
        except OSError:
            shutil.copytree(HARNESS / name, link)
    (harness_dir / "run").mkdir()
    sprints = harness_dir / "sprints"
    sprints.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(sprints))

    import graph_node_dispatcher as gnd
    import graph_scheduler

    monkeypatch.setattr(gnd, "HARNESS_DIR", harness_dir)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "DISPATCH_LEDGER", harness_dir / "run" / "dispatch-ledger.jsonl")
    monkeypatch.setattr(gnd, "NO_DISPATCH_FLAG", harness_dir / "run" / "no-dispatch.flag")
    monkeypatch.setattr(gnd, "MULTI_TASK_RUN_DIR", harness_dir / "run" / "multi-task")
    monkeypatch.setattr(gnd, "_refresh_requirement_coverage_artifacts", lambda sid, dry_run=False: {"ok": True, "skipped": "test"})
    monkeypatch.setattr(graph_scheduler, "HARNESS_DIR", harness_dir)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(graph_scheduler, "STATE_DB", harness_dir / "run" / "state.db")
    return harness_dir, sprints


def _write_graph(
    sprints: Path,
    *,
    sid: str,
    evidence_path: Path,
    status: str = "reviewing",
    max_repair_attempts: int = 1,
) -> Path:
    relative_evidence = Path("artifacts") / "scientific" / sid / "paper_ingest" / "research_paper.v1.json"
    staged_evidence = sprints / sid / "workdir" / relative_evidence
    staged_evidence.parent.mkdir(parents=True, exist_ok=True)
    if evidence_path.is_file():
        shutil.copyfile(evidence_path, staged_evidence)
    graph = {
        "schema_version": "solar.task_graph.v1",
        "workflow_contract": "research.autosci.v1",
        "research_mode": True,
        "sprint_id": sid,
        "artifact_roots": {"canonical": f"artifacts/scientific/{sid}/"},
        "required_gates": ["G_PAPER_INGEST"],
        "nodes": [
            {
                "id": "paper_ingest",
                "goal": "Ingest supplied paper sources into Solar research paper evidence.",
                "logical_operator": "ScientificPaperIngestor",
                "capability_capsule_id": "cap.research-paper-ingest",
                "depends_on": [],
                "write_scope": [str(relative_evidence)],
                "acceptance": ["Emits or validates research_paper.v1 evidence."],
                "gate": "G_PAPER_INGEST",
                "workflow_contract": "research.autosci.v1",
                "evidence_policy": {"expected_schema": "research_paper.v1"},
                "status": status,
                "max_repair_attempts": max_repair_attempts,
            }
        ],
        "node_results": {
            "paper_ingest": {
                "status": status,
                "artifacts": {"evidence_payload_path": str(relative_evidence)},
            }
        },
        "gate_results": {},
    }
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    (sprints / f"{sid}.paper_ingest-handoff.md").write_text("# handoff\n\nAutoSci evidence produced.\n", encoding="utf-8")
    return graph_path


def _capture_and_consume_autosci_intake(harness_dir: Path, sprints: Path, tmp_path: Path) -> Path:
    request = (
        "Official full-runtime AutoSci integration test through normal solar intake. "
        "Do not call a manual autosci shim. The workflow must ingest papers, extract claims, "
        "generate ideas, run exp-design, exp-run, exp-eval, and produce a report."
    )
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(sprints)
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    # This helper exercises graph compilation/dispatch, not the asynchronous
    # Planner operator lifecycle.  Keep it on the legacy managed-pane seam so
    # no real operator daemon is launched from a unit test.
    env["SOLAR_PANE_RUNTIME"] = "codex"
    env["SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH"] = "0"
    capture = subprocess.run(
        [
            sys.executable,
            str(harness_dir / "lib" / "intent_gateway.py"),
            "capture",
            "--text",
            request,
            "--source-channel",
            "pm_dispatch",
            "--source-trust",
            "pm_dispatch",
            "--json",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert capture.returncode == 0, capture.stdout + capture.stderr
    intent_id = json.loads(capture.stdout)["intent_id"]
    consume = subprocess.run(
        [
            sys.executable,
            str(harness_dir / "lib" / "intent_consumer.py"),
            "consume",
            "--intent-id",
            intent_id,
            "--json",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert consume.returncode == 0, consume.stdout + consume.stderr
    result = json.loads(consume.stdout)["results"][0]
    assert result["status"] == "consumed"
    sid = result["sprint_id"]
    from compiled_sprint_planner import generate_planner_artifacts

    planning = generate_planner_artifacts(runtime_root=harness_dir, sprint_id=sid)
    assert planning["ok"] is True, planning
    graph_path = sprints / f"{sid}.task_graph.json"
    certified = json.loads(graph_path.read_text(encoding="utf-8"))
    assert certified["plan_certificate"]["verdict"] == "PASS"
    return graph_path


def _mock_independent_evaluator(monkeypatch: pytest.MonkeyPatch, gnd, submitted: list[dict]) -> None:
    monkeypatch.setattr(
        gnd,
        "_discover_evaluators",
        lambda dry_run=False: [
            {
                "pane": "operator-pool:evaluator.0",
                "models": ["gpt-5.5"],
                "skills": ["review", "testing"],
                "busy": False,
                "title": "operator pool evaluator",
            }
        ],
    )

    def fake_submit(**kwargs):
        submitted.append(kwargs)
        return {
            "ok": True,
            "pane": "operator:mini-codex-gpt55-medium-evaluator-1",
            "operator_id": "mini-codex-gpt55-medium-evaluator-1",
            "pm_dispatch": {"pm_task_id": "pm-test-independent-evaluator"},
            "dispatch_mode": "operator_pool_eval",
        }

    monkeypatch.setattr(gnd, "_submit_eval_to_operator_pool", fake_submit)


def test_autosci_eval_adapter_writes_gate_consumable_pass_and_fail(tmp_path: Path) -> None:
    registry = json.loads((HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8"))
    gate_operator = registry["operators"]["autosci-evaluator-worker"]
    assert gate_operator["role"] == "policy-gate"
    assert "graph_eval" not in gate_operator["task_classes"]
    assert "evaluator" not in gate_operator["preferred_for"]

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": "sprint-adapter",
                "workflow_contract": "research.autosci.v1",
                "nodes": [
                    {
                        "id": "paper_ingest",
                        "logical_operator": "ScientificPaperIngestor",
                        "capability_capsule_id": "cap.research-paper-ingest",
                        "write_scope": [str(PASS_EVIDENCE)],
                        "evidence_policy": {"expected_schema": "research_paper.v1"},
                    }
                ],
                "node_results": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = dict(os.environ, HARNESS_DIR=str(HARNESS))
    pass_json = tmp_path / "pass-eval.json"
    pass_md = tmp_path / "pass-eval.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--graph",
            str(graph_path),
            "--node",
            "paper_ingest",
            "--eval-json",
            str(pass_json),
            "--eval-md",
            str(pass_md),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(pass_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "solar.eval.v1"
    assert payload["verdict"] == "PASS"
    assert payload["generated_by"] == "autosci-evaluator-worker"
    assert payload["proof_level"] == "deterministic_policy_gate"
    assert payload["independent_author"] == ""
    assert payload["evidence"]["gate_result"]["ok"] is True

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["nodes"][0]["write_scope"] = [str(FAIL_EVIDENCE)]
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    fail_json = tmp_path / "fail-eval.json"
    fail_md = tmp_path / "fail-eval.md"
    envelope = tmp_path / "autosci-evaluator-envelope.json"
    envelope.write_text(
        json.dumps(
            {
                "inputs": {
                    "graph_path": str(graph_path),
                    "node_id": "paper_ingest",
                },
                "outputs": {
                    "eval_json_path": str(fail_json),
                    "eval_md_path": str(fail_md),
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--envelope",
            str(envelope),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(fail_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "solar.eval.v1"
    assert payload["verdict"] == "FAIL"
    assert "paper parse_status is failed" in " ".join(payload["failed_conditions"])
    assert fail_md.read_text(encoding="utf-8").strip()


def test_autosci_eval_adapter_resolves_relative_evidence_from_sprint_workdir(tmp_path: Path) -> None:
    sid = "sprint-adapter-workdir"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    relative_evidence = Path("artifacts/scientific") / sid / "paper_ingest" / "research_paper.v1.json"
    evidence = sprints / sid / "workdir" / relative_evidence
    evidence.parent.mkdir(parents=True)
    evidence.write_text(PASS_EVIDENCE.read_text(encoding="utf-8"), encoding="utf-8")
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "workflow_contract": "research.autosci.v1",
                "nodes": [
                    {
                        "id": "paper_ingest",
                        "logical_operator": "ScientificPaperIngestor",
                        "write_scope": [str(relative_evidence)],
                        "evidence_policy": {"expected_schema": "research_paper.v1"},
                    }
                ],
                "node_results": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate_json = sprints / f"{sid}.paper_ingest-scientific-gate.json"
    gate_md = sprints / f"{sid}.paper_ingest-scientific-gate.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--graph",
            str(graph_path),
            "--node",
            "paper_ingest",
            "--eval-json",
            str(gate_json),
            "--eval-md",
            str(gate_md),
        ],
        env=dict(os.environ, HARNESS_DIR=str(HARNESS)),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(gate_json.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["provenance"]["evidence_path"] == str(evidence)


def test_dispatch_node_evals_routes_autosci_contract_to_autosci_evaluator_green(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    evidence = harness_dir / "artifacts" / "green" / "research_paper.v1.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(PASS_EVIDENCE.read_text(encoding="utf-8"), encoding="utf-8")
    graph_path = _write_graph(sprints, sid="sprint-autosci-eval-green", evidence_path=evidence)

    import graph_node_dispatcher as gnd

    submitted: list[dict] = []
    _mock_independent_evaluator(monkeypatch, gnd, submitted)

    result = gnd.dispatch_node_evals(str(graph_path), ttl=30)
    saved = gnd.load_graph(graph_path)
    node = saved["nodes"][0]

    assert result["ok"] is True, result
    assert submitted
    assert submitted[0]["eval_generation"] == 0
    assert result["dispatched"][0]["pane"] == "operator:mini-codex-gpt55-medium-evaluator-1"
    assert result["dispatched"][0]["evaluation_plan"]["independence_policy"]["mechanism"] == (
        "solar_policy_gate_plus_independent_codex_evaluator"
    )
    assert node["status"] == "reviewing"
    assert saved["node_results"]["paper_ingest"]["status"] == "reviewing"
    gate = node["autosci_scientific_gate"]
    assert gate["ok"] is True
    assert gate["proof_level"] == "deterministic_policy_gate"
    assert gnd._validate_autosci_scientific_gate(node)["ok"] is True
    dispatch_text = Path(result["dispatched"][0]["instruction_file"]).read_text(encoding="utf-8")
    assert "You remain an independent Codex Evaluator" in dispatch_text
    assert gate["json_path"] in dispatch_text
    Path(gate["json_path"]).write_text("{}\n", encoding="utf-8")
    assert gnd._validate_autosci_scientific_gate(node)["ok"] is False


def test_autosci_eval_waits_for_durable_builder_result_before_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    sid = "sprint-autosci-builder-still-running"
    evidence = harness_dir / "artifacts" / "pending" / "research_paper.v1.json"
    graph_path = _write_graph(
        sprints,
        sid=sid,
        evidence_path=evidence,
        status="dispatched",
    )
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    node = graph["nodes"][0]
    task_id = f"pm-{sid}-paper_ingest-builder"
    operator_id = "autosci-paper-ingest-worker"
    node.update(
        {
            "dispatched_via": "pm_dispatch",
            "pm_task_id": task_id,
            "operator_id": operator_id,
            "assigned_to": f"operator:{operator_id}",
            "execution_attempt": {
                "schema_version": "solar.node_attempt.v1",
                "phase": "execution",
                "sequence": 1,
                "repair_generation": 0,
                "task_id": task_id,
                "dispatch_id": task_id,
                "operator_id": operator_id,
                "source": "pm_dispatch",
                "logical_role": "builder",
                "status": "submitted",
                "requires_operator_result": True,
                "sprint_id": sid,
                "node_id": "paper_ingest",
                "activated_at": "2026-08-03T01:40:00Z",
                "updated_at": "2026-08-03T01:40:00Z",
            },
        }
    )
    graph["plan_certificate"] = {"verdict": "PASS"}
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    import graph_node_dispatcher as gnd

    submitted: list[dict] = []
    _mock_independent_evaluator(monkeypatch, gnd, submitted)

    result = gnd.dispatch_node_evals(str(graph_path), ttl=30)
    saved = gnd.load_graph(graph_path)

    assert result["ok"] is True
    assert result["dispatched"] == []
    assert result["skipped"] == [
        {
            "node": "paper_ingest",
            "reason": "builder_operator_result_pending",
            "task_id": task_id,
            "operator_id": operator_id,
            "complete": False,
            "result_json": None,
        }
    ]
    assert result["waiting"] == result["skipped"]
    assert result["blocking_skips"] == []
    assert saved["nodes"][0]["status"] == "dispatched"
    assert saved["node_results"]["paper_ingest"]["status"] == "dispatched"
    assert not (sprints / f"{sid}.paper_ingest-eval-snapshot.json").exists()
    assert not (sprints / f"{sid}.paper_ingest-eval-dispatch.md").exists()
    assert not (sprints / f"{sid}.paper_ingest-eval.json").exists()


def test_autosci_eval_snapshot_uses_workdir_and_exact_operator_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    sid = "sprint-autosci-snapshot-root"
    task_id = f"pm-{sid}-literature_discover-builder"
    operator_id = "autosci-literature-discover-worker"
    relative_output = f"artifacts/scientific/{sid}/01_paper/literature_discovery.v1.json"
    workdir = sprints / sid / "workdir"
    output = workdir / relative_output
    output.parent.mkdir(parents=True)
    output.write_text('{"schema":"literature_discovery.v1","status":"completed"}\n', encoding="utf-8")
    envelope = harness_dir / "run" / "operator-results" / operator_id / task_id / "envelope.json"
    envelope.parent.mkdir(parents=True)
    envelope.write_text('{"expected_action":"discover_literature"}\n', encoding="utf-8")
    node = {
        "id": "literature_discover",
        "status": "reviewing",
        "read_scope": ["dispatch/envelope.json"],
        "write_scope": [relative_output],
        "execution_attempt": {
            "schema_version": "solar.node_attempt.v1",
            "phase": "execution",
            "sequence": 1,
            "repair_generation": 0,
            "task_id": task_id,
            "dispatch_id": task_id,
            "operator_id": operator_id,
            "source": "pm_dispatch",
            "logical_role": "builder",
            "status": "completed",
            "requires_operator_result": True,
            "sprint_id": sid,
            "node_id": "literature_discover",
            "activated_at": "2026-08-03T02:11:08Z",
            "updated_at": "2026-08-03T02:13:58Z",
        },
    }
    graph = {
        "sprint_id": sid,
        "workflow_contract": "research.autosci.v1",
        "workflow_contract_id": "research.autosci.v1",
        "artifact_roots": {"canonical": f"artifacts/scientific/{sid}/"},
        "nodes": [node],
        "node_results": {"literature_discover": {"status": "reviewing"}},
    }

    import graph_node_dispatcher as gnd

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)

    assert snapshot["ok"] is True, snapshot
    assert snapshot["violations"] == []
    rows = {row["declared"]: row for row in snapshot["rows"]}
    assert rows["dispatch/envelope.json"]["authority"] == "operator_dispatch"
    assert rows["dispatch/envelope.json"]["path"] == str(envelope)
    assert rows[relative_output]["resolved_root"] == "canonical"
    assert rows[relative_output]["path"] == str(output)
    assert rows[relative_output]["exists"] is True


def test_autosci_dispatch_names_the_same_workdir_used_by_eval_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    sid = "sprint-autosci-dispatch-root"
    relative_output = f"artifacts/scientific/{sid}/01_paper/literature_discovery.v1.json"
    node = {
        "id": "literature_discover",
        "goal": "discover live sources",
        "read_scope": ["dispatch/envelope.json"],
        "write_scope": [relative_output],
        "outputs": [relative_output],
        "acceptance": ["live evidence exists"],
    }
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "workflow_contract": "research.autosci.v1",
                "workflow_contract_id": "research.autosci.v1",
                "nodes": [node],
            }
        ),
        encoding="utf-8",
    )

    import graph_node_dispatcher as gnd

    text = gnd.build_dispatch_text(
        {"sprint_id": sid, "node": node, "graph": str(graph_path)},
        "operator-pool:builder.0",
    )
    workdir = sprints / sid / "workdir"
    expected = workdir / relative_output

    assert "## AutoSci Staging Workdir" in text
    assert f"sole staging root for every relative `write_scope` and `outputs` path is: `{workdir}`" in text
    assert f"`write_scope` `{relative_output}` -> `{expected}`" in text
    assert f"`outputs` `{relative_output}` -> `{expected}`" in text
    assert f"Do not create a second artifact tree at `{sprints / sid / 'artifacts'}`" in text


def test_normal_intake_autosci_graph_dispatches_autosci_evaluator_after_handoff(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = tmp_path_factory.mktemp("a")
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    graph_path = _capture_and_consume_autosci_intake(harness_dir, sprints, tmp_path)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    paper_node = next(node for node in graph["nodes"] if node["id"] == "paper_ingest")
    workdir = sprints / graph["sprint_id"] / "workdir"
    upstream_scope = next(
        scope for scope in paper_node["read_scope"] if str(scope).endswith("literature_discovery.v1.json")
    )
    upstream = workdir / str(upstream_scope)
    upstream.parent.mkdir(parents=True, exist_ok=True)
    upstream.write_text('{"schema_version":"literature_discovery.v1","status":"completed"}\n', encoding="utf-8")
    evidence = workdir / str(paper_node["write_scope"][0])
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(PASS_EVIDENCE.read_text(encoding="utf-8"), encoding="utf-8")
    paper_node["status"] = "reviewing"
    paper_node["artifacts"] = {"evidence_payload_path": str(evidence)}
    graph["node_results"] = {
        "paper_ingest": {
            "status": "reviewing",
            "artifacts": {"evidence_payload_path": str(evidence)},
        }
    }
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    (sprints / f"{graph['sprint_id']}.paper_ingest-handoff.md").write_text(
        "# handoff\n\nAutoSci paper_ingest evidence produced by intake-bound graph.\n",
        encoding="utf-8",
    )

    import graph_node_dispatcher as gnd

    submitted: list[dict] = []
    _mock_independent_evaluator(monkeypatch, gnd, submitted)

    result = gnd.dispatch_node_evals(str(graph_path), ttl=30)
    saved = gnd.load_graph(graph_path)

    assert result["ok"] is True, result
    assert submitted
    assert result["dispatched"][0]["pane"] == "operator:mini-codex-gpt55-medium-evaluator-1"
    assert saved["workflow_contract"] == "research.autosci.v1"
    assert saved["node_results"]["paper_ingest"]["status"] == "reviewing"
    saved_paper = next(node for node in saved["nodes"] if node["id"] == "paper_ingest")
    assert saved_paper["autosci_scientific_gate"]["ok"] is True


def test_normal_intake_autosci_dispatch_ready_uses_exact_autosci_operator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    graph_path = _capture_and_consume_autosci_intake(harness_dir, sprints, tmp_path)

    import graph_node_dispatcher as gnd

    result = gnd.dispatch_ready(str(graph_path), dry_run=True, ttl=30, max_parallel=1)

    assert result["ok"] is True
    assert result["enqueue"]["worker_blocked"] == []
    assert result["enqueue"]["queued"] == []
    enqueued = result["enqueue"]["enqueued"][0]
    assert enqueued["node"] == "evidence_import"
    assert enqueued["pane"] == "operator:autosci-paper-ingest-worker"

    dispatched = result["drain"]["results"][0]
    assert dispatched["ok"] is True
    assert dispatched["dispatch_mode"] == "autosci_operator_direct"
    assert dispatched["operator_id"] == "autosci-paper-ingest-worker"
    assert dispatched["operator_envelope"]["expected_action"] == "ingest_paper"
    assert dispatched["operator_envelope"]["runner_contract"] == "research.autosci.v1"
    assert dispatched["operator_envelope"]["outputs"]["evidence_payload_path"].endswith(
        "research_evidence_import.v1.json"
    )


def test_autosci_operator_envelope_preserves_node_required_skills() -> None:
    import graph_node_dispatcher as gnd
    implementation = getattr(gnd, "_IMPL", gnd)

    envelope = implementation._build_autosci_operator_envelope(
        sid="sprint-skill-bridge",
        node_id="R3",
        node={
            "id": "R3",
            "goal": "Compile the grounded research report.",
            "dispatch_task_type": "research",
            "capability_capsule_id": "cap.skill-execution-bridge",
            "required_skills": ["research_compilation"],
            "write_scope": ["workspace/research/report/"],
        },
        graph={},
        graph_path=str(HARNESS / "sprints" / "sprint-skill-bridge.task_graph.json"),
        operator_id="mini-codex-gpt55-medium-builder-1",
        dispatch_id="graph-sprint-skill-bridge-R3",
        instruction_file=HARNESS / "sprints" / "sprint-skill-bridge.R3-dispatch.md",
        payload={"capsule_plan_ir": {"selected_skills": []}},
        ttl=30,
    )

    assert envelope["selected_skills"] == ["research_compilation"]


def test_openai_policy_keeps_provider_neutral_autosci_operator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    graph_path = _capture_and_consume_autosci_intake(harness_dir, sprints, tmp_path)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["provider_policy"] = {
        "runtime": "codex",
        "allowed_providers": ["openai"],
        "route_proof_required": True,
    }
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    import graph_node_dispatcher as gnd

    result = gnd.dispatch_ready(str(graph_path), dry_run=True, ttl=30, max_parallel=1)

    assert result["ok"] is True
    assert result["enqueue"]["enqueued"][0]["pane"] == "operator:autosci-paper-ingest-worker"
    dispatched = result["drain"]["results"][0]
    assert dispatched["dispatch_mode"] == "autosci_operator_direct"
    assert dispatched["operator_id"] == "autosci-paper-ingest-worker"


def test_autosci_operator_direct_dispatch_submits_to_operator_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    graph_path = _capture_and_consume_autosci_intake(harness_dir, sprints, tmp_path)
    submitted: list[dict] = []

    class FakeOperatorRuntime:
        @staticmethod
        def submit(envelope: dict) -> dict:
            submitted.append(envelope)
            return {
                "task_id": envelope["task_id"],
                "operator_id": envelope["operator_id"],
                "lease_id": "lease-test",
                "inbox_path": str(
                    harness_dir
                    / "run"
                    / "operator-inbox"
                    / envelope["operator_id"]
                    / f"{envelope['task_id']}.json"
                ),
                "submitted_at": "2026-07-08T00:00:00Z",
            }

    monkeypatch.setitem(sys.modules, "operator_runtime", FakeOperatorRuntime)

    import graph_node_dispatcher as gnd

    dry_run_result = gnd.dispatch_ready(str(graph_path), dry_run=True, ttl=30, max_parallel=3)
    payload = next(
        item["payload"]
        for item in dry_run_result["enqueue"]["enqueued"]
        if item["node"] == "literature_discover"
    )
    payload["assignment"]["pane"] = "operator:autosci-literature-discover-worker"
    payload["dispatch_id"] = "graph-test-autosci-direct-submit"

    result = gnd.dispatch_queue_item(
        {
            "sprint_id": payload["sprint_id"],
            "intent": "graph_node|node_id=literature_discover",
            "priority": 80,
            "payload": payload,
        },
        dry_run=False,
        ttl=30,
    )
    saved = gnd.load_graph(graph_path)

    assert result["ok"] is True
    assert submitted
    assert submitted[0]["operator_id"] == "autosci-literature-discover-worker"
    assert submitted[0]["expected_action"] == "discover_literature"
    assert submitted[0]["runner_contract"] == "research.autosci.v1"
    assert submitted[0]["outputs"]["evidence_payload_path"].endswith("literature_discovery.v1.json")
    node = next(node for node in saved["nodes"] if node["id"] == "literature_discover")
    assert node["status"] == "dispatched"
    assert node["operator_id"] == "autosci-literature-discover-worker"
    assert node["dispatch_mode"] == "autosci_operator_direct"


def test_dispatch_node_evals_autosci_fail_blocks_stage_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness_dir, sprints = _prepare_isolated_harness(tmp_path, monkeypatch)
    evidence = harness_dir / "artifacts" / "red" / "research_paper.v1.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(FAIL_EVIDENCE.read_text(encoding="utf-8"), encoding="utf-8")
    graph_path = _write_graph(sprints, sid="sprint-autosci-eval-red", evidence_path=evidence)

    import graph_node_dispatcher as gnd

    submitted: list[dict] = []
    _mock_independent_evaluator(monkeypatch, gnd, submitted)

    result = gnd.dispatch_node_evals(str(graph_path), ttl=30)
    saved = gnd.load_graph(graph_path)
    node = saved["nodes"][0]

    assert result["ok"] is True
    assert submitted
    assert result["dispatched"][0]["pane"] == "operator:mini-codex-gpt55-medium-evaluator-1"
    assert node["status"] == "reviewing"
    assert saved["node_results"]["paper_ingest"]["status"] == "reviewing"
    assert node["autosci_scientific_gate"]["verdict"] == "FAIL"
    assert node["autosci_scientific_gate"]["ok"] is False
    assert gnd._validate_autosci_scientific_gate(node)["ok"] is False
    gate_payload = json.loads(Path(node["autosci_scientific_gate"]["json_path"]).read_text(encoding="utf-8"))
    assert "paper parse_status is failed" in " ".join(gate_payload["failed_conditions"])
    assert saved["gate_results"].get("G_PAPER_INGEST", {}).get("status") != "passed"

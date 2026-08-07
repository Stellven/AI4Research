"""Contracted intake (P2 smoke cause 1 — design §0 router->compiler->task_graph).

The first live smoke ran the GENERIC path because code.cli_smoke's trigger is
"explicit workflow_id only" and no intake seam could carry a workflow_id.
workflow_intake.py is that seam: given an explicit workflow_id it instantiates
the registered contract into a sprint the coordinator can pick up (drafting
scaffold + planner artifacts derived from the contract), fail-closed on any
unknown/planner-generated id — never a silent fall-through to the generic path.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import workflow_intake as wi  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
INTAKE_CLI = _HARNESS / "lib" / "workflow_intake.py"

# The status-server attributes the sprint from stdout with this exact pattern
# (symphony/status-server.py _extract_intake_id) — the CLI's output must match.
_SERVER_SID_PATTERN = re.compile(r"Sprint created:\s*(\S+)")


def _create(tmp_path, **kwargs):
    return wi.create_contract_sprint(
        workflow_id=kwargs.pop("workflow_id", "code.cli_smoke"),
        request=kwargs.pop("request", "P2 smoke: run the contracted cli smoke"),
        workspace_root=kwargs.pop("workspace_root", str(tmp_path / "ws")),
        inputs=kwargs.pop("inputs", {"tool": "uniqwords"}),
        sprints_dir=tmp_path / "sprints",
        workflows_dir=WORKFLOWS_DIR,
        **kwargs,
    )


def test_creates_contracted_sprint_with_coordinator_scaffold(tmp_path):
    result = _create(tmp_path)
    sid = result["sprint_id"]
    sprints = tmp_path / "sprints"

    graph = json.loads((sprints / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    assert graph["workflow_contract_id"] == "code.cli_smoke"
    assert graph["workflow_contract_hash"].startswith("sha256:")
    contract_stage_ids = ["S1", "S2", "S3"]
    assert [n["id"] for n in graph["nodes"]] == contract_stage_ids
    assert graph["sprint_id"] == sid

    status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "drafting"
    assert status["phase"] == "prd_ready"
    assert status["id"] == sid
    assert any(h.get("event") == "contract_sprint_instantiated" for h in status["history"])

    # The coordinator's drafting auto-promote requires PRD+design+plan+task_graph.
    for suffix in ("prd.md", "contract.md", "design.md", "plan.md"):
        artifact = sprints / f"{sid}.{suffix}"
        assert artifact.exists() and artifact.stat().st_size > 0, suffix
        assert "code.cli_smoke" in artifact.read_text(encoding="utf-8")

    events = (sprints / f"{sid}.events.jsonl").read_text(encoding="utf-8")
    assert "contract_sprint_instantiated" in events


def test_placeholder_inputs_substitute_into_write_scope(tmp_path):
    """cli_smoke's paths use <sid>/<tool> placeholders; sid is auto-provided,
    tool comes from --input. Every write_scope path must be fully resolved."""
    result = _create(tmp_path, inputs={"tool": "uniqwords"})
    sid = result["sprint_id"]
    graph = json.loads((tmp_path / "sprints" / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    scopes = [s for n in graph["nodes"] for s in (n.get("write_scope") or [])]
    assert scopes, "cli_smoke stages must declare write_scope"
    assert any("uniqwords.py" in s for s in scopes), scopes
    assert all(sid in s for s in scopes), scopes
    assert not any("<" in s for s in scopes), scopes


def test_unresolved_placeholders_fail_closed(tmp_path):
    """A contract placeholder with no input must abort the intake — a graph with
    literal <tool> paths would dispatch builders at nonsense write scopes."""
    with pytest.raises(wi.WorkflowIntakeError) as exc:
        _create(tmp_path, inputs={})
    assert "UNRESOLVED_PLACEHOLDERS" in str(exc.value)
    assert "tool" in str(exc.value)


def test_unknown_workflow_id_fails_closed(tmp_path):
    with pytest.raises(wi.WorkflowIntakeError) as exc:
        _create(tmp_path, workflow_id="no.such.contract")
    assert "WORKFLOW_ID_UNREGISTERED" in str(exc.value)
    assert not list((tmp_path / "sprints").glob("*")) if (tmp_path / "sprints").exists() else True


def test_planner_generated_contract_rejected(tmp_path):
    with pytest.raises(wi.WorkflowIntakeError) as exc:
        _create(tmp_path, workflow_id="pm.generic.v1")
    assert "PLANNER_GENERATED" in str(exc.value)


def test_cli_output_matches_server_attribution_pattern(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(INTAKE_CLI),
         "--workflow-id", "code.cli_smoke",
         "--request", "P2 smoke via CLI",
         "--workspace-root", str(tmp_path / "ws"),
         "--input", "tool=uniqwords",
         "--sprints-dir", str(tmp_path / "sprints"),
         "--workflows-dir", str(WORKFLOWS_DIR)],
        text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    match = _SERVER_SID_PATTERN.search(proc.stdout)
    assert match, f"stdout must carry 'Sprint created: <sid>' for _extract_intake_id:\n{proc.stdout}"
    sid = match.group(1)
    assert (tmp_path / "sprints" / f"{sid}.task_graph.json").exists()
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["sprint_id"] == sid
    assert payload["workflow_contract_id"] == "code.cli_smoke"


def test_cli_unknown_id_exit_3_no_files(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(INTAKE_CLI),
         "--workflow-id", "no.such.contract",
         "--request", "x",
         "--sprints-dir", str(tmp_path / "sprints"),
         "--workflows-dir", str(WORKFLOWS_DIR)],
        text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "WORKFLOW_ID_UNREGISTERED" in (proc.stdout + proc.stderr)
    assert not (tmp_path / "sprints").exists() or not list((tmp_path / "sprints").glob("*"))


def test_intake_stub_wiring_is_fail_closed():
    """The solar-harness.sh intake branch: SOLAR_INTAKE_WORKFLOW_ID present must
    route through workflow_intake.py and must NEVER fall through to the generic
    path on failure (static assertions on the shipped script; the live wiring is
    exercised by the e2e smoke)."""
    script = (_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
    assert "SOLAR_INTAKE_WORKFLOW_ID" in script
    branch = script.split("SOLAR_INTAKE_WORKFLOW_ID", 1)[1][:2000]
    assert "workflow_intake.py" in branch
    assert "return 1" in branch, "unknown/failed contract intake must fail closed"

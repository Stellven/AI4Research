from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml


HARNESS = (Path(__file__).resolve().parents[2] / 'harness')
REPO = HARNESS.parent
SOLAR_HARNESS = HARNESS / "solar-harness.sh"
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
RUNNER = HARNESS / "tools" / "run_scientific_workflow.py"

REQUIRED_ROUTE_FIELDS = {
    "native_skill",
    "autosci_command",
    "feature_kind",
    "native_paths",
    "solar_capability",
    "solar_logical_operator",
    "solar_backend_action",
    "coverage_status",
    "backend_mode",
    "side_effect_policy",
    "evidence_schema",
    "primary_tools",
    "required_capabilities",
    "limitations",
}
REQUIRED_LIST_ROUTE_FIELDS = {
    "native_paths",
    "primary_tools",
    "required_capabilities",
    "limitations",
}
REQUIRED_LOGICAL_OPERATORS = {
    "ScientificLiteratureDiscoverer",
    "ScientificPaperIngestor",
    "ScientificPaperAnalyzer",
    "ScientificMemoryUpdater",
    "ScientificGraphUpdater",
    "ScientificClaimExtractor",
    "ScientificMethodExtractor",
    "ScientificCodeEvidenceMapper",
    "ScientificIdeaGenerator",
    "ScientificIdeaEvaluator",
    "ScientificExperimentDesigner",
    "ScientificExperimentRunner",
    "ScientificExperimentMonitor",
    "ScientificClaimVerifier",
    "ScientificReportPlanner",
    "ScientificReportDrafter",
    "ScientificArtifactReviewer",
    "ScientificPublicationProducer",
    "ScientificWorkflowEvolver",
}
REQUIRED_PHYSICAL_WORKERS = {
    "autosci-literature-discover-worker",
    "autosci-paper-ingest-worker",
    "autosci-paper-analyze-worker",
    "autosci-memory-update-worker",
    "autosci-graph-update-worker",
    "autosci-claim-extract-worker",
    "autosci-method-extract-worker",
    "autosci-code-evidence-map-worker",
    "autosci-idea-worker",
    "autosci-idea-evaluate-worker",
    "autosci-experiment-design-worker",
    "autosci-experiment-run-worker",
    "autosci-experiment-monitor-worker",
    "autosci-claim-verify-worker",
    "autosci-artifact-review-worker",
    "autosci-report-plan-worker",
    "autosci-report-worker",
    "autosci-publication-compile-worker",
    "autosci-workflow-evolve-worker",
}
REQUIRED_CAPABILITY_CAPSULES = {
    "cap.research-literature-discover",
    "cap.research-paper-ingest",
    "cap.research-paper-analyze",
    "cap.research-memory-update",
    "cap.research-graph-update",
    "cap.research-claim-extract",
    "cap.research-method-extract",
    "cap.research-code-evidence-map",
    "cap.research-idea-generate",
    "cap.research-idea-evaluate",
    "cap.research-experiment-design",
    "cap.research-experiment-run",
    "cap.research-experiment-monitor",
    "cap.research-claim-verify",
    "cap.research-report-plan",
    "cap.scientific-report-draft",
    "cap.research-artifact-review",
    "cap.research-publication-produce",
    "cap.research-workflow-evolve",
}


def _prepare_isolated_harness(tmp_path: Path) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    for name in ("bin", "config", "personas", "tools", "plugins", "evaluators", "schemas", "lib", "templates"):
        target = HARNESS / name
        link = harness_dir / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=target.is_dir())
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def _env_for(harness_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "20"
    env.pop("AUTOSCI_ARTIFACT_ROOT", None)
    env.pop("SCIENTIFIC_ARTIFACT_ROOT", None)
    return env


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_autosci_product_entrypoint_writes_to_unified_artifact_root(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-a-artifact-root-contract-{uuid.uuid4().hex}"
    proc = subprocess.run(
        ["bash", str(SOLAR_HARNESS), "autosci", f"$review README.md --run-id {run_id}"],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    run_dir = harness_dir / "artifacts" / "autosci" / "runs" / run_id
    wiki_dir = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    assert Path(summary["evidence_path"]).resolve() == run_dir / "autosci_skill_run.json"
    assert Path(summary["wiki_path"]).resolve() == wiki_dir
    assert summary["work_dir"] == f"artifacts/autosci/runs/{run_id}"
    assert run_dir.is_dir()
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_autosci_route_config_abi_matches_skill_list(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    route_payload = _load_json(ROUTE_CONFIG)
    routes = route_payload.get("routes")
    assert isinstance(routes, list)
    assert len(routes) == 28

    route_skills: set[str] = set()
    for route in routes:
        assert isinstance(route, dict)
        missing = REQUIRED_ROUTE_FIELDS - set(route)
        assert not missing, f"{route.get('native_skill', 'N/A')} missing {sorted(missing)}"
        route_skills.add(str(route["native_skill"]))
        assert str(route["autosci_command"]).startswith("/")
        assert str(route["coverage_status"]) in {"full", "partial", "gated", "missing"}
        assert str(route["side_effect_policy"]) in {"none", "dry_run_only", "approval_required"}
        for field in REQUIRED_LIST_ROUTE_FIELDS:
            assert isinstance(route[field], list) and route[field], f"{route['native_skill']} {field}"

    proc = subprocess.run(
        [sys.executable, str(SHIM), "skills", "list"],
        cwd=HARNESS,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    skills_payload = json.loads(proc.stdout)
    listed_skills = {item["skill"] for item in skills_payload["skills"]}
    assert skills_payload["count"] == len(routes)
    assert listed_skills == route_skills


def test_autosci_registries_include_priority_a_scientific_bindings() -> None:
    logical = _load_json(HARNESS / "config" / "logical-operators.json")
    physical = _load_json(HARNESS / "config" / "physical-operators.json")
    registry = yaml.safe_load((HARNESS / "config" / "capability-capsules.registry.yaml").read_text(encoding="utf-8"))

    logical_names = set(logical["logical_operators"])
    physical_names = set(physical["operators"])
    capability_entries = registry["capsules"]["capability"]
    capsule_ids = {entry["capability_capsule_id"] for entry in capability_entries}

    assert REQUIRED_LOGICAL_OPERATORS <= logical_names
    assert REQUIRED_PHYSICAL_WORKERS <= physical_names
    assert REQUIRED_CAPABILITY_CAPSULES <= capsule_ids


def test_scientific_workflow_runner_uses_scientific_artifact_root(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    paper = harness_dir / "raw" / "priority-a-paper.md"
    paper.parent.mkdir()
    paper.write_text(
        "# Priority A Scientific Root\n\n"
        "## Abstract\n"
        "This paper checks the generic workflow runner artifact root contract.\n\n"
        "## Results\n"
        "The runner must write scientific lifecycle artifacts under the shared scientific root.\n",
        encoding="utf-8",
    )
    env = _env_for(harness_dir)
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(harness_dir / "artifacts" / "scientific")
    job_id = "priority-a-scientific-root-contract"

    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--harness-dir",
            str(harness_dir),
            "--job-id",
            job_id,
            "--paper",
            str(paper),
            "--node-id",
            "paper_ingest",
            "--timeout-seconds",
            "20",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    workflow_root = harness_dir / "artifacts" / "scientific" / "workflow-runs" / job_id
    assert (workflow_root / "scientific_workflow_runtime.json").exists()
    assert (workflow_root / "scientific_workflow_runtime_manifest.json").exists()
    node_result = summary["node_results"]["paper_ingest"]
    assert Path(node_result["artifact_path"]).parts[:4] == ("artifacts", "scientific", "workflow-runs", job_id)
    assert (harness_dir / node_result["artifact_path"]).exists()
    assert summary["dispatch_boundary"]["status"] == "generic_workflow_runner"

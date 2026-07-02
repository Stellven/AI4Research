from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
TOOL = REPO / "tools" / "semantic_parity_audit_matrix.py"
PROOF_TOOL = REPO / "tools" / "semantic_parity_runtime_proof.py"


def write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    autosci_repo = tmp_path / "AutoSci"
    native_skill = autosci_repo / "i18n" / "en" / "skills" / "ask" / "SKILL.md"
    native_skill.parent.mkdir(parents=True)
    native_skill.write_text("# /ask\n\nNative ask semantics.\n", encoding="utf-8")

    wrapper_root = tmp_path / "solar-wrappers"
    wrapper = wrapper_root / "ask" / "SKILL.md"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("# $ask\n\nSolar wrapper semantics.\n", encoding="utf-8")

    route_config = tmp_path / "feature_parity_routes.v1.json"
    route_config.write_text(
        json.dumps(
            {
                "schema": "autosci_feature_parity_routes.v1",
                "routes": [
                    {
                        "native_skill": "ask",
                        "autosci_command": "/ask",
                        "solar_backend_action": "ask_wiki",
                        "coverage_status": "partial",
                        "backend_mode": "route_plan",
                        "side_effect_policy": "none",
                        "required_capabilities": ["wiki retrieval", "answer synthesis"],
                        "limitations": ["Needs completed semantic audit."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return autosci_repo, wrapper_root, route_config, native_skill


def run_matrix(
    tmp_path: Path,
    autosci_repo: Path,
    wrapper_root: Path,
    route_config: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    out_dir = tmp_path / "semantic-audits"
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "generate",
            "--autosci-repo",
            str(autosci_repo),
            "--solar-wrapper-root",
            str(wrapper_root),
            "--route-config",
            str(route_config),
            "--out-dir",
            str(out_dir),
            *extra,
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_default_generation_writes_partial_semantic_audit_without_promotion(tmp_path: Path) -> None:
    autosci_repo, wrapper_root, route_config, _native_skill = write_fixture(tmp_path)
    proc = run_matrix(tmp_path, autosci_repo, wrapper_root, route_config)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["semantic_full_count"] == 0
    assert summary["semantic_partial_count"] == 1

    audit = json.loads((tmp_path / "semantic-audits/ask.semantic-audit.json").read_text(encoding="utf-8"))
    assert audit["schema"] == "autosci_semantic_parity_audit.v1"
    assert audit["native_skill"] == "ask"
    assert audit["semantic_parity"] == "partial"
    checks = {check["check"]: check["status"] for check in audit["acceptance_checks"]}
    assert checks["native_skill_doc_exists"] == "ok"
    assert checks["solar_wrapper_doc_exists"] == "ok"
    assert checks["solar_route_binding_declared"] == "ok"
    assert checks["full_semantic_assessment_supplied"] == "pending"
    for ref in [*audit["native_evidence_refs"], *audit["solar_evidence_refs"]]:
        assert Path(ref).exists()


def test_full_assessment_writes_full_audit_and_runtime_proof(tmp_path: Path) -> None:
    autosci_repo, wrapper_root, route_config, native_skill = write_fixture(tmp_path)
    assessment = tmp_path / "assessment.json"
    assessment.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_assessment.v1",
                "assessments": {
                    "ask": {
                        "semantic_parity": "full",
                        "auditor": "unit-semantic-auditor",
                        "acceptance_checks": [
                            {
                                "check": "native_command_surface",
                                "status": "ok",
                                "evidence_refs": [str(native_skill)],
                            },
                            {
                                "check": "solar_route_behavior",
                                "status": "passed",
                                "evidence_refs": [str(route_config)],
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_matrix(tmp_path, autosci_repo, wrapper_root, route_config, "--assessment-json", str(assessment))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    audit_path = tmp_path / "semantic-audits/ask.semantic-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["semantic_parity"] == "full"
    assert all(check["status"] in {"ok", "passed"} for check in audit["acceptance_checks"])

    proof_path = tmp_path / "semantic-audits/ask.semantic-proof.json"
    proof = subprocess.run(
        [
            sys.executable,
            str(PROOF_TOOL),
            "from-audit",
            str(audit_path),
            "--native-skill",
            "ask",
            "--runtime-proof-out",
            str(proof_path),
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proof.returncode == 0, proof.stdout + proof.stderr
    proof_summary = json.loads(proof.stdout)
    assert proof_summary["runtime_proof_manifest_status"] == "written"
    assert proof_path.exists()


def test_full_assessment_with_nonpassing_check_is_blocked_and_downgraded(tmp_path: Path) -> None:
    autosci_repo, wrapper_root, route_config, native_skill = write_fixture(tmp_path)
    assessment = tmp_path / "assessment.json"
    assessment.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_assessment.v1",
                "assessments": {
                    "ask": {
                        "semantic_parity": "full",
                        "auditor": "unit-semantic-auditor",
                        "acceptance_checks": [
                            {
                                "check": "native_command_surface",
                                "status": "ok",
                                "evidence_refs": [str(native_skill)],
                            },
                            {
                                "check": "solar_route_behavior",
                                "status": "pending",
                                "evidence_refs": [str(route_config)],
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_matrix(tmp_path, autosci_repo, wrapper_root, route_config, "--assessment-json", str(assessment))
    assert proc.returncode == 1
    summary = json.loads(proc.stdout)
    assert summary["status"] == "completed_with_blocked_full_requests"
    assert "ask" in summary["full_request_errors"]
    audit = json.loads((tmp_path / "semantic-audits/ask.semantic-audit.json").read_text(encoding="utf-8"))
    assert audit["semantic_parity"] == "partial"
    checks = {check["check"]: check["status"] for check in audit["acceptance_checks"]}
    assert checks["full_semantic_assessment_guard"] == "blocked"

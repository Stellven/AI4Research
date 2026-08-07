from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "semantic_parity_runtime_proof.py"


def run_tool(tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def write_audit(tmp_path: Path, *, semantic_parity: str = "full") -> Path:
    root = tmp_path / "artifacts/runtime/semantic"
    native = root / "native-novelty.md"
    solar = root / "solar-novelty.json"
    root.mkdir(parents=True)
    native.write_text("# Native /novelty semantics\n", encoding="utf-8")
    solar.write_text('{"route": "novelty"}\n', encoding="utf-8")
    audit = root / "novelty-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": semantic_parity,
                "auditor": "phase19-human-audit",
                "native_evidence_refs": ["artifacts/runtime/semantic/native-novelty.md"],
                "solar_evidence_refs": ["artifacts/runtime/semantic/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
                "provenance": {"timestamp": "2026-06-29T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    return audit


def test_completed_semantic_audit_writes_runtime_proof_manifest(tmp_path: Path) -> None:
    audit = write_audit(tmp_path)
    proof = tmp_path / "artifacts/runtime/semantic/novelty.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-audit",
            str(audit),
            "--native-skill",
            "novelty",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "completed"
    assert result["runtime_proof_manifest_status"] == "written"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    proof_entry = manifest["proofs"][0]
    assert proof_entry["native_skill"] == "novelty"
    assert proof_entry["categories"] == ["semantic_equivalence_evidence"]
    assert proof_entry["collection_mode"] == "semantic_audit"
    assert proof_entry["production_ready"] is True
    assert proof_entry["provenance"]["source"] == "phase19-human-audit"
    assert proof_entry["provenance"]["artifact_kind"] == "autosci_semantic_parity_audit.v1"
    assert proof_entry["evidence_refs"] == [
        "artifacts/runtime/semantic/novelty-audit.json",
        "artifacts/runtime/semantic/native-novelty.md",
        "artifacts/runtime/semantic/solar-novelty.json",
    ]


def test_partial_semantic_audit_does_not_write_runtime_proof(tmp_path: Path) -> None:
    audit = write_audit(tmp_path, semantic_parity="partial")
    proof = tmp_path / "artifacts/runtime/semantic/novelty.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-audit",
            str(audit),
            "--native-skill",
            "novelty",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "inconclusive"
    assert result["runtime_proof_manifest_status"] == "not_written"
    assert "semantic_parity must be full" in result["errors"]
    assert not proof.exists()


def test_semantic_audit_resolves_configured_native_and_evidence_roots(tmp_path: Path) -> None:
    autosci_repo = tmp_path / "AutoSci"
    native = autosci_repo / "i18n/en/skills/novelty/SKILL.md"
    native.parent.mkdir(parents=True)
    native.write_text("# /novelty\n\nNative novelty semantics.\n", encoding="utf-8")
    evidence_root = tmp_path / "external-evidence-root"
    solar = evidence_root / "harness/artifacts/runtime/semantic/solar-novelty.json"
    solar.parent.mkdir(parents=True)
    solar.write_text('{"route": "novelty", "status": "verified"}\n', encoding="utf-8")
    audit = tmp_path / "semantic-audits/novelty-audit.json"
    audit.parent.mkdir(parents=True)
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "full",
                "auditor": "worktree-portability-audit",
                "native_evidence_refs": ["../AutoSci/i18n/en/skills/novelty/SKILL.md"],
                "solar_evidence_refs": ["harness/artifacts/runtime/semantic/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "semantic-audits/novelty.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-audit",
            str(audit),
            "--native-skill",
            "novelty",
            "--runtime-proof-out",
            str(proof),
            extra_env={
                "AUTOSCI_REPO": str(autosci_repo),
                "SOLAR_AUTOSCI_EVIDENCE_ROOTS": str(evidence_root),
            },
        )
    )
    assert result["status"] == "completed"
    assert result["runtime_proof_manifest_status"] == "written"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    refs = manifest["proofs"][0]["evidence_refs"]
    assert refs[0].endswith("semantic-audits/novelty-audit.json")
    assert "AutoSci/i18n/en/skills/novelty/SKILL.md" in refs
    assert "external-evidence-root/harness/artifacts/runtime/semantic/solar-novelty.json" in refs

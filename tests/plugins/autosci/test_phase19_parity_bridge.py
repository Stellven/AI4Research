from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from plugins.autosci.bin import autosci_parity_bridge as parity_bridge

HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_parity_bridge.py"
GATE = HARNESS / "evaluators" / "scientific" / "autosci_feature_parity_gate.py"
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"


def test_resolve_output_keeps_repo_relative_harness_paths() -> None:
    resolved = parity_bridge.resolve_output("harness/artifacts/autosci/runs")
    assert resolved == HARNESS / "artifacts" / "autosci" / "runs"
    assert parity_bridge.resolve_output("artifacts/autosci/phase19/out.json") == parity_bridge.OUTPUT_HARNESS / "artifacts/autosci/phase19/out.json"


def test_wiki_mutation_requirement_honors_explicit_no_wiki_mutation_text() -> None:
    assert not parity_bridge.wiki_mutation_required_from_text(
        "$exp-pilot-run writes pilot runtime evidence only and does not mutate wiki pages; "
        "$exp-pilot-eval owns approved wiki writeback."
    )
    assert parity_bridge.wiki_mutation_required_from_text(
        "$exp-pilot-eval writes approved wiki verdict pages and graph edges."
    )


def route_skills() -> list[str]:
    config = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))
    return sorted(route["native_skill"] for route in config["routes"])


def make_autosci_fixture(tmp_path: Path, *, extra_skill: str | None = None) -> Path:
    repo = tmp_path / "AutoSci"
    skills_root = repo / "i18n" / "en" / "skills"
    for skill in route_skills() + ([extra_skill] if extra_skill else []):
        skill_dir = skills_root / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_dir.joinpath("SKILL.md").write_text(
            f"---\ndescription: fixture for {skill}\n---\n\n# /{skill}\n",
            encoding="utf-8",
        )
    return repo


def run_bridge(
    args: list[str],
    tmp_path: Path,
    autosci_repo: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    env["AUTOSCI_REPO"] = str(autosci_repo)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_inventory_routes_every_native_autosci_skill(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    out = "artifacts/autosci/phase19/parity.json"
    proc = run_bridge(["inventory", "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["missing_route_count"] == 0
    assert summary["native_skill_count"] == len(route_skills())
    assert sum(summary["runtime_proof_status_counts"].values()) == len(route_skills())
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    parity = payload["outputs"]["parity"]
    assert parity["configured_route_count"] == len(route_skills())
    assert parity["routed_count"] == len(route_skills())
    assert {item["native_skill"] for item in parity["items"]} == set(route_skills())
    assert all(item["evidence_ids"] for item in parity["items"])
    assert all(item["semantic_parity"] in {"full", "partial", "missing"} for item in parity["items"])
    assert all(item["execution_policy"] in {"pure", "bounded_local", "approval_required", "provider_required"} for item in parity["items"])
    assert all(item["proof_level"] in {"E0", "E1", "E2", "E3", "E4", "E5"} for item in parity["items"])
    assert all(item["proof_refs"] for item in parity["items"])
    assert all(isinstance(item["remaining_requirements"], list) for item in parity["items"])
    assert all(item["runtime_proof_status"] in {"not_required", "pending", "supplied", "verified"} for item in parity["items"])
    assert all(isinstance(item["runtime_proof_refs"], list) for item in parity["items"])
    assert all(isinstance(item["proof_requirements"], list) and item["proof_requirements"] for item in parity["items"])
    assert any(item["runtime_proof_status"] == "pending" for item in parity["items"])
    assert any(
        any(requirement["category"] == "external_runtime_evidence" for requirement in item["proof_requirements"])
        for item in parity["items"]
    )
    assert parity["semantic_full_count"] == 0
    assert parity["semantic_partial_count"] == len(route_skills())
    assert parity["semantic_missing_count"] == 0
    assert sum(parity["execution_policy_counts"].values()) == len(route_skills())
    assert sum(parity["proof_level_counts"].values()) == len(route_skills())
    assert sum(parity["runtime_proof_status_counts"].values()) == len(route_skills())
    assert sum(parity["proof_requirement_status_counts"].values()) >= len(route_skills())

    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_route_writes_single_skill_parity_evidence(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    out = "artifacts/autosci/phase19/daily_arxiv_route.json"
    proc = run_bridge(["route", "--skill", "daily-arxiv", "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["runtime_proof_status_counts"]["pending"] == 1
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    items = payload["outputs"]["parity"]["items"]
    assert [item["native_skill"] for item in items] == ["daily-arxiv"]
    assert items[0]["coverage_status"] == "gated"
    assert items[0]["side_effect_policy"] == "approval_required"
    assert items[0]["semantic_parity"] == "partial"
    assert items[0]["execution_policy"] == "approval_required"
    assert items[0]["proof_level"] == "E2"
    assert items[0]["remaining_requirements"]
    assert items[0]["runtime_proof_status"] == "pending"
    assert any(requirement["category"] == "external_runtime_evidence" for requirement in items[0]["proof_requirements"])


def test_inventory_attaches_runtime_proof_manifest_without_promoting_full(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_artifact = tmp_path / "artifacts/runtime/daily-arxiv/result.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"status": "completed"}\n', encoding="utf-8")
    manifest = tmp_path / "runtime-proof-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:test",
                        "categories": [
                            "external_runtime_evidence",
                            "approval_boundary_evidence",
                            "provider_source_evidence",
                        ],
                        "collection_mode": "live_provider",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily-arxiv provider contract test",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "provider_response",
                            "command": "$daily-arxiv --live",
                        },
                        "evidence_refs": ["artifacts/runtime/daily-arxiv/result.json"],
                        "description": "Provider manifest represents supplied runtime proof metadata only.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_with_runtime.json"
    proc = run_bridge(["inventory", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    daily = next(item for item in payload["outputs"]["parity"]["items"] if item["native_skill"] == "daily-arxiv")
    assert daily["coverage_status"] == "gated"
    assert daily["semantic_parity"] == "partial"
    assert daily["runtime_proof_status"] == "supplied"
    assert daily["runtime_proof_sources"][0]["proof_id"] == "runtime:daily-arxiv:test"
    assert daily["runtime_proof_sources"][0]["collection_mode"] == "live_provider"
    assert daily["runtime_proof_sources"][0]["production_ready"] is True
    assert daily["runtime_proof_sources"][0]["provenance"]["source"] == "daily-arxiv provider contract test"
    assert daily["runtime_proof_sources"][0]["evidence_ref_statuses"][0]["status"] == "ok"
    assert "runtime:daily-arxiv:test" in daily["runtime_proof_refs"]
    supplied_categories = {
        requirement["category"]
        for requirement in daily["proof_requirements"]
        if requirement["status"] == "supplied"
    }
    assert "external_runtime_evidence" in supplied_categories
    assert payload["outputs"]["parity"]["full_count"] == 0
    assert payload["outputs"]["parity"]["semantic_full_count"] == 0
    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_route_declares_optional_external_model_proof_for_pure_route(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_artifact = tmp_path / "artifacts/runtime/check/model-review.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"schema": "autosci_model_response.v1", "status": "completed"}\n', encoding="utf-8")
    manifest = tmp_path / "check-model-proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "check",
                        "proof_id": "runtime:check:model-review",
                        "categories": ["review_llm_or_model_evidence", "external_runtime_evidence"],
                        "collection_mode": "manual_review",
                        "production_ready": True,
                        "provenance": {
                            "source": "check model proof test",
                            "captured_at": "2026-06-30T00:00:00Z",
                            "artifact_kind": "autosci_model_response.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/check/model-review.json"],
                        "description": "Pure route supplied model execution evidence without making runtime mandatory.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/check_optional_external_model_proof.json"
    proc = run_bridge(["route", "--skill", "check", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "check"
    assert item["runtime_proof_status"] == "not_required"
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert requirements["external_runtime_evidence"]["status"] == "supplied"
    assert requirements["review_llm_or_model_evidence"]["status"] == "supplied"
    assert item["semantic_parity"] == "partial"
    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_inventory_attaches_runtime_proof_manifest_from_directory(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    proof_dir = tmp_path / "runtime-proofs/nested"
    runtime_artifact = tmp_path / "artifacts/runtime/daily-arxiv/result.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"status": "completed"}\n', encoding="utf-8")
    proof_dir.mkdir(parents=True)
    proof_dir.joinpath("not-a-proof.json").write_text('{"schema": "ordinary.json"}\n', encoding="utf-8")
    manifest = proof_dir / "daily-arxiv.proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:dir-proof",
                        "categories": ["external_runtime_evidence"],
                        "collection_mode": "live_provider",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily-arxiv provider directory test",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "provider_response",
                        },
                        "evidence_refs": ["artifacts/runtime/daily-arxiv/result.json"],
                        "description": "Directory-collected runtime proof.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_with_runtime_dir.json"
    proc = run_bridge(["inventory", "--runtime-proof-dir", str(tmp_path / "runtime-proofs"), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["runtime_proof_status_counts"]["supplied"] == 1
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    assert payload["inputs"]["runtime_proof_dirs"] == [str(tmp_path / "runtime-proofs")]
    assert str(manifest) in payload["inputs"]["runtime_proof_manifest_paths"]
    daily = next(item for item in payload["outputs"]["parity"]["items"] if item["native_skill"] == "daily-arxiv")
    assert daily["runtime_proof_status"] == "supplied"
    assert daily["runtime_proof_sources"][0]["proof_id"] == "runtime:daily-arxiv:dir-proof"
    assert payload["outputs"]["parity"]["full_count"] == 0
    assert payload["outputs"]["parity"]["semantic_full_count"] == 0


def test_runtime_proof_dir_resolves_configured_evidence_roots(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    evidence_root = tmp_path / "external-evidence-root"
    runtime_artifact = evidence_root / "harness/artifacts/runtime/daily-arxiv/result.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"status": "completed"}\n', encoding="utf-8")
    proof_dir = tmp_path / "runtime-proofs"
    proof_dir.mkdir()
    manifest = proof_dir / "daily-arxiv.proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:external-root",
                        "categories": ["external_runtime_evidence"],
                        "collection_mode": "live_provider",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily-arxiv external-root provider test",
                            "captured_at": "2026-07-02T00:00:00Z",
                            "artifact_kind": "provider_response",
                        },
                        "evidence_refs": ["harness/artifacts/runtime/daily-arxiv/result.json"],
                        "description": "Directory-collected runtime proof with artifact root outside the worktree.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_with_external_root_runtime_dir.json"
    proc = run_bridge(
        ["inventory", "--runtime-proof-dir", str(proof_dir), "--out", out],
        tmp_path,
        autosci_repo,
        extra_env={"SOLAR_AUTOSCI_EVIDENCE_ROOTS": str(evidence_root)},
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    daily = next(item for item in payload["outputs"]["parity"]["items"] if item["native_skill"] == "daily-arxiv")
    source = daily["runtime_proof_sources"][0]
    assert source["status"] == "supplied"
    assert source["evidence_ref_statuses"][0]["status"] == "ok"
    assert source["evidence_ref_statuses"][0]["path"] == str(runtime_artifact)


def test_runtime_proof_dir_ignores_non_route_workflow_node_proofs(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    proof_dir = tmp_path / "runtime-proofs"
    proof_dir.mkdir()
    manifest = proof_dir / "scientific_workflow_runtime_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "scientific_workflow_runtime_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "ingest",
                        "proof_id": "workflow-runtime:paper_ingest",
                        "categories": ["workflow_node_runtime_evidence"],
                        "evidence_refs": ["run/operator-results/autosci-paper-ingest-worker/task/result.json"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_without_workflow_node_proof.json"
    proc = run_bridge(["route", "--skill", "ingest", "--runtime-proof-dir", str(proof_dir), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "ingest"
    assert item["runtime_proof_sources"] == []
    assert all(
        "workflow_node_runtime_evidence" not in requirement["category"]
        for requirement in item["proof_requirements"]
    )


def test_route_marks_runtime_proof_verified_without_semantic_auto_promotion(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_artifact = tmp_path / "artifacts/runtime/daily-arxiv/final-digest.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"schema": "literature_discovery.v1", "status": "completed"}\n', encoding="utf-8")
    manifest = tmp_path / "daily-arxiv-verified-runtime.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:verified-runtime",
                        "categories": [
                            "external_runtime_evidence",
                            "approval_boundary_evidence",
                            "side_effect_execution_evidence",
                            "review_llm_or_model_evidence",
                            "provider_source_evidence",
                            "wiki_mutation_evidence",
                        ],
                        "collection_mode": "approved_side_effect",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily-arxiv approved provider delivery test",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "literature_discovery.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/daily-arxiv/final-digest.json"],
                        "description": "Completed runtime proof covers provider, approval, review, side-effect, and wiki mutation boundaries.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/daily_arxiv_verified_runtime.json"
    proc = run_bridge(["route", "--skill", "daily-arxiv", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["runtime_proof_status_counts"]["verified"] == 1
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "daily-arxiv"
    assert item["coverage_status"] == "gated"
    assert item["semantic_parity"] == "partial"
    assert item["runtime_proof_status"] == "verified"
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    for category in [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "review_llm_or_model_evidence",
        "provider_source_evidence",
        "wiki_mutation_evidence",
    ]:
        assert requirements[category]["status"] == "supplied"
    assert requirements["semantic_equivalence_evidence"]["status"] == "pending"
    assert payload["outputs"]["parity"]["full_count"] == 0
    assert payload["outputs"]["parity"]["semantic_full_count"] == 0

    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_inventory_marks_semantic_equivalence_requirement_supplied_without_auto_promotion(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_artifact = tmp_path / "artifacts/runtime/novelty/semantic-audit.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"schema": "autosci_semantic_parity_audit.v1", "status": "completed"}\n', encoding="utf-8")
    manifest = tmp_path / "novelty-semantic-proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "novelty",
                        "proof_id": "runtime:novelty:semantic-audit",
                        "categories": ["semantic_equivalence_evidence"],
                        "collection_mode": "semantic_audit",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 semantic audit",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "autosci_semantic_parity_audit.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/novelty/semantic-audit.json"],
                        "description": "Semantic parity audit proof.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_semantic_proof.json"
    proc = run_bridge(["route", "--skill", "novelty", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "novelty"
    assert item["coverage_status"] == "partial"
    assert item["semantic_parity"] == "partial"
    assert item["runtime_proof_status"] == "supplied"
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert requirements["semantic_equivalence_evidence"]["status"] == "supplied"
    assert requirements["external_runtime_evidence"]["status"] == "pending"
    assert payload["outputs"]["parity"]["semantic_full_count"] == 0


def test_inventory_promotes_verified_full_semantic_audit(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/novelty"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-novelty.md"
    solar_ref = runtime_dir / "solar-novelty.json"
    native_ref.write_text("# Native /novelty semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "novelty", "status": "verified"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-full.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "full",
                "auditor": "phase19-semantic-audit",
                "native_evidence_refs": ["artifacts/runtime/novelty/native-novelty.md"],
                "solar_evidence_refs": ["artifacts/runtime/novelty/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "novelty-semantic-proof-full.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "novelty",
                        "proof_id": "runtime:novelty:semantic-audit-full",
                        "categories": ["semantic_equivalence_evidence"],
                        "collection_mode": "semantic_audit",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 semantic audit",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "autosci_semantic_parity_audit.v1",
                        },
                        "evidence_refs": [
                            "artifacts/runtime/novelty/semantic-audit-full.json",
                            "artifacts/runtime/novelty/native-novelty.md",
                            "artifacts/runtime/novelty/solar-novelty.json",
                        ],
                        "description": "Semantic parity audit proof.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_semantic_full_proof.json"
    proc = run_bridge(["route", "--skill", "novelty", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "novelty"
    assert item["semantic_parity"] == "full"
    assert item["semantic_audit_status"] == "verified"
    assert item["semantic_audit_refs"] == ["artifacts/runtime/novelty/semantic-audit-full.json"]
    assert item["proof_level"] == "E3"
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert requirements["semantic_equivalence_evidence"]["status"] == "supplied"
    assert payload["outputs"]["parity"]["semantic_full_count"] == 1

    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_daily_arxiv_delivery_finality_does_not_require_optional_wiki_mutation(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/daily-arxiv-delivery"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-daily-arxiv.md"
    solar_ref = runtime_dir / "solar-daily-arxiv.json"
    runtime_ref = runtime_dir / "daily-runtime.json"
    native_ref.write_text("# Native /daily-arxiv semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "daily-arxiv", "status": "verified"}\n', encoding="utf-8")
    runtime_ref.write_text('{"status": "completed", "delivery_status": "delivered"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-full.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "daily-arxiv",
                "semantic_parity": "full",
                "auditor": "phase19-daily-arxiv-audit",
                "native_evidence_refs": ["artifacts/runtime/daily-arxiv-delivery/native-daily-arxiv.md"],
                "solar_evidence_refs": ["artifacts/runtime/daily-arxiv-delivery/solar-daily-arxiv.json"],
                "acceptance_checks": [
                    {"check": "provider_candidates", "status": "ok"},
                    {"check": "review_llm_ranking", "status": "ok"},
                    {"check": "delivery_boundary", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "daily-arxiv-delivery-proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:semantic-audit-full",
                        "categories": ["semantic_equivalence_evidence"],
                        "collection_mode": "semantic_audit",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 semantic audit",
                            "captured_at": "2026-07-02T00:00:00Z",
                            "artifact_kind": "autosci_semantic_parity_audit.v1",
                        },
                        "evidence_refs": [
                            "artifacts/runtime/daily-arxiv-delivery/semantic-audit-full.json",
                            "artifacts/runtime/daily-arxiv-delivery/native-daily-arxiv.md",
                            "artifacts/runtime/daily-arxiv-delivery/solar-daily-arxiv.json",
                        ],
                        "description": "Daily arXiv semantic parity audit proof.",
                    },
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:delivery-finality",
                        "categories": [
                            "approval_boundary_evidence",
                            "external_runtime_evidence",
                            "provider_source_evidence",
                            "review_llm_or_model_evidence",
                            "side_effect_execution_evidence",
                        ],
                        "collection_mode": "approved_side_effect",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily arXiv final provider delivery boundary",
                            "captured_at": "2026-07-02T00:00:00Z",
                            "artifact_kind": "autosci_daily_arxiv_final_provider_delivery_boundary.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/daily-arxiv-delivery/daily-runtime.json"],
                        "description": "Daily arXiv provider, Review LLM, approval, and delivery proof.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/daily_arxiv_delivery_finality.json"
    proc = run_bridge(["route", "--skill", "daily-arxiv", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert item["semantic_parity"] == "full"
    assert item["semantic_audit_status"] == "verified"
    assert item["runtime_proof_status"] == "verified"
    assert item["coverage_status"] == "gated"
    assert item["remaining_requirements"] == []
    assert "wiki_mutation_evidence" not in requirements

    gate = subprocess.run(
        [sys.executable, str(GATE), "--require-full-parity", str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_route_accepts_direct_semantic_audit_path(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/novelty-direct"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-novelty.md"
    solar_ref = runtime_dir / "solar-novelty.json"
    native_ref.write_text("# Native /novelty semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "novelty", "status": "verified"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-direct.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "full",
                "auditor": "phase19-direct-semantic-audit",
                "native_evidence_refs": ["artifacts/runtime/novelty-direct/native-novelty.md"],
                "solar_evidence_refs": ["artifacts/runtime/novelty-direct/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
                "provenance": {"timestamp": "2026-06-30T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_direct_semantic_audit.json"
    proc = run_bridge(["route", "--skill", "novelty", "--semantic-audit", str(audit), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["semantic_parity"] == "full"
    assert item["semantic_audit_status"] == "verified"
    assert item["semantic_audit_refs"] == ["artifacts/runtime/novelty-direct/semantic-audit-direct.json"]
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert requirements["semantic_equivalence_evidence"]["status"] == "supplied"
    assert payload["outputs"]["parity"]["semantic_full_count"] == 1
    assert any(artifact["type"] == "semantic_parity_audit" for artifact in payload["artifacts"])


def test_inventory_discovers_semantic_audit_dir_without_promoting_partial_audits(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/novelty-direct-partial"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-novelty.md"
    solar_ref = runtime_dir / "solar-novelty.json"
    native_ref.write_text("# Native /novelty semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "novelty", "status": "partial"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-partial.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "partial",
                "auditor": "phase19-direct-semantic-audit",
                "native_evidence_refs": ["artifacts/runtime/novelty-direct-partial/native-novelty.md"],
                "solar_evidence_refs": ["artifacts/runtime/novelty-direct-partial/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_direct_semantic_audit_partial.json"
    proc = run_bridge(["route", "--skill", "novelty", "--semantic-audit-dir", str(runtime_dir), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["semantic_parity"] == "partial"
    assert item["semantic_audit_status"] == "inconclusive"
    assert any("audit semantic_parity must be full" in reason for reason in item["semantic_audit_reasons"])
    assert item["runtime_proof_sources"][0]["status"] == "blocked"
    assert "audit semantic_parity must be full" in item["runtime_proof_sources"][0]["block_reasons"]
    requirements = {req["category"]: req for req in item["proof_requirements"]}
    assert requirements["semantic_equivalence_evidence"]["status"] == "pending"
    assert payload["outputs"]["parity"]["semantic_full_count"] == 0
    assert any(artifact["type"] == "semantic_audit_dir" for artifact in payload["artifacts"])


def test_route_promotes_coverage_when_all_full_parity_proofs_are_verified(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/novelty-full"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-novelty.md"
    solar_ref = runtime_dir / "solar-novelty.json"
    runtime_ref = runtime_dir / "novelty-runtime.json"
    native_ref.write_text("# Native /novelty semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "novelty", "status": "verified"}\n', encoding="utf-8")
    runtime_ref.write_text('{"schema": "novelty_runtime.v1", "status": "completed"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-full.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "full",
                "auditor": "phase19-semantic-audit",
                "native_evidence_refs": ["artifacts/runtime/novelty-full/native-novelty.md"],
                "solar_evidence_refs": ["artifacts/runtime/novelty-full/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "ok"},
                    {"check": "review_and_source_boundaries", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "novelty-full-parity-proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "novelty",
                        "proof_id": "runtime:novelty:semantic-audit-full",
                        "categories": ["semantic_equivalence_evidence"],
                        "collection_mode": "semantic_audit",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 semantic audit",
                            "captured_at": "2026-06-30T00:00:00Z",
                            "artifact_kind": "autosci_semantic_parity_audit.v1",
                        },
                        "evidence_refs": [
                            "artifacts/runtime/novelty-full/semantic-audit-full.json",
                            "artifacts/runtime/novelty-full/native-novelty.md",
                            "artifacts/runtime/novelty-full/solar-novelty.json",
                        ],
                        "description": "Semantic parity audit proof.",
                    },
                    {
                        "native_skill": "novelty",
                        "proof_id": "runtime:novelty:review-source-wiki",
                        "categories": [
                            "external_runtime_evidence",
                            "review_llm_or_model_evidence",
                            "provider_source_evidence",
                            "wiki_mutation_evidence",
                        ],
                        "collection_mode": "live_provider",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 novelty runtime audit",
                            "captured_at": "2026-06-30T00:00:00Z",
                            "artifact_kind": "novelty_runtime.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/novelty-full/novelty-runtime.json"],
                        "description": "Novelty provider, review, external runtime, and wiki mutation proof.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_full_parity_proof.json"
    proc = run_bridge(["route", "--skill", "novelty", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "novelty"
    assert item["semantic_parity"] == "full"
    assert item["semantic_audit_status"] == "verified"
    assert item["runtime_proof_status"] == "verified"
    assert item["coverage_status"] == "full"
    assert item["remaining_requirements"] == []
    assert payload["outputs"]["parity"]["full_count"] == 1

    gate = subprocess.run(
        [sys.executable, str(GATE), "--require-full-parity", str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
    gate_payload = json.loads(gate.stdout)
    assert gate_payload["status"] == "passed"


def test_direct_semantic_audit_resolves_configured_native_and_evidence_roots(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    evidence_root = tmp_path / "external-evidence-root"
    solar_ref = evidence_root / "harness/artifacts/runtime/novelty/solar-novelty.json"
    solar_ref.parent.mkdir(parents=True)
    solar_ref.write_text('{"route": "novelty", "status": "verified"}\n', encoding="utf-8")
    audit_dir = tmp_path / "semantic-audits"
    audit_dir.mkdir()
    audit = audit_dir / "novelty.semantic-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "novelty",
                "semantic_parity": "full",
                "auditor": "worktree-portability-audit",
                "native_evidence_refs": ["../AutoSci/i18n/en/skills/novelty/SKILL.md"],
                "solar_evidence_refs": ["harness/artifacts/runtime/novelty/solar-novelty.json"],
                "acceptance_checks": [
                    {"check": "native_command_abi", "status": "ok"},
                    {"check": "solar_route_behavior", "status": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/novelty_semantic_external_roots.json"
    proc = run_bridge(
        ["route", "--skill", "novelty", "--semantic-audit", str(audit), "--out", out],
        tmp_path,
        autosci_repo,
        extra_env={"SOLAR_AUTOSCI_EVIDENCE_ROOTS": str(evidence_root)},
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "novelty"
    assert item["semantic_parity"] == "full"
    assert item["semantic_audit_status"] == "verified"
    assert item.get("semantic_audit_reasons", []) == []


def test_research_route_promotes_to_e4_when_lifecycle_proofs_are_verified(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_dir = tmp_path / "artifacts/runtime/research-full"
    runtime_dir.mkdir(parents=True)
    native_ref = runtime_dir / "native-research.md"
    solar_ref = runtime_dir / "solar-research.json"
    runtime_ref = runtime_dir / "research-lifecycle-runtime.json"
    native_ref.write_text("# Native /research lifecycle semantics\n", encoding="utf-8")
    solar_ref.write_text('{"route": "research", "status": "verified"}\n', encoding="utf-8")
    runtime_ref.write_text('{"schema": "scientific_workflow_runtime_manifest.v1", "status": "completed"}\n', encoding="utf-8")
    audit = runtime_dir / "semantic-audit-full.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_semantic_parity_audit.v1",
                "status": "completed",
                "native_skill": "research",
                "semantic_parity": "full",
                "auditor": "phase19-research-lifecycle-audit",
                "native_evidence_refs": ["artifacts/runtime/research-full/native-research.md"],
                "solar_evidence_refs": ["artifacts/runtime/research-full/solar-research.json"],
                "acceptance_checks": [
                    {"check": "lifecycle_stage_equivalence", "status": "ok"},
                    {"check": "resume_and_gate_semantics", "status": "passed"},
                    {"check": "provider_runtime_boundaries", "status": "ok"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "research-full-parity-proof.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "research",
                        "proof_id": "runtime:research:semantic-audit-full",
                        "categories": ["semantic_equivalence_evidence"],
                        "collection_mode": "semantic_audit",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 research semantic audit",
                            "captured_at": "2026-06-30T00:00:00Z",
                            "artifact_kind": "autosci_semantic_parity_audit.v1",
                        },
                        "evidence_refs": [
                            "artifacts/runtime/research-full/semantic-audit-full.json",
                            "artifacts/runtime/research-full/native-research.md",
                            "artifacts/runtime/research-full/solar-research.json",
                        ],
                        "description": "Research lifecycle semantic parity audit proof.",
                    },
                    {
                        "native_skill": "research",
                        "proof_id": "runtime:research:lifecycle-approved-runtime",
                        "categories": [
                            "external_runtime_evidence",
                            "approval_boundary_evidence",
                            "review_llm_or_model_evidence",
                            "provider_source_evidence",
                        ],
                        "collection_mode": "approved_side_effect",
                        "production_ready": True,
                        "provenance": {
                            "source": "phase19 research lifecycle runtime audit",
                            "captured_at": "2026-06-30T00:00:00Z",
                            "artifact_kind": "scientific_workflow_runtime_manifest.v1",
                        },
                        "evidence_refs": ["artifacts/runtime/research-full/research-lifecycle-runtime.json"],
                        "description": "Research lifecycle provider, approval, review, and runtime proof.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/research_full_parity_proof.json"
    proc = run_bridge(["route", "--skill", "research", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    item = payload["outputs"]["parity"]["items"][0]
    assert item["native_skill"] == "research"
    assert item["semantic_parity"] == "full"
    assert item["runtime_proof_status"] == "verified"
    assert item["coverage_status"] == "gated"
    assert item["proof_level"] == "E4"

    gate = subprocess.run(
        [sys.executable, str(GATE), "--require-full-parity", str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
    gate_payload = json.loads(gate.stdout)
    assert gate_payload["status"] == "passed"


def test_inventory_blocks_runtime_proof_manifest_with_missing_local_ref(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    manifest = tmp_path / "runtime-proof-manifest-missing-ref.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:missing-ref",
                        "categories": ["external_runtime_evidence"],
                        "collection_mode": "live_provider",
                        "production_ready": True,
                        "provenance": {
                            "source": "daily-arxiv provider contract test",
                            "captured_at": "2026-06-29T00:00:00Z",
                            "artifact_kind": "provider_response",
                        },
                        "evidence_refs": ["artifacts/runtime/daily-arxiv/missing-result.json"],
                        "description": "Missing local evidence should block supplied proof.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_with_missing_runtime_ref.json"
    proc = run_bridge(["inventory", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    daily = next(item for item in payload["outputs"]["parity"]["items"] if item["native_skill"] == "daily-arxiv")
    assert daily["runtime_proof_status"] == "pending"
    assert daily["runtime_proof_sources"][0]["status"] == "blocked"
    assert daily["runtime_proof_sources"][0]["evidence_ref_statuses"][0]["status"] == "missing"
    assert "runtime:daily-arxiv:missing-ref" not in daily["runtime_proof_refs"]
    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert "blocked proof has unresolved local refs" in gate.stdout


def test_inventory_blocks_runtime_proof_manifest_without_production_provenance(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path)
    runtime_artifact = tmp_path / "artifacts/runtime/daily-arxiv/result.json"
    runtime_artifact.parent.mkdir(parents=True)
    runtime_artifact.write_text('{"status": "completed"}\n', encoding="utf-8")
    manifest = tmp_path / "runtime-proof-manifest-unready.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_proof_manifest.v1",
                "proofs": [
                    {
                        "native_skill": "daily-arxiv",
                        "proof_id": "runtime:daily-arxiv:unready",
                        "categories": ["external_runtime_evidence"],
                        "evidence_refs": ["artifacts/runtime/daily-arxiv/result.json"],
                        "description": "Runtime proof without production provenance must stay blocked.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = "artifacts/autosci/phase19/parity_with_unready_runtime.json"
    proc = run_bridge(["inventory", "--runtime-proof-manifest", str(manifest), "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    daily = next(item for item in payload["outputs"]["parity"]["items"] if item["native_skill"] == "daily-arxiv")
    source = daily["runtime_proof_sources"][0]
    assert daily["runtime_proof_status"] == "pending"
    assert source["status"] == "blocked"
    assert source["block_reasons"]
    assert "runtime:daily-arxiv:unready" not in daily["runtime_proof_refs"]
    gate = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / out)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert "blocked proof requires block_reasons" not in gate.stdout


def test_overclaimed_smoke_routes_are_marked_partial() -> None:
    config = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))
    routes = {item["native_skill"]: item for item in config["routes"]}
    for skill in ["exp-design", "exp-status", "ideate", "paper-draft", "paper-plan"]:
        assert routes[skill]["coverage_status"] == "partial"
        assert routes[skill]["backend_mode"] == "route_plan"
        assert routes[skill]["limitations"]


def test_inventory_fails_when_autosci_adds_unmapped_native_skill(tmp_path: Path) -> None:
    autosci_repo = make_autosci_fixture(tmp_path, extra_skill="new-native-skill")
    out = "artifacts/autosci/phase19/parity_missing.json"
    proc = run_bridge(["inventory", "--out", out], tmp_path, autosci_repo)
    assert proc.returncode == 2
    payload = json.loads((tmp_path / out).read_text(encoding="utf-8"))
    parity = payload["outputs"]["parity"]
    assert payload["status"] == "failed"
    assert parity["missing_route_count"] == 1
    missing = [item for item in parity["items"] if item["coverage_status"] == "missing"]
    assert missing[0]["native_skill"] == "new-native-skill"
    assert missing[0]["semantic_parity"] == "missing"
    assert missing[0]["proof_level"] == "E0"
    assert missing[0]["remaining_requirements"]
    assert missing[0]["runtime_proof_status"] == "pending"
    assert any(requirement["status"] == "missing" for requirement in missing[0]["proof_requirements"])

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "harness" / "lib"))
sys.path.insert(0, str(REPO / "harness" / "plugins" / "autosci"))

from backends.artifact_review import review_artifact
from research.claim_compiler import AlignmentStatus, NaiveClaimCompiler
from research.evidence.review_proof import claim_support_assessment, normalize_review_proof


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, claim: str = "The trial reduced systolic blood pressure by 12%.") -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "report.md"
    artifact.write_text(
        "# Review target\n\n"
        "This report documents a controlled method, dataset, metric, baseline, evidence artifact, "
        "and reproducible result. The study enrolled adults and compared the intervention against a "
        "pre-registered baseline. Methods, limitations, and measurements are included for independent "
        "review. The primary metric was systolic blood pressure measured with the same calibrated device "
        "at baseline and follow-up. The evidence below is intentionally narrow: it does not establish "
        "effects outside this trial. Additional replication, external validation, and safety follow-up "
        "remain necessary before any wider scientific conclusion. These constraints define the acceptance "
        "criterion for the claim under review and make residual risk visible to the reviewer.\n"
        "The report also records sample selection, measurement timing, missing-data handling, uncertainty, "
        "and exclusion rules. Reviewers can inspect the linked source span without relying on the writer's "
        "summary or approval. No claim extends beyond the enrolled population, measured outcome, and follow-up "
        "window documented here.\n",
        encoding="utf-8",
    )
    source = tmp_path / "trial.txt"
    evidence = "In this randomized adult trial, systolic blood pressure was reduced by 12% at follow-up."
    source.write_text(evidence, encoding="utf-8")
    span_text = "systolic blood pressure was reduced by 12%"
    start = evidence.index(span_text)
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps({
        "schema": "scientific_review_proof.v1",
        "writer": {"provider": "writer-provider", "model": "writer-model"},
        "artifact": {"path": str(artifact), "sha256": _sha(artifact)},
        "claims": [{
            "claim_id": "claim.bp",
            "claim": claim,
            "source": {"source_id": "trial-1", "path": str(source), "sha256": _sha(source)},
            "evidence_span": {"start": start, "end": start + len(span_text), "text": span_text},
            "acceptance_criterion": "The claim must be limited to the measured adult trial result and its exact evidence span.",
            "residual_risk": "Single-trial evidence requires replication.",
        }],
    }, indent=2), encoding="utf-8")
    return artifact, source, proof


def test_supported_claim_is_reloaded_and_same_provider_limit_is_visible(tmp_path: Path) -> None:
    artifact, _, proof = _fixture(tmp_path)
    result = review_artifact(
        {"artifact_path": str(artifact), "proof_bundle_path": str(proof)},
        workspace_root=tmp_path,
        repository_root=tmp_path,
    )

    review = result["review"]
    contract = review["proof_contract"]
    assert contract["verdict"] == "supported"
    assert contract["claims"][0]["verdict"] == "supported"
    assert review["recommendation"] == "pass_with_review_required"
    assert contract["reviewer_separation"]["artifact_reloaded_from_disk"] is True
    assert contract["reviewer_separation"]["writer_output_excluded_from_reviewer_context"] is True
    assert contract["reviewer_separation"]["independence"]["status"] == "same_provider_limitation"
    assert any("Same-provider limitation" in item for item in result["limitations"])


def test_unreferenced_and_overbroad_claims_fail_closed(tmp_path: Path) -> None:
    artifact, _, proof = _fixture(tmp_path, claim="The intervention cures all cancers.")
    broad = normalize_review_proof(
        proof_bundle_path=proof,
        artifact_path=artifact,
        workspace_root=tmp_path,
    )
    assert broad["verdict"] == "not_supported"
    assert "claim_scope_too_broad" in broad["blockers"]

    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps({"schema": "scientific_review_proof.v1", "artifact": {"path": str(artifact), "sha256": _sha(artifact)}, "claims": []}), encoding="utf-8")
    no_evidence = normalize_review_proof(proof_bundle_path=missing, artifact_path=artifact, workspace_root=tmp_path)
    assert no_evidence["verdict"] == "not_supported"
    assert "claims_missing" in no_evidence["blockers"]


def test_chinese_claim_support_uses_cjk_terms_and_still_fails_closed() -> None:
    supported = claim_support_assessment(
        "镜像世界通过数字孪生映射城市与工业系统，使现实世界可被预测和优化。",
        "高精度数字孪生能够把城市、工业与自然系统映射到虚拟空间，让现实世界可被预测和优化。",
    )
    unrelated = claim_support_assessment(
        "可控核聚变将在2035年实现商业化。",
        "高精度数字孪生能够映射城市和工业系统。",
    )

    assert supported["supported"] is True
    assert supported["term_coverage"] >= 0.45
    assert "claim_not_substantive" not in supported["blockers"]
    assert unrelated["supported"] is False
    assert any(item.startswith("evidence_does_not_support_claim") for item in unrelated["blockers"])
    assert "claim_numbers_missing_from_evidence:2035" in unrelated["blockers"]


def test_tampered_evidence_and_writer_approval_are_blockers(tmp_path: Path) -> None:
    artifact, source, proof = _fixture(tmp_path)
    source.write_text("Tampered evidence says something unrelated.", encoding="utf-8")
    tampered = normalize_review_proof(proof_bundle_path=proof, artifact_path=artifact, workspace_root=tmp_path)
    assert "evidence_hash_mismatch_or_stale" in tampered["blockers"]

    artifact, _, proof = _fixture(tmp_path / "approval")
    approved = normalize_review_proof(
        proof_bundle_path=proof,
        artifact_path=artifact,
        workspace_root=tmp_path,
        writer_output={"verdict": "approved"},
    )
    assert "writer_self_approval_rejected" in approved["blockers"]


def test_second_provider_is_observable_as_independent(tmp_path: Path) -> None:
    artifact, _, proof = _fixture(tmp_path)
    result = normalize_review_proof(
        proof_bundle_path=proof,
        artifact_path=artifact,
        workspace_root=tmp_path,
        reviewer_provider="reviewer-provider",
        reviewer_model="reviewer-model",
    )
    assert result["verdict"] == "supported"
    assert result["reviewer_separation"]["independence"]["status"] == "independent_provider"
    assert result["reviewer_separation"]["independence"]["fully_independent"] is True


def test_claim_compiler_does_not_promote_broad_link_to_supported() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE claims (id TEXT, claim_text TEXT, section_ref TEXT, confidence REAL, stance TEXT, run_id TEXT);
        CREATE TABLE claim_evidence (claim_id TEXT, evidence_id TEXT, relation TEXT, strength REAL);
        CREATE TABLE evidence_items (id TEXT, content TEXT);
    """)
    conn.execute("INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?)", ("narrow", "The trial reduced blood pressure by 12%.", "results", .8, "support", "run"))
    conn.execute("INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?)", ("broad", "The intervention cures all cancers.", "results", .8, "support", "run"))
    conn.execute("INSERT INTO evidence_items VALUES (?, ?)", ("ev", "The trial reduced blood pressure by 12%."))
    conn.executemany("INSERT INTO claim_evidence VALUES (?, ?, ?, ?)", [("narrow", "ev", "supports", 1), ("broad", "ev", "supports", 1)])
    alignments = {item.claim_id: item for item in NaiveClaimCompiler().compile(conn, "run")}
    assert alignments["narrow"].alignment_status is AlignmentStatus.SUPPORTED
    assert alignments["broad"].alignment_status is AlignmentStatus.UNVERIFIED

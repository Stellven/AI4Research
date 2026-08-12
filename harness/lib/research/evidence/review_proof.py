"""Fail-closed proof normalization for scientific review.

The reviewer receives a *path* to a writer-produced proof bundle, never the
writer's in-memory object.  It re-reads the reviewed artifact and each cited
source before emitting a verdict.  This keeps the evidence ABI small while
making the provenance and independence boundary observable.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "scientific_review_proof.v1"
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were",
    "with", "we", "our", "study", "result", "results", "show", "shows",
}
_BROAD_CLAIM = re.compile(r"\b(all|always|never|every|none|prove[sd]?|guarantee[sd]?|cure[sd]?|universally)\b", re.I)
_NUMBERS = re.compile(r"\b\d+(?:\.\d+)?%?\b")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tokens(text: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower()) if item not in _STOP_WORDS}


def claim_support_assessment(claim: str, evidence_span: str) -> dict[str, Any]:
    """Return an explainable lexical safety check, not a scientific truth oracle."""
    claim_terms = _tokens(claim)
    evidence_terms = _tokens(evidence_span)
    overlap = sorted(claim_terms & evidence_terms)
    coverage = len(overlap) / len(claim_terms) if claim_terms else 0.0
    missing_numbers = sorted(set(_NUMBERS.findall(claim)) - set(_NUMBERS.findall(evidence_span)))
    broad = bool(_BROAD_CLAIM.search(claim))
    blockers: list[str] = []
    if not evidence_span.strip():
        blockers.append("evidence_span_empty")
    if not claim_terms:
        blockers.append("claim_not_substantive")
    if coverage < 0.45:
        blockers.append(f"evidence_does_not_support_claim:term_coverage={coverage:.2f}")
    if missing_numbers:
        blockers.append("claim_numbers_missing_from_evidence:" + ",".join(missing_numbers))
    if broad:
        blockers.append("claim_scope_too_broad")
    return {
        "supported": not blockers,
        "term_coverage": round(coverage, 3),
        "overlap_terms": overlap,
        "missing_numbers": missing_numbers,
        "broad_claim": broad,
        "blockers": blockers,
    }


def _path(raw: Any, base: Path) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    item = Path(value)
    return item if item.is_absolute() else (base / item)


def _writer_self_approval(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_writer_self_approval(item) for item in value.values())
    if isinstance(value, list):
        return any(_writer_self_approval(item) for item in value)
    return str(value or "").strip().lower() in {"approved", "approve", "pass", "supported"}


def _independence(bundle: dict[str, Any], reviewer_provider: str, reviewer_model: str) -> dict[str, Any]:
    writer = bundle.get("writer") if isinstance(bundle.get("writer"), dict) else {}
    writer_provider = str(writer.get("provider") or "").strip().lower()
    writer_model = str(writer.get("model") or "").strip()
    reviewer_provider = reviewer_provider.strip().lower()
    if not reviewer_provider:
        status = "same_provider_limitation"
        reason = "No second reviewer provider is configured; deterministic reviewer checks are separated by role but not provider."
    elif not writer_provider:
        status = "same_provider_limitation"
        reason = "Writer provider provenance is missing, so independent-provider review cannot be claimed."
    elif writer_provider == reviewer_provider:
        status = "same_provider_limitation"
        reason = "Writer and reviewer use the same provider; full provider independence is not established."
    else:
        status = "independent_provider"
        reason = "Writer and reviewer providers differ."
    return {
        "status": status,
        "writer": {"provider": writer_provider or "unknown", "model": writer_model or "unknown"},
        "reviewer": {"provider": reviewer_provider or "local_deterministic", "model": reviewer_model or "local"},
        "reason": reason,
        "fully_independent": status == "independent_provider",
    }


def bind_reviewer_execution(
    proof: dict[str, Any],
    review_execution: dict[str, Any],
) -> dict[str, Any]:
    """Bind provider-independence provenance to a completed provider call.

    A requested provider is configuration, not execution evidence.  This
    function intentionally leaves the review fail-closed when the provider
    was unavailable/failed, when a supplied file or command bridge was used,
    or when the writer provenance is only a local fixture.
    """
    separation = proof.get("reviewer_separation")
    if not isinstance(separation, dict):
        return proof
    current = separation.get("independence")
    current = current if isinstance(current, dict) else {}
    writer = current.get("writer") if isinstance(current.get("writer"), dict) else {}
    writer_provider = str(writer.get("provider") or "").strip().lower()
    writer_model = str(writer.get("model") or "").strip()
    status = str(review_execution.get("status") or "").strip().lower()
    mode = str(review_execution.get("invocation_mode") or "").strip().lower()
    reviewer_provider = str(review_execution.get("provider") or "").strip().lower()
    reviewer_model = str(review_execution.get("model") or "").strip()

    if status != "completed" or mode != "provider" or not reviewer_provider:
        reason = (
            "Provider independence is not established because no completed "
            "reviewer-provider invocation with provider provenance was recorded."
        )
        independence = {
            "status": "same_provider_limitation",
            "writer": {
                "provider": writer_provider or "unknown",
                "model": writer_model or "unknown",
            },
            "reviewer": {
                "provider": reviewer_provider or "unverified",
                "model": reviewer_model or "unverified",
            },
            "reason": reason,
            "fully_independent": False,
            "execution_bound": False,
        }
    elif writer_provider in {"", "unknown", "local", "local_fixture", "fixture"}:
        independence = {
            "status": "same_provider_limitation",
            "writer": {
                "provider": writer_provider or "unknown",
                "model": writer_model or "unknown",
            },
            "reviewer": {
                "provider": reviewer_provider,
                "model": reviewer_model or "unknown",
            },
            "reason": (
                "The reviewer provider completed, but writer provenance is a "
                "local fixture or is missing; cross-provider independence cannot be claimed."
            ),
            "fully_independent": False,
            "execution_bound": True,
        }
    else:
        synthetic_bundle = {
            "writer": {"provider": writer_provider, "model": writer_model},
        }
        independence = _independence(
            synthetic_bundle,
            reviewer_provider,
            reviewer_model,
        )
        independence["execution_bound"] = True
    separation["independence"] = independence
    proof["reviewer_separation"] = separation
    return proof


def normalize_review_proof(
    *,
    proof_bundle_path: str | Path | None,
    artifact_path: Path | None,
    workspace_root: Path,
    reviewer_provider: str = "",
    reviewer_model: str = "",
    writer_output: Any = None,
) -> dict[str, Any]:
    """Reload and evaluate a persisted proof bundle.

    Contract per claim: claim, evidence span, source, source hash, acceptance
    criterion, reviewer verdict, verdict reason, blockers, and residual risk.
    Invalid or absent parts are represented as blockers; callers must not turn
    those into an approval.
    """
    blockers: list[str] = []
    residual_risks: list[str] = []
    bundle_path = _path(proof_bundle_path, workspace_root)
    bundle: dict[str, Any] = {}
    if bundle_path is None:
        blockers.append("proof_bundle_path_missing")
    elif not bundle_path.is_file():
        blockers.append(f"proof_bundle_missing:{bundle_path}")
    else:
        try:
            loaded = json.loads(bundle_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                blockers.append("proof_bundle_not_object")
            else:
                bundle = loaded
        except (OSError, json.JSONDecodeError) as exc:
            blockers.append(f"proof_bundle_unreadable:{exc}")
    if bundle and str(bundle.get("schema") or "") != SCHEMA:
        blockers.append("proof_bundle_schema_invalid")
    if _writer_self_approval(writer_output) or _writer_self_approval(bundle.get("writer_verdict")):
        blockers.append("writer_self_approval_rejected")

    artifact = bundle.get("artifact") if isinstance(bundle.get("artifact"), dict) else {}
    declared_artifact_path = _path(artifact.get("path"), bundle_path.parent if bundle_path else workspace_root)
    actual_artifact = artifact_path or declared_artifact_path
    artifact_hash = ""
    if actual_artifact is None or not actual_artifact.is_file():
        blockers.append("review_artifact_missing")
    else:
        artifact_hash = sha256_file(actual_artifact)
        if declared_artifact_path is not None and declared_artifact_path.resolve() != actual_artifact.resolve():
            blockers.append("proof_artifact_path_mismatch")
        if str(artifact.get("sha256") or "").lower() != artifact_hash:
            blockers.append("artifact_hash_mismatch_or_stale")

    claims_raw = bundle.get("claims") if isinstance(bundle.get("claims"), list) else []
    if not claims_raw:
        blockers.append("claims_missing")
    claim_results: list[dict[str, Any]] = []
    for index, raw in enumerate(claims_raw):
        item = raw if isinstance(raw, dict) else {}
        claim_id = str(item.get("claim_id") or f"claim-{index + 1}")
        claim = str(item.get("claim") or item.get("claim_text") or "").strip()
        criterion = str(item.get("acceptance_criterion") or "").strip()
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        span = item.get("evidence_span") if isinstance(item.get("evidence_span"), dict) else {}
        item_blockers: list[str] = []
        if not claim:
            item_blockers.append("claim_missing")
        if not criterion:
            item_blockers.append("acceptance_criterion_missing")
        source_path = _path(source.get("path"), bundle_path.parent if bundle_path else workspace_root)
        source_id = str(source.get("source_id") or source.get("id") or "").strip()
        if not source_id:
            item_blockers.append("source_id_missing")
        if source_path is None or not source_path.is_file():
            item_blockers.append("evidence_source_missing")
            source_text = ""
        else:
            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            if str(source.get("sha256") or "").lower() != sha256_file(source_path):
                item_blockers.append("evidence_hash_mismatch_or_stale")
        try:
            start, end = int(span.get("start")), int(span.get("end"))
            span_text = str(span.get("text") or "")
            if start < 0 or end <= start or source_text[start:end] != span_text:
                item_blockers.append("evidence_span_mismatch")
        except (TypeError, ValueError):
            span_text = ""
            item_blockers.append("evidence_span_invalid")
        support = claim_support_assessment(claim, span_text)
        item_blockers.extend(str(value) for value in support["blockers"])
        risk = item.get("residual_risk")
        risks = [str(value) for value in risk] if isinstance(risk, list) else ([str(risk)] if str(risk or "").strip() else [])
        if not risks:
            risks = ["Evidence support is limited to the cited span and stated acceptance criterion."]
        residual_risks.extend(risks)
        verdict = "supported" if not item_blockers else "not_supported"
        claim_results.append({
            "claim_id": claim_id,
            "claim": claim,
            "evidence_span": {"start": span.get("start"), "end": span.get("end"), "text": span_text},
            "source": {"source_id": source_id, "path": str(source_path) if source_path else "", "sha256": str(source.get("sha256") or "")},
            "acceptance_criterion": criterion,
            "verdict": verdict,
            "verdict_reason": "All persisted source, hash, span, and scope checks passed." if verdict == "supported" else "; ".join(dict.fromkeys(item_blockers)),
            "blockers": list(dict.fromkeys(item_blockers)),
            "residual_risk": risks,
            "support_assessment": support,
        })
    all_blockers = list(dict.fromkeys([*blockers, *[blocker for item in claim_results for blocker in item["blockers"]]]))
    independence = _independence(bundle, reviewer_provider, reviewer_model)
    if independence["status"] != "independent_provider":
        residual_risks.append(independence["reason"])
    return {
        "schema": SCHEMA,
        "proof_bundle_path": str(bundle_path) if bundle_path else "",
        "proof_bundle_sha256": sha256_file(bundle_path) if bundle_path and bundle_path.is_file() else "",
        "artifact": {"path": str(actual_artifact) if actual_artifact else "", "sha256": artifact_hash},
        "claims": claim_results,
        "verdict": "supported" if not all_blockers else "not_supported",
        "blockers": all_blockers,
        "residual_risk": list(dict.fromkeys(residual_risks)),
        "reviewer_separation": {
            "reviewer_role": "independent_reviewer",
            "artifact_reloaded_from_disk": bool(actual_artifact and actual_artifact.is_file()),
            "proof_bundle_reloaded_from_disk": bool(bundle_path and bundle_path.is_file()),
            "writer_output_excluded_from_reviewer_context": True,
            "independence": independence,
        },
    }

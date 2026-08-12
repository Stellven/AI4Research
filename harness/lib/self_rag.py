#!/usr/bin/env python3
"""Bounded, provenance-gated retrieval/reflection CLI (not neural training)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FEATURES = ("term_overlap", "citation_match", "authority", "freshness")
DEFAULT_WEIGHTS = dict(zip(FEATURES, (0.30, 0.35, 0.25, 0.10)))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("retrieval artifact must be a JSON object")
    return value


def _weights(path: Path | None) -> tuple[dict[str, float], dict[str, Any]]:
    if path is None:
        return dict(DEFAULT_WEIGHTS), {"type": "evidence_heuristic", "source": "built_in"}
    result = _object(path)
    raw = result.get("model", {}).get("weights", {})
    if result.get("status") != "accepted" or not all(isinstance(raw.get(k), (int, float)) for k in FEATURES):
        raise ValueError("reranker result must be accepted and contain every feature weight")
    return ({k: float(raw[k]) for k in FEATURES}, {
        "type": str(result.get("model", {}).get("type") or "linear_reranker"),
        "source": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })


def evaluate(artifact_path: Path, *, max_iterations: int, reranker_path: Path | None = None) -> dict[str, Any]:
    artifact_path = artifact_path.resolve()
    if not 1 <= max_iterations <= 20:
        raise ValueError("max_iterations must be between 1 and 20")
    artifact = _object(artifact_path)
    question, claims = artifact.get("question"), artifact.get("required_claims")
    sources, rounds = artifact.get("sources"), artifact.get("retrieval_rounds")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    if not isinstance(claims, list) or not claims:
        raise ValueError("required_claims must be non-empty")
    if not isinstance(sources, list) or not isinstance(rounds, list) or not rounds:
        raise ValueError("sources and retrieval_rounds are required")
    claim_text: dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("claim_id") or not claim.get("text"):
            raise ValueError("every required claim needs claim_id and text")
        claim_id = str(claim["claim_id"])
        if claim_id in claim_text:
            raise ValueError(f"duplicate claim_id: {claim_id}")
        claim_text[claim_id] = str(claim["text"])

    source_index: dict[str, dict[str, Any]] = {}
    invalid_sources: list[str] = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("source_id"):
            invalid_sources.append("missing_source_id")
            continue
        sid, content = str(source["source_id"]), source.get("content")
        valid = (isinstance(content, str) and bool(source.get("uri")) and
                 source.get("sha256") == hashlib.sha256(content.encode()).hexdigest())
        if sid in source_index or not valid:
            invalid_sources.append(sid)
        else:
            source_index[sid] = source

    weights, model = _weights(reranker_path.resolve() if reranker_path else None)
    accumulated: dict[str, dict[str, Any]] = {}
    fingerprints: set[str] = set()
    trace: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    status, final_supporters, final_conflicts, final_reasons = "abstained", {}, [], []
    for iteration, batch in enumerate(rounds[:max_iterations], 1):
        if not isinstance(batch, list):
            raise ValueError(f"retrieval round {iteration} must be a list")
        fingerprint = _hash(batch)
        cycle = fingerprint in fingerprints
        fingerprints.add(fingerprint)
        rejected = []
        for candidate in batch:
            if not isinstance(candidate, dict):
                rejected.append({"document_id": "", "reason": "candidate_not_object"})
                continue
            did, sid, citation = (str(candidate.get(k) or "") for k in ("document_id", "source_id", "citation_id"))
            supports, contradicts = candidate.get("supports", []), candidate.get("contradicts", [])
            valid = (did and sid in source_index and citation and isinstance(supports, list) and
                     isinstance(contradicts, list) and all(str(x) in claim_text for x in supports + contradicts))
            if not valid:
                rejected.append({"document_id": did, "reason": "missing_or_invalid_provenance_or_claim_binding"})
                continue
            features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
            accumulated[did] = {
                "document_id": did, "source_id": sid, "citation_id": citation,
                "supports": sorted({str(x) for x in supports}),
                "contradicts": sorted({str(x) for x in contradicts}),
                "rerank_score": sum(weights[k] * float(features.get(k, 0)) for k in FEATURES),
            }
        ranked = sorted(accumulated.values(), key=lambda x: (-x["rerank_score"], x["document_id"]))
        supporters = {cid: [x for x in ranked if cid in x["supports"]] for cid in claim_text}
        contradictors = {cid: [x for x in ranked if cid in x["contradicts"]] for cid in claim_text}
        missing = [cid for cid, values in supporters.items() if not values]
        conflicts = [cid for cid in claim_text if supporters[cid] and contradictors[cid]]
        exhausted = iteration >= max_iterations or iteration >= len(rounds)
        if cycle:
            decision, reasons = "abstain", ["retrieval_cycle_detected"]
        elif not missing and not conflicts:
            decision, reasons = "accept", []
        elif exhausted:
            decision = "abstain"
            reasons = ["iteration_budget_exhausted" if iteration >= max_iterations else "retrieval_rounds_exhausted"]
            reasons += ["required_claim_coverage_missing"] if missing else []
            reasons += ["unresolved_evidence_conflict"] if conflicts else []
        else:
            decision = "retrieve_more"
            reasons = (["required_claim_coverage_missing"] if missing else []) + (["unresolved_evidence_conflict"] if conflicts else [])
        state = {
            "iteration": iteration, "batch_sha256": fingerprint,
            "accepted_document_ids": [x["document_id"] for x in ranked],
            "rejected_candidates": rejected,
            "ranked_candidates": [{"document_id": x["document_id"], "source_id": x["source_id"], "score": x["rerank_score"]} for x in ranked],
            "covered_claim_ids": [cid for cid in claim_text if supporters[cid]],
            "missing_claim_ids": missing, "conflicting_claim_ids": conflicts,
            "decision": decision, "reasons": reasons,
        }
        trace_hash = hashlib.sha256(bytes.fromhex(previous_hash) + _canonical(state)).hexdigest()
        trace.append({**state, "previous_trace_sha256": previous_hash, "trace_sha256": trace_hash})
        previous_hash = trace_hash
        final_supporters, final_conflicts, final_reasons = supporters, conflicts, reasons
        if decision != "retrieve_more":
            status = "accepted" if decision == "accept" else "abstained"
            break

    answer = []
    if status == "accepted":
        for cid, text in claim_text.items():
            best = final_supporters[cid][0]
            answer.append({"claim_id": cid, "text": text, "citation_id": best["citation_id"], "source_id": best["source_id"]})
    unsupported = sum(item["claim_id"] not in claim_text or not final_supporters.get(item["claim_id"]) for item in answer)
    return {
        "schema_version": "solar.self_rag.v1", "status": status, "question": question,
        "source_artifact": {"path": str(artifact_path), "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest()},
        "reranker": {**model, "weights": weights}, "iterations_used": len(trace),
        "max_iterations": max_iterations, "trace": trace, "trace_sha256": previous_hash,
        "answer": answer,
        "answer_policy": {"unsupported_answer_count": unsupported, "abstained_on_failure": status != "accepted" and not answer},
        "unresolved_conflicting_claim_ids": final_conflicts, "reasons": final_reasons,
        "invalid_source_ids": sorted(set(invalid_sources)),
        "limitations": [
            "This is a bounded evidence-reflection control loop, not neural Self-RAG fine-tuning.",
            "Quality claims are limited to the hash-bound retrieval artifact and configured lightweight reranker.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", nargs="?")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--reranker-result", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(args.artifact, max_iterations=args.max_iterations, reranker_path=args.reranker_result)
        code = 0
    except Exception as exc:
        result, code = {"schema_version": "solar.self_rag.v1", "status": "rejected", "errors": [str(exc)]}, 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

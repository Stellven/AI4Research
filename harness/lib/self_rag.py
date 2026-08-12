#!/usr/bin/env python3
"""Bounded evidence reflection over the production local learning retriever."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from advanced_ai4rnd.retrieval.learning_retrieval import LearningRetriever, Reranker


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_corpus(corpus_dir: Path) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    documents: list[dict[str, Any]] = []
    versions: dict[str, set[str]] = {}
    for path in sorted(corpus_dir.resolve().glob("*.json")):
        raw = read_object(path)
        logical_id, text, provenance = raw.get("document_id"), raw.get("text"), raw.get("provenance")
        if not isinstance(logical_id, str) or not logical_id or not isinstance(text, str) or not text:
            raise ValueError(f"{path} needs document_id and text")
        if not isinstance(provenance, dict) or not provenance.get("uri"):
            raise ValueError(f"{path} needs provenance.uri")
        version_hash = digest({"text": text, "provenance": provenance})
        versions.setdefault(logical_id, set()).add(version_hash)
        documents.append({
            "id": f"{logical_id}@{version_hash}", "logical_id": logical_id,
            "text": text, "provenance": {**provenance, "logical_document_id": logical_id,
            "version_sha256": version_hash, "corpus_path": str(path)},
        })
    if not documents:
        raise ValueError("corpus directory contains no JSON documents")
    return documents, versions


def exact_support(claim: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quote = claim.get("required_exact_quote")
    if not isinstance(quote, str) or not quote:
        raise ValueError("every claim needs required_exact_quote")
    matches = []
    for row in rows:
        text = str(row["text"])
        offset = text.find(quote)
        if offset < 0:
            continue
        span = text[offset:offset + len(quote)]
        matches.append({
            "document_version_id": row["id"], "logical_document_id": row["provenance"]["logical_document_id"],
            "source_uri": row["provenance"]["uri"], "source_version_sha256": row["provenance"]["version_sha256"],
            "start": offset, "end": offset + len(quote), "quote": span,
            "quote_sha256": hashlib.sha256(span.encode("utf-8")).hexdigest(),
        })
    return matches


def evaluate(request_path: Path, corpus_dir: Path, state_path: Path, *, max_iterations: int,
             top_k: int = 2, reranker_state: Path | None = None) -> dict[str, Any]:
    if not 1 <= max_iterations <= 20 or top_k < 1:
        raise ValueError("max_iterations must be 1..20 and top_k positive")
    request, documents_versions = read_object(request_path.resolve()), None
    question, claims = request.get("question"), request.get("required_claims")
    if not isinstance(question, str) or not question.strip() or not isinstance(claims, list) or not claims:
        raise ValueError("question and non-empty required_claims are required")
    claim_ids = [str(c.get("claim_id") or "") for c in claims if isinstance(c, dict)]
    if len(claim_ids) != len(claims) or "" in claim_ids or len(set(claim_ids)) != len(claim_ids):
        raise ValueError("claim IDs must be present and unique")
    documents, documents_versions = load_corpus(corpus_dir)
    retriever = LearningRetriever(state_path.resolve())
    retriever.index(documents)
    reranker = Reranker(reranker_state.resolve()) if reranker_state else None

    version_conflicts = sorted(key for key, value in documents_versions.items() if len(value) > 1)
    query, seen_batches, accumulated = question, set(), {}
    trace, prior_hash, status, reasons, supports = [], "0" * 64, "abstained", [], {}
    for iteration in range(1, max_iterations + 1):
        retrieved = retriever.retrieve(query, top_k=min(len(documents), top_k * iteration))
        ranked = reranker.rerank(query, retrieved) if reranker else retrieved
        batch_hash = digest([{"id": row["id"], "version": row["provenance"]["version_sha256"]} for row in ranked])
        cycle = batch_hash in seen_batches
        seen_batches.add(batch_hash)
        for row in ranked:
            existing = accumulated.get(row["id"])
            immutable = {"text": row["text"], "provenance": row["provenance"]}
            if existing is not None and digest(existing) != digest(immutable):
                version_conflicts.append(row["provenance"]["logical_document_id"])
            accumulated[row["id"]] = immutable
        verified_rows = [{"id": key, **value} for key, value in accumulated.items()]
        supports = {claim_id: exact_support(claim, verified_rows) for claim_id, claim in zip(claim_ids, claims)}
        missing = [claim_id for claim_id in claim_ids if not supports[claim_id]]
        # A logical document with multiple content/provenance hashes is an
        # immutable-version conflict even if ranking would hide one version.
        active_conflicts = sorted(set(version_conflicts))
        if active_conflicts:
            decision, reasons = "abstain", ["immutable_document_version_conflict"]
        elif not missing:
            decision, reasons = "accept", []
        elif cycle:
            decision, reasons = "abstain", ["retrieval_cycle_detected", "required_claim_coverage_missing"]
        elif iteration >= max_iterations:
            decision, reasons = "abstain", ["iteration_budget_exhausted", "required_claim_coverage_missing"]
        else:
            decision, reasons = "retrieve_more", ["required_claim_coverage_missing"]
            missing_quotes = [str(claim["required_exact_quote"]) for claim in claims if str(claim["claim_id"]) in missing]
            query = " ".join([question, *missing_quotes])
        state = {
            "iteration": iteration, "query": query, "retrieval_entrypoint": "LearningRetriever.retrieve",
            "retrieved_document_version_ids": [row["id"] for row in ranked], "batch_sha256": batch_hash,
            "verified_support": supports, "missing_claim_ids": missing,
            "document_version_conflicts": active_conflicts, "decision": decision, "reasons": reasons,
        }
        trace_hash = hashlib.sha256(bytes.fromhex(prior_hash) + canonical(state)).hexdigest()
        trace.append({**state, "previous_trace_sha256": prior_hash, "trace_sha256": trace_hash})
        prior_hash = trace_hash
        if decision != "retrieve_more":
            status = "accepted" if decision == "accept" else "abstained"
            break
    answer = [] if status != "accepted" else [
        {"claim_id": cid, "text": str(claim.get("text") or claim["required_exact_quote"]), "evidence": supports[cid]}
        for cid, claim in zip(claim_ids, claims)
    ]
    return {
        "schema_version": "solar.self_rag.v2", "status": status, "question": question,
        "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        "corpus": {"path": str(corpus_dir.resolve()), "document_version_count": len(documents),
                   "index_state": str(state_path.resolve()), "retrieval_entrypoint": "advanced_ai4rnd.retrieval.learning_retrieval.LearningRetriever"},
        "iterations_used": len(trace), "max_iterations": max_iterations, "trace": trace, "trace_sha256": prior_hash,
        "answer": answer, "answer_policy": {"unsupported_answer_count": 0, "abstained_on_failure": status != "accepted" and not answer},
        "reasons": reasons, "limitations": [
            "Exact-span evidence verification is deterministic and conservative; semantic paraphrase entailment is not claimed.",
            "This is a bounded local retrieval reflection loop, not neural Self-RAG fine-tuning or broad-corpus generalization.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", nargs="?")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--index-state", required=True, type=Path)
    parser.add_argument("--reranker-state", type=Path)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(args.request, args.corpus, args.index_state, max_iterations=args.max_iterations,
                          top_k=args.top_k, reranker_state=args.reranker_state)
        code = 0
    except Exception as exc:
        result, code = {"schema_version": "solar.self_rag.v2", "status": "rejected", "errors": [str(exc)]}, 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def test_p22_self_rag_bounded_reflection(repo_root: Path) -> None:
    run_id = "p22-self-rag-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    output_dir.mkdir(parents=True)
    fixture = repo_root / "tests/journeys/phase22/fixtures/significant/self_rag/retrieval-artifact.json"
    production_cli = repo_root / "harness/lib/self_rag.py"
    reranker_cli = repo_root / "harness/lib/retrieval_reranker.py"
    reranker_dataset = output_dir / "labeled-retrieval.jsonl"
    rows = []
    for split, query in (("train", "train-query"), ("holdout", "holdout-query")):
        rows.extend([
            {"split": split, "query_id": query, "document_id": query + "-relevant",
             "provenance_id": "source:" + query + "-relevant", "relevance": 2, "base_score": .2,
             "features": {"term_overlap": 1, "citation_match": 1, "authority": .9, "freshness": .5}},
            {"split": split, "query_id": query, "document_id": query + "-noise",
             "provenance_id": "source:" + query + "-noise", "relevance": 0, "base_score": .9,
             "features": {"term_overlap": .1, "citation_match": 0, "authority": .1, "freshness": .5}},
        ])
    reranker_dataset.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    reranker_result = output_dir / "reranker-result.json"
    reranker_command = [sys.executable, str(reranker_cli), "train", "--dataset", str(reranker_dataset),
                        "--k", "1", "--output", str(reranker_result)]
    reranker_process = subprocess.run(reranker_command, cwd=repo_root, capture_output=True, text=True, timeout=30)
    result_path = output_dir / "self-rag-result.json"
    command = [sys.executable, str(production_cli), "run", "--artifact", str(fixture),
               "--max-iterations", "3", "--reranker-result", str(reranker_result),
               "--output", str(result_path)]
    process = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=30)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assertions = {
        "production_cli_exited_zero": process.returncode == 0,
        "learned_reranker_bound": reranker_process.returncode == 0 and result["reranker"]["source"] == str(reranker_result.resolve())
                                    and len(result["reranker"]["sha256"]) == 64,
        "reflection_retrieved_more": result["trace"][0]["decision"] == "retrieve_more",
        "second_round_accepted": result["status"] == "accepted" and result["iterations_used"] == 2,
        "missing_provenance_rejected": result["trace"][0]["rejected_candidates"] == [
            {"document_id": "unbound-result", "reason": "missing_or_invalid_provenance_or_claim_binding"}],
        "all_claims_source_bound": len(result["answer"]) == 2 and all(x["source_id"] for x in result["answer"]),
        "no_unsupported_answer": result["answer_policy"]["unsupported_answer_count"] == 0,
        "trace_hash_chained": result["trace"][1]["previous_trace_sha256"] == result["trace"][0]["trace_sha256"],
        "input_hash_recorded": len(result["source_artifact"]["sha256"]) == 64,
    }
    evidence = {
        "schema_version": "phase22.self_rag_journey.v1", "journey_id": "NT-memory-retrieval",
        "run_id": run_id, "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "production_commands": [reranker_command, command], "input_fixture": str(fixture), "assertions": assertions,
        "stdout_tail": process.stdout[-2000:], "stderr_tail": process.stderr[-2000:],
        "artifacts": [str(reranker_dataset), str(reranker_result), str(result_path)],
        "status": "PASS_WITH_KNOWN_LIMITATIONS" if all(assertions.values()) else "FAIL",
        "limitations": result.get("limitations", []),
    }
    evidence_path = output_dir / "journey-result.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    assert all(assertions.values()), evidence_path

import copy
import hashlib
import json

from harness.lib.self_rag import evaluate


def source(source_id, content):
    return {"source_id": source_id, "uri": f"fixture://{source_id}", "content": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest()}


def candidate(document_id, source_id, *, supports=(), contradicts=()):
    return {"document_id": document_id, "source_id": source_id, "citation_id": f"cite:{source_id}",
            "supports": list(supports), "contradicts": list(contradicts),
            "features": {"term_overlap": 1, "citation_match": 1, "authority": .8, "freshness": .5}}


def artifact():
    return {"question": "q", "required_claims": [{"claim_id": "a", "text": "claim a"},
            {"claim_id": "b", "text": "claim b"}], "sources": [source("sa", "a"), source("sb", "b")],
            "retrieval_rounds": [[candidate("da", "sa", supports=("a",))],
                                 [candidate("db", "sb", supports=("b",))]]}


def write(tmp_path, value, name="artifact.json"):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_retrieves_more_then_accepts_source_bound_claims(tmp_path):
    result = evaluate(write(tmp_path, artifact()), max_iterations=3)
    assert result["status"] == "accepted"
    assert [x["decision"] for x in result["trace"]] == ["retrieve_more", "accept"]
    assert result["answer_policy"]["unsupported_answer_count"] == 0
    assert {x["source_id"] for x in result["answer"]} == {"sa", "sb"}
    assert result["trace"][1]["previous_trace_sha256"] == result["trace"][0]["trace_sha256"]


def test_missing_provenance_is_rejected_and_budget_abstains(tmp_path):
    value = artifact()
    value["retrieval_rounds"] = [[candidate("bad", "unknown", supports=("a", "b"))]]
    result = evaluate(write(tmp_path, value), max_iterations=1)
    assert result["status"] == "abstained" and result["answer"] == []
    assert result["trace"][0]["rejected_candidates"][0]["reason"].startswith("missing_or_invalid")
    assert "required_claim_coverage_missing" in result["reasons"]


def test_conflicting_evidence_never_produces_answer(tmp_path):
    value = artifact()
    value["retrieval_rounds"] = [[candidate("support", "sa", supports=("a", "b")),
                                  candidate("conflict", "sb", contradicts=("a",))]]
    result = evaluate(write(tmp_path, value), max_iterations=1)
    assert result["status"] == "abstained" and result["answer"] == []
    assert result["unresolved_conflicting_claim_ids"] == ["a"]
    assert "unresolved_evidence_conflict" in result["reasons"]


def test_repeated_retrieval_round_detects_cycle(tmp_path):
    value = artifact()
    value["retrieval_rounds"] = [value["retrieval_rounds"][0], copy.deepcopy(value["retrieval_rounds"][0])]
    result = evaluate(write(tmp_path, value), max_iterations=5)
    assert result["status"] == "abstained" and result["iterations_used"] == 2
    assert result["reasons"] == ["retrieval_cycle_detected"]


def test_tampered_source_hash_cannot_support_answer(tmp_path):
    value = artifact()
    value["sources"][0]["sha256"] = "0" * 64
    result = evaluate(write(tmp_path, value), max_iterations=2)
    assert result["status"] == "abstained" and "sa" in result["invalid_source_ids"]
    assert result["answer_policy"]["abstained_on_failure"] is True

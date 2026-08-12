import json
from pathlib import Path

from harness.lib.self_rag import evaluate


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def doc(corpus, file_name, doc_id, text, uri=None):
    return write(corpus / file_name, {"document_id": doc_id, "text": text,
                 "provenance": {"uri": uri or f"local://{doc_id}"}})


def request(path, question="controlled trial findings", quote="Observed nitrate declined by twelve percent."):
    return write(path, {"question": question, "required_claims": [
        {"claim_id": "finding", "text": "Nitrate declined.", "required_exact_quote": quote}]})


def run(tmp_path, **kwargs):
    return evaluate(tmp_path / "request.json", tmp_path / "corpus", tmp_path / "index.json",
                    max_iterations=kwargs.get("max_iterations", 3), top_k=kwargs.get("top_k", 1))


def test_real_index_retrieves_and_verifies_exact_span(tmp_path):
    corpus = tmp_path / "corpus"
    doc(corpus, "noise.json", "cats", "Domestic cats sleep for much of the day.")
    text = "Methods were preregistered. Observed nitrate declined by twelve percent."
    doc(corpus, "result.json", "nitrate", text)
    request(tmp_path / "request.json", question="controlled nitrate trial findings")
    result = run(tmp_path)
    evidence = result["answer"][0]["evidence"][0]
    assert result["status"] == "accepted"
    assert evidence["quote"] == text[evidence["start"]:evidence["end"]]
    assert len(evidence["quote_sha256"]) == len(evidence["source_version_sha256"]) == 64
    assert result["corpus"]["retrieval_entrypoint"].endswith("LearningRetriever")


def test_moon_cheese_claim_cannot_be_supported_by_cat_document(tmp_path):
    corpus = tmp_path / "corpus"
    doc(corpus, "cats.json", "cats", "Domestic cats sleep for much of the day and hunt at dusk.")
    request(tmp_path / "request.json", question="Are cats evidence the Moon is cheese?",
            quote="The Moon is made of cheese.")
    result = run(tmp_path, max_iterations=2)
    assert result["status"] == "abstained" and result["answer"] == []
    assert result["answer_policy"]["unsupported_answer_count"] == 0
    assert "required_claim_coverage_missing" in result["reasons"]


def test_same_document_id_changed_content_is_immutable_conflict(tmp_path):
    corpus = tmp_path / "corpus"
    quote = "Observed nitrate declined by twelve percent."
    doc(corpus, "version-a.json", "result", quote, "local://result/a")
    doc(corpus, "version-b.json", "result", quote + " Later analysis disputes it.", "local://result/b")
    request(tmp_path / "request.json", question="nitrate result", quote=quote)
    result = run(tmp_path, top_k=2)
    assert result["status"] == "abstained" and result["answer"] == []
    assert result["reasons"] == ["immutable_document_version_conflict"]
    assert result["trace"][0]["document_version_conflicts"] == ["result"]


def test_changed_document_across_runs_conflicts_despite_top_k_one(tmp_path):
    corpus = tmp_path / "corpus"
    quote = "Observed nitrate declined by twelve percent."
    result_path = corpus / "result.json"
    doc(corpus, "result.json", "result", quote, "local://result/a")
    request(tmp_path / "request.json", question="nitrate result", quote=quote)
    first = run(tmp_path, top_k=1)
    assert first["status"] == "accepted"
    result_path.unlink()
    doc(corpus, "result.json", "result", quote + " A correction changed the source.", "local://result/b")
    second = run(tmp_path, top_k=1)
    assert second["status"] == "abstained" and second["answer"] == []
    assert second["reasons"] == ["immutable_document_version_conflict"]
    assert len(second["corpus"]["persistent_document_lineage"]["result"]) == 2


def test_budget_and_cycle_guards_remain(tmp_path):
    corpus = tmp_path / "corpus"
    doc(corpus, "cats.json", "cats", "Domestic cats sleep for much of the day.")
    request(tmp_path / "request.json", quote="The Moon is made of cheese.")
    budget = run(tmp_path, max_iterations=1)
    assert budget["reasons"][0] == "iteration_budget_exhausted"
    cycle = evaluate(tmp_path / "request.json", corpus, tmp_path / "cycle-index.json", max_iterations=3, top_k=10)
    assert cycle["reasons"][0] == "retrieval_cycle_detected"
    assert cycle["iterations_used"] == 2

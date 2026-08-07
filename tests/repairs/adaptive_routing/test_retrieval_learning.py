from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "harness" / "lib"))

from advanced_ai4rnd.retrieval import LearningRetriever, Reranker, SelfRAGLoop  # noqa: E402


def _documents() -> list[dict]:
    return [
        {
            "id": "polymer-note",
            "text": "Polymer stability baseline for encapsulation.",
            "provenance": {"source": "fixture", "line": 1},
        },
        {
            "id": "perovskite-note",
            "text": "Solar perovskite degradation protocol with iodide migration evidence.",
            "provenance": {"source": "fixture", "line": 2},
        },
        {
            "id": "control-note",
            "text": "Control document about unrelated lab inventory.",
            "provenance": {"source": "fixture", "line": 3},
        },
    ]


def test_memory_retrieval_learning_changes_later_results_and_recovers_after_restart(tmp_path: Path) -> None:
    state = tmp_path / "retriever.json"
    retriever = LearningRetriever(state)
    retriever.index(_documents())

    before = retriever.retrieve("polymer stability", top_k=2)
    assert [item["id"] for item in before] == ["polymer-note", "control-note"]
    assert all(item["provenance"]["source"] == "fixture" for item in before)

    update = retriever.learn_feedback("polymer stability", ["perovskite-note"], amount=5.0)
    after = retriever.retrieve("polymer stability", top_k=2)
    assert update["before"] != update["after"]
    assert after[0]["id"] == "perovskite-note"

    restarted = LearningRetriever(state)
    recovered = restarted.retrieve("polymer stability", top_k=1)
    assert recovered[0]["id"] == "perovskite-note"


def test_self_rag_has_observable_retrieve_critique_revise_loop(tmp_path: Path) -> None:
    retriever = LearningRetriever(tmp_path / "retriever.json")
    retriever.index(_documents())
    loop = SelfRAGLoop(retriever).answer(
        "polymer stability",
        required_terms=("perovskite", "iodide"),
        top_k=1,
    )

    assert [step["step"] for step in loop["steps"]] == ["retrieve", "critique", "revise"]
    assert loop["steps"][1]["passes"] is False
    assert "perovskite" in loop["steps"][2]["query"]
    assert loop["steps"][2]["document_ids"] == ["perovskite-note"]
    assert loop["citations"][0]["source"] == "fixture"


def test_reranker_trains_or_loads_real_scoring_state_not_original_order(tmp_path: Path) -> None:
    state = tmp_path / "reranker.json"
    candidates = [
        {"id": "first", "score": 10.0, "text": "first original item"},
        {"id": "preferred", "score": 9.5, "text": "preferred relevant item"},
    ]
    reranker = Reranker(state)
    before = reranker.rerank("routing evidence", candidates)
    assert [item["id"] for item in before] == ["first", "preferred"]

    event = reranker.train(
        [
            {"query": "routing evidence", "doc_id": "preferred", "label": 1},
            {"query": "routing evidence", "doc_id": "first", "label": 0},
        ]
    )
    after = reranker.rerank("routing evidence", candidates)
    assert event["changed"] is True
    assert [item["id"] for item in after] == ["preferred", "first"]

    reloaded = Reranker(state)
    loaded = reloaded.rerank("routing evidence", candidates)
    assert [item["id"] for item in loaded] == ["preferred", "first"]

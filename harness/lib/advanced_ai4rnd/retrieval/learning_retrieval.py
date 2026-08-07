"""Stateful deterministic retrieval learning, reranking, and Self-RAG."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(text)]


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class LearningRetriever:
    """Simple lexical retriever whose learned boosts persist across restarts."""

    schema_version = "solar.advanced_ai4rnd.learning_retriever.v1"

    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        self.state: dict[str, Any] = (
            json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        ) or {"schema_version": self.schema_version, "documents": {}, "boosts": {}, "events": []}

    def index(self, documents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        for document in documents:
            doc_id = str(document["id"])
            provenance = document.get("provenance") or {}
            if not provenance:
                raise ValueError(f"document {doc_id} missing provenance")
            self.state["documents"][doc_id] = {
                "id": doc_id,
                "text": str(document["text"]),
                "provenance": provenance,
            }
        event = {"event_type": "index_write", "created_at": _now(), "document_count": len(documents)}
        self.state["events"].append(event)
        self.save()
        return event

    def retrieve(self, query: str, *, top_k: int = 3) -> list[dict[str, Any]]:
        query_counts = Counter(_tokens(query))
        rows: list[dict[str, Any]] = []
        for doc_id, document in self.state["documents"].items():
            lexical = sum(Counter(_tokens(document["text"]))[token] * count for token, count in query_counts.items())
            learned = float(self.state["boosts"].get(doc_id, 0.0))
            score = lexical + learned
            rows.append(
                {
                    "id": doc_id,
                    "score": round(score, 8),
                    "lexical_score": lexical,
                    "learned_boost": round(learned, 8),
                    "text": document["text"],
                    "provenance": document["provenance"],
                }
            )
        rows.sort(key=lambda item: (-item["score"], item["id"]))
        event = {
            "event_type": "retrieve",
            "created_at": _now(),
            "query": query,
            "top_ids": [item["id"] for item in rows[:top_k]],
        }
        self.state["events"].append(event)
        self.save()
        return rows[:top_k]

    def learn_feedback(self, query: str, relevant_doc_ids: Sequence[str], *, amount: float = 2.0) -> dict[str, Any]:
        before = dict(self.state["boosts"])
        query_tokens = set(_tokens(query))
        for doc_id in relevant_doc_ids:
            if doc_id not in self.state["documents"]:
                raise KeyError(f"unknown document: {doc_id}")
            overlap = len(query_tokens & set(_tokens(self.state["documents"][doc_id]["text"])))
            self.state["boosts"][doc_id] = round(float(self.state["boosts"].get(doc_id, 0.0)) + amount + overlap * 0.1, 8)
        event = {
            "event_type": "retrieval_learning_update",
            "created_at": _now(),
            "query": query,
            "relevant_doc_ids": list(relevant_doc_ids),
            "before": before,
            "after": dict(self.state["boosts"]),
        }
        self.state["events"].append(event)
        self.save()
        return event

    def save(self) -> None:
        _atomic_write_json(self.state_path, self.state)


class Reranker:
    """Persistent linear reranker that changes candidate order from state."""

    schema_version = "solar.advanced_ai4rnd.reranker.v1"

    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        self.state: dict[str, Any] = (
            json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        ) or {"schema_version": self.schema_version, "doc_weights": {}, "token_weights": {}, "events": []}

    def train(self, examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not examples:
            raise ValueError("reranker training requires examples")
        before = json.loads(json.dumps(self.state, sort_keys=True))
        doc_weights = Counter({str(k): float(v) for k, v in self.state.get("doc_weights", {}).items()})
        token_weights = Counter({str(k): float(v) for k, v in self.state.get("token_weights", {}).items()})
        for example in examples:
            doc_id = str(example["doc_id"])
            label = float(example["label"])
            delta = 1.0 if label > 0 else -1.0
            doc_weights[doc_id] += delta
            for token in set(_tokens(str(example.get("query", "")))):
                token_weights[token] += 0.15 * delta
        self.state["doc_weights"] = {k: round(v, 8) for k, v in sorted(doc_weights.items())}
        self.state["token_weights"] = {k: round(v, 8) for k, v in sorted(token_weights.items())}
        event = {
            "event_type": "reranker_train",
            "created_at": _now(),
            "example_count": len(examples),
            "changed": before != self.state,
            "state_path": str(self.state_path),
        }
        self.state["events"].append(event)
        self.save()
        return event

    def rerank(self, query: str, candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        query_bonus = sum(float(self.state["token_weights"].get(token, 0.0)) for token in set(_tokens(query)))
        rows: list[dict[str, Any]] = []
        for position, candidate in enumerate(candidates):
            doc_id = str(candidate["id"])
            base = float(candidate.get("score", 0.0))
            learned = float(self.state["doc_weights"].get(doc_id, 0.0)) + query_bonus
            item = dict(candidate)
            item["rerank_score"] = round(base + learned, 8)
            item["original_rank"] = position
            item["learned_score"] = round(learned, 8)
            rows.append(item)
        rows.sort(key=lambda item: (-item["rerank_score"], item["id"]))
        return rows

    def save(self) -> None:
        _atomic_write_json(self.state_path, self.state)


class SelfRAGLoop:
    """Observable retrieve/critique/revise loop over local fixtures."""

    def __init__(self, retriever: LearningRetriever, reranker: Reranker | None = None):
        self.retriever = retriever
        self.reranker = reranker

    def answer(self, query: str, *, required_terms: Sequence[str], top_k: int = 2) -> dict[str, Any]:
        retrieved = self.retriever.retrieve(query, top_k=top_k)
        ranked = self.reranker.rerank(query, retrieved) if self.reranker else retrieved
        critique = self._critique(ranked, required_terms)
        revised_query = query
        revised = ranked
        if not critique["passes"]:
            missing = " ".join(critique["missing_terms"])
            revised_query = f"{query} {missing}".strip()
            revised = self.retriever.retrieve(revised_query, top_k=top_k)
            revised = self.reranker.rerank(revised_query, revised) if self.reranker else revised
        answer_text = " ".join(item["text"] for item in revised)
        loop = {
            "schema_version": "solar.advanced_ai4rnd.self_rag_loop.v1",
            "query": query,
            "steps": [
                {"step": "retrieve", "query": query, "document_ids": [item["id"] for item in retrieved]},
                {"step": "critique", **critique},
                {"step": "revise", "query": revised_query, "document_ids": [item["id"] for item in revised]},
            ],
            "answer": answer_text,
            "citations": [item["provenance"] for item in revised],
        }
        self.retriever.state["events"].append({"event_type": "self_rag_loop", "created_at": _now(), "loop": loop})
        self.retriever.save()
        return loop

    @staticmethod
    def _critique(candidates: Sequence[Mapping[str, Any]], required_terms: Sequence[str]) -> dict[str, Any]:
        joined = " ".join(str(item.get("text", "")).lower() for item in candidates)
        missing = [term for term in required_terms if term.lower() not in joined]
        return {"passes": not missing, "missing_terms": missing}

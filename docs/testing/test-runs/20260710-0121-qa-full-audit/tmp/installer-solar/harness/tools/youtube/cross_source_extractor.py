"""Cross-source entity and link extraction for transcript text."""
from __future__ import annotations

import re
from dataclasses import dataclass


ENTITY_PATTERNS: dict[str, str] = {
    "repo": r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b",
    "paper": r"\barXiv:\d{4}\.\d{4,5}\b|\b[A-Z][a-z]+ et al\.\b",
    "model": r"\b(?:GPT-\d(?:\.\d+)?|Qwen[\w.-]+|Llama[\w.-]+|Gemini[\w.-]+)\b",
    "product": r"\b(?:YouTube|ChatGPT|GitHub|TensorRT-LLM|vLLM)\b",
    "company": r"\b(?:OpenAI|Google|Microsoft|Meta|NVIDIA|Anthropic)\b",
    "people": r"\b(?:Sam Altman|Jensen Huang|Demis Hassabis)\b",
    "term": r"\b(?:KV cache|continuous batching|hallucination|diarization)\b",
}


@dataclass
class CrossSourceExtraction:
    entities: dict[str, list[str]]
    links: list[dict[str, str]]
    recall_estimate: float
    trigger_source: str


def extract_entities(text: str) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for entity_type, pattern in ENTITY_PATTERNS.items():
        matches = sorted(set(match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE)))
        if matches:
            results[entity_type] = matches
    return results


def build_links(*, source_kind: str, source_id: str, entities: dict[str, list[str]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    mapping = {
        "repo": "github_repo",
        "paper": "paper",
        "model": "model",
    }
    for entity_type, target_type in mapping.items():
        for entity in entities.get(entity_type, []):
            links.append(
                {
                    "source_type": source_kind,
                    "source_id": source_id,
                    "target_type": target_type,
                    "target_id": entity,
                    "link_type": "mentioned",
                }
            )
    return links


def extract_cross_source(text: str, *, source_kind: str, source_id: str) -> CrossSourceExtraction:
    entities = extract_entities(text)
    links = build_links(source_kind=source_kind, source_id=source_id, entities=entities)
    expected_classes = {"repo", "paper", "model", "product", "company", "people", "term"}
    present = {entity_type for entity_type, values in entities.items() if values}
    recall_estimate = round(len(present) / len(expected_classes), 2)
    trigger_source = "primary" if recall_estimate >= 0.70 else "fallback_no_r11"
    return CrossSourceExtraction(
        entities=entities,
        links=links,
        recall_estimate=recall_estimate,
        trigger_source=trigger_source,
    )

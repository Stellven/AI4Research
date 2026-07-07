#!/usr/bin/env python3
"""AutoSci model-command bridge backed by a local Ollama chat model."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
import urllib.error
import urllib.request


REQUIRED_PATHS = [
    ("A:landscape-driven", "landscape gap"),
    ("B:incremental", "incremental improvement"),
    ("C:combination", "combined mechanism"),
    ("D:innovation", "new mechanism"),
    ("E:cross-domain-transfer", "transfer probe"),
]

OFF_TOPIC_SOLAR_TERMS = (
    "solar panel",
    "wind energy",
    "perovskite",
    "photovoltaic",
    "aerospace",
)


def _request_target_id(request: dict) -> str:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    topic = str(context.get("topic") or context.get("target") or request.get("action") or "")
    match = re.search(r"([a-z]+-\d{2}|r\d{2})", topic.lower())
    return match.group(1) if match else ""


def _primary_source_context(request: dict) -> tuple[str, list[str], str]:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    target_id = _request_target_id(request)
    source_summary = context.get("source_summary") if isinstance(context.get("source_summary"), dict) else {}
    source_refs = [str(item) for item in source_summary.get("source_refs") or [] if str(item).strip()]
    source_ids = [str(item) for item in source_summary.get("source_ids") or [] if str(item).strip()]
    selected_refs: list[str] = []
    if target_id:
        selected_refs = [ref for ref in source_refs if f"paper-{target_id}" in Path(ref).name.lower()]
    if not selected_refs and source_refs:
        selected_refs = source_refs[:1]
    chunks: list[str] = []
    for ref in selected_refs[:1]:
        try:
            chunks.append(Path(ref).read_text(encoding="utf-8")[:3000])
        except OSError:
            chunks.append(ref)
    primary_ids = [sid for sid in source_ids if target_id and f"paper-{target_id}" in sid.lower()]
    if not primary_ids and target_id:
        primary_ids = [f"wiki:papers/paper-{target_id}"]
    return "\n\n".join(chunks)[:3500], primary_ids or [f"autosci-request:{request.get('action', 'generate_ideas')}"], target_id


def _json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    candidates = [text]
    brace_delta = text.count("{") - text.count("}")
    bracket_delta = text.count("[") - text.count("]")
    if brace_delta > 0 or bracket_delta > 0:
        candidates.append(f"{text}{']' * max(0, bracket_delta)}{'}' * max(0, brace_delta)}")
    try:
        payload = json.loads(candidates[-1])
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        matched = match.group(0)
        brace_delta = matched.count("{") - matched.count("}")
        bracket_delta = matched.count("[") - matched.count("]")
        payload = json.loads(f"{matched}{']' * max(0, bracket_delta)}{'}' * max(0, brace_delta)}")
    if isinstance(payload, list):
        return {"outputs": {"ideas": payload}}
    if not isinstance(payload, dict):
        raise ValueError("model response JSON is not an object or idea list")
    return payload


def _normalize_payload(
    payload: dict,
    *,
    request: dict,
    model: str,
    primary_ids: list[str],
    primary_context: str,
    target_id: str,
) -> dict:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else payload
    ideas = outputs.get("ideas") if isinstance(outputs.get("ideas"), list) else payload.get("ideas")
    if not isinstance(ideas, list):
        raise ValueError("model response missing outputs.ideas list")
    normalized_ideas = []
    seen_paths = set()
    for index, raw in enumerate(ideas, start=1):
        if isinstance(raw, str):
            raw = {
                "title": raw.strip()[:90] or f"Ollama idea {index}",
                "hypothesis": raw.strip() or f"Ollama idea {index} is testable against the supplied source evidence.",
                "approach": raw.strip() or "Run a bounded AutoSci validation against supplied source evidence.",
                "novelty_hypothesis": raw.strip()
                or "Novelty is assessed against the supplied source and novelty evidence.",
                "origin_evidence_ids": [f"autosci-request:{request.get('action', 'generate_ideas')}"],
            }
        if not isinstance(raw, dict):
            continue
        default_path = REQUIRED_PATHS[(index - 1) % len(REQUIRED_PATHS)][0]
        raw_path = raw.get("generation_path") or ""
        if isinstance(raw_path, list):
            raw_path = next((str(item) for item in raw_path if str(item).strip()), "")
        if isinstance(raw_path, dict):
            raw_path = next(
                (
                    f"{key}:{value}"
                    for key, value in raw_path.items()
                    if str(key).strip() and str(value).strip()
                ),
                "",
            )
        path = str(raw_path or "").strip()
        approach_value = raw.get("approach")
        if isinstance(approach_value, list):
            approach_text = " ".join(str(item) for item in approach_value if str(item).strip())
        else:
            approach_text = str(approach_value or "").strip()
        if not re.match(r"^[A-E]:", path) and re.match(r"^[A-E]:", approach_text):
            path = approach_text.split()[0].strip()
        if not path:
            path = default_path
        title = str(raw.get("title") or "").strip()
        hypothesis = str(raw.get("hypothesis") or "").strip()
        approach = approach_text
        if not (path and title and hypothesis and approach):
            continue
        combined = " ".join([title, hypothesis, approach]).lower()
        if "solar" not in primary_context.lower() and any(term in combined for term in OFF_TOPIC_SOLAR_TERMS):
            raise ValueError("model generated off-topic solar-energy ideas for a non-solar primary source")
        code = path.split(":", 1)[0].strip().upper()
        if code not in {"A", "B", "C", "D", "E"}:
            continue
        raw_idea_id = str(raw.get("idea_id") or "").strip()
        if target_id and target_id not in raw_idea_id.lower():
            path_slug = path.split(":", 1)[1].strip().lower()
            path_slug = re.sub(r"[^a-z0-9]+", "-", path_slug).strip("-") or f"path-{code.lower()}"
            idea_id = f"idea-{target_id}-{path_slug}-{index}"
        else:
            idea_id = raw_idea_id or f"idea-ollama-path-{code.lower()}-{index:03d}"
        seen_paths.add(code)
        origin_ids = [
            str(item)
            for item in raw.get("origin_evidence_ids", [])
            if str(item).strip()
        ]
        for primary_id in primary_ids:
            if primary_id not in origin_ids:
                origin_ids.append(primary_id)
        normalized_ideas.append(
            {
                "idea_id": idea_id,
                "title": title,
                "hypothesis": hypothesis,
                "approach": approach,
                "novelty_hypothesis": str(
                    raw.get("novelty_hypothesis")
                    or "Novelty is assessed against the supplied attached-document source record and novelty evidence."
                ),
                "origin_evidence_ids": origin_ids,
                "duplicate_status": str(raw.get("duplicate_status") or "new"),
                "generation_path": path,
                "source_mode": str(raw.get("source_mode") or "model_command"),
                "status": str(raw.get("status") or "candidate"),
            }
        )
    missing = sorted({"A", "B", "C", "D", "E"} - seen_paths)
    if missing:
        raise ValueError(f"model response missing generation paths: {', '.join(missing)}")
    if len(normalized_ideas) < 5:
        raise ValueError("model response produced fewer than five valid ideas")
    evidence_ids = outputs.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        evidence_ids = primary_ids
    return {
        "schema": "autosci_model_response.v1",
        "status": "completed",
        "outputs": {
            "answer": str(outputs.get("answer") or "Ollama generated five source-grounded AutoSci idea candidates."),
            "confidence": float(outputs.get("confidence") or 0.68),
            "provider": "ollama",
            "model": model,
            "evidence_ids": [str(item) for item in evidence_ids if str(item).strip()],
            "ideas": normalized_ideas[:5],
        },
    }


def main() -> int:
    request = json.loads(sys.stdin.read())
    model = os.environ.get("AUTOSCI_OLLAMA_MODEL", "qwen3:4b")
    endpoint = os.environ.get("AUTOSCI_OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/chat")
    topic = request.get("context", {}).get("topic") or request.get("context", {}).get("target") or "attached literature source"
    primary_context, primary_ids, target_id = _primary_source_context(request)
    request_hint = json.dumps(request.get("context", request), sort_keys=True)[:2500]
    prompt = (
        "Return one compact JSON object only. "
        "Schema: {\"schema\":\"autosci_model_response.v1\",\"status\":\"completed\","
        "\"outputs\":{\"answer\":string,\"confidence\":0.0-1.0,\"provider\":\"ollama\","
        f"\"model\":\"{model}\",\"evidence_ids\":[string],\"ideas\":[idea x5]}}. "
        "Each idea needs idea_id,title,hypothesis,approach,novelty_hypothesis,"
        "origin_evidence_ids,duplicate_status,source_mode,status,generation_path. "
        f"Use exactly these five generation_path values once each: {', '.join(path for path, _ in REQUIRED_PATHS)}. "
        f"Topic: {topic}. Primary source excerpt: {primary_context}. "
        "Ideas must be about validating or extending this primary source record, not about the repository name. "
        "Do not propose solar panels, wind energy, photovoltaics, or energy materials unless the primary source is about those topics. "
        f"Evidence/context: {request_hint}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1800},
    }
    data = json.dumps(body).encode("utf-8")
    http_request = urllib.request.Request(endpoint, data=data, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(http_request, timeout=int(os.environ.get("AUTOSCI_OLLAMA_TIMEOUT", "180"))) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Ollama model command failed: {exc}", file=sys.stderr)
        return 2
    content = response_payload.get("message", {}).get("content", "")
    try:
        payload = _json_from_text(content)
        normalized = _normalize_payload(
            payload,
            request=request,
            model=model,
            primary_ids=primary_ids,
            primary_context=primary_context,
            target_id=target_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Ollama response did not satisfy autosci_model_response.v1: {exc}", file=sys.stderr)
        print(content[:4000], file=sys.stderr)
        return 3
    print(json.dumps(normalized, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

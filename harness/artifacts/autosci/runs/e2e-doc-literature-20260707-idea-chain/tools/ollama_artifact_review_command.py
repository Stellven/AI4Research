#!/usr/bin/env python3
"""AutoSci review-llm-command bridge backed by local Ollama."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


def _json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    brace_delta = text.count("{") - text.count("}")
    bracket_delta = text.count("[") - text.count("]")
    candidate = f"{text}{']' * max(0, bracket_delta)}{'}' * max(0, brace_delta)}"
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("review response JSON is not an object")
    return payload


def _clamp_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.62
    return round(max(0.0, min(score, 1.0)), 3)


def main() -> int:
    request = json.loads(sys.stdin.read())
    inputs = request.get("inputs") if isinstance(request.get("inputs"), dict) else {}
    target = str(inputs.get("target") or request.get("target") or "autosci-artifact")
    difficulty = str(request.get("difficulty") or inputs.get("difficulty") or "standard")
    focus = str(request.get("focus") or inputs.get("focus") or "novelty")
    model = os.environ.get("AUTOSCI_OLLAMA_MODEL", "gemma3:4b")
    endpoint = os.environ.get("AUTOSCI_OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/chat")
    prompt = (
        "Return compact JSON only with keys score, recommendation, evidence, suggestion. "
        "Review this AutoSci artifact for novelty, source grounding, and feasibility. "
        f"Target: {target}. Difficulty: {difficulty}. Focus: {focus}. "
        f"Request: {json.dumps(request, sort_keys=True)[:5000]}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a strict research artifact reviewer. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 900},
    }
    data = json.dumps(body).encode("utf-8")
    http_request = urllib.request.Request(endpoint, data=data, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(http_request, timeout=int(os.environ.get("AUTOSCI_OLLAMA_TIMEOUT", "180"))) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        model_content = response_payload.get("message", {}).get("content", "")
        review_json = _json_from_text(model_content)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"Ollama review command failed: {exc}", file=sys.stderr)
        return 2
    score = _clamp_score(review_json.get("score"))
    recommendation = str(review_json.get("recommendation") or "revise")
    evidence = str(review_json.get("evidence") or review_json.get("rationale") or "Ollama reviewed the artifact.")
    suggestion = str(review_json.get("suggestion") or "Keep source, novelty, and experiment evidence attached.")
    payload = {
        "schema": "artifact_review.v1",
        "status": "completed",
        "inputs": {"target": target, "difficulty": difficulty, "focus": focus},
        "outputs": {
            "review": {
                "artifact_id": f"artifact:{target}",
                "target": target,
                "review_mode": "review_llm",
                "review_available": True,
                "difficulty": difficulty,
                "focus": focus,
                "score": score,
                "recommendation": recommendation,
                "evidence_ids": [f"review-llm:ollama:{target}"],
            },
            "findings": [
                {
                    "finding_id": "review-llm.ollama-finding",
                    "severity": "medium" if score < 0.7 else "low",
                    "category": focus,
                    "evidence": evidence,
                    "suggestion": suggestion,
                }
            ],
            "artifact": {"artifact_id": f"artifact:{target}"},
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "ollama-review-command",
            "implementation_package": "run-artifact",
            "source": "ollama",
            "model": model,
        },
        "limitations": ["Local Ollama Review LLM evidence; no external SaaS provider was used."],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

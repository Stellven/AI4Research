#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, limitations, outputs, require_non_empty_string, run_cli, validate_schema

SCHEMA = "literature_discovery.v1"
ONLINE_SOURCE_CHANNELS = {
    "arxiv",
    "citations",
    "deepxiv",
    "paper_copilot",
    "recommend",
    "references",
    "s2",
    "search_s2",
    "semantic_scholar",
    "openalex",
    "crossref",
    "europe_pmc",
    "web",
}
FIXTURE_SOURCE_CHANNELS = {"fixture", "local_fixture", "smoke_fixture"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _min_online_channels(value: Any) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    out = outputs(payload)
    require_non_empty_string(out.get("query"), "outputs.query", reasons)
    candidates = out.get("candidates")
    if not isinstance(candidates, list):
        reasons.append("outputs.candidates must be an array")
        candidates = []
    mode = str(out.get("mode") or "unknown")
    limit = int(out.get("limit") or len(candidates) or 0)
    if limit <= 0:
        reasons.append("outputs.limit must be positive")
    if len(candidates) > limit:
        reasons.append(f"candidate count {len(candidates)} exceeds limit {limit}")

    evidence_status = str(payload.get("status") or "")
    if evidence_status == "completed" and not candidates:
        reasons.append("completed discovery must include at least one candidate")
    if evidence_status == "inconclusive":
        warnings.append("literature discovery is inconclusive; do not treat as a complete shortlist")
        if not limitations(payload):
            reasons.append("inconclusive discovery must explain limitations")
    if evidence_status == "failed":
        reasons.append("literature discovery evidence status is failed")

    require_online = _truthy(inputs.get("require_online_source_evidence"))
    min_online_channels = _min_online_channels(inputs.get("min_online_source_channels"))
    online_channels_seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            reasons.append(f"candidates[{index}] must be an object")
            continue
        channels = candidate.get("source_channels")
        if not isinstance(channels, list) or not channels:
            reasons.append(f"candidates[{index}].source_channels must be non-empty")
            continue
        normalized_channels = {str(channel).strip() for channel in channels if str(channel).strip()}
        if mode != "fixture" and normalized_channels & FIXTURE_SOURCE_CHANNELS:
            reasons.append(f"candidates[{index}] uses fixture source outside fixture mode")
        online_channels_seen.update(channel for channel in normalized_channels if channel in ONLINE_SOURCE_CHANNELS)
        if not candidate.get("ranking_rationale"):
            reasons.append(f"candidates[{index}].ranking_rationale is required")

    if mode == "fixture":
        warnings.append("fixture discovery passed only as smoke evidence; it is not live literature discovery")
    if require_online:
        if evidence_status != "completed":
            reasons.append("online source evidence requires completed literature discovery")
        if mode == "fixture":
            reasons.append("online source evidence cannot use fixture discovery mode")
        if not online_channels_seen:
            reasons.append("online source evidence requires at least one non-fixture online source channel")
        if len(online_channels_seen) < min_online_channels:
            reasons.append(
                "online source evidence requires at least "
                f"{min_online_channels} online source channel(s); found {len(online_channels_seen)}"
            )
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))

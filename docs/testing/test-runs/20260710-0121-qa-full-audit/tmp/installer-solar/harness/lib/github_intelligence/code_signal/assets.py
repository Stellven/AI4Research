"""Output asset shapes — 7 legal output asset contracts.

Each asset type carries evidence_refs[]. Claims without evidence_refs
trigger evaluator FAIL condition.
"""
from __future__ import annotations

from typing import Any

from .models import OutputAsset, _json_dump, _gen_id, utc_now_iso


def make_hotspot_card(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    content["asset_type"] = "github_hotspot_card"
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="github_hotspot_card",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_direction_brief(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="direction_brief",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_intervention_plan(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="community_intervention_plan",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_open_source_brief(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="open_source_project_brief",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_ai_influence_topic(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="ai_influence_topic",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_deep_research_seed(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="deep_research_seed_pack",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


def make_action_queue(
    repo_key: str,
    evidence_refs: list[str],
    content: dict[str, Any],
) -> OutputAsset:
    return OutputAsset(
        asset_id=_gen_id("asset-"),
        asset_type="action_queue",
        repo_key=repo_key,
        generated_at=utc_now_iso(),
        evidence_refs_json=_json_dump(evidence_refs),
        content_json=_json_dump(content),
    )


BUILDERS = {
    "github_hotspot_card": make_hotspot_card,
    "direction_brief": make_direction_brief,
    "community_intervention_plan": make_intervention_plan,
    "open_source_project_brief": make_open_source_brief,
    "ai_influence_topic": make_ai_influence_topic,
    "deep_research_seed_pack": make_deep_research_seed,
    "action_queue": make_action_queue,
}

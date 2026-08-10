from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Any

import pytest

from evidence import JourneyRecorder
from journey_runner import action_evidence, bootstrap_live_environment, has_network_authorization, run_autosci


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def _normalize(value: str | None) -> str:
    return (value or "").strip()


def _candidate_id(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("candidate_id") or item.get("citation_id") or item.get("source_ref") or item.get("url") or ""))


def _candidate_url(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("source_ref") or item.get("url") or ""))


def _candidate_title(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("title") or item.get("headline") or ""))


def _candidate_year(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("year") or item.get("published_year") or item.get("publication_year") or ""))


def _candidate_channels(item: dict[str, Any]) -> list[str]:
    return [_normalize(channel).lower() for channel in (item.get("source_channels") or []) if _normalize(channel)]


def _contains_any(text: str, needles: list[str]) -> bool:
    low_text = _normalize(text).lower()
    return any(needle and needle.lower() in low_text for needle in needles)


def _identity_stable(value: str) -> bool:
    token = _normalize(value).lower()
    if not token:
        return False
    if " " in token:
        return False
    for marker in ("fixture", "sample_", "/fixtures/", "mock_", "synthetic", "placeholder", "dummy"):
        if marker in token:
            return False
    if re.match(r"^\d{4}\.\d{4,5}$", token):
        return True
    if token.startswith(("http://", "https://", "arxiv:", "doi:", "paper:", "paperid:", "ss_", "provider_", "runtime_")):
        return True
    return bool(re.match(r"^[a-z0-9][a-z0-9._:/+\-~]+$", token))


def _json_contains_token(payload: Any, token: str) -> bool:
    if token == "":
        return False
    needle = token.lower()
    if isinstance(payload, dict):
        return any(_json_contains_token(v, needle) for v in payload.values())
    if isinstance(payload, list):
        return any(_json_contains_token(item, needle) for item in payload)
    return needle in _normalize(str(payload)).lower()


def _present(token: str | None) -> str:
    return "present" if _normalize(token) else "absent"


def _run_discovery(
    rec: JourneyRecorder,
    sandbox: Path,
    *,
    label: str,
    topic: str,
    run_id: str,
    limit: int,
    anchors: list[str],
    negative_ids: list[str],
) -> tuple[dict[str, Any], Path | None, dict[str, Any], list[dict[str, Any]]]:
    args = [
        "--topic",
        topic,
        "--run-id",
        run_id,
        "--limit",
        str(limit),
        "--online",
        *(item for anchor in anchors for item in ("--anchor", anchor)),
        *(item for neg in negative_ids for item in ("--negative", neg)),
    ]
    timeout_seconds = max(1, int(os.environ.get("PHASE22_J05_DISCOVERY_TIMEOUT_SECONDS", "240")))
    summary, _ = run_autosci(rec, sandbox, "discover", args, timeout=timeout_seconds, allow_live=True)
    # Failed provider-backed actions still print a structured skill-run summary.
    # Recover it from the runner's error wrapper so the referenced action
    # evidence can classify provider/network outages truthfully.
    evidence_summary = summary
    if summary.get("_error"):
        try:
            parsed_error = json.loads(str(summary["_error"]))
        except (TypeError, ValueError):
            parsed_error = {}
        if isinstance(parsed_error, dict):
            evidence_summary = parsed_error
    discovery_path = action_evidence(evidence_summary, "discover_literature")
    payload = _read_payload(discovery_path) if discovery_path else {}
    outputs = payload.get("outputs", {}) if isinstance(payload, dict) else {}
    if not isinstance(outputs, dict):
        outputs = {}
    candidates = [item for item in outputs.get("candidates", []) if isinstance(item, dict)]
    rec.add_assertion(f"{label}_discover_command_completed", not summary.get("_error"), summary.get("_error") or summary.get("status"))
    rec.add_assertion(f"{label}_discover_literature_action_present", discovery_path is not None, str(discovery_path))
    if discovery_path:
        rec.add_artifact(discovery_path, f"j05-{label}-literature-discovery-evidence")
    return summary, discovery_path, payload, candidates


def _provider_blocker(summary: dict[str, Any], payload: dict[str, Any]) -> str:
    message = _normalize(str(summary.get("_error") or ""))
    outputs = payload.get("outputs", {}) if isinstance(payload, dict) else {}
    boundary = outputs.get("source_provider_boundary", {}) if isinstance(outputs, dict) else {}
    provider_status = _normalize(str(boundary.get("status", boundary.get("state", "")))).lower() if isinstance(boundary, dict) else ""
    invalid_reasons = [
        _normalize(str(item)).lower()
        for item in (boundary.get("invalid_reasons") or [])
        if isinstance(boundary, dict) and _normalize(str(item))
    ]
    provider_channels = [
        _normalize(str(item)).lower()
        for item in (boundary.get("provider_channels") or boundary.get("source_channels") or [])
        if isinstance(boundary, dict) and _normalize(str(item))
    ]
    final_boundary = boundary.get("final_shortlist_boundary", {}) if isinstance(boundary, dict) else {}
    final_status = _normalize(str(final_boundary.get("status", ""))).lower() if isinstance(final_boundary, dict) else ""
    lower = " ".join([message.lower(), provider_status, final_status, *invalid_reasons])
    provider_unproven = provider_status in {"incomplete", "pending"} and not provider_channels
    provider_missing_reason = any("provider" in reason and "channel" in reason for reason in invalid_reasons)
    if summary.get("_returncode") == 124:
        return message or "Provider-backed discovery command timed out."
    if any(token in lower for token in ("provider", "network", "connection", "timeout", "timed out", "dns", "unreachable", "requests", "429", "503", "blocked", "unavailable")):
        return message or f"Provider boundary was not available: {provider_status}"
    if provider_unproven and provider_missing_reason:
        return (
            "Provider-backed source channel was not proven by discovery evidence "
            f"(status={provider_status or 'missing'}, final_status={final_status or 'missing'})."
        )
    return ""


@pytest.mark.live_provider
def test_p22_j05_literature_discovery(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J05")
    os.environ.update(bootstrap_live_environment(repo_root))
    network_discovery_authorized = has_network_authorization()
    rec.add_assertion(
        "network_discovery_authorized",
        network_discovery_authorized,
        {
            "PHASE22_ENABLE_NETWORK_JOURNEYS": _present(os.environ.get("PHASE22_ENABLE_NETWORK_JOURNEYS")),
            "SOLAR_AUTOSCI_ALLOW_NETWORK": _present(os.environ.get("SOLAR_AUTOSCI_ALLOW_NETWORK")),
            "AUTOSCI_LIVE_PROVIDER_TESTS": _present(os.environ.get("AUTOSCI_LIVE_PROVIDER_TESTS")),
            "OPENAI_API_KEY": _present(os.environ.get("OPENAI_API_KEY")),
            "OPENROUTER_API_KEY": _present(os.environ.get("OPENROUTER_API_KEY")),
        },
    )

    if not has_network_authorization():
        blocker = (
            "Live network authorization was not enabled. "
            "Set PHASE22_ENABLE_NETWORK_JOURNEYS=1 and SOLAR_AUTOSCI_ALLOW_NETWORK=1, or enable AUTOSCI_LIVE_PROVIDER_TESTS in harness/.env."
        )
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=[blocker])
        return

    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "j02_j05"
    request_file = fixture_root / "j05_discovery_request.json"
    expectation_file = fixture_root / "j05_discovery_expectations.json"
    request_spec = _read_payload(request_file)
    expectation_spec = _read_payload(expectation_file)

    if not request_file.exists() or not expectation_file.exists():
        rec.add_assertion("discovery_fixtures_present", False, {"request_file": request_file, "expectations_file": expectation_file})
        rec.finalize("NOT_AVAILABLE", blockers=["Missing required discovery fixture files."])
        return

    run_id = str(request_spec.get("run_id", expectation_spec.get("run_id", "p22-j05-literature")))
    topic = _normalize(str(request_spec.get("topic", "")))
    anchors = [_normalize(str(item)) for item in request_spec.get("anchors", []) if _normalize(str(item))]
    negative_ids = [_normalize(str(item)) for item in request_spec.get("negative_ids", []) if _normalize(str(item))]
    limit = int(request_spec.get("limit", expectation_spec.get("limit", 5)))
    min_candidates = int(request_spec.get("min_candidates", expectation_spec.get("min_candidates", 3)))
    required_channels = [_normalize(str(item)).lower() for item in request_spec.get("required_source_channels", []) if _normalize(str(item))]
    source_provider = _normalize(str(request_spec.get("source_provider", expectation_spec.get("source_provider", ""))))

    if not topic:
        rec.add_assertion("discovery_request_topic_present", False, request_spec)
        rec.finalize("NOT_AVAILABLE", blockers=["Missing J05 discovery topic in fixtures."])
        return

    sandbox_override = _normalize(os.environ.get("PHASE22_J05_SANDBOX"))
    sandbox = Path(sandbox_override) if sandbox_override else tmp_path / "p22-j05"
    topic_summary, topic_path, topic_payload, topic_candidates = _run_discovery(
        rec,
        sandbox,
        label="topic",
        topic=topic,
        run_id=f"{run_id}-topic",
        limit=limit,
        anchors=[],
        negative_ids=negative_ids,
    )
    anchor_summary, anchor_path, anchor_payload, anchor_candidates = _run_discovery(
        rec,
        sandbox,
        label="anchor",
        topic=topic,
        run_id=f"{run_id}-anchor",
        limit=limit,
        anchors=anchors,
        negative_ids=negative_ids,
    )

    blocker = _provider_blocker(topic_summary, topic_payload) or _provider_blocker(anchor_summary, anchor_payload)
    if blocker:
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=[f"Discovery provider unavailable in current execution: {blocker}"])
        return

    if topic_summary.get("_error") or anchor_summary.get("_error"):
        rec.finalize(
            "FAIL",
            blockers=[
                f"Autosci discover command failed: topic={topic_summary.get('_error')}; anchor={anchor_summary.get('_error')}"
            ],
        )
        return

    rec.add_assertion("topic_autosci_skill_is_discover", topic_summary.get("skill") == "discover", topic_summary.get("skill"))
    rec.add_assertion("anchor_autosci_skill_is_discover", anchor_summary.get("skill") == "discover", anchor_summary.get("skill"))

    for label, discovery_path, discovery_payload in (
        ("topic", topic_path, topic_payload),
        ("anchor", anchor_path, anchor_payload),
    ):
        if discovery_path is None:
            rec.finalize("FAIL", blockers=[f"{label} discover_literature action evidence missing."])
            return
        if not isinstance(discovery_payload, dict):
            rec.add_assertion(f"{label}_discover_evidence_parseable", False, discovery_path)
            rec.finalize("FAIL", blockers=[f"{label} discover_literature evidence is not valid JSON."])
            return
        rec.add_assertion(f"{label}_discovery_schema_version", discovery_payload.get("schema") == "literature_discovery.v1", discovery_payload.get("schema"))
        outputs = discovery_payload.get("outputs", {})
        if not isinstance(outputs, dict):
            outputs = {}
        discovery_status = outputs.get("status") or discovery_payload.get("status")
        rec.add_assertion(f"{label}_discovery_status_completed", str(discovery_status or "").lower() == "completed", discovery_status)

    candidates = topic_candidates + anchor_candidates
    rec.add_assertion("topic_candidate_count_meets_minimum", len(topic_candidates) >= min_candidates, {"count": len(topic_candidates), "min_required": min_candidates})
    rec.add_assertion("anchor_candidate_count_meets_minimum", len(anchor_candidates) >= min_candidates, {"count": len(anchor_candidates), "min_required": min_candidates})
    rec.add_assertion("topic_candidate_count_within_limit", len(topic_candidates) <= limit, {"count": len(topic_candidates), "limit": limit})
    rec.add_assertion("anchor_candidate_count_within_limit", len(anchor_candidates) <= limit, {"count": len(anchor_candidates), "limit": limit})
    if len(candidates) == 0:
        rec.add_assertion("non_empty_candidate_set", False, {"topic": topic_payload, "anchor": anchor_payload})
        rec.finalize("FAIL", blockers=["Discovery returned zero candidates."])
        return

    ids = [_candidate_id(item) for item in candidates]
    urls = [_candidate_url(item) for item in candidates]
    titles = [_candidate_title(item) for item in candidates]
    years = [_candidate_year(item) for item in candidates]
    channels = [channel for item in candidates for channel in _candidate_channels(item)]
    dedupe_pairs = [(ids[i] or urls[i] or str(i), urls[i] or ids[i] or str(i)) for i in range(len(candidates))]

    has_identity = [bool(item) for item in [ids[i] or urls[i] for i in range(len(candidates))]]
    title_required = [bool(t) for t in titles]
    candidate_channels = [_candidate_channels(item) for item in candidates]
    observed_channels = set(channels)
    expected_channels = set(required_channels)

    rec.add_assertion("candidate_identity_present", all(has_identity), {"missing": [i for i, ok in enumerate(has_identity) if not ok]})
    rec.add_assertion(
        "candidate_identity_stable",
        all(_identity_stable(ids[i] or urls[i]) for i in range(len(candidates))),
        {
            "ids": ids,
            "urls": urls,
        },
    )
    rec.add_assertion("candidate_title_required", all(title_required), titles)
    rec.add_assertion("candidate_year_required", all(year.isdigit() and 1900 <= int(year) <= 2100 for year in years), years)
    rec.add_assertion("candidate_source_channels_required", all(len(item) > 0 for item in candidate_channels), channels)
    rec.add_assertion(
        "required_source_channels_present",
        expected_channels.issubset(observed_channels),
        {"required": sorted(expected_channels), "observed": sorted(observed_channels)},
    )

    rec.add_assertion(
        "candidates_are_unique",
        len(dedupe_pairs) == len(set(dedupe_pairs)),
        {
            "pair_count": len(dedupe_pairs),
            "unique_pairs": len(set(dedupe_pairs)),
            "ids": ids,
            "urls": urls,
        },
    )

    anchor_outputs = anchor_payload.get("outputs", {}) if isinstance(anchor_payload, dict) else {}
    if not isinstance(anchor_outputs, dict):
        anchor_outputs = {}
    observed_anchors = [item for item in (anchor_outputs.get("anchors") or []) if _normalize(str(item))]
    rec.add_assertion(
        "requested_anchors_recorded",
        set(observed_anchors).issuperset(set(anchors)),
        {"requested": anchors, "observed": observed_anchors},
    )
    anchor_candidate_channels = [
        channel for item in anchor_candidates for channel in _candidate_channels(item)
    ]
    anchor_rationales = [
        _normalize(str(item.get("ranking_rationale") or item.get("rationale") or "")).lower()
        for item in anchor_candidates
    ]
    anchor_provenance_observed = bool(anchor_candidates) and (
        any(channel in {"s2_reference", "s2_citation", "s2_recommend"} for channel in anchor_candidate_channels)
        or any("anchor" in rationale for rationale in anchor_rationales)
    )
    rec.add_assertion(
        "anchor_influence_observed",
        anchor_provenance_observed,
        {
            "requested_anchors": anchors,
            "observed_anchors": observed_anchors,
            "anchor_candidate_channels": sorted(set(anchor_candidate_channels)),
            "anchor_rationale_count": sum(1 for rationale in anchor_rationales if "anchor" in rationale),
        },
    )

    rec.add_assertion(
        "negative_candidates_excluded",
        all(not _contains_any(_normalize(ids[i]), negative_ids) and not _contains_any(_normalize(urls[i]), negative_ids) for i in range(len(candidates))),
        {"negative_ids": negative_ids, "ids": ids, "urls": urls},
    )

    fixture_markers = ("fixture", "sample_", "/fixtures/", "mock_", "synthetic", "placeholder", "dummy")
    fixture_like = [
        {
            "id": ids[i],
            "url": urls[i],
            "title": titles[i],
        }
        for i in range(len(candidates))
        if any(marker in (ids[i] + urls[i] + titles[i]).lower() for marker in fixture_markers)
    ]
    rec.add_assertion("fixture_candidates_not_used", not fixture_like, fixture_like)

    source_boundaries = []
    for label, payload in (("topic", topic_payload), ("anchor", anchor_payload)):
        outputs = payload.get("outputs", {}) if isinstance(payload, dict) else {}
        boundary = outputs.get("source_provider_boundary", {}) if isinstance(outputs, dict) else {}
        if not isinstance(boundary, dict):
            boundary = {}
        provider_status = _normalize(str(boundary.get("status", boundary.get("state", "")))).lower()
        provider_channels = [_normalize(str(item)).lower() for item in (boundary.get("provider_channels") or boundary.get("channels") or [])]
        source_boundaries.append((label, boundary, provider_status, provider_channels))
        rec.add_assertion(f"{label}_source_provider_boundary_present", bool(boundary), {
            "provider_boundary": boundary,
            "status": provider_status,
        })
        if provider_status in {"unavailable", "blocked", "provider_unavailable", "network_unavailable", "error", "pending"}:
            rec.finalize("ENVIRONMENT_BLOCKED", blockers=[f"{label} provider boundary was not available: {provider_status}"])
            return
    provider_channels = sorted({channel for _, _, _, channels_for_run in source_boundaries for channel in channels_for_run})
    provider_statuses = [status for _, _, status, _ in source_boundaries]
    rec.add_assertion(
        "provider_boundary_complete",
        all(status in {"completed", "ready", "active", "verified"} for status in provider_statuses),
        {"provider_statuses": provider_statuses, "provider_channels": provider_channels},
    )
    if source_provider:
        rec.add_assertion("provider_channel_target_met", source_provider in provider_channels, {"required": source_provider, "observed": provider_channels})
    else:
        rec.add_assertion("provider_channel_target_met", True, {"required": source_provider, "observed": provider_channels})

    modes = []
    for payload in (topic_payload, anchor_payload):
        outputs = payload.get("outputs", {}) if isinstance(payload, dict) else {}
        modes.append(_normalize(str(outputs.get("mode", ""))).lower() if isinstance(outputs, dict) else "")
    rec.add_assertion("runtime_discovery_mode_verified", all(mode and "pending" not in mode for mode in modes), modes)

    rec.add_assertion(
        "run_id_bound_to_discovery_output",
        _json_contains_token(topic_payload, f"{run_id}-topic") and _json_contains_token(anchor_payload, f"{run_id}-anchor"),
        {"run_id": run_id, "topic_path": str(topic_path), "anchor_path": str(anchor_path)},
    )

    if not all(item["passed"] for item in rec.assertions):
        rec.add_assertion("j05_integrity_check", False, "One or more discovery evidence checks failed.")
        rec.finalize("FAIL", blockers=["P22-J05 discovery evidence did not satisfy all required checks."])
        return

    rec.add_assertion("non_empty_candidate_set", len(topic_candidates) >= min_candidates and len(anchor_candidates) >= min_candidates, {"topic": len(topic_candidates), "anchor": len(anchor_candidates), "min_required": min_candidates})
    rec.add_assertion("candidates_effective", len(topic_candidates) <= limit and len(anchor_candidates) <= limit, {"topic": len(topic_candidates), "anchor": len(anchor_candidates), "limit": limit})
    rec.add_artifact(request_file, "j05-intake-request")

    rec.add_l2(
        "Workflow",
        "Search Strategy Formation",
        "separate topic and anchor discover_literature runs used the fixture query, anchors, negative IDs, limit, and online provider mode.",
        rec.run_dir / "commands.json",
        True,
    )
    rec.finalize("PASS")

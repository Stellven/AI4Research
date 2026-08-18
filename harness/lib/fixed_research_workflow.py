"""Typed intake and source-pack authority for the fixed research workflow.

This module does not run a scheduler.  It specializes the registered fixed
contract with host-verified source evidence and exact physical identities.
"""
from __future__ import annotations

import hashlib
import datetime
import json
import os
import shutil
from pathlib import Path
from typing import Any

import workflow_contract as wc


WORKFLOW_ID = "research.evidence_to_poc.v1"
PART_A_NODE_IDS = (
    "seed_fetch",
    "source_discovery",
    "source_validation",
    "evidence_synthesis",
    "report_draft",
    "independent_review",
    "report_revision",
    "final_acceptance",
)
CREDENTIAL_FREE_PART_A_NODE_IDS = (
    "seed_fetch",
    "source_discovery",
    "source_validation",
)
DISPATCHABLE_PART_A_NODE_IDS = PART_A_NODE_IDS
PART_B_NODE_IDS = (
    "poc_handoff",
    "idea_evaluation",
    "experiment_design",
    "experiment_approval",
    "experiment_run",
    "claim_verification",
    "final_delivery",
)
PART_B_EXECUTABLE_NODE_IDS = PART_B_NODE_IDS
DISPATCHABLE_NODE_IDS = PART_A_NODE_IDS + PART_B_EXECUTABLE_NODE_IDS
PHYSICAL_OPERATOR_BY_NODE = {
    "seed_fetch": "autosci-research-synthesis-seed-fetch-worker",
    "source_discovery": "autosci-research-synthesis-source-discovery-worker",
    "source_validation": "autosci-research-synthesis-source-validation-worker",
    "evidence_synthesis": "codex-research-evidence-synthesis-worker",
    "report_draft": "codex-research-report-draft-worker",
    "independent_review": "codex-research-independent-review-worker",
    "report_revision": "codex-research-report-revision-worker",
    "final_acceptance": "autosci-research-synthesis-final-acceptance-worker",
    "poc_handoff": "autosci-research-poc-handoff-worker",
    "idea_evaluation": "autosci-research-poc-idea-evaluation-worker",
    "experiment_design": "autosci-research-poc-experiment-design-worker",
    "experiment_approval": "autosci-research-poc-experiment-approval-worker",
    "experiment_run": "autosci-research-poc-experiment-run-worker",
    "claim_verification": "autosci-research-poc-claim-verification-worker",
    "final_delivery": "autosci-research-poc-final-delivery-worker",
}
RESEARCH_OPERATOR_BY_NODE = {
    node_id: f"{node_id}_operator" for node_id in DISPATCHABLE_NODE_IDS
}
EXPECTED_SCHEMA_BY_NODE = {
    "seed_fetch": "research_synthesis.seed_snapshot.v1",
    "source_discovery": "research_synthesis.source_discovery.v1",
    "source_validation": "research_synthesis.source_validation.v1",
    "evidence_synthesis": "research_synthesis.evidence_synthesis.v1",
    "report_draft": "research_synthesis.report_draft.v1",
    "independent_review": "research_synthesis.independent_review.v1",
    "report_revision": "research_synthesis.report_revision.v1",
    "final_acceptance": "research_synthesis.final_acceptance.v1",
    "poc_handoff": "solar.fixed_research.poc_handoff.v1",
    "idea_evaluation": "solar.fixed_research.idea_evaluation.v1",
    "experiment_design": "solar.fixed_research.experiment_plan.v1",
    "experiment_approval": "solar.fixed_research.experiment_approval.v1",
    "experiment_run": "solar.fixed_research.experiment_result.v1",
    "claim_verification": "solar.fixed_research.claim_verification.v1",
    "final_delivery": "solar.fixed_research.final_delivery.v1",
}
EXECUTION_PROFILES = {"part_a_only", "part_a_plus_poc"}
ACQUISITION_MODES = {"source_pack", "live_search", "hybrid"}
PUBLIC_RETRIEVAL_POLICY_ID = "public_bibliographic_no_key_v1"
PUBLIC_RETRIEVAL_PROVIDERS = ["semantic_scholar", "openalex", "crossref"]
EXPERIMENT_POLICY_ID = "evidence_lineage_integrity_v1"
EXPERIMENT_POLICY_RUNNER = "harness/tools/fixed_research_benchmark.py"
EXPERIMENT_POLICY_CAPABILITIES = ["execute:fixed_evidence_lineage_benchmark", "network:none"]
MAX_SOURCE_COUNT = 50
MAX_EXTRACT_BYTES = 262_144
MAX_CANDIDATE_BYTES = 3_145_728
MAX_INDEX_BYTES = 1_048_576
MAX_EVIDENCE_COUNT = 200
MAX_EVIDENCE_CONTENT_BYTES = 262_144
MAX_SOURCE_PACK_BYTES = 4_194_304


class FixedResearchContractError(ValueError):
    """A typed fixed-research intake failed closed."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return _sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _write_fixed_experiment_policy(
    *,
    sprint_id: str,
    request: str,
    source_pack_manifest: dict[str, Any],
    snapshot_root: str | os.PathLike[str],
    actor: str,
    statement: str,
) -> dict[str, Any]:
    actor = str(actor or "").strip()
    statement = str(statement or "").strip()
    if not actor or actor.lower() in {"system", "policy", "operator", "worker", "solar", "automation"}:
        raise FixedResearchContractError("fixed experiment preauthorization requires an attributable human actor")
    if not statement:
        raise FixedResearchContractError("fixed experiment preauthorization requires an exact human statement")
    snapshot = Path(snapshot_root).resolve(strict=False)
    work_dir = snapshot.parent.parent
    harness = Path(__file__).resolve().parents[1]
    runner = harness / "tools" / "fixed_research_benchmark.py"
    runner_bytes = _regular_bytes(runner, label="fixed experiment runner")
    relative = Path("artifacts/research_evidence_to_poc/poc/approval/experiment_policy_authorization.json")
    target = work_dir / relative
    if target.exists() or target.is_symlink():
        raise FixedResearchContractError("fixed experiment policy artifact already exists")
    payload = {
        "schema": "solar.fixed_research.experiment_policy_authorization.v1",
        "policy_id": EXPERIMENT_POLICY_ID,
        "decision": "preauthorized",
        "sprint_id": sprint_id,
        "node_id": "experiment_approval",
        "generation": 1,
        "actor": actor,
        "author": {"type": "human", "id": actor},
        "statement": statement,
        "request_sha256": _sha256_bytes(request.encode("utf-8")),
        "source_pack_manifest_sha256": _canonical_sha256(source_pack_manifest),
        "benchmark_policy": {
            "benchmark_id": EXPERIMENT_POLICY_ID.replace("_", "-"),
            "runner": EXPERIMENT_POLICY_RUNNER,
            "runner_sha256": _sha256_bytes(runner_bytes),
            "sandbox": "linux_user_and_network_namespace",
            "network": "none",
            "timeout_max_seconds": 60,
            "capabilities": list(EXPERIMENT_POLICY_CAPABILITIES),
        },
        "issued_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "issued_by": "workflow_intake",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return {
        "mode": "policy_preauthorized",
        "policy_id": EXPERIMENT_POLICY_ID,
        "path": str(relative).replace("\\", "/"),
        "sha256": _sha256_bytes(target.read_bytes()),
        "request_sha256": payload["request_sha256"],
        "source_pack_manifest_sha256": payload["source_pack_manifest_sha256"],
    }


def _write_public_retrieval_policy(
    *,
    sprint_id: str,
    request: str,
    source_pack_manifest: dict[str, Any],
    work_dir: str | os.PathLike[str],
) -> dict[str, Any]:
    """Materialize the controller-owned, no-key A2 network authorization."""

    root = Path(work_dir).resolve(strict=False)
    relative = Path("inputs/retrieval/public_bibliographic_no_key_v1.authorization.json")
    target = root / relative
    if target.exists() or target.is_symlink():
        raise FixedResearchContractError("public retrieval policy artifact already exists")
    payload = {
        "schema": "solar.fixed_research.public_retrieval_authorization.v1",
        "policy_id": PUBLIC_RETRIEVAL_POLICY_ID,
        "decision": "authorized",
        "sprint_id": sprint_id,
        "node_id": "source_discovery",
        "request_sha256": _sha256_bytes(request.encode("utf-8")),
        "source_pack_manifest_sha256": _canonical_sha256(source_pack_manifest),
        "providers": list(PUBLIC_RETRIEVAL_PROVIDERS),
        "credential_mode": "public_no_key",
        "secret_refs": [],
        "network_scope": "https_public_bibliographic_apis_only",
        "minimum_live_sources": 3,
        "max_candidates": 12,
        "max_attempts_per_provider": 2,
        "max_total_wait_seconds": 12.0,
        "issued_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "issued_by": "workflow_intake",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return {
        "policy_id": PUBLIC_RETRIEVAL_POLICY_ID,
        "path": relative.as_posix(),
        "sha256": _sha256_bytes(target.read_bytes()),
        "request_sha256": payload["request_sha256"],
        "providers": list(PUBLIC_RETRIEVAL_PROVIDERS),
        "minimum_live_sources": 3,
    }


def _strict_child(path: Path, root: Path, *, label: str) -> Path:
    if path.is_absolute():
        raise FixedResearchContractError(f"{label} must be relative to the source-pack root")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise FixedResearchContractError(f"{label} contains an unsafe path segment")
    candidate = root.joinpath(path)
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise FixedResearchContractError(f"{label} must not contain symlinks: {path}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FixedResearchContractError(f"{label} escapes the source-pack root") from exc
    return resolved


def _regular_bytes(path: Path, *, label: str, max_bytes: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FixedResearchContractError(f"{label} must be a regular non-symlink file: {path}")
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise FixedResearchContractError(f"{label} exceeds {max_bytes} bytes")
    data = path.read_bytes()
    if not data:
        raise FixedResearchContractError(f"{label} must not be empty: {path}")
    return data


def _jsonl(data: bytes, *, label: str) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixedResearchContractError(f"{label} must be UTF-8") from exc
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FixedResearchContractError(f"{label}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise FixedResearchContractError(f"{label}:{line_number} must be an object")
        rows.append(row)
    if not rows:
        raise FixedResearchContractError(f"{label} contains no records")
    return rows


def _unique(rows: list[dict[str, Any]], keys: tuple[str, ...], *, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = next((str(row.get(key) or "").strip() for key in keys if str(row.get(key) or "").strip()), "")
        if not identity:
            raise FixedResearchContractError(f"{label} row has no {keys[0]}")
        if identity in indexed:
            raise FixedResearchContractError(f"{label} contains duplicate identity: {identity}")
        indexed[identity] = row
    return indexed


def validate_source_pack(
    source_pack_root: str | os.PathLike[str],
    *,
    authority_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Rehash a canonical source pack and return content-bearing candidates.

    Relative roots are accepted only relative to an explicit host authority
    root.  Both this intake boundary and the physical adapter call this
    function, so mutation after intake is detected before operator execution.
    """

    raw_root = Path(source_pack_root)
    if any(part in {"", ".", ".."} for part in raw_root.parts):
        raise FixedResearchContractError("source-pack root contains an unsafe path segment and escapes authority_root")
    authority: Path | None = None
    if authority_root is not None:
        authority = Path(authority_root).resolve(strict=True)
    if raw_root.is_absolute():
        lexical_root = raw_root.absolute()
    else:
        if authority is None:
            raise FixedResearchContractError("relative source-pack root requires an authority_root")
        lexical_root = authority / raw_root
    if authority is not None:
        try:
            lexical_relative = lexical_root.relative_to(authority)
        except ValueError as exc:
            raise FixedResearchContractError("source-pack root escapes authority_root") from exc
        cursor = authority
        for part in lexical_relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise FixedResearchContractError("source-pack root has a symlink parent")
    if lexical_root.is_symlink() or not lexical_root.is_dir():
        raise FixedResearchContractError(f"source-pack root must be a regular non-symlink directory: {lexical_root}")
    root = lexical_root.resolve(strict=True)
    if authority is not None:
        try:
            root.relative_to(authority)
        except ValueError as exc:
            raise FixedResearchContractError("source-pack root resolves outside authority_root") from exc

    sources_path = _strict_child(Path("sources.jsonl"), root, label="sources.jsonl")
    evidence_path = _strict_child(Path("evidence.jsonl"), root, label="evidence.jsonl")
    sources_bytes = _regular_bytes(sources_path, label="sources.jsonl", max_bytes=MAX_INDEX_BYTES)
    evidence_bytes = _regular_bytes(evidence_path, label="evidence.jsonl", max_bytes=MAX_INDEX_BYTES)
    if len(sources_bytes) > MAX_INDEX_BYTES or len(evidence_bytes) > MAX_INDEX_BYTES:
        raise FixedResearchContractError(f"source-pack index exceeds {MAX_INDEX_BYTES} bytes")
    sources = _unique(_jsonl(sources_bytes, label="sources.jsonl"), ("source_id", "id"), label="sources.jsonl")
    evidence = _unique(_jsonl(evidence_bytes, label="evidence.jsonl"), ("evidence_id", "id"), label="evidence.jsonl")
    if len(sources) > MAX_SOURCE_COUNT:
        raise FixedResearchContractError(f"source pack exceeds {MAX_SOURCE_COUNT} sources")
    if len(evidence) > MAX_EVIDENCE_COUNT:
        raise FixedResearchContractError(f"source pack exceeds {MAX_EVIDENCE_COUNT} evidence rows")

    evidence_by_source: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for evidence_id, row in evidence.items():
        source_id = str(row.get("source_id") or "").strip()
        if source_id not in sources:
            raise FixedResearchContractError(f"evidence {evidence_id} references unknown source_id: {source_id}")
        content = row.get("content")
        expected = str(row.get("content_hash") or "").lower()
        if not isinstance(content, str) or not content:
            raise FixedResearchContractError(f"evidence {evidence_id} has no content")
        if len(content.encode("utf-8")) > MAX_EVIDENCE_CONTENT_BYTES:
            raise FixedResearchContractError(f"evidence content exceeds {MAX_EVIDENCE_CONTENT_BYTES} bytes: {evidence_id}")
        if len(expected) != 64 or _sha256_bytes(content.encode("utf-8")) != expected:
            raise FixedResearchContractError(f"evidence content hash mismatch: {evidence_id}")
        evidence_by_source.setdefault(source_id, []).append((evidence_id, row))

    candidates: list[dict[str, Any]] = []
    extract_files: list[dict[str, Any]] = []
    seen_extracts: set[str] = set()
    for source_id, row in sources.items():
        extract_raw = str(row.get("extract_path") or "").strip()
        if not extract_raw:
            raise FixedResearchContractError(f"source {source_id} has no extract_path")
        if extract_raw in seen_extracts:
            raise FixedResearchContractError(f"duplicate extract_path: {extract_raw}")
        seen_extracts.add(extract_raw)
        extract_path = _strict_child(Path(extract_raw), root, label=f"source {source_id} extract_path")
        extract_bytes = _regular_bytes(
            extract_path, label=f"source {source_id} extract", max_bytes=MAX_EXTRACT_BYTES
        )
        if len(extract_bytes) > MAX_EXTRACT_BYTES:
            raise FixedResearchContractError(f"source extract exceeds {MAX_EXTRACT_BYTES} bytes: {source_id}")
        try:
            extract_text = extract_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FixedResearchContractError(f"source {source_id} extract must be UTF-8") from exc
        expected = str(row.get("content_sha256") or "").lower()
        if len(expected) != 64 or _sha256_bytes(extract_text.encode("utf-8")) != expected:
            raise FixedResearchContractError(f"source extract hash mismatch: {source_id}")
        linked = evidence_by_source.get(source_id) or []
        if not linked:
            raise FixedResearchContractError(f"source has no evidence record: {source_id}")
        evidence_text = "\n\n".join(str(item[1]["content"]) for item in linked)
        if evidence_text != extract_text:
            raise FixedResearchContractError(f"source extract and evidence content differ: {source_id}")
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or row.get("source_url") or "").strip()
        provider = str(row.get("provider") or "").strip()
        if not title or not url or not provider:
            raise FixedResearchContractError(f"source {source_id} requires title, url, and provider")
        candidates.append({
            "source_id": source_id,
            "title": title,
            "url": url,
            "canonical_id": str(row.get("canonical_id") or source_id),
            "provider": provider,
            "content_summary": extract_text,
            "metadata": {
                "source_type": str(row.get("source_type") or "other"),
                "source_pack_extract_sha256": expected,
                "source_pack_evidence_ids": [item[0] for item in linked],
                "source_pack_extract_bytes": len(extract_bytes),
            },
            "provenance": {
                "provider": provider,
                "source_pack_root": str(root),
                "extract_path": extract_raw,
                "content_sha256": expected,
            },
        })
        extract_files.append({
            "path": extract_raw,
            "bytes": len(extract_bytes),
            "sha256": _sha256_bytes(extract_bytes),
            "source_id": source_id,
        })

    serialized_candidates = json.dumps(candidates, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(serialized_candidates) > MAX_CANDIDATE_BYTES:
        raise FixedResearchContractError(f"source-pack candidates exceed {MAX_CANDIDATE_BYTES} serialized bytes")
    total_bytes = len(sources_bytes) + len(evidence_bytes) + sum(int(item["bytes"]) for item in extract_files)
    if total_bytes > MAX_SOURCE_PACK_BYTES:
        raise FixedResearchContractError(f"source pack exceeds {MAX_SOURCE_PACK_BYTES} total bytes")

    return {
        "schema": "solar.fixed_research.source_pack_authority.v1",
        "status": "verified",
        "root": str(root),
        "authority_root": str(authority) if authority is not None else "",
        "files": [
            {"path": "sources.jsonl", "bytes": len(sources_bytes), "sha256": _sha256_bytes(sources_bytes)},
            {"path": "evidence.jsonl", "bytes": len(evidence_bytes), "sha256": _sha256_bytes(evidence_bytes)},
            *extract_files,
        ],
        "source_count": len(sources),
        "evidence_count": len(evidence),
        "candidates": candidates,
    }


def snapshot_source_pack(authority: dict[str, Any], destination: str | os.PathLike[str]) -> dict[str, Any]:
    """Copy only verified canonical pack files into a new Solar-owned root."""

    source_root = Path(str(authority.get("root") or "")).resolve(strict=True)
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FixedResearchContractError(f"source-pack snapshot already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        raise FixedResearchContractError(f"source-pack snapshot staging path already exists: {staging}")
    try:
        for item in authority.get("files") or []:
            rel = Path(str(item.get("path") or ""))
            source = _strict_child(rel, source_root, label="source-pack snapshot source")
            data = _regular_bytes(
                source,
                label="source-pack snapshot source",
                max_bytes=max(0, int(item.get("bytes") or 0)),
            )
            if len(data) != int(item.get("bytes") or -1) or _sha256_bytes(data) != str(item.get("sha256") or ""):
                raise FixedResearchContractError(f"source-pack changed before snapshot: {rel}")
            output = _strict_child(rel, staging.resolve(strict=False), label="source-pack snapshot target")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    snapshotted = validate_source_pack(target, authority_root=target.parent)
    if [item.get("sha256") for item in snapshotted["files"]] != [item.get("sha256") for item in authority["files"]]:
        raise FixedResearchContractError("source-pack snapshot digest inventory mismatch")
    return snapshotted


def build_fixed_research_graph(
    *,
    sprint_id: str,
    request: str,
    execution_profile: str,
    acquisition_mode: str,
    source_pack_root: str | os.PathLike[str] | None,
    authority_root: str | os.PathLike[str] | None = None,
    workflows_dir: str | os.PathLike[str] | None = None,
    snapshot_root: str | os.PathLike[str] | None = None,
    allow_unavailable_source_pack: bool = False,
    experiment_policy: str = "",
    experiment_policy_actor: str = "",
    experiment_policy_statement: str = "",
    retrieval_policy: str = "",
) -> dict[str, Any]:
    profile = str(execution_profile or "").strip()
    mode = str(acquisition_mode or "").strip()
    if profile not in EXECUTION_PROFILES:
        raise FixedResearchContractError(f"unsupported execution_profile: {profile or '<missing>'}")
    if mode not in ACQUISITION_MODES:
        raise FixedResearchContractError(f"unsupported acquisition_mode: {mode or '<missing>'}")
    live_enabled = mode in {"live_search", "hybrid"}
    retrieval = str(retrieval_policy or "").strip()
    if live_enabled and retrieval != PUBLIC_RETRIEVAL_POLICY_ID:
        raise FixedResearchContractError(
            f"{mode} acquisition requires retrieval_policy={PUBLIC_RETRIEVAL_POLICY_ID}"
        )
    if not live_enabled and retrieval:
        raise FixedResearchContractError("source_pack acquisition must not carry a live retrieval policy")
    contract = wc.find_contract(WORKFLOW_ID, workflows_dir, skip_invalid=False)
    if contract is None:
        raise FixedResearchContractError(f"registered workflow contract is missing: {WORKFLOW_ID}")
    pack_required = mode in {"source_pack", "hybrid"}
    if source_pack_root is None or not str(source_pack_root).strip():
        if pack_required and not allow_unavailable_source_pack:
            raise FixedResearchContractError("source_pack acquisition requires source_pack_root")
        authority: dict[str, Any] = {
            "schema": "solar.fixed_research.source_pack_authority.v1",
            "status": "not_available",
            "reason": "source_pack_root was not supplied",
            "root": "",
            "authority_root": "",
            "files": [],
            "source_count": 0,
            "evidence_count": 0,
            "candidates": [],
        }
    else:
        authority = validate_source_pack(source_pack_root, authority_root=authority_root)
        if snapshot_root is not None:
            authority = snapshot_source_pack(authority, snapshot_root)
    graph = wc.instantiate(contract, {"sprint_id": sprint_id, "sid": sprint_id})
    graph["workflow_contract"] = WORKFLOW_ID
    graph["plan_compile_required"] = False
    graph["fixed_topology"] = True
    graph["intent_binding"] = {"required": True, "status": "pending", "intent_id": ""}
    part_b_enabled = profile == "part_a_plus_poc"
    graph["execution_profile"] = {
        "kind": profile,
        "part_b": "enabled" if part_b_enabled else "not_applicable",
    }
    graph["acquisition_mode"] = {
        "kind": mode,
        "network_required": live_enabled,
        "pack_required": pack_required,
    }
    graph["source_pack_authority"] = {key: value for key, value in authority.items() if key != "candidates"}
    if live_enabled:
        if snapshot_root is None:
            raise FixedResearchContractError("live retrieval requires a controller-owned sprint work directory")
        graph["retrieval_policy"] = _write_public_retrieval_policy(
            sprint_id=sprint_id,
            request=request,
            source_pack_manifest=graph["source_pack_authority"],
            work_dir=Path(snapshot_root).parent.parent,
        )
    else:
        graph["retrieval_policy"] = {"policy_id": "", "path": "", "sha256": ""}
    policy = str(experiment_policy or "").strip()
    if policy and policy != EXPERIMENT_POLICY_ID:
        raise FixedResearchContractError(f"unsupported experiment_policy: {policy}")
    if policy:
        if not part_b_enabled:
            raise FixedResearchContractError("experiment preauthorization requires execution_profile=part_a_plus_poc")
        if snapshot_root is None:
            raise FixedResearchContractError("experiment preauthorization requires a controller-owned work directory")
        graph["experiment_policy"] = _write_fixed_experiment_policy(
            sprint_id=sprint_id,
            request=request,
            source_pack_manifest=graph["source_pack_authority"],
            snapshot_root=snapshot_root,
            actor=experiment_policy_actor,
            statement=experiment_policy_statement,
        )
    else:
        graph["experiment_policy"] = {"mode": "interactive_exact_plan", "policy_id": ""}
    graph["codex_execution"] = {
        "mode": "fresh_context_per_node",
        "structured_response": True,
        "ambient_api_keys_allowed": False,
        "max_parallel": 1,
    }
    graph["execution_mode"] = "single_threaded"
    graph["part_b"] = dict((graph.get("dashboard") or {}).get("conditional_part_b") or {})
    graph["part_b"]["status"] = "pending" if part_b_enabled else "not_applicable"
    graph["part_b"]["reason"] = (
        (
            "execution_profile=part_a_plus_poc; the controller must prove the generated plan is within the "
            "intake-time fixed experiment policy before experiment_run"
            if str((graph.get("experiment_policy") or {}).get("mode") or "") == "policy_preauthorized"
            else "execution_profile=part_a_plus_poc; exact human approval is required before experiment_run"
        )
        if part_b_enabled
        else "execution_profile=part_a_only"
    )
    graph["handoff_to"] = "builder"
    graph["target_role"] = "builder"
    graph.setdefault("node_results", {})
    nodes_by_id = {
        str(item.get("id") or ""): item
        for item in graph.get("nodes") or []
        if isinstance(item, dict)
    }
    primary_by_node = {
        node_id: next(
            (
                str(output.get("path") or "")
                for output in nodes_by_id[node_id].get("outputs") or []
                if str(output.get("type") or "") != "directory"
            ),
            "",
        )
        for node_id in (*PART_A_NODE_IDS, *PART_B_NODE_IDS)
    }
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        if node_id in PART_B_NODE_IDS:
            if not part_b_enabled:
                node["status"] = "skipped"
                node["condition_status"] = "not_applicable"
                node["condition_reason"] = "execution_profile=part_a_only"
                node.pop("required_operator_id", None)
                node["capability_native"] = False
                graph["node_results"][node_id] = {
                    "status": "skipped",
                    "condition_status": "not_applicable",
                    "reason": "execution_profile=part_a_only",
                }
                continue
            node["status"] = "pending"
            node["condition_status"] = "enabled"
            node["condition_reason"] = "execution_profile=part_a_plus_poc"
        if node_id in DISPATCHABLE_NODE_IDS:
            node["required_operator_id"] = PHYSICAL_OPERATOR_BY_NODE[node_id]
            node["research_physical_operator_id"] = RESEARCH_OPERATOR_BY_NODE[node_id]
            node["capability_native"] = True
        else:
            node.pop("required_operator_id", None)
            node.pop("research_physical_operator_id", None)
            node["capability_native"] = False
        node["expected_schema"] = EXPECTED_SCHEMA_BY_NODE[node_id]
        node["read_scope"] = [
            primary_by_node[dependency]
            for dependency in node.get("depends_on") or []
            if dependency in primary_by_node and primary_by_node[dependency]
        ]
        for dependency in node.get("depends_on") or []:
            dependency_node = nodes_by_id.get(str(dependency)) or {}
            node["read_scope"].extend(
                str(output.get("path") or "")
                for output in dependency_node.get("outputs") or []
                if isinstance(output, dict) and str(output.get("evidence_schema") or "")
            )
        if node_id == "source_discovery" and authority["status"] == "verified":
            node["read_scope"].extend(
                f"sprints/{sprint_id}/workdir/inputs/source-pack/{item['path']}"
                for item in authority.get("files") or []
            )
        if node_id == "source_discovery" and live_enabled:
            node["read_scope"].append(
                f"sprints/{sprint_id}/workdir/{graph['retrieval_policy']['path']}"
            )
        if node_id == "experiment_approval" and part_b_enabled:
            node["read_scope"].extend(
                [
                    f"sprints/{sprint_id}/workdir/artifacts/research_evidence_to_poc/poc/approval/approval_request.json",
                    f"sprints/{sprint_id}/workdir/artifacts/research_evidence_to_poc/poc/approval/human_approval.json",
                ]
            )
            if str((graph.get("experiment_policy") or {}).get("mode") or "") == "policy_preauthorized":
                node["read_scope"].append(
                    f"sprints/{sprint_id}/workdir/{graph['experiment_policy']['path']}"
                )
        if node_id == "experiment_run" and part_b_enabled:
            node["read_scope"].extend(
                primary_by_node[part_a_node]
                for part_a_node in PART_A_NODE_IDS
                if primary_by_node.get(part_a_node)
            )
        node["operator_payload"] = {
            "request": request,
            "execution_profile": profile,
            "acquisition_mode": mode,
            "source_pack_root": authority["root"],
            "source_pack_manifest": graph["source_pack_authority"],
            "retrieval_policy": dict(graph["retrieval_policy"]),
        }
        if pack_required and authority["status"] != "verified" and node_id == "seed_fetch":
            node["status"] = "needs_human_review"
            node["next_action"] = "Supply a host-authorized canonical source pack."
            graph["node_results"][node_id] = {
                "status": "needs_human_review",
                "reason": "source_pack_not_available",
            }
    graph["workflow_contract_hash"] = wc.graph_contract_hash(graph)
    return graph

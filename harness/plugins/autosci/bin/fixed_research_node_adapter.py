#!/usr/bin/env python3
"""Execute one fixed Solar research node through the production binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema

HARNESS_DIR = Path(__file__).resolve().parents[3]
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
if str(HARNESS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR.parent))

from fixed_research_workflow import (  # noqa: E402
    EXPECTED_SCHEMA_BY_NODE,
    PART_B_EXECUTABLE_NODE_IDS,
    PHYSICAL_OPERATOR_BY_NODE,
    PUBLIC_RETRIEVAL_POLICY_ID,
    PUBLIC_RETRIEVAL_PROVIDERS,
    RESEARCH_OPERATOR_BY_NODE,
    WORKFLOW_ID,
    FixedResearchContractError,
    validate_source_pack,
)
from research_orchestration.dispatch import dispatch_research_node  # noqa: E402
from research_orchestration.evaluator import evaluate_production_result  # noqa: E402
from research_orchestration.runtime import default_production_resolver  # noqa: E402
from harness.plugins.autosci.services.codex_research import (  # noqa: E402
    CodexResearchModelService,
    SharedInvocationJournal,
)
from harness.plugins.autosci.services.production_research import (  # noqa: E402
    LiteratureDiscoveryService,
    ResearchModelService,
)
from harness.plugins.autosci.operators.research_synthesis.evidence_synthesis import (  # noqa: E402
    MAX_SYNTHESIS_ATTEMPTS,
)
from harness.plugins.autosci.operators.fixed_research_poc import (  # noqa: E402
    execute_part_b,
    verify_final_delivery_artifact,
)
from harness.plugins.autosci.operators.research_synthesis.base import ResearchOperatorError  # noqa: E402
from harness.plugins.autosci.operators.research_synthesis.report_revision import (  # noqa: E402
    MAX_REVISION_ATTEMPTS,
    verify_revision_response_preservation,
)


REQUEST_SCHEMA = HARNESS_DIR / "schemas" / "draft" / "research_node_request.v1.schema.json"
RESULT_SCHEMA = HARNESS_DIR / "schemas" / "evidence" / "research_node_result.v1.schema.json"


class AdapterError(ValueError):
    pass


class _RoleBoundApiResearchModelService:
    """Add fixed-workflow role/session provenance to an API model service."""

    def __init__(self, backend: ResearchModelService, *, role: str) -> None:
        self.backend = backend
        self.role = role
        self.service_id = backend.service_id
        self.service_version = backend.service_version

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.backend(**kwargs)
        usage_rows = payload.get("provider_usage") if isinstance(payload.get("provider_usage"), list) else []
        for index, item in enumerate(usage_rows, start=1):
            if not isinstance(item, dict):
                continue
            response_hash = str(item.get("response_sha256") or item.get("request_sha256") or "")
            item.update(
                {
                    "principal_role": self.role,
                    "session_mode": "ephemeral",
                    "status": "completed",
                    "invocation_id": f"{self.role}:{response_hash or index}",
                    "call_index": index,
                    "role_call_index": index,
                }
            )
        return payload


def _io_path(path: Path) -> Path:
    """Return a Windows extended-length spelling without changing identity."""
    absolute = path.absolute()
    raw = str(absolute)
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        return Path("\\\\?\\" + raw)
    return absolute


def _is_file(path: Path) -> bool:
    return _io_path(path).is_file()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with _io_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root)).replace("\\", "/")
        if path.is_symlink():
            inventory[relative] = {"type": "symlink", "sha256": ""}
        elif path.is_file():
            inventory[relative] = {"type": "file", "sha256": _sha(path)}
    return inventory


def _contained(raw: str, root: Path, *, label: str) -> tuple[Path, str]:
    path = Path(raw)
    resolved = (path if path.is_absolute() else root / path).resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise AdapterError(f"{label} escapes work_dir") from exc
    return resolved, str(relative).replace("\\", "/")


def _primary_output(envelope: dict[str, Any], work_dir: Path, node_id: str) -> tuple[Path, str, Path, str]:
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    raw_outputs = inputs.get("declared_outputs") if isinstance(inputs.get("declared_outputs"), list) else []
    expected_schema = EXPECTED_SCHEMA_BY_NODE[node_id]
    expected_name = {
        "seed_fetch": "seed_snapshot.json",
        "source_discovery": "source_discovery.json",
        "source_validation": "source_validation.json",
        "evidence_synthesis": "evidence_synthesis.json",
        "report_draft": "report_draft.json",
        "independent_review": "independent_review.json",
        "report_revision": "report_revision.json",
        "final_acceptance": "final_acceptance.json",
        "poc_handoff": "poc_handoff.json",
        "idea_evaluation": "idea_evaluation.json",
        "experiment_design": "experiment_plan.json",
        "experiment_approval": "experiment_approval.json",
        "experiment_run": "experiment_result.json",
        "claim_verification": "claim_verification.json",
        "final_delivery": "final_delivery.json",
    }[node_id]
    primary_raw = next(
        (
            str(item.get("path") or "")
            for item in raw_outputs
            if isinstance(item, dict) and Path(str(item.get("path") or "")).name == expected_name
        ),
        "",
    )
    directory_raw = next(
        (
            str(item.get("path") or "")
            for item in raw_outputs
            if isinstance(item, dict) and str(item.get("type") or "") == "directory"
        ),
        "",
    )
    if not primary_raw or not directory_raw or str(inputs.get("expected_schema") or "") != expected_schema:
        raise AdapterError("declared primary output/directory/schema does not match fixed node contract")
    primary, primary_rel = _contained(primary_raw, work_dir, label="primary output")
    stage_dir, stage_rel = _contained(directory_raw, work_dir, label="stage directory")
    if primary.parent != stage_dir:
        raise AdapterError("primary output is not directly inside the declared stage directory")
    return primary, primary_rel, stage_dir, stage_rel


def _dependency_refs(envelope: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    refs: list[dict[str, Any]] = []
    for item in inputs.get("dependency_artifacts") or []:
        if not isinstance(item, dict):
            continue
        path, relative = _contained(str(item.get("path") or ""), work_dir, label="dependency artifact")
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            raise AdapterError(f"dependency artifact is missing or unsafe: {relative}")
        actual = _sha(path)
        expected = str(item.get("sha256") or "").lower()
        schema = str(item.get("schema") or "").strip()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise AdapterError(f"dependency artifact has no valid sha256: {relative}")
        if not (
            schema.startswith("research_synthesis.")
            or schema.startswith("solar.fixed_research.")
            or schema in {"text/plain", "text/markdown"}
        ):
            raise AdapterError(f"dependency artifact has an unexpected schema: {relative}")
        if actual != expected:
            raise AdapterError(f"dependency artifact hash mismatch: {relative}")
        refs.append({
            "artifact_id": str(item.get("artifact_id") or Path(relative).stem),
            "path": relative,
            "schema": schema,
            "sha256": actual,
            "controller_closeout": dict(item.get("controller_closeout") or {}),
        })
    return refs


def _source_authority(envelope: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    declared = inputs.get("source_pack_manifest") if isinstance(inputs.get("source_pack_manifest"), dict) else {}
    root, _relative = _contained(str(declared.get("root") or ""), work_dir, label="source-pack snapshot")
    authority_root, _ = _contained(str(declared.get("authority_root") or ""), work_dir, label="source-pack authority root")
    actual = validate_source_pack(root, authority_root=authority_root)
    comparable_keys = ("schema", "status", "root", "authority_root", "files", "source_count", "evidence_count")
    if {key: actual.get(key) for key in comparable_keys} != {key: declared.get(key) for key in comparable_keys}:
        raise AdapterError("source-pack snapshot no longer matches the intake manifest")
    return actual


def _source_pack_refs(authority: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    root = Path(str(authority["root"])).resolve(strict=True)
    refs: list[dict[str, Any]] = []
    for index, item in enumerate(authority.get("files") or [], start=1):
        path = root / str(item["path"])
        try:
            relative = path.resolve(strict=True).relative_to(work_dir)
        except ValueError as exc:
            raise AdapterError("source-pack snapshot file escapes work_dir") from exc
        refs.append({
            "artifact_id": f"source-pack-{index:03d}",
            "path": str(relative).replace("\\", "/"),
            "schema": "solar.source_pack.file.v1",
            "sha256": str(item["sha256"]),
        })
    return refs


def _retrieval_policy_ref(envelope: dict[str, Any], work_dir: Path, request_text: str) -> dict[str, Any]:
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    meta = inputs.get("retrieval_policy") if isinstance(inputs.get("retrieval_policy"), dict) else {}
    path, relative = _contained(str(meta.get("path") or ""), work_dir, label="retrieval policy")
    if relative != "inputs/retrieval/public_bibliographic_no_key_v1.authorization.json":
        raise AdapterError("retrieval policy path is not controller-owned")
    if path.is_symlink() or not path.is_file() or _sha(path) != str(meta.get("sha256") or ""):
        raise AdapterError("retrieval policy bytes do not match controller metadata")
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("retrieval policy is not valid JSON") from exc
    source_manifest = inputs.get("source_pack_manifest") if isinstance(inputs.get("source_pack_manifest"), dict) else {}
    manifest_sha = hashlib.sha256(
        json.dumps(source_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    checks = {
        "schema": policy.get("schema") == "solar.fixed_research.public_retrieval_authorization.v1",
        "policy": policy.get("policy_id") == meta.get("policy_id") == PUBLIC_RETRIEVAL_POLICY_ID,
        "decision": policy.get("decision") == "authorized",
        "run": str(policy.get("sprint_id") or "") == str(envelope.get("sprint_id") or ""),
        "node": policy.get("node_id") == "source_discovery",
        "request": policy.get("request_sha256") == hashlib.sha256(request_text.encode("utf-8")).hexdigest(),
        "source_manifest": policy.get("source_pack_manifest_sha256") == manifest_sha,
        "providers": policy.get("providers") == PUBLIC_RETRIEVAL_PROVIDERS,
        "no_key": policy.get("credential_mode") == "public_no_key" and policy.get("secret_refs") == [],
        "network_scope": policy.get("network_scope") == "https_public_bibliographic_apis_only",
        "budget": 1 <= int(policy.get("max_attempts_per_provider") or 0) <= 2
        and 0 < float(policy.get("max_total_wait_seconds") or 0) <= 12.0,
    }
    if not all(checks.values()):
        raise AdapterError(
            "retrieval policy binding mismatch: "
            + ",".join(sorted(key for key, value in checks.items() if not value))
        )
    return {
        "artifact_id": "public-retrieval-authorization",
        "path": relative,
        "schema": "solar.fixed_research.public_retrieval_authorization.v1",
        "sha256": _sha(path),
        "policy": policy,
    }


def _approval_control_refs(envelope: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    controls = inputs.get("approval_controls") if isinstance(inputs.get("approval_controls"), dict) else {}
    refs: list[dict[str, Any]] = []
    for key, expected_schema in (
        ("request", "solar.fixed_research.approval_request.v1"),
        ("approval", "solar.fixed_research.human_approval.v1"),
        ("policy", "solar.fixed_research.experiment_policy_authorization.v1"),
    ):
        item = controls.get(key) if isinstance(controls.get(key), dict) else {}
        if key == "policy" and not item:
            continue
        path, relative = _contained(str(item.get("path") or ""), work_dir, label=f"approval {key}")
        if path.is_symlink() or not path.is_file():
            raise AdapterError(f"approval {key} artifact is missing or unsafe")
        digest = _sha(path)
        if str(item.get("sha256") or "").lower() != digest or str(item.get("schema") or "") != expected_schema:
            raise AdapterError(f"approval {key} artifact binding mismatch")
        refs.append({"artifact_id": f"approval-{key}", "path": relative, "schema": expected_schema, "sha256": digest})
    return refs


def _codex_services(
    *,
    node_id: str,
    stage_dir: Path,
) -> dict[str, Any]:
    if node_id == "final_acceptance":
        return {}
    # The research operators name no provider: this adapter chose one CLI, so a
    # Codex quota exhaustion stopped every stage past source_validation. The
    # provider is now selectable, and the model default follows it so a Codex
    # model id cannot leak into a Claude run.
    provider = _selected_provider()
    _expected_usage_provider()
    service_cls = CodexResearchModelService
    default_model = "gpt-5.5"
    service_options: dict[str, Any] = {}
    if provider in {"gemini", "google", "zhipu", "glm", "deepseek", "local", "thunderomlx"}:
        from structured_model import ALIASES
        import model_registry
        from harness.plugins.autosci.services.registry_research import RegistryResearchModelService
        canonical = ALIASES.get(provider, provider)
        service_cls = RegistryResearchModelService
        service_options["provider"] = canonical
        default_model = next(model_id for model_id, spec in model_registry.load_registry()["models"].items()
                             if spec["provider"] == canonical)
    if provider in {"openrouter", "openai"}:
        configured_provider = str(os.environ.get("AUTOSCI_RESEARCH_LLM_PROVIDER") or "").strip().lower()
        if configured_provider != provider:
            raise AdapterError(
                "API research provider selection must match AUTOSCI_RESEARCH_LLM_PROVIDER"
            )
        writer_backend = ResearchModelService.from_environment(stage_dir)
        reviewer_backend = ResearchModelService.from_environment(stage_dir)
        if not writer_backend.routes or {route.provider for route in writer_backend.routes} != {provider}:
            raise AdapterError(f"selected API research provider is unavailable: {provider}")
        writer = _RoleBoundApiResearchModelService(writer_backend, role="writer")
        reviewer = _RoleBoundApiResearchModelService(reviewer_backend, role="reviewer")
        services: dict[str, Any] = {
            "service_metadata": {
                "model_generate": {"service_id": writer.service_id, "version": writer.service_version},
                "review_model_generate": {"service_id": reviewer.service_id, "version": reviewer.service_version},
            },
        }
        if node_id in {"evidence_synthesis", "report_draft", "report_revision"}:
            services["model_generate"] = writer
        if node_id in {"independent_review", "report_revision"}:
            services["review_model_generate"] = reviewer
        return services
    if provider in {"claude", "anthropic"}:
        # Same absolute package path the Codex service is imported by above;
        # the adapter runs as a bare module, so a relative `services.` import
        # does not resolve and fails only at dispatch time.
        from harness.plugins.autosci.services.claude_research import (
            DEFAULT_CLAUDE_MODEL,
            ClaudeResearchModelService,
        )

        service_cls = ClaudeResearchModelService
        default_model = DEFAULT_CLAUDE_MODEL

    writer_model = str(os.environ.get("SOLAR_RESEARCH_MODEL") or os.environ.get("SOLAR_CODEX_RESEARCH_MODEL") or default_model).strip()
    reviewer_model = str(os.environ.get("SOLAR_RESEARCH_REVIEWER_MODEL") or os.environ.get("SOLAR_CODEX_REVIEW_MODEL") or writer_model).strip()
    reasoning_effort = str(os.environ.get("SOLAR_CODEX_RESEARCH_REASONING_EFFORT") or "high").strip()
    # Shared deliberately: the resolver deepcopies the services dict, so a plain
    # list would leave the adapter reading an empty journal and unable to
    # recover calls hidden by an operator failure.
    invocation_journal: list[dict[str, Any]] = SharedInvocationJournal()
    writer = service_cls(
        stage_dir,
        model=writer_model,
        role="writer",
        reasoning_effort=reasoning_effort,
        invocation_journal=invocation_journal,
        **service_options,
    )
    reviewer = service_cls(
        stage_dir,
        model=reviewer_model,
        role="reviewer",
        reasoning_effort=reasoning_effort,
        invocation_journal=invocation_journal,
        **service_options,
    )
    services: dict[str, Any] = {
        "service_metadata": {
            "model_generate": {"service_id": writer.service_id, "version": writer.service_version},
            "review_model_generate": {"service_id": reviewer.service_id, "version": reviewer.service_version},
        },
    }
    if node_id in {"evidence_synthesis", "report_draft", "report_revision"}:
        services["model_generate"] = writer
    if node_id in {"independent_review", "report_revision"}:
        services["review_model_generate"] = reviewer
    return services


def _merge_codex_invocation_usage(
    result: dict[str, Any],
    services: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind every attempted Codex call, including calls hidden by operator failure."""
    existing = [
        dict(item)
        for item in result.get("model_provider_usage") or []
        if isinstance(item, dict)
    ]
    existing_by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(existing):
        key = str(item.get("invocation_id") or item.get("archive_path") or f"existing:{index}")
        existing_by_key[key] = item

    journals: list[list[dict[str, Any]]] = []
    seen_journal_ids: set[int] = set()
    for service_name in ("model_generate", "review_model_generate"):
        service = services.get(service_name)
        journal = getattr(service, "invocation_journal", None)
        if isinstance(journal, list) and id(journal) not in seen_journal_ids:
            seen_journal_ids.add(id(journal))
            journals.append(journal)

    merged: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for journal in journals:
        for index, raw in enumerate(journal):
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("invocation_id") or raw.get("archive_path") or f"journal:{index}")
            item = dict(existing_by_key.get(key) or {})
            item.update(raw)
            merged.append(item)
            consumed.add(key)
    for index, item in enumerate(existing):
        key = str(item.get("invocation_id") or item.get("archive_path") or f"existing:{index}")
        if key not in consumed:
            merged.append(item)

    total_calls = len(merged)
    for index, item in enumerate(merged, start=1):
        item["aggregate_call_index"] = int(item.get("aggregate_call_index") or index)
        item["role_call_index"] = int(item.get("role_call_index") or item.get("call_index") or 1)
        item["call_index"] = item["role_call_index"]
        item["total_calls"] = total_calls
    result["model_provider_usage"] = merged
    return merged


# Per-stage model-call ceilings, taken from the operators' own declared bounds so
# the two cannot drift apart. A stage absent from this table gets exactly one
# call, which is the safe default.
MAX_CALLS_BY_NODE = {
    # writer + reviewer per attempt
    "report_revision": MAX_REVISION_ATTEMPTS * 2,
    # one call per grounding repair attempt
    "evidence_synthesis": MAX_SYNTHESIS_ATTEMPTS,
}


# Each selectable CLI records its own provenance label. The guard below checks
# the usage against the label for the provider that was actually selected, so
# swapping providers stays legal while a service recording something other than
# what was requested still fails. Widening this must never become removing it.
_USAGE_PROVIDER_BY_SELECTION = {
    "codex": "codex_subscription",
    "claude": "claude_subscription",
    "anthropic": "claude_subscription",
    "gemini": "gemini", "google": "gemini",
    "zhipu": "zhipu", "glm": "zhipu",
    "deepseek": "deepseek", "local": "local", "thunderomlx": "local",
    "openrouter": "openrouter",
    "openai": "openai",
}


def _selected_provider() -> str:
    return str(os.environ.get("SOLAR_RESEARCH_MODEL_PROVIDER") or "codex").strip().lower()


def _expected_usage_provider() -> str:
    selection = _selected_provider()
    expected = _USAGE_PROVIDER_BY_SELECTION.get(selection)
    if not expected:
        # An unrecognised provider must stop the run rather than fall back to a
        # default that would attribute the call to the wrong CLI.
        raise AdapterError(f"unknown research model provider selection: {selection!r}")
    return expected


def _verify_model_usage(
    *,
    node_id: str,
    result: dict[str, Any],
) -> None:
    usage = [item for item in result.get("model_provider_usage") or [] if isinstance(item, dict)]
    if node_id == "final_acceptance":
        if usage:
            raise AdapterError("deterministic final acceptance unexpectedly used a model provider")
        return
    expected_roles: set[str] = set()
    if node_id in {"evidence_synthesis", "report_draft"}:
        expected_roles = {"writer"}
    elif node_id == "independent_review":
        expected_roles = {"reviewer"}
    elif node_id == "report_revision":
        # No revision call is valid when the prior review already accepts.
        if not usage:
            return
        expected_roles = {"writer", "reviewer"}
    if not usage:
        raise AdapterError("completed model stage emitted no provider usage")
    actual_roles = {str(item.get("principal_role") or "") for item in usage}
    expected_provider = _expected_usage_provider()
    actual_providers = {str(item.get("provider") or "") for item in usage}
    if actual_providers != {expected_provider}:
        # Naming both sides matters: the previous message said only "non-Codex
        # provider", which sent the reader after the CLI when the real cause was
        # a service that reported no provenance at all and was labelled
        # "injected" by the operator's fallback.
        raise AdapterError(
            "model stage recorded a provider other than the one selected: expected "
            f"{expected_provider}, recorded {sorted(actual_providers) or ['<none>']}"
        )
    if any(str(item.get("session_mode") or "") != "ephemeral" for item in usage):
        raise AdapterError("model stage did not use a fresh provider context")
    if any(str(item.get("status") or "completed") != "completed" for item in usage):
        raise AdapterError("completed model stage includes a failed provider invocation")
    if not actual_roles.issubset(expected_roles) or not expected_roles.intersection(actual_roles):
        raise AdapterError("provider worker role does not match the fixed node")
    if node_id == "report_revision" and usage:
        role_counts = {
            role: sum(1 for item in usage if str(item.get("principal_role") or "") == role)
            for role in expected_roles
        }
        if actual_roles != expected_roles or role_counts.get("writer") != role_counts.get("reviewer"):
            raise AdapterError("report revision must pair each writer attempt with a reviewer attempt")
    # One call per stage unless the operator declares a bounded repair loop, and
    # the bound is READ FROM THAT OPERATOR rather than restated here. Restating
    # it is how this check silently forbade the grounding repair loop the moment
    # evidence_synthesis grew one: the operator retried up to three times, the
    # ceiling was still a hardcoded 1, and a stage that had done exactly what it
    # was designed to do was refused.
    max_calls = MAX_CALLS_BY_NODE.get(node_id, 1)
    if len(usage) > max_calls:
        raise AdapterError(
            f"model stage exceeded its declared call ceiling: {len(usage)} > {max_calls}"
        )


def _normalize_provider_archives(result: dict[str, Any], work_dir: Path, stage_dir: Path) -> set[str]:
    allowed: set[str] = set()
    for usage in result.get("model_provider_usage") or []:
        if not isinstance(usage, dict) or not str(usage.get("archive_path") or "").strip():
            continue
        raw = Path(str(usage["archive_path"]))
        candidates = [raw] if raw.is_absolute() else [stage_dir / raw, work_dir / raw]
        archive = next((path.absolute() for path in candidates if _is_file(path)), None)
        if archive is None and os.name == "nt":
            # On Windows, freshly replaced service-evidence files can briefly
            # be invisible to a second process while an indexer/AV handle is
            # closing. Keep the verification bounded and still hash the exact
            # bytes once visible.
            for _ in range(10):
                time.sleep(0.05)
                archive = next((path.absolute() for path in candidates if _is_file(path)), None)
                if archive is not None:
                    break
        if archive is None:
            raise AdapterError(
                "provider archive_path is missing: "
                f"raw={raw}; candidates={[str(path) for path in candidates]}"
            )
        try:
            relative = archive.relative_to(work_dir)
            archive.relative_to(stage_dir)
        except ValueError as exc:
            raise AdapterError("provider archive_path escapes the stage directory") from exc
        usage["archive_path"] = str(relative).replace("\\", "/")
        usage["archive_sha256"] = _sha(archive)
        allowed.add(str(relative).replace("\\", "/"))
        evidence_hashes: dict[str, str] = {}
        for raw_evidence in usage.get("evidence_paths") or []:
            raw_path = Path(str(raw_evidence))
            evidence_candidates = [raw_path] if raw_path.is_absolute() else [stage_dir / raw_path, work_dir / raw_path]
            evidence_path = next(
                (path.absolute() for path in evidence_candidates if _is_file(path)),
                None,
            )
            if evidence_path is None:
                raise AdapterError("provider evidence_path is missing")
            try:
                evidence_relative = evidence_path.relative_to(work_dir)
                evidence_path.relative_to(stage_dir)
            except ValueError as exc:
                raise AdapterError("provider evidence_path escapes the stage directory") from exc
            normalized = str(evidence_relative).replace("\\", "/")
            evidence_hashes[normalized] = _sha(evidence_path)
            allowed.add(normalized)
        usage["evidence_paths"] = sorted(evidence_hashes)
        usage["evidence_sha256"] = evidence_hashes
    return allowed


def _verify_report_revision_artifact(
    primary: Path,
    work_dir: Path,
    dependencies: list[dict[str, Any]],
) -> None:
    revision = json.loads(primary.read_text(encoding="utf-8"))
    if not bool(revision.get("revision_applied")):
        return
    draft_ref = next(
        (item for item in dependencies if item.get("artifact_id") == "report_draft"),
        None,
    )
    if not isinstance(draft_ref, dict):
        raise AdapterError("report revision has no accepted base report dependency")
    base_report = json.loads((work_dir / str(draft_ref["path"])).read_text(encoding="utf-8"))
    proof = revision.get("preservation") if isinstance(revision.get("preservation"), dict) else {}
    recomputed = verify_revision_response_preservation(
        base_report,
        {
            "report": revision.get("revised_report"),
            "limitations": revision.get("limitations"),
            "preservation": proof.get("model_declaration"),
        },
        required_limitations=[
            str(item).strip()
            for item in revision.get("limitations") or []
            if str(item).strip()
        ],
    )
    if proof != recomputed:
        raise AdapterError("report revision preservation proof does not match recomputed lineage")


def execute(envelope: dict[str, Any]) -> dict[str, Any]:
    if str(envelope.get("runner_contract") or "") != WORKFLOW_ID:
        raise AdapterError("wrong runner_contract")
    node_id = str(envelope.get("node_id") or "")
    operator_id = str(envelope.get("operator_id") or "")
    if operator_id != PHYSICAL_OPERATOR_BY_NODE.get(node_id):
        raise AdapterError("outer physical operator does not match fixed node")
    work_dir = Path(str(envelope.get("work_dir") or "")).resolve(strict=True)
    primary, primary_rel, stage_dir, stage_rel = _primary_output(envelope, work_dir, node_id)
    before = _inventory(work_dir)
    dependencies = _dependency_refs(envelope, work_dir)
    if node_id == "experiment_approval":
        dependencies.extend(_approval_control_refs(envelope, work_dir))
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    payload = inputs.get("operator_payload") if isinstance(inputs.get("operator_payload"), dict) else {}
    request_text = str(payload.get("request") or envelope.get("objective") or "")
    acquisition_mode = str(payload.get("acquisition_mode") or "source_pack")
    authority: dict[str, Any] = {}
    if node_id == "source_discovery":
        source_manifest = inputs.get("source_pack_manifest") if isinstance(inputs.get("source_pack_manifest"), dict) else {}
        if str(source_manifest.get("status") or "") == "verified":
            authority = _source_authority(envelope, work_dir)
        if acquisition_mode in {"live_search", "hybrid"}:
            dependencies.append(_retrieval_policy_ref(envelope, work_dir, request_text))
    typed_payload: dict[str, Any] = {
        "task_contract": {
            "user_intent": request_text,
            "deliverable": {
                "kind": "research_report",
                "format": "markdown",
                "description": "Evidence-linked research report with method, findings, conclusions, and limitations.",
                "required_content": [
                    {"requirement_id": "result_claims", "required": True},
                    {"requirement_id": "limitations", "required": True},
                    {"requirement_id": "method_evidence", "required": True},
                ],
            },
            "success_criteria": [
                "At least 1 validated source",
                "At least 1 conclusion",
                "Every conclusion is linked to evidence sources",
                "Report body is non empty",
                "Independent review verdict is accept",
            ],
        },
        "execution_profile": str(payload.get("execution_profile") or "part_a_only"),
        "acquisition_mode": acquisition_mode,
    }
    if node_id == "seed_fetch":
        typed_payload["seed_inputs"] = [{"seed_kind": "research_brief", "value": typed_payload["task_contract"]["user_intent"]}]
    if node_id == "source_discovery":
        if authority:
            typed_payload["supplied_source_candidates"] = authority["candidates"]
            dependencies.extend(_source_pack_refs(authority, work_dir))
        typed_payload["minimum_live_sources"] = 3
    part_b_stage = node_id in PART_B_EXECUTABLE_NODE_IDS
    model_stage = node_id in {"evidence_synthesis", "report_draft", "independent_review", "report_revision"}
    deterministic_acceptance = node_id == "final_acceptance"
    approved = ["research_poc" if part_b_stage else "research_synthesis"] + (["research_model_generate"] if model_stage else [])
    public_discovery = node_id == "source_discovery" and acquisition_mode in {"live_search", "hybrid"}
    request_authorization = {
        "scope_id": f"{envelope.get('sprint_id')}:{node_id}",
        "approved_capabilities": approved + (["public_bibliographic_discovery"] if public_discovery else []),
        "allow_network": model_stage or public_discovery,
        "allow_live_provider": model_stage or public_discovery,
        "secret_refs": [],
    }
    if model_stage:
        request_authorization["approval_ref"] = f"solar:required-operator:{operator_id}"
    elif public_discovery:
        policy_ref = next(item for item in dependencies if item.get("artifact_id") == "public-retrieval-authorization")
        request_authorization["approval_ref"] = f"{policy_ref['path']}#{policy_ref['sha256']}"
    request = {
        "schema": "research_node_request.v1",
        # The research-synthesis artifact ABI binds every stage in one run to
        # one stable task identity.  The outer dispatch id remains per-node,
        # but must not leak into cross-stage artifact identity checks.
        "task_id": f"{envelope.get('sprint_id')}:research-evidence-to-poc",
        "run_id": str(envelope.get("sprint_id") or ""),
        "workflow_id": WORKFLOW_ID,
        "node_id": node_id,
        "logical_operator": {"operator_id": str(inputs.get("logical_operator") or ""), "operator_kind": "logical", "capabilities": approved},
        "physical_operator": {"operator_id": RESEARCH_OPERATOR_BY_NODE[node_id], "operator_kind": "physical", "capabilities": approved},
        "typed_inputs": {"input_schema": f"{node_id}.fixed_source_pack.v1", "payload": typed_payload},
        "input_artifact_refs": [
            {key: item[key] for key in ("artifact_id", "path", "schema", "sha256")}
            for item in dependencies
        ],
        "authorization": request_authorization,
        "read_scope": sorted({item["path"] for item in dependencies}),
        "write_scope": [stage_rel],
        "timeout_retry_policy": {"timeout_seconds": int(envelope.get("lease_ttl_seconds") or 900), "max_attempts": 1, "retry_on": []},
    }
    services = _codex_services(node_id=node_id, stage_dir=stage_dir) if model_stage else {}
    if public_discovery:
        services = {
            "discover_sources": LiteratureDiscoveryService(stage_dir, limit=12),
            "service_metadata": {
                "discover_sources": {
                    "service_id": "autosci-production-literature-discovery",
                    "version": "1.0.0",
                }
            },
        }
    # All controller-owned inputs and exact operator bindings have now been
    # validated.  Only this bounded stage directory may be created.
    stage_dir.mkdir(parents=True, exist_ok=True)
    resolver = default_production_resolver(services=services, workspace_root=work_dir)
    provider_archives: set[str] = set()

    def run(inner_request: dict[str, Any]) -> dict[str, Any]:
        inner_result = resolver.execute(inner_request)
        provider_archives.update(_normalize_provider_archives(inner_result, work_dir, stage_dir))
        return inner_result

    if part_b_stage:
        result = execute_part_b(
            request=request,
            node_id=node_id,
            primary_rel=primary_rel,
            stage_dir=stage_dir,
            work_dir=work_dir,
            dependencies=dependencies,
            approval_controls=(inputs.get("approval_controls") if isinstance(inputs.get("approval_controls"), dict) else {}),
        )
        jsonschema.Draft202012Validator(
            json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        ).validate(result)
    else:
        result = dispatch_research_node(
            request,
            runner=run,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=work_dir,
            operator_resolver=resolver.resolve,
        )
    if model_stage:
        _merge_codex_invocation_usage(result, services)
        provider_archives.update(_normalize_provider_archives(result, work_dir, stage_dir))
        jsonschema.Draft202012Validator(
            json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        ).validate(result)
    if str(result.get("status") or "") == "completed" and (model_stage or deterministic_acceptance):
        _verify_model_usage(node_id=node_id, result=result)
    output_paths = {str(item.get("path") or "") for item in result.get("output_artifacts") or [] if isinstance(item, dict)}
    if str(result.get("status") or "") == "completed" and primary_rel not in output_paths:
        raise AdapterError(f"completed result did not emit exact contract primary artifact: {primary_rel}")
    if node_id == "report_revision" and str(result.get("status") or "") == "completed":
        _verify_report_revision_artifact(primary, work_dir, dependencies)
    if node_id == "final_delivery" and str(result.get("status") or "") == "completed":
        verify_final_delivery_artifact(
            request=request,
            work_dir=work_dir,
            primary=primary,
            markdown_path=stage_dir / "final_delivery.md",
            dependencies=dependencies,
        )
    evaluator = evaluate_production_result(request, result, {}, artifact_root=work_dir)
    result_path, _ = _contained(str((envelope.get("outputs") or {}).get("result_path") or ""), work_dir, label="result_path")
    expected_result_path = stage_dir / "research_node_result.json"
    if result_path != expected_result_path:
        raise AdapterError("result_path is not the controller-owned stage result path")
    if result_path.is_symlink():
        raise AdapterError("result_path must not be a symlink")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    handoff = Path(str(envelope.get("handoff_path") or ""))
    graph_path = Path(str(envelope.get("graph_path") or "")).resolve(strict=True)
    expected_handoff = graph_path.parent / f"{envelope.get('sprint_id')}.{node_id}-handoff.md"
    if handoff.resolve(strict=False) != expected_handoff.resolve(strict=False) or handoff.is_symlink():
        raise AdapterError("handoff_path is not the controller-owned node handoff path")
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "# Fixed research node handoff\n\n"
        f"- node: `{node_id}`\n- result: `{result_path}`\n- primary: `{primary}`\n"
        f"- production evaluator accepted: `{bool(evaluator.get('accepted'))}`\n",
        encoding="utf-8",
    )
    after = _inventory(work_dir)
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    result_rel = str(result_path.relative_to(work_dir)).replace("\\", "/")
    allowed = output_paths | provider_archives | {result_rel}
    unexpected = sorted(path for path in changed if path not in allowed)
    if unexpected:
        raise AdapterError(f"operator changed unreported files: {unexpected}")
    if any(not path.startswith(stage_rel.rstrip("/") + "/") for path in changed):
        raise AdapterError("operator changed files outside its stage directory")
    if any(record.get("type") == "symlink" for path, record in after.items() if path in changed):
        raise AdapterError("operator created or changed a symlink")
    return {"ok": bool(evaluator.get("accepted")), "node_id": node_id, "result": result, "evaluator": evaluator, "result_path": str(result_path), "handoff_path": str(handoff)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict):
            raise AdapterError("envelope must be a JSON object")
        payload = execute(envelope)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError, FixedResearchContractError, ResearchOperatorError, AdapterError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

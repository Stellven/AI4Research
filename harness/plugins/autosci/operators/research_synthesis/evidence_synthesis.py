"""evidence_synthesis node implementation."""

from __future__ import annotations

from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    no_provider_result,
    output_path,
    provider_usage_from,
    require_node,
    utc_now,
    write_artifact,
)


def _load_validation(context: OperatorContext) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=("research_synthesis.source_validation.v1",),
        artifact_ids=("source_validation",),
        filenames=("source_validation.json",),
        payload_keys=("source_validation",),
        expected_node_ids=("source_validation",),
    )


def _load_seed(context: OperatorContext) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=("research_synthesis.seed_snapshot.v1",),
        artifact_ids=("seed_snapshot",),
        filenames=("seed_snapshot.json",),
        payload_keys=("seed_snapshot",),
        expected_node_ids=("seed_fetch",),
    )


def _normalize_quotes(
    item: dict[str, Any],
    *,
    claim_id: str,
    evidence_ids: list[str],
    source_text_by_id: dict[str, str],
) -> list[dict[str, str]]:
    """Keep only quotes that really appear in the source they claim to come from.

    A claim recording which SOURCE backed it, but never which TEXT, cannot be
    verified downstream -- only its linkage can. The model is asked for the
    supporting sentence per cited source; this checks each one is an exact
    substring of that source before it is stored, so a paraphrase or an
    invented sentence is dropped here rather than travelling into a report
    that looks quote-verified.

    Dropping is deliberate: a quote that does not appear in its source is not
    evidence, and repairing it would mean choosing the support ourselves.
    """
    quotes: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in item.get("evidence_quotes") or []:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("source_id") or "").strip()
        quote = " ".join(str(raw.get("quote") or "").split())
        if not source_id or not quote or source_id not in evidence_ids:
            continue
        haystack = " ".join(str(source_text_by_id.get(source_id) or "").split())
        if not haystack or quote not in haystack:
            continue
        if source_id in seen:
            continue
        seen.add(source_id)
        quotes.append({"source_id": source_id, "quote": quote})
    return quotes


def _normalize_claims(
    response: dict[str, Any],
    accepted_ids: set[str],
    source_text_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    source_text_by_id = source_text_by_id or {}
    claims: list[dict[str, Any]] = []
    for index, item in enumerate(response.get("claims", []) if isinstance(response.get("claims"), list) else []):
        if not isinstance(item, dict):
            continue
        evidence_ids = [str(value) for value in item.get("evidence_ids", []) if str(value).strip()]
        invalid = sorted(set(evidence_ids) - accepted_ids)
        if invalid:
            raise ResearchOperatorError(
                f"Model returned evidence ids outside validated source set: {', '.join(invalid)}",
                error_type="unvalidated_evidence",
            )
        claims.append(
            {
                "claim_id": str(item.get("claim_id") or f"claim-{index + 1:03d}"),
                "text": str(item.get("text") or ""),
                "evidence_ids": evidence_ids,
                "evidence_quotes": _normalize_quotes(
                    item,
                    claim_id=str(item.get("claim_id") or f"claim-{index + 1:03d}"),
                    evidence_ids=evidence_ids,
                    source_text_by_id=source_text_by_id,
                ),
                "uncertainty": str(item.get("uncertainty") or "unknown"),
                "limitations": [str(value) for value in item.get("limitations", []) if str(value).strip()],
            }
        )
    return claims


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "evidence_synthesis")
    model_generate = context.services.get("model_generate")
    if model_generate is None:
        return no_provider_result(context, "model_generate")
    validation, validation_ref = _load_validation(context)
    accepted = [item for item in validation.get("accepted", []) if isinstance(item, dict)]
    if not accepted:
        return build_node_result(
            context,
            status="blocked",
            errors=[{"error_id": "evidence_synthesis.no_sources", "error_type": "missing_validated_sources", "message": "No validated sources were available for synthesis."}],
            limitations=["Evidence synthesis only consumes validated sources and cannot synthesize from unvalidated candidates."],
        )
    seed_snapshot, seed_ref = _load_seed(context)
    response = model_generate(
        node_id="evidence_synthesis",
        task_contract=context.payload.get("task_contract"),
        seed_snapshot=seed_snapshot,
        validated_sources=accepted,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
    accepted_ids = {str(item.get("source_id")) for item in accepted if item.get("source_id")}
    # The text each quote is checked against is the same content the model was
    # shown, so a verbatim quote verifies and a paraphrase does not.
    source_text_by_id = {
        str(item.get("source_id")): str(item.get("content_summary") or item.get("content") or "")
        for item in accepted
        if item.get("source_id")
    }
    claims = _normalize_claims(response, accepted_ids, source_text_by_id)
    if not claims:
        raise ResearchOperatorError("model_generate returned no grounded claims", error_type="provider_contract")
    limitations = list(dict.fromkeys([
        *[str(item) for item in validation.get("limitations", []) if str(item).strip()],
        *[str(item) for item in response.get("limitations", []) if str(item).strip()],
    ]))
    artifact_payload = {
        "schema": "research_synthesis.evidence_synthesis.v1",
        "node_id": "evidence_synthesis",
        "created_at": utc_now(),
        "source_ids": sorted(accepted_ids),
        "claims": claims,
        "claim_count": len(claims),
        "input_lineage": {
            "seed_snapshot": "seed_snapshot" if seed_snapshot else "",
            "source_validation": "source_validation" if validation else "",
        },
        "source_lineage": [
            {
                "source_id": str(item.get("source_id") or ""),
                "url": str(item.get("url") or ""),
                "provider": str((item.get("provenance") or {}).get("provider") or ""),
                "acquisition_channel": str(item.get("acquisition_channel") or ""),
                "candidate_sha256": str(item.get("candidate_sha256") or ""),
            }
            for item in accepted
        ],
        "source_policy_summary": dict(validation.get("source_policy_summary") or {}),
        "input_artifact_hashes": {
            "seed_snapshot": str((seed_ref or {}).get("sha256") or ""),
            "source_validation": str((validation_ref or {}).get("sha256") or ""),
        },
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "evidence_synthesis.json"),
        artifact_payload,
        artifact_id="evidence_synthesis",
        schema="research_synthesis.evidence_synthesis.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("evidence_synthesis.claims", "claim_evidence_linkage", f"{len(claims)} grounded claim(s) synthesized.", artifact["artifact_id"])],
        hashes=[hash_record],
        model_provider_usage=provider_usage_from(response, usage_kind="llm"),
        limitations=limitations,
    )

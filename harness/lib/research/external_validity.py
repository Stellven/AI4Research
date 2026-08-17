"""Fail-closed evaluation of preregistered, artifact-backed external holdouts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .trust_registry import TrustRegistryError, load_registry, trusted_artifact, trusted_site_identity
except ImportError:  # pragma: no cover - direct script execution fallback
    from trust_registry import TrustRegistryError, load_registry, trusted_artifact, trusted_site_identity

SCHEMA = "solar.external_validity_holdout.v2"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(raw: Any, base: Path) -> Path:
    path = Path(_text(raw))
    return path if path.is_absolute() else base / path


def _instant(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(_text(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate_external_holdout(
    path: str | Path,
    trusted_plan_sha256: str = "",
    trust_registry_path: str | Path | None = None,
    trust_registry_sha256: str = "",
) -> dict[str, Any]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    errors: list[str] = []
    trust_registry: dict[str, Any] = {}
    trust_registry_error = ""
    if not trust_registry_path:
        errors.append("trust_registry_required")
    else:
        try:
            trust_registry = load_registry(
                trust_registry_path,
                trust_registry_sha256,
            )
        except TrustRegistryError as exc:
            trust_registry_error = str(exc)
            errors.append("trust_registry_invalid:" + trust_registry_error)

    plan_ref = payload.get("external_plan") if isinstance(payload, dict) and isinstance(payload.get("external_plan"), dict) else {}
    plan_path = _resolve(plan_ref.get("path"), base)
    plan: dict[str, Any] = {}
    if not plan_path.is_file():
        errors.append("external_plan_missing")
    elif _text(plan_ref.get("sha256")).lower() != _sha(plan_path):
        errors.append("external_plan_hash_mismatch")
    elif not _text(trusted_plan_sha256) or _text(trusted_plan_sha256).lower() != _sha(plan_path):
        errors.append("external_plan_not_matched_by_out_of_band_trust_anchor")
    else:
        loaded = json.loads(plan_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            plan = loaded
        else:
            errors.append("external_plan_not_object")

    claim_id = _text(plan.get("claim_id"))
    metric_name = _text(plan.get("metric_name"))
    authority = plan.get("authority") if isinstance(plan.get("authority"), dict) else {}
    registered_at = _instant(plan.get("registered_at"))
    allowed_development = {_text(x) for x in plan.get("development_site_ids", []) if _text(x)}
    allowed_holdout = {_text(x) for x in plan.get("external_holdout_site_ids", []) if _text(x)}
    try:
        threshold = float(plan.get("minimum_site_support_rate"))
    except (TypeError, ValueError):
        threshold = -1.0
    if not claim_id or not metric_name or not _text(authority.get("authority_id")) or authority.get("role") != "independent_protocol_owner":
        errors.append("external_plan_contract_incomplete")
    if not registered_at:
        errors.append("external_plan_registration_time_invalid")
    if not 0 <= threshold <= 1:
        errors.append("external_plan_threshold_invalid")
    if len(allowed_holdout) < 2 or allowed_development & allowed_holdout:
        errors.append("external_plan_site_partition_invalid")
    plan_trust_pin: dict[str, Any] = {}
    if trust_registry and plan_path.is_file() and claim_id:
        try:
            plan_trust_pin = trusted_artifact(
                trust_registry,
                purpose="external_validity_plan",
                sha256=_sha(plan_path),
                artifact_id=claim_id,
            )
        except TrustRegistryError as exc:
            errors.append("external_plan_not_matched_by_trust_registry:" + str(exc))

    refs = payload.get("observations") if isinstance(payload, dict) and isinstance(payload.get("observations"), list) else []
    observations: list[dict[str, Any]] = []
    evidence_artifacts: list[dict[str, str]] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"observation_ref_not_object:{index}")
            continue
        evidence_path = _resolve(ref.get("path"), base)
        declared_hash = _text(ref.get("sha256")).lower()
        if not evidence_path.is_file():
            errors.append(f"observation_evidence_missing:{index}")
            continue
        actual_hash = _sha(evidence_path)
        if declared_hash != actual_hash:
            errors.append(f"observation_evidence_hash_mismatch:{index}")
            continue
        loaded = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            errors.append(f"observation_evidence_not_object:{index}")
            continue
        loaded["_evidence_path"] = str(evidence_path)
        loaded["_evidence_sha256"] = actual_hash
        observations.append(loaded)
        evidence_artifacts.append({"path": str(evidence_path), "sha256": actual_hash})

    development = [row for row in observations if row.get("split") == "development"]
    holdout = [row for row in observations if row.get("split") == "external_holdout"]
    if not development or not holdout or len(development) + len(holdout) != len(observations):
        errors.append("development_and_external_holdout_evidence_required")

    ids: dict[str, list[str]] = {key: [] for key in ("observation_id", "evidence_id", "source_lineage_id")}
    site_ids: list[str] = []
    measured: list[dict[str, Any]] = []
    site_identity_pins: list[dict[str, Any]] = []
    for index, row in enumerate(observations):
        site = row.get("site") if isinstance(row.get("site"), dict) else {}
        metric = row.get("metric") if isinstance(row.get("metric"), dict) else {}
        site_id = _text(site.get("site_id"))
        site_ids.append(site_id)
        for field in ids:
            ids[field].append(_text(row.get(field)))
        required_site = all(_text(site.get(field)) for field in ("site_id", "organization_id", "collection_protocol_id"))
        if site.get("kind") != "experimental_site" or not required_site:
            errors.append(f"experimental_site_identity_incomplete:{index}")
        elif trust_registry:
            try:
                pin = trusted_site_identity(
                    trust_registry,
                    site_id=site_id,
                    organization_id=_text(site.get("organization_id")),
                    collection_protocol_id=_text(site.get("collection_protocol_id")),
                    evidence_sha256=_text(row.get("_evidence_sha256")),
                )
                site_identity_pins.append(
                    {
                        "site_id": pin.get("site_id"),
                        "organization_id": pin.get("organization_id"),
                        "anchor_id": pin.get("anchor_id"),
                        "identity_uri": pin.get("identity_uri"),
                        "evidence_sha256": _text(row.get("_evidence_sha256")),
                    }
                )
            except TrustRegistryError as exc:
                errors.append(f"site_identity_not_trust_pinned:{index}:{exc}")
        expected_sites = allowed_development if row.get("split") == "development" else allowed_holdout
        if site_id not in expected_sites:
            errors.append(f"site_not_preregistered:{index}")
        collected_at = _instant(row.get("collected_at"))
        if not collected_at or (registered_at and collected_at <= registered_at):
            errors.append(f"observation_not_post_registration:{index}")
        if _text(metric.get("name")) != metric_name:
            errors.append(f"observation_metric_not_preregistered:{index}")
        numerator, denominator = metric.get("numerator"), metric.get("denominator")
        if isinstance(numerator, bool) or isinstance(denominator, bool) or not isinstance(numerator, int) or not isinstance(denominator, int) or denominator <= 0 or numerator < 0 or numerator > denominator:
            errors.append(f"observation_metric_counts_invalid:{index}")
            rate = 0.0
        else:
            rate = numerator / denominator
        measured.append({**row, "_site_id": site_id, "_rate": rate})

    for field, values in ids.items():
        if any(not value for value in values):
            errors.append(f"{field}_missing")
        if len(values) != len(set(values)):
            errors.append(f"{field}_not_unique")
    if any(not site_id for site_id in site_ids):
        errors.append("site_id_missing")
    dev_lineages = {_text(row.get("source_lineage_id")) for row in development}
    hold_lineages = {_text(row.get("source_lineage_id")) for row in holdout}
    if dev_lineages & hold_lineages:
        errors.append("development_holdout_source_lineage_contamination")

    observed_holdout_sites = {row["_site_id"] for row in measured if row.get("split") == "external_holdout"}
    if observed_holdout_sites != allowed_holdout:
        errors.append("external_holdout_site_coverage_incomplete")
    holdout_organizations = [
        _text(row.get("site", {}).get("organization_id"))
        for row in measured
        if row.get("split") == "external_holdout" and isinstance(row.get("site"), dict)
    ]
    site_organizations = {
        row["_site_id"]: _text(row.get("site", {}).get("organization_id"))
        for row in measured
        if row.get("split") == "external_holdout" and isinstance(row.get("site"), dict)
    }
    if len(set(holdout_organizations)) != len(observed_holdout_sites):
        errors.append("external_holdout_organizations_not_independent")
    site_results: list[dict[str, Any]] = []
    for site_id in sorted(observed_holdout_sites):
        site_rows = [row for row in measured if row.get("split") == "external_holdout" and row["_site_id"] == site_id]
        numerator = sum(int(row["metric"]["numerator"]) for row in site_rows if isinstance(row.get("metric", {}).get("numerator"), int))
        denominator = sum(int(row["metric"]["denominator"]) for row in site_rows if isinstance(row.get("metric", {}).get("denominator"), int))
        rate = numerator / denominator if denominator else 0.0
        site_results.append({
            "site_id": site_id,
            "numerator": numerator,
            "denominator": denominator,
            "support_rate": round(rate, 4),
            "passed": rate >= threshold,
            "evidence_artifact_sha256s": sorted(row["_evidence_sha256"] for row in site_rows),
            "source_lineage_ids": sorted(_text(row.get("source_lineage_id")) for row in site_rows),
            "organization_id": site_organizations.get(site_id, ""),
        })
    failed_sites = [row["site_id"] for row in site_results if not row["passed"]]
    if failed_sites:
        errors.append("external_site_threshold_failed:" + ",".join(failed_sites))

    accepted = not errors
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "claim_id": claim_id,
        "manifest": {"path": str(manifest_path), "sha256": _sha(manifest_path)},
        "external_plan": {"path": str(plan_path), "sha256": _sha(plan_path) if plan_path.is_file() else "", "registered_at": _text(plan.get("registered_at"))},
        "external_plan_trust": {
            "registry": str(Path(trust_registry_path).resolve()) if trust_registry_path else "",
            "registry_sha256": trust_registry_sha256.lower(),
            "artifact_id": plan_trust_pin.get("artifact_id"),
            "anchor_id": plan_trust_pin.get("anchor_id"),
            "signature_sha256": plan_trust_pin.get("signature_sha256"),
            "status": "accepted" if plan_trust_pin else "rejected",
            "error": trust_registry_error,
        },
        "evidence_artifacts": evidence_artifacts,
        "site_identity_contract": {
            "status": "accepted" if trust_registry and len(site_identity_pins) == len(observations) and not any(error.startswith("site_identity_not_trust_pinned") for error in errors) else "rejected",
            "pins": site_identity_pins,
            "required_count": len(observations),
            "accepted_count": len(site_identity_pins),
        },
        "policy": {"metric_name": metric_name, "minimum_site_support_rate": threshold, "preregistered_external_sites": sorted(allowed_holdout)},
        "site_results": site_results,
        "errors": list(dict.fromkeys(errors)),
        "claim_boundary": {
            "supported_on_preregistered_external_sites": accepted,
            "supports_unobserved_sites": False,
            "supports_universal_generalization": False,
        },
        "limitations": [
            "Acceptance is limited to the hash-bound plan, evidence artifacts, metric, and named experimental sites.",
            "Artifact integrity and cross-site agreement do not establish causal validity or universal generalization.",
            "The evaluator cannot authenticate the real-world identity of an organization; signed or independently hosted evidence is still required for adversarial settings.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate preregistered external holdout evidence")
    parser.add_argument("input", type=Path)
    parser.add_argument("--trusted-plan-sha256", required=True, help="Out-of-band plan digest supplied by the protocol owner")
    parser.add_argument("--trust-registry", required=True, type=Path)
    parser.add_argument("--trust-registry-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_external_holdout(
        args.input,
        args.trusted_plan_sha256,
        args.trust_registry,
        args.trust_registry_sha256,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())

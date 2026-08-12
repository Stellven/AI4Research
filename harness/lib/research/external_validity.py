"""Fail-closed evaluation of source-isolated external holdout evidence.

This module does not infer universal scientific validity.  It proves only
whether a named claim met a predeclared threshold on every supplied external
site while keeping development and holdout source lineages disjoint.
"""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
from typing import Any


SCHEMA = "solar.external_validity_holdout.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def evaluate_external_holdout(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = payload.get("observations") if isinstance(payload, dict) else None
    rows = rows if isinstance(rows, list) else []
    errors: list[str] = []
    threshold = float(payload.get("minimum_site_support_rate", 0.8)) if isinstance(payload, dict) else 0.8
    if not 0.0 <= threshold <= 1.0:
        errors.append("minimum_site_support_rate_out_of_range")
    if not isinstance(payload, dict) or not _text(payload.get("claim_id")):
        errors.append("claim_id_required")
    development = [row for row in rows if isinstance(row, dict) and row.get("split") == "development"]
    holdout = [row for row in rows if isinstance(row, dict) and row.get("split") == "external_holdout"]
    if not development or not holdout or len(development) + len(holdout) != len(rows):
        errors.append("development_and_external_holdout_splits_required")

    def values(items: list[dict[str, Any]], field: str) -> set[str]:
        return {_text(row.get(field)) for row in items if _text(row.get(field))}

    dev_sites, holdout_sites = values(development, "site_id"), values(holdout, "site_id")
    dev_sources, holdout_sources = values(development, "source_id"), values(holdout, "source_id")
    if dev_sites & holdout_sites:
        errors.append("development_holdout_site_contamination")
    if dev_sources & holdout_sources:
        errors.append("development_holdout_source_contamination")
    if len(holdout_sites) < 2:
        errors.append("at_least_two_external_holdout_sites_required")

    missing: list[str] = []
    for index, row in enumerate(holdout):
        for field in ("observation_id", "site_id", "source_id", "provider_family", "evidence_id"):
            if not _text(row.get(field)):
                missing.append(f"external_holdout[{index}].{field}")
        if not isinstance(row.get("claim_supported"), bool):
            missing.append(f"external_holdout[{index}].claim_supported")
    if missing:
        errors.append("required_external_evidence_missing:" + ",".join(missing))

    site_results: list[dict[str, Any]] = []
    for site_id in sorted(holdout_sites):
        site_rows = [row for row in holdout if _text(row.get("site_id")) == site_id]
        supported = sum(row.get("claim_supported") is True for row in site_rows)
        rate = supported / len(site_rows) if site_rows else 0.0
        site_results.append({
            "site_id": site_id,
            "observations": len(site_rows),
            "supported": supported,
            "support_rate": round(rate, 4),
            "passed": rate >= threshold,
            "source_ids": sorted(values(site_rows, "source_id")),
            "provider_families": sorted(values(site_rows, "provider_family")),
            "evidence_ids": sorted(values(site_rows, "evidence_id")),
        })
    failed_sites = [item["site_id"] for item in site_results if not item["passed"]]
    if failed_sites:
        errors.append("external_site_threshold_failed:" + ",".join(failed_sites))
    provider_families = values(holdout, "provider_family")
    if len(provider_families) < 2:
        errors.append("external_holdout_provider_diversity_insufficient")

    accepted = not errors
    observed_scope = {
        "development_sites": sorted(dev_sites),
        "external_holdout_sites": sorted(holdout_sites),
        "external_provider_families": sorted(provider_families),
    }
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "claim_id": _text(payload.get("claim_id")) if isinstance(payload, dict) else "",
        "source": {
            "path": str(source_path),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "observations": len(rows),
        },
        "policy": {
            "minimum_site_support_rate": threshold,
            "required_external_sites": 2,
            "require_source_isolation": True,
            "require_provider_diversity": True,
        },
        "scope": observed_scope,
        "site_results": site_results,
        "errors": errors,
        "claim_boundary": {
            "supported_on_observed_external_sites": accepted,
            "supports_unobserved_sites": False,
            "supports_universal_generalization": False,
            "allowed_statement": (
                "The claim met the predeclared threshold on the named, source-isolated external holdout sites."
                if accepted else
                "The supplied external holdout does not support extending the claim beyond development evidence."
            ),
        },
        "limitations": [
            "Acceptance is limited to the hash-bound observations and named external sites.",
            "Cross-site agreement does not establish causal validity or universal generalization.",
            "Scientific and human review remain required for deployment or publication claims.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate source-isolated external holdout evidence")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_external_holdout(args.input)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())

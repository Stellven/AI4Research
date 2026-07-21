#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    finish,
    has_any_evidence_ids,
    outputs,
    require_non_empty_list,
    require_non_empty_string,
    run_cli,
    validate_schema,
)

SCHEMA = "research_claims.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    claims = require_non_empty_list(outputs(payload).get("claims"), "outputs.claims", reasons)
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            reasons.append(f"claims[{index}] must be an object")
            continue
        require_non_empty_string(claim.get("claim_id"), f"claims[{index}].claim_id", reasons)
        require_non_empty_string(claim.get("claim_type"), f"claims[{index}].claim_type", reasons)
        testability = str(claim.get("testability") or "")
        if testability in {"testable", "partially_testable"}:
            require_non_empty_string(claim.get("source_anchor"), f"claims[{index}].source_anchor", reasons)
        elif testability == "not_testable":
            if not claim.get("non_testable_reason") and not claim.get("limitations"):
                reasons.append(f"claims[{index}] non-testable claim requires non_testable_reason or limitations")
        if str(claim.get("verification_status") or "") != "unverified":
            reasons.append(f"claims[{index}].verification_status must remain unverified at extraction stage")
        if not has_any_evidence_ids(claim.get("evidence_ids")):
            reasons.append(f"claims[{index}].evidence_ids must contain at least one id")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))

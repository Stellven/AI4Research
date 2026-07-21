#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import GateResult, run_cli
from evaluators.scientific.lifecycle_gate import SCHEMA, evaluate as evaluate_lifecycle


def evaluate(payload: dict[str, Any], path: str | Path | None = None) -> GateResult:
    if payload.get("schema") == SCHEMA and "artifact_contract" not in payload:
        return GateResult(
            ok=False,
            status="failed",
            reasons=["lifecycle_contract_gate requires a graph contract with artifact_contract; use lifecycle_runtime_gate.py for runtime summaries"],
            warnings=[],
            schema=SCHEMA,
            path=str(path) if path else None,
            evidence_status="failed",
        )
    return evaluate_lifecycle(payload, path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))

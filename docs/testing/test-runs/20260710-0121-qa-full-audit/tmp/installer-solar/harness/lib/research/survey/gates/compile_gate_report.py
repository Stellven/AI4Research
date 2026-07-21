"""Compile gate report — aggregator that runs all registered gates.

Collects partial verdicts from each gate plugin via ``GateRegistry`` and
assembles a ``GateReport``.  Degrades gracefully when a gate is not yet
registered (partial_verdicts).
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..schemas import GateReport, GateVerdict
from . import GateRegistry

GATE_SLOTS = [
    "source_quality",
    "argument_density",
    "controversy_matrix",
    "exploration_log",
]
_REGISTRY_ALIASES = {
    "controversy_matrix": ("controversy_matrix", "controversy"),
}


def _stable_report_id(
    *,
    run_metadata: dict[str, Any],
    artifact_paths: dict[str, str],
    scorecard_ref: dict[str, Any],
) -> str:
    explicit = run_metadata.get("report_id") or run_metadata.get("run_id")
    if explicit:
        return str(explicit)
    seed = repr(
        (
            sorted(run_metadata.items()),
            sorted(artifact_paths.items()),
            sorted(scorecard_ref.items()),
        )
    ).encode("utf-8")
    return f"gate_report_{hashlib.sha256(seed).hexdigest()[:12]}"


def _get_gate(slot: str):
    for name in _REGISTRY_ALIASES.get(slot, (slot,)):
        try:
            return GateRegistry.get(name), name
        except KeyError:
            continue
    raise KeyError(slot)


def _result_value(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _result_refs(result: Any) -> list[str]:
    if isinstance(result, dict):
        refs = result.get("evidence_refs")
        if isinstance(refs, list):
            return [str(v) for v in refs]
        rows = result.get("rows")
        if isinstance(rows, list):
            return [
                str(row.get("claim_id"))
                for row in rows
                if isinstance(row, dict) and row.get("claim_id")
            ]
        return []
    return list(getattr(result, "source_ids", [])) + list(
        getattr(result, "claim_ids", [])
    )


def _result_section(result: Any, registered_name: str) -> dict[str, Any]:
    if isinstance(result, dict):
        section = dict(result)
        section["registered_name"] = registered_name
        return section
    return {
        "section_id": getattr(result, "section_id", ""),
        "registered_name": registered_name,
    }


def compile_gate_report(
    *,
    evidence_pack: Any = None,
    section: Any = None,
    text: str = "",
    claim_evidence_rows: list[dict[str, Any]] | None = None,
    report_ast: Any = None,
    run_metadata: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
    scorecard_ref: dict[str, Any] | None = None,
) -> GateReport:
    """Run all registered gate plugins and assemble a ``GateReport``.

    For each gate slot, attempts ``GateRegistry.get(slot)``.  If the gate is
    missing, records a ``GateVerdict(verdict="not_applicable")`` with an
    explanatory note instead of crashing.
    """
    metadata = dict(run_metadata or {})
    paths = dict(artifact_paths or {})
    scorecard = dict(scorecard_ref or {})
    gate_verdicts: dict[str, GateVerdict] = {}
    partial_verdicts: list[str] = []

    for slot in GATE_SLOTS:
        try:
            gate_fn, registered_name = _get_gate(slot)
        except KeyError:
            partial_verdicts.append(slot)
            gate_verdicts[slot] = GateVerdict(
                gate_id=slot,
                verdict="not_applicable",
                evidence_refs=[],
                report_section={"reason": "gate_not_registered"},
            )
            continue

        try:
            if slot == "source_quality" and evidence_pack is not None:
                result = gate_fn(evidence_pack)
            elif slot == "argument_density" and section is not None:
                result = gate_fn(section, text)
            elif slot == "controversy_matrix" and claim_evidence_rows is not None:
                result = gate_fn(
                    evidence_pack if evidence_pack else {},
                    claim_evidence_rows,
                )
            elif slot == "exploration_log":
                result = gate_fn(paths)
            else:
                gate_verdicts[slot] = GateVerdict(
                    gate_id=slot,
                    verdict="not_applicable",
                    evidence_refs=[],
                    report_section={"reason": "missing_input"},
                )
                partial_verdicts.append(slot)
                continue

            gate_verdicts[slot] = GateVerdict(
                gate_id=slot,
                verdict=_result_value(result, "verdict", "fail"),
                evidence_refs=_result_refs(result),
                report_section=_result_section(result, registered_name),
            )
        except Exception as exc:
            gate_verdicts[slot] = GateVerdict(
                gate_id=slot,
                verdict="fail",
                evidence_refs=[],
                report_section={
                    "error": str(exc),
                    "registered_name": registered_name,
                },
            )

    metadata["partial_verdicts"] = list(partial_verdicts)
    report_id = _stable_report_id(
        run_metadata=metadata,
        artifact_paths=paths,
        scorecard_ref=scorecard,
    )

    report = GateReport(
        report_id=report_id,
        run_metadata=metadata,
        gate_verdicts=gate_verdicts,
        artifact_paths=paths,
        scorecard_ref=scorecard,
    )
    # Backward-compatible observable field without mutating the N1 dataclass schema.
    report.partial_verdicts = list(partial_verdicts)
    return report

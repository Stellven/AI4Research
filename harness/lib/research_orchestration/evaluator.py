"""Production evidence evaluator for Solar research node results."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def evaluate_production_result(
    request: dict,
    result: dict,
    state: dict,
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    """Evaluate worker evidence without trusting the worker's completion label."""

    del state  # state is accepted for the orchestrator evaluator ABI
    status = str(result.get("status") or "failed")
    evidence = [item for item in result.get("evidence") or [] if isinstance(item, dict)]
    errors: list[dict[str, str]] = []
    limitations = [str(item) for item in result.get("limitations") or []]

    if status != "completed":
        return {
            "accepted": False,
            "status": status,
            "evidence_refs": [],
            "errors": list(result.get("errors") or []),
            "limitations": limitations,
        }
    if result.get("errors"):
        errors.append({"message": "completed worker result contains errors"})
    if not evidence:
        errors.append({"message": "completed worker result contains no evidence"})

    root = Path(artifact_root).expanduser().resolve()
    linked_evidence: set[str] = set()
    for artifact in result.get("output_artifacts") or []:
        artifact_id = str(artifact.get("artifact_id") or "")
        raw_path = str(artifact.get("path") or "")
        path = Path(raw_path)
        resolved = (path if path.is_absolute() else root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append({"message": f"artifact escapes production root: {artifact_id}"})
            continue
        if not resolved.is_file() or resolved.stat().st_size <= 0:
            errors.append({"message": f"artifact is missing or empty: {artifact_id}"})
            continue
        expected_hash = str(artifact.get("sha256") or "").lower()
        actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if not expected_hash or expected_hash != actual_hash:
            errors.append({"message": f"artifact hash mismatch: {artifact_id}"})
            continue
        linked = {
            str(item.get("evidence_id"))
            for item in evidence
            if str(item.get("artifact_id") or "") == artifact_id and str(item.get("evidence_id") or "")
        }
        if not linked:
            errors.append({"message": f"artifact has no linked evidence: {artifact_id}"})
        linked_evidence.update(linked)

    accepted = not errors
    return {
        "accepted": accepted,
        "status": "completed" if accepted else "failed",
        "evidence_refs": sorted(linked_evidence) if accepted else [],
        "errors": errors,
        "limitations": limitations,
    }

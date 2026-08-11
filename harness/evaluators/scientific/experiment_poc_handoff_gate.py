#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import ARTIFACT_HARNESS_DIR, finish, run_cli, validate_schema

SCHEMA = "autosci_experiment_poc_handoff.v1"
COMPONENT_SCHEMAS = {
    "experiment_plan": "experiment_plan.v1",
    "allowlist": "autosci_experiment_command_allowlist.v1",
    "manifest": "autosci_experiment_poc_manifest.v1",
    "expected_result": "experiment_result.v1",
    "runtime_evidence": "autosci_runtime_evidence.v1",
    "result": "experiment_result.v1",
    "lease_report": "autosci_experiment_execution_lease_report.v1",
}


def _resolve(raw: str, package_path: str | Path | None) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    package_dir = Path(package_path).resolve().parent if package_path else Path.cwd()
    candidates = [package_dir / path, *[parent / path for parent in package_dir.parents], ARTIFACT_HARNESS_DIR / path]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[-1])


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    integration = payload.get("integration") if isinstance(payload.get("integration"), dict) else {}
    if integration.get("approved_argv") != integration.get("executed_argv"):
        reasons.append("integration.executed_argv must exactly match integration.approved_argv")
    if integration.get("exit_code") != 0:
        reasons.append("integration.exit_code must be zero")

    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    for name, raw in components.items():
        raw_path = str(raw or "").strip()
        if not raw_path:
            reasons.append(f"components.{name} must be present")
            continue
        component_path = _resolve(raw_path, path)
        if not component_path.is_file():
            reasons.append(f"components.{name} does not exist: {raw_path}")
            continue
        expected_schema = COMPONENT_SCHEMAS.get(name)
        if expected_schema:
            try:
                component_payload = json.loads(component_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                reasons.append(f"components.{name} is not readable JSON: {exc}")
                continue
            if component_payload.get("schema") != expected_schema:
                reasons.append(
                    f"components.{name}.schema must be {expected_schema}, got {component_payload.get('schema')}"
                )

    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))

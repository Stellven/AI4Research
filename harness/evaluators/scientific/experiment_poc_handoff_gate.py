#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
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
    component_hashes = payload.get("component_hashes") if isinstance(payload.get("component_hashes"), dict) else {}
    resolved_components: dict[str, Path] = {}
    component_payloads: dict[str, dict[str, Any]] = {}
    for name, raw in components.items():
        raw_path = str(raw or "").strip()
        if not raw_path:
            reasons.append(f"components.{name} must be present")
            continue
        component_path = _resolve(raw_path, path)
        if not component_path.is_file():
            reasons.append(f"components.{name} does not exist: {raw_path}")
            continue
        resolved_components[name] = component_path
        digest = component_hashes.get(name) if isinstance(component_hashes.get(name), dict) else {}
        actual_sha256 = hashlib.sha256(component_path.read_bytes()).hexdigest()
        if digest.get("path") != raw_path:
            reasons.append(f"component_hashes.{name}.path must match components.{name}")
        if digest.get("sha256") != actual_sha256:
            reasons.append(f"component_hashes.{name}.sha256 does not match component bytes")
        if digest.get("bytes") != component_path.stat().st_size:
            reasons.append(f"component_hashes.{name}.bytes does not match component bytes")
        expected_schema = COMPONENT_SCHEMAS.get(name)
        if expected_schema:
            try:
                component_payload = json.loads(component_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                reasons.append(f"components.{name} is not readable JSON: {exc}")
                continue
            component_payloads[name] = component_payload
            if component_payload.get("schema") != expected_schema:
                reasons.append(
                    f"components.{name}.schema must be {expected_schema}, got {component_payload.get('schema')}"
                )
            elif name in {"experiment_plan", "result", "runtime_evidence"}:
                component_reasons, component_warnings = validate_schema(component_payload, expected_schema)
                reasons.extend(f"components.{name}:{item}" for item in component_reasons)
                warnings.extend(f"components.{name}:{item}" for item in component_warnings)

    package_experiment_id = str(payload.get("experiment_id") or "")
    identity_values: dict[str, str] = {}
    plan_payload = component_payloads.get("experiment_plan", {})
    identity_values["experiment_plan"] = str(((plan_payload.get("outputs") or {}).get("experiment_plan") or {}).get("experiment_id") or "")
    for name in ("expected_result", "result"):
        component_payload = component_payloads.get(name, {})
        identity_values[name] = str(((component_payload.get("outputs") or {}).get("result") or {}).get("experiment_id") or "")
    for name in ("allowlist", "manifest"):
        identity_values[name] = str(component_payloads.get(name, {}).get("experiment_id") or "")

    lease_payload = component_payloads.get("lease_report", {})
    lease_identity = lease_payload.get("lease_identity") if isinstance(lease_payload.get("lease_identity"), dict) else {}
    stale_recovery = lease_payload.get("stale_recovery") if isinstance(lease_payload.get("stale_recovery"), dict) else {}
    identity_values.update(
        {
            "lease_report": str(lease_payload.get("experiment_id") or ""),
            "lease_identity.experiment_id": str(lease_identity.get("experiment_id") or ""),
            "lease_identity.run_id": str(lease_identity.get("run_id") or ""),
            "stale_recovery.run_id": str(stale_recovery.get("run_id") or ""),
        }
    )
    for name, observed in identity_values.items():
        if observed != package_experiment_id:
            reasons.append(
                f"experiment identity mismatch: {name}={observed or '<missing>'} must equal package experiment_id={package_experiment_id}"
            )

    recovery_claim = payload.get("lease_recovery") if isinstance(payload.get("lease_recovery"), dict) else {}
    if recovery_claim.get("claimed") is True:
        if recovery_claim.get("experiment_id") != package_experiment_id:
            reasons.append("lease_recovery.experiment_id must equal package experiment_id")
        if not all(recovery_claim.get(key) is True for key in ("stale_observed", "recovered", "audit_recorded")):
            reasons.append("claimed lease recovery must be observed, recovered, and audited")
        audit_path = resolved_components.get("lease_recovery_audit")
        audit_digest = component_hashes.get("lease_recovery_audit")
        if audit_path is None or not isinstance(audit_digest, dict):
            reasons.append("claimed lease recovery requires a hashed lease_recovery_audit component")
        else:
            try:
                audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                reasons.append(f"components.lease_recovery_audit is not readable JSON: {exc}")
            else:
                for key in ("research_run_id", "run_id", "sprint_id"):
                    if str(audit_payload.get(key) or "") != package_experiment_id:
                        reasons.append(f"components.lease_recovery_audit.{key} must equal package experiment_id")
                if audit_payload.get("state") != "stale" or audit_payload.get("recovery_reason") != "experiment_stale_recovery_probe":
                    reasons.append("lease recovery audit must record the stale state and canonical recovery reason")
                if str(audit_payload.get("lease_id") or "") != str(stale_recovery.get("lease_id") or ""):
                    reasons.append("lease recovery audit lease_id must match the lease report")

    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    plan_digest = component_hashes.get("experiment_plan") if isinstance(component_hashes.get("experiment_plan"), dict) else {}
    if provenance.get("source_experiment_plan_sha256") != plan_digest.get("sha256"):
        reasons.append("provenance.source_experiment_plan_sha256 must match the bundled experiment plan")

    replay = payload.get("replay") if isinstance(payload.get("replay"), dict) else {}
    replay_argv = replay.get("argv") if isinstance(replay.get("argv"), list) else []
    expected_replay = [
        (integration.get("approved_argv") or [""])[0],
        components.get("runner"),
        components.get("dataset"),
        replay.get("expected_output"),
    ]
    if replay_argv != expected_replay:
        reasons.append("replay.argv must use the approved executable and bundled runner/dataset/output paths exactly")

    manifest_path = resolved_components.get("manifest")
    if manifest_path:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            reasons.append(f"components.manifest is not readable JSON: {exc}")
        else:
            expected_manifest_paths = {
                "runner_path": "runner.py",
                "input_path": "dataset.csv",
                "allowlist_path": "command_allowlist.json",
                "result_path": "../replay/result.json",
                "replay_cwd": "..",
            }
            for key, expected in expected_manifest_paths.items():
                if manifest.get(key) != expected:
                    reasons.append(f"components.manifest.{key} must be {expected}")

    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))

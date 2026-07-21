#!/usr/bin/env python3
"""capsule_execution_gate.py — pre-dispatch gating for capability capsules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent.parent
RUN_DIR = HARNESS_DIR / "run"
DEDUP_PATH = RUN_DIR / "dispatch-dedup.json"
COOLDOWN_PATH = RUN_DIR / "capsule-cooldown.json"


@dataclass
class IdempotencyResult:
    allowed: bool
    fingerprint: str
    reason: str = ""


@dataclass
class GateDecision:
    ok: bool
    blocks: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_inputs(task_envelope: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = manifest.get("contract", {}).get("inputs", {}).get("required", []) or []
    for item in required:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name and not task_envelope.get(name):
            failures.append(f"missing required input: {name}")
    return failures


def check_preconditions(task_envelope: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for condition in manifest.get("contract", {}).get("preconditions", []) or []:
        if not isinstance(condition, dict):
            continue
        check = condition.get("check")
        if check == "input_present":
            field = str(condition.get("field") or "")
            if field and not task_envelope.get(field):
                failures.append(f"missing precondition input: {field}")
        elif check == "task_type_in":
            values = {str(item) for item in condition.get("values", []) or []}
            if values and str(task_envelope.get("task_type") or "") not in values:
                failures.append(f"task_type not allowed: {task_envelope.get('task_type')}")
    return failures


def _fingerprint(task_envelope: dict[str, Any]) -> str:
    blob = json.dumps(task_envelope, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def check_idempotency(
    task_id: str,
    task_envelope: dict[str, Any],
    *,
    dedup_path: Path | None = None,
) -> IdempotencyResult:
    fingerprint = _fingerprint(task_envelope)
    path = Path(dedup_path or DEDUP_PATH)
    payload = _read_json(path)
    existing = payload.get(task_id)
    if isinstance(existing, dict) and existing.get("fingerprint") == fingerprint and existing.get("status") == "dispatched":
        return IdempotencyResult(allowed=False, fingerprint=fingerprint, reason="duplicate active dispatch")
    payload[str(task_id)] = {
        "fingerprint": fingerprint,
        "status": "dispatched",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_json(path, payload)
    return IdempotencyResult(allowed=True, fingerprint=fingerprint)


def check_cooldown(
    capsule_id: str,
    *,
    cooldown_s: int = 0,
    cooldown_path: Path | None = None,
) -> bool:
    if cooldown_s <= 0:
        return True
    path = Path(cooldown_path or COOLDOWN_PATH)
    payload = _read_json(path)
    existing = payload.get(capsule_id)
    if not isinstance(existing, dict) or not existing.get("last_run_ts"):
        return True
    last_run = datetime.fromisoformat(str(existing["last_run_ts"]).replace("Z", "+00:00"))
    return datetime.now(timezone.utc) >= last_run + timedelta(seconds=cooldown_s)


def classify_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "TRANSIENT"
    if isinstance(exc, PermissionError):
        return "POLICY_VIOLATION"
    text = str(exc).lower()
    if "blocked" in text or "waiting_human" in text:
        return "BLOCKED"
    return "FATAL"


def validate_proof_obligations(obligations: list[Any], artifacts_dir: str | Path) -> list[str]:
    root = Path(artifacts_dir)
    failures: list[str] = []
    for obligation in obligations:
        if isinstance(obligation, dict) and obligation.get("kind") == "artifact_present":
            target = root / str(obligation.get("path") or "")
            if not target.exists():
                failures.append(f"missing proof artifact: {target.name}")
    return failures


def validate_artifact_existence(artifact_paths: list[str], artifacts_dir: str | Path) -> list[str]:
    root = Path(artifacts_dir)
    failures: list[str] = []
    for artifact_path in artifact_paths:
        target = Path(artifact_path)
        if not target.is_absolute():
            target = root / artifact_path
        if not target.exists():
            failures.append(f"missing artifact: {target.name}")
    return failures


def guard_sensitive_actions(manifest: dict[str, Any], task_envelope: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    risks = {str(item) for item in manifest.get("effects", {}).get("risk", []) or []}
    secret_refs = manifest.get("bindings", {}).get("secret_refs", []) or []
    if (secret_refs or "destructive_shell" in risks) and task_envelope.get("allow_sensitive") is not True:
        failures.append("sensitive capability requires allow_sensitive=true")
    return failures


def run_gate(
    task_envelope: dict[str, Any],
    manifest: dict[str, Any],
    artifacts_dir: str | Path,
    *,
    cooldown_path: Path | None = None,
    dedup_path: Path | None = None,
) -> GateDecision:
    blocks: list[str] = []
    warnings: list[str] = []
    blocks.extend(validate_inputs(task_envelope, manifest))
    blocks.extend(check_preconditions(task_envelope, manifest))
    blocks.extend(guard_sensitive_actions(manifest, task_envelope))

    task_id = str(task_envelope.get("task_id") or "")
    if task_id:
        idem = check_idempotency(task_id, task_envelope, dedup_path=dedup_path)
        if not idem.allowed:
            blocks.append(idem.reason)

    capsule_id = str(task_envelope.get("capability_capsule_id") or manifest.get("capability_capsule_id") or "")
    cooldown_s = int(task_envelope.get("cooldown_s") or 0)
    if capsule_id and not check_cooldown(capsule_id, cooldown_s=cooldown_s, cooldown_path=cooldown_path):
        blocks.append(f"cooldown active for {capsule_id}")

    proof_failures = validate_proof_obligations(
        manifest.get("verification", {}).get("self_check", []) or [],
        artifacts_dir,
    )
    warnings.extend(item for item in proof_failures if item not in blocks)
    expected_artifacts = [str(item) for item in task_envelope.get("expected_artifacts", []) or []]
    warnings.extend(validate_artifact_existence(expected_artifacts, artifacts_dir))
    return GateDecision(ok=not blocks, blocks=blocks, warnings=warnings)

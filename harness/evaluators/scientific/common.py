#!/usr/bin/env python3
"""Shared deterministic gate helpers for scientific Evidence ABI payloads."""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HARNESS_DIR = Path(__file__).resolve().parents[2]
ARTIFACT_HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HARNESS_DIR))
SCHEMAS_DIR = HARNESS_DIR / "schemas" / "evidence"
REPO_DIR = HARNESS_DIR.parent


@dataclass
class GateResult:
    ok: bool
    status: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema: str | None = None
    path: str | None = None
    evidence_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "schema": self.schema,
            "path": self.path,
            "evidence_status": self.evidence_status,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("gate input must be a JSON object")
    return payload


def schema_path(schema_name: str) -> Path:
    return SCHEMAS_DIR / f"{schema_name}.schema.json"


def _repo_venv_site_packages() -> Path:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return REPO_DIR / ".venv" / "lib" / version / "site-packages"


def _import_jsonschema():
    try:
        import jsonschema  # type: ignore

        return jsonschema
    except ModuleNotFoundError as exc:
        if exc.name != "jsonschema":
            raise
        site_packages = _repo_venv_site_packages()
        if site_packages.exists():
            site_path = str(site_packages)
            if site_path not in sys.path:
                sys.path.insert(0, site_path)
            import jsonschema  # type: ignore

            return jsonschema
        raise


def validate_schema(payload: dict[str, Any], expected_schema: str) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    if payload.get("schema") != expected_schema:
        reasons.append(f"schema must be {expected_schema}")
        return reasons, warnings

    path = schema_path(expected_schema)
    if not path.exists():
        reasons.append(f"schema file missing: {path}")
        return reasons, warnings

    schema = load_json(path)
    try:
        jsonschema = _import_jsonschema()
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            reasons.append(f"schema:{location}: {error.message}")
    except ModuleNotFoundError as exc:
        reasons.append(
            "schema validator dependency missing: "
            f"{exc.name or 'jsonschema'}; run with the repo .venv Python or rebuild .venv"
        )
    return reasons, warnings


def _fallback_schema_check(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    missing = [key for key in schema.get("required", []) if key not in payload]
    if missing:
        warnings.append(f"fallback schema check missing top-level keys: {', '.join(missing)}")
    outputs = payload.get("outputs")
    output_required = (
        schema.get("properties", {})
        .get("outputs", {})
        .get("required", [])
    )
    if isinstance(outputs, dict):
        missing_outputs = [key for key in output_required if key not in outputs]
        if missing_outputs:
            warnings.append(f"fallback schema check missing outputs: {', '.join(missing_outputs)}")
    else:
        warnings.append("fallback schema check found non-object outputs")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        warnings.append("fallback schema check found non-object provenance")
    else:
        missing_provenance = [
            key
            for key in ("operator_id", "implementation_package", "timestamp")
            if not provenance.get(key)
        ]
        if missing_provenance:
            warnings.append(f"fallback schema check missing provenance: {', '.join(missing_provenance)}")
    return warnings


def finish(
    payload: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
    *,
    path: str | Path | None = None,
) -> GateResult:
    evidence_status = str(payload.get("status") or "")
    if reasons:
        status = "failed"
    elif evidence_status == "failed":
        status = "failed"
        reasons.append("evidence status is failed")
    elif evidence_status == "inconclusive":
        status = "inconclusive"
        warnings.append("evidence status is inconclusive")
    else:
        status = "passed"
    return GateResult(
        ok=status == "passed",
        status=status,
        reasons=reasons,
        warnings=warnings,
        schema=str(payload.get("schema") or ""),
        path=str(path) if path else None,
        evidence_status=evidence_status,
    )


def outputs(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("outputs")
    return value if isinstance(value, dict) else {}


def limitations(payload: dict[str, Any]) -> list[str]:
    value = payload.get("limitations")
    return [str(item) for item in value] if isinstance(value, list) else []


def require_non_empty_list(value: Any, name: str, reasons: list[str]) -> list[Any]:
    if not isinstance(value, list) or not value:
        reasons.append(f"{name} must be a non-empty list")
        return []
    return value


def require_non_empty_string(value: Any, name: str, reasons: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{name} must be a non-empty string")
        return ""
    return value.strip()


def has_any_evidence_ids(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


def check_artifact_paths(payload: dict[str, Any], evidence_path: str | Path | None, reasons: list[str]) -> None:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        reasons.append("artifacts must contain at least one entry")
        return
    evidence_dir = Path(evidence_path).resolve().parent if evidence_path else HARNESS_DIR
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            reasons.append(f"artifacts[{index}] must be an object")
            continue
        raw_path = str(artifact.get("path") or "").strip()
        if not raw_path:
            reasons.append(f"artifacts[{index}].path must be present")
            continue
        if raw_path.startswith("unavailable:"):
            if not raw_path.split(":", 1)[1].strip():
                reasons.append(f"artifacts[{index}].path declares unavailable without a reason")
            continue
        path = Path(raw_path).expanduser()
        candidates = [path] if path.is_absolute() else [evidence_dir / path, ARTIFACT_HARNESS_DIR / path, HARNESS_DIR / path]
        if not any(candidate.exists() for candidate in candidates):
            reasons.append(f"artifacts[{index}].path does not exist or declare unavailable: {raw_path}")


def run_cli(evaluator: Callable[[dict[str, Any], str | Path | None], GateResult], expected_schema: str) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        payload = load_json(args.path)
        result = evaluator(payload, args.path)
    except Exception as exc:  # noqa: BLE001 - gate CLI should return structured failure.
        result = GateResult(
            ok=False,
            status="failed",
            reasons=[f"{type(exc).__name__}: {exc}"],
            schema=expected_schema,
            path=args.path,
        )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.status == "passed":
        return 0
    if result.status == "inconclusive":
        return 3
    return 2

#!/usr/bin/env python3
"""Validator for AI Influence operator metadata.json files.

This module validates the metadata.json files produced by each AI Influence operator
(X, GitHub, HF Papers, YouTube, Gemini). It ensures the metadata conforms to the
expected schema and provides detailed error reporting.

Usage:
    python -m lib.metadata_validator validate /path/to/metadata.json
    python -m lib.metadata_validator check-all /path/to/reports/dir
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class ValidationError(Enum):
    """Enumeration of validation error types."""
    MISSING_SCHEMA_VERSION = "E_MISSING_SCHEMA_VERSION"
    MISSING_RUN_ID = "E_MISSING_RUN_ID"
    MISSING_OPERATOR = "E_MISSING_OPERATOR"
    MISSING_RUN_STATUS = "E_MISSING_RUN_STATUS"
    MISSING_STARTED_AT = "E_MISSING_STARTED_AT"
    INVALID_RUN_STATUS = "E_INVALID_RUN_STATUS"
    MISSING_ARTIFACTS = "E_MISSING_ARTIFACTS"
    ARTIFACT_PATH_NOT_EXISTS = "E_ARTIFACT_PATH_NOT_EXISTS"
    INVALID_TIMESTAMP = "E_INVALID_TIMESTAMP"


class RunStatus(str, Enum):
    """Valid run status values."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ValidationResult:
    """Result of a metadata validation."""
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class OperatorMetadata:
    """Schema for AI Influence operator metadata."""
    schema_version: str
    run_id: str
    operator: str  # x_social, github_new, github_legacy, hf_papers, youtube, gemini
    run_status: RunStatus
    started_at: str  # ISO 8601 timestamp
    completed_at: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    # Optional fields for enhanced reporting
    schedule_type: str | None = None  # daily, on_demand
    source_count: int | None = None
    processed_count: int | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        payload = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "operator": self.operator,
            "run_status": self.run_status.value if isinstance(self.run_status, RunStatus) else self.run_status,
            "started_at": self.started_at,
        }
        if self.completed_at:
            payload["completed_at"] = self.completed_at
        if self.artifacts:
            payload["artifacts"] = self.artifacts
        if self.stats:
            payload["stats"] = self.stats
        if self.errors:
            payload["errors"] = self.errors
        if self.schedule_type:
            payload["schedule_type"] = self.schedule_type
        if self.source_count is not None:
            payload["source_count"] = self.source_count
        if self.processed_count is not None:
            payload["processed_count"] = self.processed_count
        if self.duration_seconds is not None:
            payload["duration_seconds"] = self.duration_seconds
        return payload


# Valid operators
VALID_OPERATORS = {
    "x_social",
    "github_new",
    "github_legacy",
    "hf_papers",
    "youtube",
    "gemini",
}

# Required fields for metadata
REQUIRED_FIELDS = {
    "schema_version",
    "run_id",
    "operator",
    "run_status",
    "started_at",
}


def _append_error(errors: list[dict[str, Any]], code: ValidationError, message: str, path: str) -> None:
    """Append an error to the errors list."""
    errors.append({
        "code": code.value,
        "message": message,
        "path": path,
    })


def _parse_timestamp(value: str) -> datetime | None:
    """Parse ISO 8601 timestamp."""
    try:
        # Try parsing with timezone
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except (ValueError, AttributeError):
        return None


def validate_metadata(data: dict[str, Any], reports_dir: Path | None = None) -> ValidationResult:
    """Validate a metadata dict against the schema.

    Args:
        data: The metadata dict to validate.
        reports_dir: Optional base reports directory for artifact path validation.

    Returns:
        ValidationResult with errors and warnings.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            _append_error(errors, ValidationError[f"MISSING_{field.upper()}"], f"missing required field: {field}", field)

    # Validate operator
    operator = data.get("operator")
    if operator and operator not in VALID_OPERATORS:
        _append_error(errors, ValidationError.INVALID_RUN_STATUS, f"invalid operator: {operator}", "operator")

    # Validate run_status
    run_status = data.get("run_status")
    if run_status:
        valid_statuses = {s.value for s in RunStatus}
        if run_status not in valid_statuses:
            _append_error(errors, ValidationError.INVALID_RUN_STATUS, f"invalid run_status: {run_status}", "run_status")

    # Validate timestamps
    started_at = data.get("started_at")
    if started_at and not _parse_timestamp(started_at):
        _append_error(errors, ValidationError.INVALID_TIMESTAMP, f"invalid started_at timestamp: {started_at}", "started_at")

    completed_at = data.get("completed_at")
    if completed_at and not _parse_timestamp(completed_at):
        _append_error(errors, ValidationError.INVALID_TIMESTAMP, f"invalid completed_at timestamp: {completed_at}", "completed_at")

    # Validate artifact paths if reports_dir is provided
    artifacts = data.get("artifacts", {})
    if reports_dir:
        for artifact_name, artifact_path in artifacts.items():
            full_path = reports_dir / artifact_path
            if not full_path.exists():
                warnings.append({
                    "code": "ARTIFACT_PATH_NOT_EXISTS",
                    "message": f"artifact path does not exist: {artifact_path}",
                    "path": f"artifacts.{artifact_name}",
                })

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def load_and_validate(path: Path, reports_dir: Path | None = None) -> ValidationResult:
    """Load and validate a metadata.json file.

    Args:
        path: Path to the metadata.json file.
        reports_dir: Optional base reports directory for artifact path validation.

    Returns:
        ValidationResult with errors and warnings.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return ValidationResult(
            ok=False,
            errors=[{
                "code": "E_FILE_READ_ERROR",
                "message": f"failed to read or parse file: {e}",
                "path": str(path),
            }]
        )
    return validate_metadata(data, reports_dir)


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a single metadata.json file."""
    path = Path(args.metadata).expanduser()
    reports_base = Path(args.reports_dir).expanduser() if args.reports_dir else None

    result = load_and_validate(path, reports_base)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def cmd_check_all(args: argparse.Namespace) -> int:
    """Check all metadata.json files in a directory."""
    reports_dir = Path(args.reports_dir).expanduser()

    if not reports_dir.is_dir():
        print(f"ERROR: reports directory does not exist: {reports_dir}", file=sys.stderr)
        return 2

    # Find all metadata.json files
    metadata_files = list(reports_dir.rglob("metadata.json"))

    if not metadata_files:
        print(f"No metadata.json files found in {reports_dir}")
        return 0

    results = []
    for mf in metadata_files:
        result = load_and_validate(mf, reports_dir)
        results.append({
            "path": str(mf.relative_to(reports_dir)),
            "result": result.to_dict(),
        })

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["result"]["ok"]),
        "failed": sum(1 for r in results if not r["result"]["ok"]),
        "results": results,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Validate AI Influence operator metadata.json files")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # validate subcommand
    validate = sub.add_parser("validate", help="Validate a single metadata.json file")
    validate.add_argument("metadata", help="Path to metadata.json file")
    validate.add_argument("--reports-dir", help="Base reports directory for artifact path validation")

    # check-all subcommand
    check_all = sub.add_parser("check-all", help="Check all metadata.json files in a directory")
    check_all.add_argument("reports_dir", help="Base reports directory to search")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    if args.cmd == "validate":
        return cmd_validate(args)
    elif args.cmd == "check-all":
        return cmd_check_all(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

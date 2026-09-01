#!/usr/bin/env python3
"""Command-backed operator that authors native Elastic Planner artifacts only."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


HARNESS_DIR = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from elastic_planner import verify_frozen_execution_chain, verify_semantic_planning_chain  # noqa: E402
from elastic_planner_runtime import RESULT_SCHEMA  # noqa: E402
from intent_compiler import MODEL_CALL_DEADLINE_ENV  # noqa: E402
from planner_failure import ensure_planner_failure, make_failure, write_planner_failure  # noqa: E402
from workspace_binding import verify_sprint_workspace_authority, workspace_authority_path  # noqa: E402


DEADLINE_MARGIN_SEC = 20


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _existing_status(root: Path) -> tuple[str, list[str]] | None:
    semantic_acceptance = root / "semantic" / "plan_acceptance.json"
    if not semantic_acceptance.is_file():
        return None
    decision = str(_read(semantic_acceptance).get("decision") or "")
    if decision == "direct_response":
        return decision, verify_semantic_planning_chain(root / "semantic")
    execution_acceptance = root / "execution" / "plan_acceptance.json"
    if execution_acceptance.is_file() and _read(execution_acceptance).get("decision") == "accepted":
        return "accepted", verify_frozen_execution_chain(root / "semantic", root / "execution")
    return decision or "failed", verify_semantic_planning_chain(root / "semantic")


def _declared_output_paths(canonical: Path) -> tuple[Path, Path]:
    """Return the worker write path and canonical publish path.

    Operatord stages declared outputs that live outside the task-local result
    directory.  The worker must update that stable staged inode; operatord is
    the only component allowed to atomically replace the canonical file after
    successful process exit.
    """
    raw = os.environ.get("SOLAR_OPERATOR_OUTPUT_PUBLISH_MAP_JSON") or "[]"
    try:
        mappings = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("elastic planner output publish map is invalid JSON") from exc
    if not isinstance(mappings, list):
        raise ValueError("elastic planner output publish map must be a list")
    canonical = canonical.expanduser().resolve()
    matches: list[Path] = []
    for item in mappings:
        if not isinstance(item, dict):
            continue
        publish = Path(str(item.get("publish_path") or "")).expanduser().resolve()
        if publish != canonical:
            continue
        write = Path(str(item.get("write_path") or "")).expanduser().resolve()
        if not str(item.get("write_path") or "").strip():
            raise ValueError("elastic planner staged write path is missing")
        matches.append(write)
    if len(matches) > 1:
        raise ValueError("elastic planner output publish map is ambiguous")
    return (matches[0] if matches else canonical), canonical


def run(envelope_path: Path) -> int:
    envelope = _read(envelope_path)
    if str(envelope.get("task_type") or "") != "elastic_planning":
        raise ValueError("operator requires task_type=elastic_planning")
    sprint_id = str(envelope.get("sprint_id") or "").strip()
    if not sprint_id:
        raise ValueError("operator envelope is missing sprint_id")
    expected_artifacts = envelope.get("expected_artifacts")
    if not isinstance(expected_artifacts, list) or len(expected_artifacts) != 1:
        raise ValueError("elastic planner requires one exact closeout artifact")
    canonical_result_path = Path(str(expected_artifacts[0] or "")).expanduser().resolve()
    result_path, canonical_result_path = _declared_output_paths(canonical_result_path)
    root = canonical_result_path.parent
    if (
        canonical_result_path.name != "planner_operator_result.json"
        or root.name != "elastic-planner"
        or root.parent.name != sprint_id
    ):
        raise ValueError("elastic planner closeout artifact is not canonical")
    # The persisted closeout contract, not a daemon's possibly stale process
    # environment, identifies the authoritative sprint root.
    sprints_dir = root.parent.parent
    requirement = sprints_dir / f"{sprint_id}.requirement_ir.json"
    raw_intent = sprints_dir / f"{sprint_id}.raw_intent.json"
    intent_ir = sprints_dir / f"{sprint_id}.intent_ir.json"
    authority_path = workspace_authority_path(sprints_dir, sprint_id)
    pm_result = Path(str(envelope.get("result_path") or "")).expanduser().resolve()
    if not requirement.is_file():
        raise FileNotFoundError(f"bound RequirementIR is missing: {requirement}")
    binding_harness_dir = Path(
        os.environ.get("SOLAR_WORKSPACE_BINDING_HARNESS_DIR") or HARNESS_DIR
    )
    workspace_authority = verify_sprint_workspace_authority(
        authority_path,
        sprints_dir=sprints_dir,
        harness_dir=binding_harness_dir,
        require_active_binding=False,
    )
    root.mkdir(parents=True, exist_ok=True)

    existing = _existing_status(root)
    if existing is None:
        command = [
            sys.executable,
            str(HARNESS_DIR / "tools" / "elastic_plan.py"),
            "--requirement-ir",
            str(requirement),
            "--output-root",
            str(root),
            "--sprint-id",
            sprint_id,
            "--workspace-root",
            str(Path(str(envelope.get("work_dir") or sprints_dir / sprint_id / "workdir")).expanduser().resolve()),
            "--context-artifact",
            f"raw_intent={raw_intent}",
            "--context-artifact",
            f"intent_ir={intent_ir}",
            "--context-artifact",
            f"workspace_authority={authority_path}",
        ]
        timeout = max(1, int(os.environ.get("SOLAR_ELASTIC_PLANNER_OPERATOR_TIMEOUT_SEC", "600") or "600"))
        env = os.environ.copy()
        env.setdefault("SOLAR_PLANNER_MAX_REPAIRS", "2")
        if not str(env.get(MODEL_CALL_DEADLINE_ENV) or "").strip():
            margin = min(DEADLINE_MARGIN_SEC, max(1, timeout // 10))
            env[MODEL_CALL_DEADLINE_ENV] = (
                f"{time.time() + max(1, timeout - margin):.0f}"
            )
        try:
            proc = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            ensure_planner_failure(
                root,
                fallback_stage="operator",
                fallback_code="operator_timeout",
                fallback_detail=(
                    f"Planner subprocess exceeded the {timeout}s operator timeout."
                ),
            )
            raise RuntimeError(f"elastic_plan_failed:timeout:{timeout}") from exc
        if proc.returncode != 0:
            failure = ensure_planner_failure(
                root,
                fallback_stage="operator",
                fallback_code=f"planner_exit_{proc.returncode}",
                fallback_detail=(proc.stderr or proc.stdout)[-2000:],
            )
            raise RuntimeError(
                f"elastic_plan_failed:{failure['stage']}:{failure['code']}"
            )
        existing = _existing_status(root)
    if existing is None:
        write_planner_failure(
            root,
            make_failure(
                stage="acceptance",
                code="elastic_plan_completed_without_acceptance",
            ),
        )
        raise RuntimeError("elastic_plan_completed_without_acceptance")
    status, errors = existing
    if status not in {"direct_response", "accepted"} or errors:
        failure = ensure_planner_failure(
            root,
            fallback_stage="chain_verification" if errors else "acceptance",
            fallback_code=errors[0] if errors else status,
            fallback_detail=",".join(errors),
        )
        raise RuntimeError(
            f"elastic_plan_not_admitted:{failure['stage']}:{failure['code']}"
        )
    payload = {
        "schema_version": RESULT_SCHEMA,
        "artifact_role": "operator_result",
        "task_id": str(envelope.get("task_id") or ""),
        "sprint_id": sprint_id,
        "status": status,
        "requirement_ir_ref": {"path": str(requirement), "sha256": _sha(requirement)},
        "workspace_authority_ref": {
            "path": str(authority_path),
            "sha256": _sha(authority_path),
            "workspace_root": workspace_authority["workspace_root"],
        },
        "output_root": str(root),
        "verification_errors": errors,
        "completed_at": _now(),
    }
    _atomic_text(result_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    _atomic_text(
        pm_result,
        f"Elastic Planner authored and verified a {status} result.\n\nOperator result: `{result_path}`\n",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.envelope.expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())

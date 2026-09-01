#!/usr/bin/env python3
"""Durable, path-safe binding between a cockpit and its user workspace.

Dashboard intake runs from the installed harness directory, while the cockpit
panes run from the directory supplied to ``solar-harness start``.  Without a
durable binding, RawIntent records the installed runtime as the repository and
verified outputs cannot be published back to the user's project safely.

The binding is intentionally small and local: it records one resolved existing
directory under ``<harness>/run``.  A sprint may use it only when its own
system-captured repo context agrees, preventing an old or foreign sprint from
publishing into the currently active project.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "solar.workspace_binding.v1"
AUTHORITY_SCHEMA = "solar.workspace_authority.v1"
BINDING_FILENAME = "workspace-binding.json"
SAFE_SPRINT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _existing_directory(value: os.PathLike[str] | str | None) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        path = Path(text).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return path if path.is_dir() else None


def binding_path(harness_dir: os.PathLike[str] | str) -> Path:
    return Path(harness_dir).expanduser() / "run" / BINDING_FILENAME


def bind_active_workspace(
    harness_dir: os.PathLike[str] | str,
    workspace_root: os.PathLike[str] | str,
    *,
    source: str = "harness_start",
) -> Path:
    """Atomically bind an existing directory as the cockpit's active workspace."""
    harness = _existing_directory(harness_dir)
    workspace = _existing_directory(workspace_root)
    if harness is None:
        raise ValueError(f"harness directory does not exist: {harness_dir}")
    if workspace is None:
        raise ValueError(f"workspace directory does not exist: {workspace_root}")

    target = binding_path(harness)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "workspace_root": str(workspace),
        "source": str(source or "harness_start"),
        "updated_at": _utc_now(),
    }
    fd, temporary = tempfile.mkstemp(prefix=f".{BINDING_FILENAME}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
    return workspace


def read_active_workspace(harness_dir: os.PathLike[str] | str) -> Path | None:
    """Return the validated active workspace, or ``None`` for stale/bad state."""
    try:
        payload = json.loads(binding_path(harness_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    return _existing_directory(payload.get("workspace_root"))


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def workspace_authority_path(
    sprints_dir: os.PathLike[str] | str,
    sprint_id: str,
) -> Path:
    sid = str(sprint_id or "").strip()
    if not SAFE_SPRINT_ID.fullmatch(sid):
        raise ValueError("invalid sprint id")
    return Path(sprints_dir).expanduser().resolve() / f"{sid}.workspace_authority.json"


def _canonical_input_paths(sprints_dir: Path, sprint_id: str) -> dict[str, Path]:
    return {
        "raw_intent": (sprints_dir / f"{sprint_id}.raw_intent.json").resolve(),
        "intent_ir": (sprints_dir / f"{sprint_id}.intent_ir.json").resolve(),
        "requirement_ir": (sprints_dir / f"{sprint_id}.requirement_ir.json").resolve(),
    }


def freeze_sprint_workspace_authority(
    sprints_dir: os.PathLike[str] | str,
    sprint_id: str,
    *,
    harness_dir: os.PathLike[str] | str,
    captured_cwd: os.PathLike[str] | str | None = None,
) -> Path:
    """Freeze the exact compiler inputs and user-workspace publication authority.

    The active binding remains the controller authority. RawIntent may confirm
    it, but neither a model-authored field nor the process cwd can redirect
    publication. A cwd outside the workspace is recorded for audit and
    normalized to the workspace root for execution.
    """
    sid = str(sprint_id or "").strip()
    if not SAFE_SPRINT_ID.fullmatch(sid):
        raise ValueError("invalid sprint id")
    root = Path(sprints_dir).expanduser().resolve()
    workspace = sprint_workspace_root(root, sid, harness_dir=harness_dir)
    if workspace is None:
        raise ValueError("active workspace binding does not match sprint source context")
    inputs = _canonical_input_paths(root, sid)
    missing = [name for name, path in inputs.items() if not path.is_file()]
    if missing:
        raise ValueError(f"canonical sprint inputs missing: {','.join(missing)}")

    raw = _read_json_object(inputs["raw_intent"])
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    captured_text = str(captured_cwd or context.get("cwd") or workspace).strip()
    captured = _existing_directory(captured_text)
    normalized = True
    effective_relative = "."
    if captured is not None:
        try:
            effective_relative = str(captured.relative_to(workspace)) or "."
            normalized = False
        except ValueError:
            effective_relative = "."
    target = workspace_authority_path(root, sid)
    payload = {
        "schema_version": AUTHORITY_SCHEMA,
        "artifact_role": "controller_frozen_authority",
        "authority_id": f"workspace-authority-{sid}",
        "path": str(target),
        "sprint_id": sid,
        "workspace_root": str(workspace),
        "cwd": {
            "captured": captured_text,
            "effective_relative": effective_relative,
            "normalized_to_workspace": normalized,
        },
        "inputs": {
            name: {"path": str(path), "sha256": _sha256(path)}
            for name, path in inputs.items()
        },
        "created_at": _utc_now(),
    }
    if target.exists():
        existing = verify_sprint_workspace_authority(
            target,
            sprints_dir=root,
            harness_dir=harness_dir,
        )
        stable_fields = (
            "authority_id",
            "path",
            "sprint_id",
            "workspace_root",
            "cwd",
            "inputs",
        )
        if any(existing.get(field) != payload.get(field) for field in stable_fields):
            raise ValueError("workspace authority conflicts with existing frozen authority")
        return target
    _atomic_json(target, payload)
    return target


def verify_sprint_workspace_authority(
    authority_path: os.PathLike[str] | str,
    *,
    sprints_dir: os.PathLike[str] | str,
    harness_dir: os.PathLike[str] | str,
    require_active_binding: bool = True,
) -> dict[str, Any]:
    """Verify canonical location and every frozen input hash.

    The active binding is an intake-time selector, not durable per-sprint
    authority. Long-running/overlapping sprints may therefore verify their
    already-frozen authority with ``require_active_binding=False`` without a
    later dashboard selection redirecting their destination.
    """
    root = Path(sprints_dir).expanduser().resolve()
    path = Path(authority_path).expanduser().resolve()
    payload = _read_json_object(path)
    sid = str(payload.get("sprint_id") or "")
    if payload.get("schema_version") != AUTHORITY_SCHEMA or not SAFE_SPRINT_ID.fullmatch(sid):
        raise ValueError("workspace authority schema or sprint id is invalid")
    if path != workspace_authority_path(root, sid):
        raise ValueError("workspace authority path is not canonical")
    if str(payload.get("path") or "") != str(path):
        raise ValueError("workspace authority self path is not canonical")
    if str(payload.get("authority_id") or "") != f"workspace-authority-{sid}":
        raise ValueError("workspace authority id is invalid")
    workspace = _existing_directory(payload.get("workspace_root"))
    if workspace is None:
        raise ValueError("workspace authority root is unavailable")
    if require_active_binding:
        active_workspace = sprint_workspace_root(root, sid, harness_dir=harness_dir)
        if active_workspace is None or active_workspace != workspace:
            raise ValueError("workspace authority does not match active workspace binding")
    expected_inputs = _canonical_input_paths(root, sid)
    declared_inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    for name, expected_path in expected_inputs.items():
        row = declared_inputs.get(name) if isinstance(declared_inputs.get(name), dict) else {}
        if Path(str(row.get("path") or "")).expanduser().resolve() != expected_path:
            raise ValueError(f"workspace authority input path mismatch: {name}")
        if not expected_path.is_file() or str(row.get("sha256") or "") != _sha256(expected_path):
            raise ValueError(f"workspace authority input hash mismatch: {name}")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), dict) else {}
    relative = str(cwd.get("effective_relative") or "")
    effective = (workspace / relative).resolve()
    try:
        effective.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("workspace authority effective cwd escapes workspace") from exc
    return payload


def _sprint_workspace_candidates(sprints_dir: Path, sid: str) -> list[Path]:
    candidates: list[Path] = []
    raw = _read_json_object(sprints_dir / f"{sid}.raw_intent.json")
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    raw_repo = _existing_directory(context.get("repo"))
    if raw_repo is not None:
        candidates.append(raw_repo)

    requirement = _read_json_object(sprints_dir / f"{sid}.requirement_ir.json")
    source_inputs = (
        requirement.get("source_inputs")
        if isinstance(requirement.get("source_inputs"), dict)
        else {}
    )
    explicit = _existing_directory(source_inputs.get("workspace_root"))
    if explicit is not None and explicit not in candidates:
        candidates.append(explicit)
    repo_context = source_inputs.get("repo_context") or []
    if isinstance(repo_context, str):
        repo_context = [repo_context]
    for value in repo_context:
        candidate = _existing_directory(value)
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def sprint_workspace_root(
    sprints_dir: os.PathLike[str] | str,
    sid: str,
    *,
    harness_dir: os.PathLike[str] | str | None = None,
) -> Path | None:
    """Resolve the user workspace a sprint is authorized to publish into.

    When ``harness_dir`` is provided (the production path), both authorities
    must agree: the active cockpit binding and the sprint's captured context.
    This rejects stale fixtures whose historical intake incorrectly recorded
    the installed harness as the repo.  The no-``harness_dir`` form is useful
    for inspecting a self-contained sprint archive.
    """
    sid = str(sid or "").strip()
    if not SAFE_SPRINT_ID.fullmatch(sid):
        return None
    candidates = _sprint_workspace_candidates(Path(sprints_dir), sid)
    if harness_dir is None:
        return candidates[0] if candidates else None
    active = read_active_workspace(harness_dir)
    if active is None or active not in candidates:
        return None
    return active


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workspace_binding.py")
    sub = parser.add_subparsers(dest="command", required=True)
    bind = sub.add_parser("bind")
    bind.add_argument("--harness-dir", required=True)
    bind.add_argument("--workspace-root", required=True)
    bind.add_argument("--source", default="harness_start")
    bind.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("--harness-dir", required=True)
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "bind":
            workspace = bind_active_workspace(
                args.harness_dir,
                args.workspace_root,
                source=args.source,
            )
        else:
            workspace = read_active_workspace(args.harness_dir)
            if workspace is None:
                if args.json:
                    print(json.dumps({"ok": False, "workspace_root": ""}))
                return 1
    except ValueError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "workspace_root": str(workspace)}))
    else:
        print(workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "solar.workspace_binding.v1"
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

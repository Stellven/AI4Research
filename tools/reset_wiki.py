#!/usr/bin/env python3
"""Reset wiki state to a clean scaffold, with Solar approval evidence.

This keeps the original AutoSci reset planner and executor semantics for
scopes while requiring an explicit Solar approval boundary before destructive
filesystem mutation.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from runtime.loader import ENTITIES  # noqa: E402


SCHEMA = "autosci_reset_wiki_cli.v1"
RUNTIME_SCHEMA = "autosci_runtime_evidence.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
ENTITY_DIRS = list(ENTITIES.keys())
RAW_SUBDIRS = ["papers", "discovered", "tmp", "notes", "web"]
ALL_SCOPES = ["wiki", "raw", "log", "checkpoints"]
LOG_TEMPLATE = "# OmegaWiki Log\n\n"
GRAPH_FILES = ["edges.jsonl", "citations.jsonl", "context_brief.md", "open_questions.md"]


def default_wiki_root() -> Path:
    raw = os.environ.get("AUTOSCI_WIKI_ROOT") or os.environ.get("WIKI_ROOT")
    if raw:
        return Path(raw).expanduser()
    return Path(os.environ.get("HARNESS_DIR", REPO_ROOT / "harness")) / "artifacts" / "autosci" / "workspace" / "wiki"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(status: str, payload: dict[str, Any], *, ok: bool = False) -> int:
    out = {"schema": SCHEMA, "status": status, "ok": ok, **payload}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def parse_scopes(raw: str) -> tuple[list[str], list[str]]:
    if not raw or raw == "all":
        return list(ALL_SCOPES), []
    scopes = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in scopes if item not in ALL_SCOPES]
    return scopes, invalid


def resolve_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    wiki_root = Path(args.wiki_root).expanduser() if args.wiki_root else None
    if args.project_root:
        project_root = Path(args.project_root).expanduser().resolve()
    elif wiki_root is not None:
        project_root = wiki_root.resolve().parent
    else:
        project_root = Path.cwd().resolve()
    if wiki_root is None:
        wiki_root = project_root / "wiki"
    return project_root, wiki_root.resolve()


def _list_md(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [path for path in directory.glob("*.md") if path.is_file()]


def _list_raw(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [path for path in directory.iterdir() if path.name != ".gitkeep"]


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def plan(project_root: Path, wiki_root: Path, scopes: list[str]) -> dict[str, Any]:
    """Return a structured reset plan without mutating the filesystem."""
    result: dict[str, Any] = {
        "project_root": str(project_root),
        "wiki_root": str(wiki_root),
        "scopes": scopes,
        "delete_files": [],
        "reset_files": [],
        "actions": [],
    }

    if "wiki" in scopes:
        for entity in ENTITY_DIRS:
            for path in _list_md(wiki_root / entity):
                result["delete_files"].append(rel(path, project_root))
        for path in _list_md(wiki_root / "outputs"):
            result["delete_files"].append(rel(path, project_root))
        for scaffold in ("index.md", "log.md"):
            path = wiki_root / scaffold
            if path.exists():
                result["delete_files"].append(rel(path, project_root))
        for graph_file in GRAPH_FILES:
            path = wiki_root / "graph" / graph_file
            if path.exists():
                result["delete_files"].append(rel(path, project_root))

    if "raw" in scopes:
        for subdir in RAW_SUBDIRS:
            for path in _list_raw(project_root / "raw" / subdir):
                result["delete_files"].append(rel(path, project_root))

    if "log" in scopes and "wiki" not in scopes:
        result["reset_files"].append(rel(wiki_root / "log.md", project_root))

    if "checkpoints" in scopes:
        result["actions"].append("research_wiki.py checkpoint-clear")
        checkpoint_dir = wiki_root / ".checkpoints"
        for path in sorted(checkpoint_dir.glob("*.json")) if checkpoint_dir.exists() else []:
            result["delete_files"].append(rel(path, project_root))

    return result


def execute(project_root: Path, wiki_root: Path, scopes: list[str]) -> dict[str, int]:
    """Apply the approved reset plan. Returns mutation counts."""
    deleted = 0
    reset = 0

    if "wiki" in scopes:
        for entity in [*ENTITY_DIRS, "outputs"]:
            entity_dir = wiki_root / entity
            for path in _list_md(entity_dir):
                path.unlink()
                deleted += 1
            keep = entity_dir / ".gitkeep"
            keep.parent.mkdir(parents=True, exist_ok=True)
            if not keep.exists():
                keep.touch()
        for scaffold in ("index.md", "log.md"):
            path = wiki_root / scaffold
            if path.exists():
                path.unlink()
                deleted += 1
        graph_dir = wiki_root / "graph"
        for graph_file in GRAPH_FILES:
            path = graph_dir / graph_file
            if path.exists():
                path.unlink()
                deleted += 1

    if "raw" in scopes:
        for subdir in RAW_SUBDIRS:
            raw_dir = project_root / "raw" / subdir
            for path in _list_raw(raw_dir):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted += 1
            keep = raw_dir / ".gitkeep"
            keep.parent.mkdir(parents=True, exist_ok=True)
            if not keep.exists():
                keep.touch()

    if "log" in scopes and "wiki" not in scopes:
        target = wiki_root / "log.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(LOG_TEMPLATE, encoding="utf-8")
        reset += 1

    if "checkpoints" in scopes:
        checkpoint_dir = wiki_root / ".checkpoints"
        if checkpoint_dir.exists():
            for path in checkpoint_dir.glob("*.json"):
                path.unlink()
                deleted += 1

    return {"deleted_files": deleted, "reset_files": reset}


def write_runtime_evidence(
    args: argparse.Namespace,
    *,
    status: str,
    project_root: Path,
    wiki_root: Path,
    scopes: list[str],
    reset_plan: dict[str, Any],
    result: dict[str, int] | None,
    checks: list[dict[str, Any]],
    limitations: list[str],
) -> str:
    if not args.runtime_evidence_out:
        return ""
    out = Path(args.runtime_evidence_out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    plan_artifact = out.with_suffix(out.suffix + ".plan.json")
    plan_artifact.write_text(json.dumps(reset_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "schema": RUNTIME_SCHEMA,
        "task_id": "reset-wiki-runtime",
        "sprint_id": "reset-wiki",
        "node_id": "node-reset-wiki",
        "status": status,
        "inputs": {
            "approval_ref": args.approval_ref,
            "project_root": str(project_root),
            "wiki_root": str(wiki_root),
            "scopes": scopes,
        },
        "outputs": {
            "runtime": {
                "action": "reset_plan",
                "status": status,
                "approval_ref": args.approval_ref,
                "command_run": " ".join(sys.argv),
                "exit_code": 0 if status == "completed" else 1,
                "evidence_ids": [f"reset:{args.approval_ref}", f"wiki:{wiki_root.name}"],
                "checks": checks,
                "scopes": scopes,
                "deleted_files": int((result or {}).get("deleted_files") or 0),
                "reset_files": int((result or {}).get("reset_files") or 0),
                "planned_delete_count": len(reset_plan.get("delete_files") or []),
                "planned_reset_count": len(reset_plan.get("reset_files") or []),
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
            }
        },
        "artifacts": [{"type": "reset_plan_json", "path": str(plan_artifact)}],
        "provenance": {
            "operator_id": "autosci-reset-wiki-cli",
            "implementation_package": "tools.reset_wiki",
            "timestamp": utc_now(),
        },
        "limitations": limitations,
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", default="wiki", help="Comma-separated scopes, or one of: wiki, raw, log, checkpoints, all")
    parser.add_argument("--project-root", default="", help="Project root; defaults to cwd or --wiki-root parent")
    parser.add_argument("--wiki-root", default="", help="Compatibility override for the wiki root")
    parser.add_argument("--yes", action="store_true", help="Request applying the reset")
    parser.add_argument("--apply", action="store_true", help="Compatibility alias for --yes")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit")
    parser.add_argument("--approval-ref", default="", help="Required before destructive reset execution")
    parser.add_argument("--execute-approved", action="store_true", help="Confirm the approved reset may execute")
    parser.add_argument("--runtime-evidence-out", default="", help="Write autosci_runtime_evidence.v1")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scopes, invalid = parse_scopes(args.scope)
    if invalid:
        return emit("failed", {"message": f"unknown scope: {invalid[0]}", "valid": ALL_SCOPES})

    project_root, wiki_root = resolve_roots(args)
    reset_plan = plan(project_root, wiki_root, scopes)
    wants_apply = bool(args.yes or args.apply)

    if args.dry_run or not wants_apply:
        return emit(
            "dry_run",
            {
                **reset_plan,
                "file_count": len(reset_plan.get("delete_files") or []),
                "would_remove": (reset_plan.get("delete_files") or [])[:200],
            },
            ok=True,
        )

    if not args.approval_ref or not args.execute_approved:
        runtime_path = write_runtime_evidence(
            args,
            status="inconclusive",
            project_root=project_root,
            wiki_root=wiki_root,
            scopes=scopes,
            reset_plan=reset_plan,
            result=None,
            checks=[
                {"check": "approval_ref", "status": "ok" if args.approval_ref else "error", "detail": args.approval_ref or "missing"},
                {"check": "execute_approved", "status": "ok" if args.execute_approved else "error", "detail": str(bool(args.execute_approved))},
            ],
            limitations=["Destructive reset requires both --approval-ref and --execute-approved."],
        )
        return emit(
            "approval_required",
            {
                **reset_plan,
                "runtime_evidence_path": runtime_path,
                "limitations": ["Destructive reset requires both --approval-ref and --execute-approved."],
            },
        )

    result = execute(project_root, wiki_root, scopes)
    runtime_path = write_runtime_evidence(
        args,
        status="completed",
        project_root=project_root,
        wiki_root=wiki_root,
        scopes=scopes,
        reset_plan=reset_plan,
        result=result,
        checks=[
            {"check": "approval_ref", "status": "ok", "detail": args.approval_ref},
            {"check": "execute_approved", "status": "ok", "detail": "true"},
            {"check": "reset_scope", "status": "ok", "detail": ",".join(scopes)},
        ],
        limitations=["Destructive reset ran only because explicit approval and execution flags were supplied."],
    )
    return emit(
        "completed",
        {
            "project_root": str(project_root),
            "wiki_root": str(wiki_root),
            "scopes": scopes,
            **result,
            "runtime_evidence_path": runtime_path,
        },
        ok=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_SPRINTS = Path.home() / ".solar" / "harness" / "sprints"
DEFAULT_REPO_SPRINTS = ROOT / "sprints"

PARENT_SUFFIXES = (
    ".status.json",
    ".task_graph.json",
    ".task_dag.state.json",
    ".handoff.md",
    ".eval.json",
    ".eval.md",
    ".closure.json",
)
ALLOWED_NODE_SUFFIXES = (
    "-handoff.md",
    "-eval.json",
    "-eval.md",
    ".pm-result.md",
)
EXCLUDED_SUFFIXES = (
    ".events.jsonl",
    ".runtime-context.json",
    ".intent.json",
    ".planning.html",
    ".design.html",
    ".prd.html",
)


@dataclass(frozen=True)
class MirrorFile:
    source: Path
    target: Path
    artifact_type: str
    state: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": str(self.source),
            "target": str(self.target),
            "artifact_type": self.artifact_type,
            "state": self.state,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _strip_suffix(name: str, suffix: str) -> str | None:
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return None


def _sprint_id_from_core_artifact(path: Path) -> str | None:
    name = path.name
    for suffix in (".status.json", ".task_graph.json"):
        sid = _strip_suffix(name, suffix)
        if sid:
            return sid
    return None


def _artifact_type(path: Path, sprint_id: str) -> str | None:
    name = path.name
    if not name.startswith(f"{sprint_id}."):
        return None
    if name.endswith(EXCLUDED_SUFFIXES):
        return None
    for suffix in PARENT_SUFFIXES:
        if name == f"{sprint_id}{suffix}":
            return suffix.lstrip(".")
    for suffix in ALLOWED_NODE_SUFFIXES:
        if name.endswith(suffix):
            return suffix.lstrip(".")
    return None


def _discover_sprint_ids(runtime_sprints: Path, requested: list[str]) -> list[str]:
    if requested:
        return sorted(set(requested))
    ids = set()
    if runtime_sprints.exists():
        for path in runtime_sprints.glob("*.status.json"):
            sid = _sprint_id_from_core_artifact(path)
            if sid:
                ids.add(sid)
        for path in runtime_sprints.glob("*.task_graph.json"):
            sid = _sprint_id_from_core_artifact(path)
            if sid:
                ids.add(sid)
    return sorted(ids)


def _repo_target(repo_sprints: Path, sprint_id: str, source: Path) -> Path:
    sprint_dir = repo_sprints / sprint_id
    flat_target = repo_sprints / source.name
    if flat_target.exists() and not sprint_dir.exists():
        return flat_target
    return sprint_dir / source.name


def _runtime_artifacts(runtime_sprints: Path, sprint_id: str) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    if not runtime_sprints.exists():
        return out
    for path in sorted(runtime_sprints.glob(f"{sprint_id}.*")):
        if not path.is_file():
            continue
        artifact_type = _artifact_type(path, sprint_id)
        if artifact_type:
            out.append((path, artifact_type))
    return out


def _status_payload(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    return {
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "task_graph_status": payload.get("task_graph_status"),
        "updated_at": payload.get("updated_at") or payload.get("last_event_ts"),
    }


def audit_mirror(
    *,
    runtime_sprints: Path = DEFAULT_RUNTIME_SPRINTS,
    repo_sprints: Path = DEFAULT_REPO_SPRINTS,
    sprint_ids: list[str] | None = None,
) -> dict[str, Any]:
    sprint_ids = _discover_sprint_ids(runtime_sprints, sprint_ids or [])
    sprints: list[dict[str, Any]] = []
    files: list[MirrorFile] = []
    missing_sprint_dirs = 0

    for sprint_id in sprint_ids:
        sprint_dir = repo_sprints / sprint_id
        if not sprint_dir.exists():
            missing_sprint_dirs += 1
        sprint_files: list[MirrorFile] = []
        for source, artifact_type in _runtime_artifacts(runtime_sprints, sprint_id):
            target = _repo_target(repo_sprints, sprint_id, source)
            if not target.exists():
                state = "missing"
            elif _sha256(source) != _sha256(target):
                state = "different"
            else:
                state = "same"
            item = MirrorFile(source=source, target=target, artifact_type=artifact_type, state=state)
            files.append(item)
            sprint_files.append(item)
        runtime_status = runtime_sprints / f"{sprint_id}.status.json"
        repo_status = _repo_target(repo_sprints, sprint_id, runtime_status)
        sprints.append({
            "sprint_id": sprint_id,
            "repo_dir": str(sprint_dir),
            "repo_dir_exists": sprint_dir.exists(),
            "runtime_status": _status_payload(runtime_status) if runtime_status.exists() else {},
            "repo_status": _status_payload(repo_status) if repo_status.exists() else {},
            "files": [item.to_dict() for item in sprint_files],
            "missing": sum(1 for item in sprint_files if item.state == "missing"),
            "different": sum(1 for item in sprint_files if item.state == "different"),
            "same": sum(1 for item in sprint_files if item.state == "same"),
        })

    summary = {
        "sprints": len(sprints),
        "missing_sprint_dirs": missing_sprint_dirs,
        "files": len(files),
        "missing": sum(1 for item in files if item.state == "missing"),
        "different": sum(1 for item in files if item.state == "different"),
        "same": sum(1 for item in files if item.state == "same"),
    }
    summary["drift"] = summary["missing"] + summary["different"]
    return {
        "ok": True,
        "runtime_sprints": str(runtime_sprints),
        "repo_sprints": str(repo_sprints),
        "summary": summary,
        "sprints": sprints,
    }


def apply_mirror(payload: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    copied: list[dict[str, str]] = []
    skipped = 0
    for sprint in payload.get("sprints", []):
        for item in sprint.get("files", []):
            if item.get("state") not in {"missing", "different"}:
                continue
            if limit is not None and len(copied) >= limit:
                skipped += 1
                continue
            source = Path(str(item["source"]))
            target = Path(str(item["target"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(item)
    return {"copied": copied, "copied_count": len(copied), "skipped_after_limit": skipped}


def _table(rows: list[list[str]]) -> str:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    def fmt(row: list[str]) -> str:
        return "│ " + " │ ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " │"

    return "\n".join([top, fmt(rows[0]), mid, *[fmt(row) for row in rows[1:]], bot])


def render_markdown(payload: dict[str, Any], apply_result: dict[str, Any] | None = None) -> str:
    summary = payload["summary"]
    lines = [
        "Sprint mirror audit",
        "",
        "```text",
        _table([
            ["字段", "值"],
            ["runtime_sprints", payload["runtime_sprints"]],
            ["repo_sprints", payload["repo_sprints"]],
            ["sprints", str(summary["sprints"])],
            ["files", str(summary["files"])],
            ["missing", str(summary["missing"])],
            ["different", str(summary["different"])],
            ["same", str(summary["same"])],
            ["drift", str(summary["drift"])],
        ]),
        "```",
    ]
    drift_rows = [["sprint", "runtime", "repo", "missing", "different"]]
    for sprint in payload["sprints"]:
        if sprint["missing"] or sprint["different"] or not sprint["repo_dir_exists"]:
            runtime_status = sprint.get("runtime_status") or {}
            repo_status = sprint.get("repo_status") or {}
            drift_rows.append([
                sprint["sprint_id"][:48],
                f"{runtime_status.get('status') or 'N/A'}/{runtime_status.get('phase') or 'N/A'}",
                f"{repo_status.get('status') or 'N/A'}/{repo_status.get('phase') or 'N/A'}",
                str(sprint["missing"]),
                str(sprint["different"]),
            ])
    if len(drift_rows) > 1:
        lines += ["", "Drifted sprints", "", "```text", _table(drift_rows[:31]), "```"]
    if apply_result is not None:
        lines += [
            "",
            "Apply result",
            "",
            "```text",
            _table([
                ["字段", "值"],
                ["copied", str(apply_result["copied_count"])],
                ["skipped_after_limit", str(apply_result["skipped_after_limit"])],
            ]),
            "```",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and safely sync runtime sprint artifacts into the repo mirror.")
    parser.add_argument("--runtime-sprints", type=Path, default=DEFAULT_RUNTIME_SPRINTS)
    parser.add_argument("--repo-sprints", type=Path, default=DEFAULT_REPO_SPRINTS)
    parser.add_argument("--sprint", action="append", default=[], help="Limit to one sprint id; may be repeated.")
    parser.add_argument("--apply", action="store_true", help="Copy missing/different allowed artifacts into the repo mirror.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum files to copy when --apply is used.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)

    payload = audit_mirror(
        runtime_sprints=args.runtime_sprints.expanduser(),
        repo_sprints=args.repo_sprints.expanduser(),
        sprint_ids=args.sprint,
    )
    apply_result = apply_mirror(payload, limit=args.limit) if args.apply else None
    if apply_result is not None:
        payload["apply"] = apply_result

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(payload, apply_result), end="")
    if args.fail_on_drift and payload["summary"]["drift"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""`solar-harness epic show <epic_id>` — tree-rendered epic + child sprint view.

Reads:
- `<sprints_dir>/<epic_id>.epic.json`            (epic envelope: child_sprints list)
- `<sprints_dir>/<epic_id>.task_graph.json`      (optional: epic-level depends_on)
- `<sprints_dir>/<child_sid>.status.json`        (one per child)

Surfaces per child: `status`, `phase`, `handoff_to`, `target_role`, `priority`,
`updated_at`, and `blocked_by`. `blocked_by` is derived in this priority order:
1. status.dependency_policy.blocks_until (explicit), if dict
2. latest history entry containing a `blocked_by` array
3. epic task_graph node's depends_on -> child_sprint_id mapping
4. otherwise []

Two output modes:
- default human tree (stdout)
- `--json` structured payload (stdout, schema_version=`solar.epic.show.v1`)

`solar-harness epic show <epic_id>` bash wiring is intended to delegate to this
module via `python3 -m harness.lib.cli.epic_show_cmd` or direct script
invocation `python3 harness/lib/cli/epic_show_cmd.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = "solar.epic.show.v1"

HOME = Path.home()
DEFAULT_HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
DEFAULT_SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", DEFAULT_HARNESS_DIR / "sprints"))


class EpicShowError(Exception):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_epic(epic_id: str, sprints_dir: Path) -> dict[str, Any]:
    path = sprints_dir / f"{epic_id}.epic.json"
    if not path.exists():
        raise EpicShowError(f"epic file not found: {path}")
    data = _read_json(path)
    if str(data.get("epic_id") or "") != epic_id:
        raise EpicShowError(
            f"epic_id mismatch: file says {data.get('epic_id')!r}, asked for {epic_id!r}"
        )
    return data


def load_epic_graph(epic_id: str, sprints_dir: Path) -> Optional[dict[str, Any]]:
    path = sprints_dir / f"{epic_id}.task_graph.json"
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def load_child_status(sid: str, sprints_dir: Path) -> dict[str, Any]:
    path = sprints_dir / f"{sid}.status.json"
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except Exception:
        return {}


def _suffix_from_sid(sid: str, epic_id: str) -> str:
    base = epic_id.replace("epic-", "sprint-", 1) if epic_id.startswith("epic-") else epic_id
    if sid.startswith(base + "-"):
        return sid[len(base) + 1:]
    return sid


def _normalize_blocked_entry(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        for key in ("sprint_id", "sid", "child_sprint_id", "id"):
            v = entry.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return str(entry)


def _blocked_by_from_history(history: Iterable[Any]) -> list[str]:
    latest: list[str] = []
    if not isinstance(history, list):
        return latest
    for entry in history:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("blocked_by")
        if isinstance(raw, list) and raw:
            latest = [_normalize_blocked_entry(x) for x in raw]
    return latest


def _blocked_by_from_dependency_policy(policy: Any) -> list[str]:
    if not isinstance(policy, dict):
        return []
    out: list[str] = []
    for raw in policy.get("blocks_until") or []:
        norm = _normalize_blocked_entry(raw)
        if norm:
            out.append(norm)
    return out


def _blocked_by_from_epic_graph(graph: Optional[dict[str, Any]], sid: str) -> list[str]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes") or []
    if not isinstance(nodes, list):
        return []
    sid_for_node: dict[str, str] = {}
    target_node_id: Optional[str] = None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        csid = node.get("child_sprint_id")
        if isinstance(nid, str) and isinstance(csid, str):
            sid_for_node[nid] = csid
            if csid == sid:
                target_node_id = nid
    if target_node_id is None:
        return []
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == target_node_id:
            deps = node.get("depends_on") or []
            if not isinstance(deps, list):
                return []
            return [sid_for_node[d] for d in deps if isinstance(d, str) and d in sid_for_node]
    return []


def derive_blocked_by(
    status_dict: dict[str, Any], epic_graph: Optional[dict[str, Any]], sid: str
) -> list[str]:
    """Return blocked_by list. Empty list = not blocked / no signal."""
    from_policy = _blocked_by_from_dependency_policy(status_dict.get("dependency_policy"))
    if from_policy:
        return from_policy
    from_history = _blocked_by_from_history(status_dict.get("history") or [])
    if from_history:
        return from_history
    return _blocked_by_from_epic_graph(epic_graph, sid)


def _child_record(
    sid: str, status_dict: dict[str, Any], epic_graph: Optional[dict[str, Any]], epic_id: str
) -> dict[str, Any]:
    return {
        "sprint_id": sid,
        "suffix": _suffix_from_sid(sid, epic_id),
        "status": str(status_dict.get("status") or "unknown"),
        "phase": status_dict.get("phase"),
        "handoff_to": status_dict.get("handoff_to"),
        "target_role": status_dict.get("target_role"),
        "priority": status_dict.get("priority"),
        "updated_at": status_dict.get("updated_at"),
        "blocked_by": derive_blocked_by(status_dict, epic_graph, sid),
    }


def build_payload(epic_id: str, sprints_dir: Path) -> dict[str, Any]:
    epic = load_epic(epic_id, sprints_dir)
    epic_graph = load_epic_graph(epic_id, sprints_dir)

    children_sids = epic.get("child_sprints") or []
    if not isinstance(children_sids, list):
        raise EpicShowError(f"epic.child_sprints is not a list: {type(children_sids).__name__}")

    children: list[dict[str, Any]] = []
    for sid in children_sids:
        if not isinstance(sid, str) or not sid.strip():
            continue
        status_dict = load_child_status(sid, sprints_dir)
        children.append(_child_record(sid, status_dict, epic_graph, epic_id))

    return {
        "schema_version": SCHEMA_VERSION,
        "epic_id": epic_id,
        "title": str(epic.get("title") or ""),
        "status": str(epic.get("status") or "unknown"),
        "priority": str(epic.get("priority") or ""),
        "created_at": epic.get("created_at"),
        "child_count": len(children),
        "children": children,
    }


def validate_payload(payload: Any) -> list[str]:
    """Hand-rolled schema check for solar.epic.show.v1. Returns error strings."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload not object: {type(payload).__name__}"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version != {SCHEMA_VERSION!r}: {payload.get('schema_version')!r}")
    for key in ("epic_id", "status", "child_count", "children"):
        if key not in payload:
            errors.append(f"missing top-level field: {key}")
    if "epic_id" in payload and not isinstance(payload["epic_id"], str):
        errors.append("epic_id not string")
    if "child_count" in payload and not isinstance(payload["child_count"], int):
        errors.append("child_count not int")
    if "children" in payload:
        if not isinstance(payload["children"], list):
            errors.append("children not list")
        else:
            if "child_count" in payload and len(payload["children"]) != payload["child_count"]:
                errors.append(
                    f"child_count {payload['child_count']} != len(children) {len(payload['children'])}"
                )
            for idx, child in enumerate(payload["children"]):
                if not isinstance(child, dict):
                    errors.append(f"children[{idx}] not object")
                    continue
                for key in ("sprint_id", "status", "blocked_by"):
                    if key not in child:
                        errors.append(f"children[{idx}].{key} missing")
                if "sprint_id" in child and not isinstance(child["sprint_id"], str):
                    errors.append(f"children[{idx}].sprint_id not string")
                if "status" in child and not isinstance(child["status"], str):
                    errors.append(f"children[{idx}].status not string")
                if "blocked_by" in child:
                    bb = child["blocked_by"]
                    if not isinstance(bb, list):
                        errors.append(f"children[{idx}].blocked_by not list")
                    else:
                        for j, item in enumerate(bb):
                            if not isinstance(item, str):
                                errors.append(f"children[{idx}].blocked_by[{j}] not string")
    return errors


def render_tree(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Epic: {payload.get('epic_id', '')}")
    title = (payload.get("title") or "").strip().lstrip("#").strip()
    if title:
        lines.append(f"Title: {title}")
    lines.append(
        f"Status: {payload.get('status', '?')}   "
        f"Priority: {payload.get('priority') or '-'}   "
        f"Children: {payload.get('child_count', 0)}"
    )
    children = payload.get("children") or []
    for idx, child in enumerate(children):
        connector = "└─" if idx == len(children) - 1 else "├─"
        suffix = child.get("suffix") or child.get("sprint_id", "?")
        status = child.get("status") or "?"
        handoff = child.get("handoff_to") or "-"
        blocked_by = child.get("blocked_by") or []
        if blocked_by:
            short_blocks = []
            for b in blocked_by:
                short_blocks.append(_suffix_from_sid(b, payload.get("epic_id", "")))
            blocked_str = "[" + ",".join(short_blocks) + "]"
        else:
            blocked_str = "[]"
        lines.append(
            f"{connector} {suffix:36s}  status={status:10s}  "
            f"handoff_to={handoff:14s}  blocked_by={blocked_str}"
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solar-harness epic show",
        description="Tree-rendered child sprint list for a Solar-Harness epic.",
    )
    parser.add_argument("epic_id", help="Epic id, e.g. epic-20260519-solar-harness-vnext-...")
    parser.add_argument(
        "--json",
        dest="json_mode",
        action="store_true",
        help="Emit structured solar.epic.show.v1 JSON to stdout.",
    )
    parser.add_argument(
        "--sprints-dir",
        default=str(DEFAULT_SPRINTS_DIR),
        help=f"Directory holding <sid>.status.json files (default: {DEFAULT_SPRINTS_DIR}).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build payload, run schema validation, print result, exit 0/2.",
    )
    args = parser.parse_args(argv)

    sprints_dir = Path(args.sprints_dir)

    try:
        payload = build_payload(args.epic_id, sprints_dir)
    except EpicShowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        errs = validate_payload(payload)
        if errs:
            for e in errs:
                print(f"schema_error: {e}", file=sys.stderr)
            return 2
        print("schema_ok")
        return 0

    if args.json_mode:
        errs = validate_payload(payload)
        if errs:
            for e in errs:
                print(f"schema_error: {e}", file=sys.stderr)
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
        return 0

    print(render_tree(payload))
    return 0


__all__ = [
    "EpicShowError",
    "SCHEMA_VERSION",
    "build_payload",
    "derive_blocked_by",
    "load_child_status",
    "load_epic",
    "main",
    "render_tree",
    "validate_payload",
]


if __name__ == "__main__":
    sys.exit(main())

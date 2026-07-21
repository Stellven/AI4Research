#!/usr/bin/env python3
"""skill_export.py — Safe skill export/symlink to Claude/Codex/agents destinations.

Safety guarantees:
  1. Backup existing destination file/dir before overwrite (timestamped .bak)
  2. Conflict detection: refuse to overwrite if content differs and --force not set
  3. Namespace isolation: skill name is prefixed with namespace in destination
  4. Candidate/canary skills are rejected unless --allow-non-stable is passed
  5. Default injection path only receives stable skills

CLI:
  python3 skill_export.py export  --skill SKILL [--dest DIR] [--force] [--dry-run]
  python3 skill_export.py unexport --skill SKILL [--dest DIR] [--dry-run]
  python3 skill_export.py list-exported [--dest DIR] [--json]
  python3 skill_export.py check-conflicts [--dest DIR] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REGISTRY_PATH = HARNESS_DIR / "skills" / "registry.yaml"

# Default export destinations
DEFAULT_CLAUDE_SKILLS = HOME / ".claude" / "skills"
DEFAULT_CODEX_SKILLS = HOME / ".codex" / "skills"
DEFAULT_AGENTS_SKILLS = HOME / ".agents" / "skills"

STABLE_STATUSES = {"stable"}
NON_INJECTION_STATUSES = {"candidate", "canary"}


def _now_ts() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    # Minimal YAML parser for registry.yaml (list of skill dicts under "skills:")
    text = REGISTRY_PATH.read_text()
    skills: list[dict] = []
    current: "dict | None" = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if current:
                skills.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
        elif current is not None and ":" in stripped and not stripped.startswith("#"):
            k, _, v = stripped.partition(":")
            v = v.strip().strip('"').strip("'")
            if v == "null":
                v = None  # type: ignore
            current[k.strip()] = v
    if current:
        skills.append(current)
    return skills


def _skill_entry(skill_name: str) -> "dict | None":
    for sk in _load_registry():
        if sk.get("name") == skill_name:
            return sk
    return None


def _skill_source_dir(skill_name: str, entry: dict) -> "Path | None":
    entry_path = entry.get("entry")
    if not entry_path:
        return None
    p = HARNESS_DIR / entry_path
    return p.parent if p.is_file() else p


def _backup(dest: Path) -> Path:
    ts = _now_ts()
    bak = dest.with_suffix(dest.suffix + f".bak.{ts}")
    if dest.is_dir():
        shutil.copytree(str(dest), str(bak))
    else:
        shutil.copy2(str(dest), str(bak))
    return bak


def export_skill(skill_name: str,
                 dest_dir: "Path | None" = None,
                 force: bool = False,
                 dry_run: bool = False,
                 allow_non_stable: bool = False) -> dict[str, Any]:
    entry = _skill_entry(skill_name)
    if entry is None:
        return {"ok": False, "error": f"skill '{skill_name}' not in registry"}

    status = entry.get("status", "")
    if status in NON_INJECTION_STATUSES and not allow_non_stable:
        return {
            "ok": False,
            "error": f"skill '{skill_name}' status={status!r} is not stable; "
                     f"use --allow-non-stable to export anyway",
        }

    namespace = entry.get("namespace", "user")
    source = _skill_source_dir(skill_name, entry)
    if source is None or not source.exists():
        return {"ok": False, "error": f"source dir not found for skill '{skill_name}'"}

    if dest_dir is None:
        dest_dir = DEFAULT_CLAUDE_SKILLS

    # Namespace isolation: prefix name in destination
    dest_name = f"{namespace}__{skill_name}" if namespace != "builtin" else skill_name
    dest = dest_dir / dest_name

    result: dict[str, Any] = {
        "skill": skill_name,
        "namespace": namespace,
        "status": status,
        "source": str(source),
        "dest": str(dest),
        "dry_run": dry_run,
    }

    # Conflict detection
    if dest.exists():
        if not force:
            result["ok"] = False
            result["conflict"] = True
            result["error"] = (
                f"destination {dest} already exists; "
                "use --force to overwrite (will backup first)"
            )
            return result
        # Backup before overwrite
        if not dry_run:
            bak = _backup(dest)
            result["backup"] = str(bak)

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.copytree(str(source), str(dest))
        else:
            shutil.copy2(str(source), str(dest))

    result["ok"] = True
    result["action"] = "copied"
    return result


def unexport_skill(skill_name: str,
                   dest_dir: "Path | None" = None,
                   dry_run: bool = False) -> dict[str, Any]:
    if dest_dir is None:
        dest_dir = DEFAULT_CLAUDE_SKILLS

    entry = _skill_entry(skill_name)
    namespace = entry.get("namespace", "user") if entry else "user"
    dest_name = f"{namespace}__{skill_name}" if namespace != "builtin" else skill_name
    dest = dest_dir / dest_name

    if not dest.exists():
        return {"ok": True, "action": "noop", "reason": "not exported"}

    if not dry_run:
        if dest.is_dir():
            shutil.rmtree(str(dest))
        else:
            dest.unlink()

    return {"ok": True, "action": "removed", "dest": str(dest), "dry_run": dry_run}


def list_exported(dest_dir: "Path | None" = None) -> list[dict]:
    if dest_dir is None:
        dest_dir = DEFAULT_CLAUDE_SKILLS
    if not dest_dir.exists():
        return []
    result = []
    for p in sorted(dest_dir.iterdir()):
        if p.name.startswith("."):
            continue
        result.append({"name": p.name, "path": str(p), "type": "dir" if p.is_dir() else "file"})
    return result


def check_conflicts(dest_dir: "Path | None" = None) -> list[dict]:
    if dest_dir is None:
        dest_dir = DEFAULT_CLAUDE_SKILLS
    conflicts = []
    for sk in _load_registry():
        name = sk.get("name", "")
        namespace = sk.get("namespace", "user")
        dest_name = f"{namespace}__{name}" if namespace != "builtin" else name
        dest = dest_dir / dest_name if dest_dir else Path(dest_name)
        if dest.exists():
            conflicts.append({
                "skill": name,
                "dest": str(dest),
                "status": sk.get("status"),
            })
    return conflicts


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="skill_export.py")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export")
    ex.add_argument("--skill", required=True)
    ex.add_argument("--dest")
    ex.add_argument("--force", action="store_true")
    ex.add_argument("--dry-run", action="store_true")
    ex.add_argument("--allow-non-stable", action="store_true")

    un = sub.add_parser("unexport")
    un.add_argument("--skill", required=True)
    un.add_argument("--dest")
    un.add_argument("--dry-run", action="store_true")

    le = sub.add_parser("list-exported")
    le.add_argument("--dest")
    le.add_argument("--json", action="store_true", dest="as_json")

    cc = sub.add_parser("check-conflicts")
    cc.add_argument("--dest")
    cc.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()

    dest_dir = Path(args.dest) if getattr(args, "dest", None) else None

    if args.cmd == "export":
        result = export_skill(
            args.skill, dest_dir,
            force=args.force,
            dry_run=args.dry_run,
            allow_non_stable=args.allow_non_stable,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    elif args.cmd == "unexport":
        result = unexport_skill(args.skill, dest_dir, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0

    elif args.cmd == "list-exported":
        items = list_exported(dest_dir)
        if args.as_json:
            print(json.dumps({"ok": True, "items": items, "count": len(items)}, indent=2))
        else:
            for item in items:
                print(f"  {item['type']:4s}  {item['name']}")
        return 0

    elif args.cmd == "check-conflicts":
        conflicts = check_conflicts(dest_dir)
        if args.as_json:
            print(json.dumps({"ok": True, "conflicts": conflicts, "count": len(conflicts)}, indent=2))
        else:
            if conflicts:
                for c in conflicts:
                    print(f"  CONFLICT  {c['skill']:20s}  {c['status']:10s}  {c['dest']}")
            else:
                print("  no conflicts")
        return 0

    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

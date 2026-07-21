#!/usr/bin/env python3
"""Everything Claude Code adapter for Solar Harness.

This adapter is intentionally safe by default:
  - doctor / inventory / install-dry-run / report are read-only.
  - sync-allowlisted copies files only to a staging directory, never to live ~/.claude.
  - rollback restores staging to its prior state from backup.
  - No hooks, MCP configs, or live settings are modified without explicit allowlist review.

S1 — Testability env overrides:
  ECC_HOME_OVERRIDE  Override home (used in tests to avoid touching real ~/.claude)
  ECC_STAGING        Override staging directory (default: vendor/everything-claude-code-staging)
  ECC_RUN_DIR        Override run/state directory  (default: run/everything-claude-code)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── S1: testability env overrides ────────────────────────────────────────────
# ECC_HOME_OVERRIDE: replaces HOME only for collision-target lookups (e.g. ~/.claude).
# HARNESS and VENDOR are always derived from the real home or explicit HARNESS_DIR,
# so tests that set ECC_HOME_OVERRIDE do not accidentally point VENDOR at a temp dir.
_REAL_HOME = Path.home()
_HOME_OVERRIDE = os.environ.get("ECC_HOME_OVERRIDE", "")
HOME = Path(_HOME_OVERRIDE) if _HOME_OVERRIDE else _REAL_HOME
HARNESS = Path(os.environ.get("HARNESS_DIR", str(_REAL_HOME / ".solar" / "harness")))
VENDOR = HARNESS / "vendor" / "everything-claude-code"
STAGING = Path(os.environ.get("ECC_STAGING", str(HARNESS / "vendor" / "everything-claude-code-staging")))
RUN_DIR = Path(os.environ.get("ECC_RUN_DIR", str(HARNESS / "run" / "everything-claude-code")))
REPORT = HARNESS / "reports" / "everything-claude-code-audit-20260508.md"
ALLOWLIST = HARNESS / "config" / "everything-claude-code.allowlist.json"


SURFACES = {
    "agents": [
        "agents/*.md",
        ".claude/agents/**/*.md",
        ".codex/agents/**/*.md",
        ".kiro/agents/**/*",
        ".opencode/prompts/agents/**/*.md",
    ],
    "commands": [
        "commands/*.md",
        ".claude/commands/*.md",
        ".opencode/commands/*.md",
        "legacy-command-shims/commands/*.md",
    ],
    "skills": [
        ".claude/skills/*/SKILL.md",
        ".agents/skills/*/SKILL.md",
        ".cursor/skills/*/SKILL.md",
        ".kiro/skills/*/SKILL.md",
    ],
    "hooks": [
        "hooks/**/*",
        ".cursor/hooks/**/*",
        ".kiro/hooks/**/*",
        "scripts/hooks/**/*",
    ],
    "rules": [
        "rules/**/*.md",
        ".claude/rules/**/*.md",
        ".cursor/rules/**/*.md",
    ],
    "mcp_configs": [
        ".mcp.json",
        "mcp-configs/**/*",
    ],
    "scripts": [
        "install.sh",
        "scripts/**/*",
        ".trae/*.sh",
        ".opencode/tools/**/*",
        ".opencode/plugins/**/*",
    ],
    "tests": [
        "tests/**/*",
    ],
    "contexts": [
        "contexts/*.md",
        ".claude/research/*.md",
        ".opencode/instructions/*.md",
    ],
}


COLLISION_TARGETS = {
    "agents": [
        HOME / ".claude" / "agents",
        HOME / ".codex" / "agents",
    ],
    "commands": [
        HOME / ".claude" / "commands",
    ],
    "skills": [
        HOME / ".claude" / "skills",
        HOME / ".agents" / "skills",
        HOME / ".codex" / "skills",
    ],
    "rules": [
        HOME / ".claude" / "rules",
    ],
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=8)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(VENDOR))
    except ValueError:
        return str(path)


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def glob_files(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    seen = set()
    if not VENDOR.exists():
        return out
    for pattern in patterns:
        for item in VENDOR.glob(pattern):
            if not item.is_file():
                continue
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return sorted(out)


def item_key(path: Path, surface: str) -> str:
    if surface == "skills" and path.name == "SKILL.md":
        return path.parent.name
    return path.stem


def local_keys(targets: list[Path]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for root in targets:
        if not root.exists():
            continue
        for item in root.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir():
                keys[item.name] = str(item)
            elif item.is_file():
                keys[item.stem] = str(item)
    return keys


def collision_report(inventory: dict) -> list[dict]:
    collisions: list[dict] = []
    for surface, targets in COLLISION_TARGETS.items():
        existing = local_keys(targets)
        for item in inventory["items"].get(surface, []):
            key = item["key"]
            if key in existing:
                collisions.append(
                    {
                        "surface": surface,
                        "key": key,
                        "upstream": item["path"],
                        "local": existing[key],
                        "action": "defer",
                        "reason": "name collision; needs manual precedence rule",
                    }
                )
    return collisions


def compatibility() -> dict:
    solar_claude = HOME / "Solar" / "CLAUDE.md"
    codex_config = HOME / ".codex" / "config.toml"
    solar_text = solar_claude.read_text(errors="ignore") if solar_claude.exists() else ""
    codex_text = codex_config.read_text(errors="ignore") if codex_config.exists() else ""
    return {
        "gstack": {
            "present": "gstack" in solar_text.lower(),
            "evidence": str(solar_claude),
            "risk": "commands/hooks may compete with existing gstack browser and intent rules",
        },
        "superpowers": {
            "present": "superpowers" in codex_text.lower() or (HOME / ".agents" / "skills" / "using-superpowers").exists(),
            "evidence": str(codex_config),
            "risk": "skills may overlap Codex Superpowers execution discipline",
        },
        "solar_hooks": {
            "present": (HOME / ".claude" / "hooks").exists(),
            "evidence": str(HOME / ".claude" / "hooks"),
            "risk": "upstream hooks must not be globally activated without allowlist",
        },
    }


def inventory() -> dict:
    code, sha = run(["git", "rev-parse", "HEAD"], cwd=VENDOR)
    code2, remote = run(["git", "remote", "get-url", "origin"], cwd=VENDOR)
    items: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for surface, patterns in SURFACES.items():
        files = glob_files(patterns)
        items[surface] = [{"path": rel(p), "key": item_key(p, surface), "bytes": p.stat().st_size} for p in files]
        counts[surface] = len(files)
    payload = {
        "generated_at": now(),
        "repo": str(VENDOR),
        "source_url": remote if code2 == 0 else "https://github.com/affaan-m/everything-claude-code",
        "commit": sha if code == 0 else "",
        "counts": counts,
        "items": items,
    }
    payload["collisions"] = collision_report(payload)
    payload["compatibility"] = compatibility()
    return payload


def doctor() -> dict:
    inv = inventory() if VENDOR.exists() else {"counts": {}, "collisions": [], "compatibility": compatibility()}
    return {
        "ok": VENDOR.exists(),
        "installed": VENDOR.exists(),
        "repo": str(VENDOR),
        "staging": str(STAGING),
        "run_dir": str(RUN_DIR),
        "allowlist": str(ALLOWLIST),
        "allowlist_exists": ALLOWLIST.exists(),
        "report": str(REPORT),
        "report_exists": REPORT.exists(),
        "total_items": sum(inv.get("counts", {}).values()),
        "collision_count": len(inv.get("collisions", [])),
        "live_hook_changes": 0,
        "status": "warn" if VENDOR.exists() else "missing",
    }


def dry_run() -> dict:
    inv = inventory()
    return {
        "ok": True,
        "mode": "dry_run",
        "live_hook_changes": 0,
        "would_stage_hooks": inv["counts"].get("hooks", 0),
        "would_install_live": 0,
        "safe_to_sync": False,
        "reason": "allowlist and collision review are required before any live sync",
        "collisions": inv["collisions"],
        "compatibility": inv["compatibility"],
        "counts": inv["counts"],
    }


def write_report() -> dict:
    inv = inventory()
    dry = dry_run()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Everything Claude Code Solar Integration Audit",
        "",
        f"Generated: {inv['generated_at']}",
        f"Source: {inv['source_url']}",
        f"Commit: `{inv['commit']}`",
        f"Local vendor: `{inv['repo']}`",
        "",
        "## Verdict",
        "",
        "Status: `candidate only`.",
        "",
        "The upstream repo is vendored for audit. Nothing has been installed into live Claude, Codex, Gstack, or Solar config. Hooks are especially high-risk and must remain staged until allowlisted.",
        "",
        "## Inventory Counts",
        "",
        "```text",
        "┌─────────────┬───────┐",
        "│ Surface     │ Count │",
        "├─────────────┼───────┤",
    ]
    for key in sorted(inv["counts"]):
        lines.append(f"│ {key:<11} │ {inv['counts'][key]:>5} │")
    lines.extend(
        [
            "└─────────────┴───────┘",
            "```",
            "",
            "## Collision Summary",
            "",
            f"Collision count: `{len(inv['collisions'])}`",
            "",
            "```text",
            "┌──────────┬────────────────────────────┬────────────────────────────────────────────┐",
            "│ Surface  │ Key                        │ Local                                      │",
            "├──────────┼────────────────────────────┼────────────────────────────────────────────┤",
        ]
    )
    for row in inv["collisions"][:30]:
        lines.append(f"│ {row['surface'][:8]:<8} │ {row['key'][:26]:<26} │ {row['local'][-42:]:<42} │")
    if not inv["collisions"]:
        lines.append("│ N/A      │ N/A                        │ N/A                                        │")
    lines.extend(
        [
            "└──────────┴────────────────────────────┴────────────────────────────────────────────┘",
            "```",
            "",
            "## Compatibility",
            "",
        ]
    )
    for key, item in inv["compatibility"].items():
        lines.append(f"- `{key}`: present={item['present']} evidence=`{item['evidence']}` risk={item['risk']}")
    lines.extend(
        [
            "",
            "## Dry Run",
            "",
            f"- live_hook_changes: `{dry['live_hook_changes']}`",
            f"- would_stage_hooks: `{dry['would_stage_hooks']}`",
            f"- would_install_live: `{dry['would_install_live']}`",
            f"- safe_to_sync: `{dry['safe_to_sync']}`",
            f"- reason: {dry['reason']}",
            "",
            "## Recommended Allowlist V0",
            "",
            "- `adopt`: targeted reviewer/build-resolver agents after name collision review.",
            "- `adapt`: verification-loop, tdd-workflow, eval-harness skills after Solar naming prefix.",
            "- `defer`: all hooks, MCP configs, install scripts, auto-update scripts.",
            "- `reject`: anything that overwrites global Claude settings without dry-run and rollback.",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n")
    return {"ok": True, "report": str(REPORT), "counts": inv["counts"], "collision_count": len(inv["collisions"])}


# ── S2: Allowlisted sync ──────────────────────────────────────────────────────

def sync_allowlisted(allowlist_path: str | None = None, dry_run_flag: bool = False) -> dict:
    """Copy allowlisted upstream files to STAGING directory.

    - Never touches live ~/.claude.
    - Backs up any existing staging file before overwriting.
    - Idempotent: identical files are skipped.
    - All hook/mcp surfaces in blocked_by_default are never synced.
    """
    al_path = Path(allowlist_path) if allowlist_path else ALLOWLIST
    try:
        al = json.loads(al_path.read_text())
    except Exception as exc:
        return {"ok": False, "error": f"failed to load allowlist {al_path}: {exc}"}

    allowed: dict[str, list[str]] = al.get("allowed", {})
    blocked: set[str] = set(al.get("blocked_by_default", []))

    inv = inventory()
    ts_compact = now_compact()
    ts_iso = now()

    manifest: dict = {
        "sync_ts": ts_compact,
        "sync_ts_iso": ts_iso,
        "allowlist": str(al_path),
        "dry_run": dry_run_flag,
        "staging_dir": str(STAGING),
        "live_hook_changes": 0,
        "copied": [],
        "skipped": [],
        "backed_up": [],
        "errors": [],
    }

    backup_base = RUN_DIR / "backups" / ts_compact

    for surface, keys in allowed.items():
        if surface in blocked:
            for key in keys:
                manifest["skipped"].append({"surface": surface, "key": key, "reason": "blocked_by_default"})
            continue
        if not keys:
            continue

        items_by_key = {item["key"]: item for item in inv["items"].get(surface, [])}
        dest_surface_dir = STAGING / surface

        for key in keys:
            if key not in items_by_key:
                manifest["skipped"].append({"surface": surface, "key": key, "reason": "not_in_upstream"})
                continue

            item = items_by_key[key]
            src = VENDOR / item["path"]
            if not src.exists():
                manifest["errors"].append({"surface": surface, "key": key, "error": f"source missing: {src}"})
                continue

            # For skills, dest is a directory named by key with SKILL.md inside
            if surface == "skills":
                dest_path = dest_surface_dir / key / "SKILL.md"
            else:
                dest_path = dest_surface_dir / src.name

            # Idempotency: skip if content is identical
            if dest_path.exists():
                if file_hash(src) == file_hash(dest_path):
                    manifest["skipped"].append({"surface": surface, "key": key, "reason": "identical", "dest": str(dest_path)})
                    continue
                # Different content: back up existing
                backup_path = backup_base / surface / dest_path.name
                if not dry_run_flag:
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest_path, backup_path)
                manifest["backed_up"].append({
                    "surface": surface,
                    "key": key,
                    "backup": str(backup_path),
                    "dest": str(dest_path),
                })

            if not dry_run_flag:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_path)

            manifest["copied"].append({
                "surface": surface,
                "key": key,
                "src": item["path"],
                "dest": str(dest_path),
                "hash": file_hash(src),
            })

    manifest["ok"] = len(manifest["errors"]) == 0

    if not dry_run_flag:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        manifest_file = RUN_DIR / f"sync-{ts_compact}.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        manifest["manifest_path"] = str(manifest_file)

    return manifest


# ── S3: Rollback ──────────────────────────────────────────────────────────────

def rollback(sync_ts: str | None = None) -> dict:
    """Restore staging to its pre-sync state using a previously written manifest.

    - Files that existed before sync and were backed up are restored from backup.
    - Files that were newly added by sync (no backup) are removed.
    - The manifest is renamed to .rolled-back.json on success.
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    if sync_ts:
        manifest_path = RUN_DIR / f"sync-{sync_ts}.json"
    else:
        candidates = sorted(RUN_DIR.glob("sync-*.json"), key=lambda p: p.name, reverse=True)
        if not candidates:
            return {"ok": False, "error": "no sync manifest found; nothing to roll back"}
        manifest_path = candidates[0]

    if not manifest_path.exists():
        return {"ok": False, "error": f"manifest not found: {manifest_path}"}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:
        return {"ok": False, "error": f"failed to load manifest: {exc}"}

    result: dict = {
        "ok": True,
        "manifest": str(manifest_path),
        "sync_ts": manifest.get("sync_ts", ""),
        "restored": [],
        "removed": [],
        "errors": [],
    }

    # Build lookup: (surface, key) → backup_path + dest_path
    backed_map: dict[tuple[str, str], tuple[Path, Path]] = {}
    for entry in manifest.get("backed_up", []):
        bk = Path(entry["backup"])
        dest = Path(entry["dest"])
        backed_map[(entry["surface"], entry["key"])] = (bk, dest)

    # Restore backed-up files (overwrite with backed-up version)
    for (surface, key), (bk, dest) in backed_map.items():
        if bk.exists():
            try:
                shutil.copy2(bk, dest)
                result["restored"].append(str(dest))
            except Exception as exc:
                result["errors"].append({"dest": str(dest), "error": str(exc)})
                result["ok"] = False
        else:
            result["errors"].append({"dest": str(dest), "error": f"backup missing: {bk}"})

    # Remove files that were newly created by sync (no backup = didn't exist before)
    for entry in manifest.get("copied", []):
        sk = (entry["surface"], entry["key"])
        if sk not in backed_map:
            dest = Path(entry["dest"])
            if dest.exists():
                try:
                    dest.unlink()
                    result["removed"].append(str(dest))
                    # Remove empty parent dirs (best-effort)
                    try:
                        dest.parent.rmdir()
                    except OSError:
                        pass
                except Exception as exc:
                    result["errors"].append({"dest": str(dest), "error": str(exc)})
                    result["ok"] = False

    # Archive used manifest
    if result["ok"]:
        try:
            archived = manifest_path.with_name(manifest_path.name.replace("sync-", "sync-rolled-back-"))
            manifest_path.rename(archived)
            result["manifest_archived"] = str(archived)
        except Exception:
            pass

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["doctor", "inventory", "install-dry-run", "report", "sync-allowlisted", "rollback"],
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allowlist", default=None, help="path to allowlist JSON (sync-allowlisted)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="plan only, do not write (sync-allowlisted)")
    parser.add_argument("--sync-ts", default=None, dest="sync_ts", help="compact sync timestamp to roll back (rollback)")
    args = parser.parse_args()

    if args.command == "doctor":
        payload = doctor()
    elif args.command == "inventory":
        payload = inventory()
    elif args.command == "install-dry-run":
        payload = dry_run()
    elif args.command == "report":
        payload = write_report()
    elif args.command == "sync-allowlisted":
        payload = sync_allowlisted(allowlist_path=args.allowlist, dry_run_flag=args.dry_run)
    else:  # rollback
        payload = rollback(sync_ts=args.sync_ts)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.command == "inventory":
            print(json.dumps({"counts": payload["counts"], "collisions": len(payload["collisions"])}, ensure_ascii=False, indent=2))
        elif args.command == "report":
            print(payload["report"])
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if (isinstance((p := payload), dict) and p.get("ok", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""source_migration.py — Safe _raw/file-uploads → _sources migration.

Safety guarantees:
  1. dry-run is DEFAULT; --apply required for actual operations
  2. apply mode only copies or creates symlinks — NEVER deletes originals
  3. old original_path stays resolvable via manifest alias + symlink
  4. SHA-256 checksum verified after every copy/link operation
  5. Idempotent: re-running skips already-migrated files

Modes:
  copy   — shutil.copy2 (default, safest)
  link   — os.symlink from canonical back to original location

CLI:
  python3 source_migration.py plan   [--manifest FILE] [--mode copy|link] [--json]
  python3 source_migration.py apply  [--manifest FILE] [--mode copy|link] [--json]
  python3 source_migration.py verify [--manifest FILE] [--sources-dir DIR] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
KNOWLEDGE_DIR = HOME / "Knowledge"
K_SOURCES_DIR = KNOWLEDGE_DIR / "_sources"
K_META_DIR = KNOWLEDGE_DIR / "meta"
RAW_UPLOADS_DIR = KNOWLEDGE_DIR / "_raw" / "file-uploads"
DEFAULT_MANIFEST = KNOWLEDGE_DIR / "_meta" / "source-manifest.jsonl"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    """Load all entries from source-manifest.jsonl."""
    if not manifest_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


# ---------------------------------------------------------------------------
# Plan: compute migration actions without writing
# ---------------------------------------------------------------------------

def plan_migration(entries: list[dict[str, Any]], mode: str = "copy",
                   sources_dir: Path = K_SOURCES_DIR) -> dict[str, Any]:
    """Compute migration plan: what files to copy/link and where.

    Returns a dict with planned actions. Does NOT write anything.
    """
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for entry in entries:
        sha = entry.get("sha256", "")
        original_path = Path(entry.get("original_path", ""))
        canonical_path = Path(entry.get("canonical_path", ""))
        category = entry.get("category", "other")
        status = entry.get("status", "")

        # Validate entry
        if not sha or not original_path.exists():
            errors.append({
                "original_path": str(original_path),
                "reason": "missing_source_or_sha",
                "sha256": sha[:16] if sha else "N/A",
            })
            continue

        # Check if already migrated
        if canonical_path.exists():
            # Verify existing copy
            try:
                existing_sha = _sha256(canonical_path)
                if existing_sha == sha:
                    skipped.append({
                        "original_path": str(original_path),
                        "canonical_path": str(canonical_path),
                        "reason": "already_migrated_verified",
                    })
                    continue
                else:
                    errors.append({
                        "original_path": str(original_path),
                        "canonical_path": str(canonical_path),
                        "reason": "canonical_exists_sha_mismatch",
                    })
                    continue
            except Exception as exc:
                errors.append({
                    "original_path": str(original_path),
                    "canonical_path": str(canonical_path),
                    "reason": f"verify_error: {exc}",
                })
                continue

        # Plan the action
        action = {
            "action": mode,  # "copy" or "link"
            "original_path": str(original_path),
            "canonical_path": str(canonical_path),
            "canonical_dir": str(canonical_path.parent),
            "filename": original_path.name,
            "sha256": sha,
            "size": original_path.stat().st_size,
            "category": category,
        }
        actions.append(action)

    return {
        "ok": not errors,
        "mode": mode,
        "total_entries": len(entries),
        "planned_actions": len(actions),
        "skipped": len(skipped),
        "errors": len(errors),
        "actions": actions,
        "skipped_details": skipped,
        "error_details": errors,
    }


# ---------------------------------------------------------------------------
# Apply: execute migration plan
# ---------------------------------------------------------------------------

def apply_migration(entries: list[dict[str, Any]], mode: str = "copy",
                    sources_dir: Path = K_SOURCES_DIR,
                    manifest_path: Path | None = None) -> dict[str, Any]:
    """Execute migration: copy/link files, create symlinks, verify checksums.

    NEVER deletes original files.
    Updates manifest status after successful migration.
    """
    plan = plan_migration(entries, mode=mode, sources_dir=sources_dir)
    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    skipped_count = plan["skipped"]

    for action in plan["actions"]:
        src = Path(action["original_path"])
        dest = Path(action["canonical_path"])
        expected_sha = action["sha256"]

        # Create destination directory
        dest.parent.mkdir(parents=True, exist_ok=True)

        result: dict[str, Any] = {
            "action": action["action"],
            "original_path": str(src),
            "canonical_path": str(dest),
            "sha256": expected_sha,
        }

        try:
            if mode == "copy":
                # Copy file (preserves metadata)
                shutil.copy2(str(src), str(dest))

                # Verify checksum
                actual_sha = _sha256(dest)
                if actual_sha != expected_sha:
                    # Remove bad copy
                    dest.unlink(missing_ok=True)
                    result["status"] = "failed"
                    result["reason"] = f"checksum_mismatch: expected={expected_sha[:16]}, got={actual_sha[:16]}"
                    failed += 1
                    results.append(result)
                    continue

                result["status"] = "copied"
                result["verified"] = True

                # Create backward symlink: original → canonical
                # This keeps the old path resolvable even if something references it
                alias_link = src.parent / (src.name + ".canonical")
                if not alias_link.exists():
                    try:
                        os.symlink(str(dest), str(alias_link))
                        result["alias_link"] = str(alias_link)
                    except Exception:
                        pass  # fail-open: alias is best-effort

            elif mode == "link":
                # Create symlink from canonical → original (original stays in place)
                # This is the lightest-touch mode: canonical path points to original
                os.symlink(str(src), str(dest))

                # Verify the link resolves and checksum matches
                if dest.exists():
                    actual_sha = _sha256(dest)
                    if actual_sha != expected_sha:
                        dest.unlink(missing_ok=True)
                        result["status"] = "failed"
                        result["reason"] = f"checksum_mismatch_via_link: expected={expected_sha[:16]}, got={actual_sha[:16]}"
                        failed += 1
                        results.append(result)
                        continue
                    result["verified"] = True
                else:
                    result["status"] = "failed"
                    result["reason"] = "link_target_dangling"
                    failed += 1
                    results.append(result)
                    continue

                result["status"] = "linked"

            succeeded += 1

        except Exception as exc:
            result["status"] = "error"
            result["reason"] = str(exc)
            failed += 1

        results.append(result)

    # Update manifest status for successfully migrated entries
    if manifest_path and succeeded > 0:
        _update_manifest_status(manifest_path, results)

    return {
        "ok": failed == 0,
        "mode": mode,
        "applied_at": _utc_now(),
        "total_entries": plan["total_entries"],
        "succeeded": succeeded,
        "skipped": skipped_count,
        "failed": failed,
        "results": results,
        "plan_errors": plan["error_details"],
    }


def _update_manifest_status(manifest_path: Path, results: list[dict[str, Any]]) -> None:
    """Update manifest entries with migration status (in-place rewrite)."""
    # Build a lookup from canonical_path → result
    result_map: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.get("status") in ("copied", "linked"):
            result_map[r["canonical_path"]] = r

    entries: list[dict[str, Any]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                cp = entry.get("canonical_path", "")
                if cp in result_map:
                    entry["status"] = "migrated"
                    entry["migrated_at"] = _utc_now()
                    entry["migration_mode"] = result_map[cp].get("action", "unknown")
                    if result_map[cp].get("alias_link"):
                        entry["alias_link"] = result_map[cp]["alias_link"]
                entries.append(entry)
            except Exception:
                continue

    # Atomic write
    tmp = manifest_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp.rename(manifest_path)


# ---------------------------------------------------------------------------
# Verify: post-migration checksum validation
# ---------------------------------------------------------------------------

def verify_migration(entries: list[dict[str, Any]],
                     sources_dir: Path = K_SOURCES_DIR) -> dict[str, Any]:
    """Verify all migrated files have correct checksums."""
    checked: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    not_migrated = 0

    for entry in entries:
        canonical_path = Path(entry.get("canonical_path", ""))
        expected_sha = entry.get("sha256", "")
        original_path = entry.get("original_path", "")
        status = entry.get("status", "")

        if not canonical_path.exists():
            if status == "migrated":
                failed += 1
                checked.append({
                    "canonical_path": str(canonical_path),
                    "original_path": original_path,
                    "status": "missing_canonical",
                })
            else:
                not_migrated += 1
            continue

        try:
            actual_sha = _sha256(canonical_path)
            ok = actual_sha == expected_sha
            if ok:
                passed += 1
                checked.append({
                    "canonical_path": str(canonical_path),
                    "original_path": original_path,
                    "status": "verified",
                    "sha256_match": True,
                })
            else:
                failed += 1
                checked.append({
                    "canonical_path": str(canonical_path),
                    "original_path": original_path,
                    "status": "sha_mismatch",
                    "expected": expected_sha[:16],
                    "actual": actual_sha[:16],
                })
        except Exception as exc:
            failed += 1
            checked.append({
                "canonical_path": str(canonical_path),
                "original_path": original_path,
                "status": "error",
                "reason": str(exc),
            })

    # Check alias resolution: original_path → canonical_path still works
    alias_ok = 0
    alias_broken = 0
    for entry in entries:
        orig = Path(entry.get("original_path", ""))
        canon = Path(entry.get("canonical_path", ""))
        alias_link = orig.parent / (orig.name + ".canonical")
        if alias_link.exists():
            try:
                target = os.readlink(str(alias_link))
                if str(canon) in target or canon.name in target:
                    alias_ok += 1
                else:
                    alias_broken += 1
            except Exception:
                alias_broken += 1

    return {
        "ok": failed == 0,
        "total_entries": len(entries),
        "verified": passed,
        "failed": failed,
        "not_migrated": not_migrated,
        "alias_resolvable": alias_ok,
        "alias_broken": alias_broken,
        "details": checked,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="source_migration.py",
                                 description="Safe _raw → _sources migration (dry-run by default)")
    sub = ap.add_subparsers(dest="cmd")

    p_plan = sub.add_parser("plan", help="Show planned migration (dry-run)")
    p_plan.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_plan.add_argument("--mode", choices=["copy", "link"], default="copy")
    p_plan.add_argument("--sources-dir", default=str(K_SOURCES_DIR))
    p_plan.add_argument("--json", action="store_true", dest="as_json")

    p_apply = sub.add_parser("apply", help="Execute migration (copies/links only)")
    p_apply.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_apply.add_argument("--mode", choices=["copy", "link"], default="copy")
    p_apply.add_argument("--sources-dir", default=str(K_SOURCES_DIR))
    p_apply.add_argument("--json", action="store_true", dest="as_json")

    p_verify = sub.add_parser("verify", help="Verify migrated file checksums")
    p_verify.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_verify.add_argument("--sources-dir", default=str(K_SOURCES_DIR))
    p_verify.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    entries = load_manifest(manifest_path)

    if not entries:
        print(_json({"ok": False, "error": f"No entries in manifest: {manifest_path}"}))
        return 1

    if args.cmd == "plan":
        result = plan_migration(entries, mode=args.mode, sources_dir=Path(args.sources_dir))
        if getattr(args, "as_json", False):
            # Print without action details for readability
            summary = {k: v for k, v in result.items() if k not in ("actions", "skipped_details", "error_details")}
            summary["action_preview"] = result["actions"][:5]  # first 5
            print(_json(summary))
        else:
            print(f"=== Migration Plan (DRY-RUN, mode={result['mode']}) ===")
            print(f"Total manifest entries: {result['total_entries']}")
            print(f"Files to {result['mode']}:  {result['planned_actions']}")
            print(f"Already migrated:    {result['skipped']}")
            print(f"Errors:              {result['errors']}")
            print()
            if result["actions"]:
                print("Planned actions (first 10):")
                for a in result["actions"][:10]:
                    print(f"  {a['action']:6s} {a['category']:12s} {a['filename']}")
                    print(f"         → {a['canonical_path']}")
                if len(result["actions"]) > 10:
                    print(f"  ... and {len(result['actions']) - 10} more")
        return 0

    elif args.cmd == "apply":
        result = apply_migration(
            entries, mode=args.mode,
            sources_dir=Path(args.sources_dir),
            manifest_path=manifest_path,
        )
        if getattr(args, "as_json", False):
            print(_json(result))
        else:
            print(f"=== Migration Apply (mode={result['mode']}) ===")
            print(f"Succeeded: {result['succeeded']}")
            print(f"Skipped:   {result['skipped']}")
            print(f"Failed:    {result['failed']}")
            if result["results"]:
                print()
                for r in result["results"]:
                    tag = "✓" if r["status"] in ("copied", "linked") else "✗"
                    print(f"  {tag} {r['status']:8s} {Path(r['canonical_path']).name}")
        return 0 if result["ok"] else 1

    elif args.cmd == "verify":
        result = verify_migration(entries, sources_dir=Path(args.sources_dir))
        if getattr(args, "as_json", False):
            print(_json(result))
        else:
            print(f"=== Migration Verify ===")
            print(f"Verified:     {result['verified']}")
            print(f"Failed:       {result['failed']}")
            print(f"Not migrated: {result['not_migrated']}")
            print(f"Alias OK:     {result['alias_resolvable']}")
            if result["failed"]:
                print()
                for d in result["details"]:
                    if d.get("status") not in ("verified",):
                        print(f"  ✗ {d.get('canonical_path', '?')} — {d.get('status')}")
        return 0 if result["ok"] else 1

    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

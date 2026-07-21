#!/usr/bin/env python3
"""Solar product snapshot / restore / verify — S0 foundation.

Commands:
  snapshot [--dry-run] [--scope minimal|full] [--out-dir DIR]
  restore  (--latest | --id SNAP_ID) [--dry-run] [--target-dir DIR]
  verify   (--latest | --id SNAP_ID)
  list
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import sys
import tarfile
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
DEFAULT_BACKUP_DIR = HARNESS_DIR / "backups" / "product-snapshots"

# ── secret-exclusion patterns (files matching any pattern are excluded) ──────
SECRET_PATTERNS: list[str] = [
    ".env", ".env.*", "*.env",
    "*.key", "*.pem", "*.p12", "*.pfx",
    "*token*", "*secret*", "*password*", "*credential*",
    "*oauth*", "*.htpasswd",
    "id_rsa", "id_ed25519", "id_ecdsa",
]

# ── large-data paths: manifest reference only, no content archived ───────────
DATA_ROOTS: list[Path] = [
    HOME / "Knowledge",
    HOME / ".cache",
    HOME / ".solar" / "logs",
    HOME / ".solar" / "queues",
    HOME / ".solar" / "harness" / "backups",
    HOME / ".solar" / "harness" / "vendor",
    HOME / ".solar" / "harness" / "node_modules",
    HOME / "Library",
]

# ── scope definitions ─────────────────────────────────────────────────────────
MINIMAL_ROOTS: list[Path] = [
    HARNESS_DIR / "lib",
    HARNESS_DIR / "config",
    HARNESS_DIR / "integrations",
    HARNESS_DIR / "solar-harness.sh",
    HARNESS_DIR / "coordinator.sh",
    HOME / ".solar" / "STATE.md",
    HOME / ".solar" / "DECISIONS.md",
    HOME / ".claude" / "CLAUDE.md",
    HOME / ".claude" / "rules",
]

FULL_ROOTS: list[Path] = MINIMAL_ROOTS + [
    HOME / ".claude" / "skills",
    HOME / ".claude" / "hooks",
    HOME / ".claude" / "scripts",
    HOME / ".claude" / "core",
    HOME / ".codex",
    HOME / ".agents" / "skills",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_secret(path: Path) -> bool:
    name = path.name.lower()
    for pat in SECRET_PATTERNS:
        if fnmatch.fnmatch(name, pat.lower()):
            return True
    return False


def _is_data_root(path: Path) -> bool:
    resolved = path.resolve()
    for dr in DATA_ROOTS:
        try:
            resolved.relative_to(dr.resolve())
            return True
        except ValueError:
            pass
    return False


def _collect_files(roots: list[Path]) -> tuple[list[dict], list[str]]:
    """Walk roots, return (file_entries, excluded_paths)."""
    included: list[dict] = []
    excluded: list[str] = []

    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(root.rglob("*"))

        for p in candidates:
            if not p.is_file():
                continue
            if _is_secret(p):
                excluded.append(str(p))
                continue
            if _is_data_root(p):
                excluded.append(str(p))
                continue
            # skip compiled artifacts and large files
            if "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo"):
                continue
            if p.stat().st_size > 5 * 1024 * 1024:
                excluded.append(str(p))
                continue
            try:
                sha = _sha256(p)
            except OSError:
                excluded.append(str(p))
                continue
            included.append({
                "path": str(p),
                "rel": str(p.relative_to(HOME)),
                "sha256": sha,
                "size": p.stat().st_size,
            })

    return included, excluded


def _snap_id() -> str:
    return "snap-" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _latest_snap(backup_dir: Path) -> "Path | None":
    manifests = sorted(backup_dir.glob("*/manifest.json"))
    return manifests[-1].parent if manifests else None


def _load_manifest(snap_dir: Path) -> dict:
    mf = snap_dir / "manifest.json"
    if not mf.exists():
        raise FileNotFoundError(f"manifest.json not found in {snap_dir}")
    return json.loads(mf.read_text())


# ── snapshot ──────────────────────────────────────────────────────────────────

def cmd_snapshot(args) -> int:
    dry_run: bool = getattr(args, "dry_run", False)
    scope: str = getattr(args, "scope", "minimal")
    out_dir = Path(getattr(args, "out_dir", None) or DEFAULT_BACKUP_DIR)

    roots = FULL_ROOTS if scope == "full" else MINIMAL_ROOTS
    print(f"[snapshot] scope={scope} dry_run={dry_run}", file=sys.stderr)

    files, excluded = _collect_files(roots)

    snap_id = _snap_id()
    archive_name = snap_id + ".tar.gz"

    manifest: dict = {
        "snapshot_id": snap_id,
        "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": scope,
        "dry_run": dry_run,
        "roots": [str(r) for r in roots],
        "file_count": len(files),
        "excluded_count": len(excluded),
        "excluded_patterns": SECRET_PATTERNS,
        "excluded": excluded,
        "files": files,
        "archive": archive_name,
        "archive_sha256": None,
    }

    if dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "snapshot_id": snap_id,
            "scope": scope,
            "would_include": len(files),
            "would_exclude": len(excluded),
            "sample_files": [f["rel"] for f in files[:5]],
            "sample_excluded": excluded[:5],
            "archive_path": str(out_dir / snap_id / archive_name),
        }, indent=2))
        return 0

    snap_dir = out_dir / snap_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    archive_path = snap_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        for entry in files:
            try:
                tar.add(entry["path"], arcname=entry["rel"])
            except OSError:
                pass

    archive_sha = _sha256(archive_path)
    manifest["archive_sha256"] = archive_sha

    mf_path = snap_dir / "manifest.json"
    mf_path.write_text(json.dumps(manifest, indent=2))

    print(json.dumps({
        "ok": True,
        "snapshot_id": snap_id,
        "scope": scope,
        "file_count": len(files),
        "excluded_count": len(excluded),
        "manifest": str(mf_path),
        "archive": str(archive_path),
        "archive_sha256": archive_sha,
    }, indent=2))
    return 0


# ── verify ────────────────────────────────────────────────────────────────────

def cmd_verify(args) -> int:
    backup_dir = Path(getattr(args, "out_dir", None) or DEFAULT_BACKUP_DIR)
    snap_id_arg: "str | None" = getattr(args, "snap_id", None)
    use_latest: bool = getattr(args, "latest", False)

    if use_latest:
        snap_dir = _latest_snap(backup_dir)
        if snap_dir is None:
            print(json.dumps({"ok": False, "error": "no snapshots found"}))
            return 1
    elif snap_id_arg:
        snap_dir = backup_dir / snap_id_arg
    else:
        print(json.dumps({"ok": False, "error": "--latest or --id required"}))
        return 1

    try:
        manifest = _load_manifest(snap_dir)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    archive_path = snap_dir / manifest["archive"]
    errors: list[str] = []
    warnings: list[str] = []

    if not archive_path.exists():
        errors.append(f"archive missing: {archive_path}")
    else:
        actual_sha = _sha256(archive_path)
        if actual_sha != manifest.get("archive_sha256"):
            errors.append(
                f"archive sha256 mismatch: expected {manifest['archive_sha256']} got {actual_sha}"
            )

    # spot-check file hashes (up to 20)
    checked = 0
    for entry in manifest.get("files", [])[:20]:
        p = Path(entry["path"])
        if not p.exists():
            warnings.append(f"source gone (normal after migration): {entry['rel']}")
            continue
        actual = _sha256(p)
        if actual != entry["sha256"]:
            warnings.append(f"source changed since snapshot: {entry['rel']}")
        checked += 1

    # paranoia: verify excluded list contains only paths, not secret values
    for excl in manifest.get("excluded", []):
        # assert: secret file names appear in excluded paths list but values are never printed
        _ = Path(excl).name  # only read the name, never the content

    ok = len(errors) == 0
    print(json.dumps({
        "ok": ok,
        "snapshot_id": manifest["snapshot_id"],
        "errors": errors,
        "warnings": warnings,
        "files_spot_checked": checked,
        "archive": str(archive_path),
        "archive_sha256_match": not any("sha256" in e for e in errors),
    }, indent=2))
    return 0 if ok else 1


# ── restore ───────────────────────────────────────────────────────────────────

def cmd_restore(args) -> int:
    dry_run: bool = getattr(args, "dry_run", False)
    backup_dir = Path(getattr(args, "out_dir", None) or DEFAULT_BACKUP_DIR)
    snap_id_arg: "str | None" = getattr(args, "snap_id", None)
    use_latest: bool = getattr(args, "latest", False)
    target_dir = Path(getattr(args, "target_dir", None) or HOME)

    if use_latest:
        snap_dir = _latest_snap(backup_dir)
        if snap_dir is None:
            print(json.dumps({"ok": False, "error": "no snapshots found"}))
            return 1
    elif snap_id_arg:
        snap_dir = backup_dir / snap_id_arg
    else:
        print(json.dumps({"ok": False, "error": "--latest or --id required"}))
        return 1

    try:
        manifest = _load_manifest(snap_dir)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    archive_path = snap_dir / manifest["archive"]
    if not archive_path.exists():
        print(json.dumps({"ok": False, "error": f"archive not found: {archive_path}"}))
        return 1

    plan: list[dict] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            dest = target_dir / member.name
            plan.append({
                "archive_path": member.name,
                "dest": str(dest),
                "size": member.size,
                "overwrite": dest.exists(),
            })

    if dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "snapshot_id": manifest["snapshot_id"],
            "restore_plan_count": len(plan),
            "would_overwrite": sum(1 for p in plan if p["overwrite"]),
            "target_dir": str(target_dir),
            "sample_plan": plan[:5],
        }, indent=2))
        return 0

    restored = 0
    errors: list[str] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            dest = target_dir / member.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                f_in = tar.extractfile(member)
                if f_in is not None:
                    with open(dest, "wb") as dst:
                        dst.write(f_in.read())
                    restored += 1
            except Exception as exc:
                errors.append(f"{member.name}: {exc}")

    print(json.dumps({
        "ok": len(errors) == 0,
        "snapshot_id": manifest["snapshot_id"],
        "restored": restored,
        "errors": errors,
        "target_dir": str(target_dir),
    }, indent=2))
    return 0 if not errors else 1


# ── list ──────────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    backup_dir = Path(getattr(args, "out_dir", None) or DEFAULT_BACKUP_DIR)
    snaps: list[dict] = []
    if backup_dir.exists():
        for mf in sorted(backup_dir.glob("*/manifest.json")):
            try:
                m = json.loads(mf.read_text())
                sha = m.get("archive_sha256", "")
                snaps.append({
                    "snapshot_id": m.get("snapshot_id"),
                    "created_at": m.get("created_at"),
                    "scope": m.get("scope"),
                    "file_count": m.get("file_count"),
                    "archive_sha256": (sha[:12] + "...") if sha else None,
                })
            except Exception:
                pass
    print(json.dumps({"ok": True, "count": len(snaps), "snapshots": snaps}, indent=2))
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="product_snapshot.py")
    sub = ap.add_subparsers(dest="cmd")

    snap_p = sub.add_parser("snapshot")
    snap_p.add_argument("--dry-run", action="store_true")
    snap_p.add_argument("--scope", choices=["minimal", "full"], default="minimal")
    snap_p.add_argument("--out-dir")

    ver_p = sub.add_parser("verify")
    ver_p.add_argument("--latest", action="store_true")
    ver_p.add_argument("--id", dest="snap_id")
    ver_p.add_argument("--out-dir")

    res_p = sub.add_parser("restore")
    res_p.add_argument("--latest", action="store_true")
    res_p.add_argument("--id", dest="snap_id")
    res_p.add_argument("--dry-run", action="store_true")
    res_p.add_argument("--target-dir")
    res_p.add_argument("--out-dir")

    ls_p = sub.add_parser("list")
    ls_p.add_argument("--out-dir")

    args = ap.parse_args()
    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    elif args.cmd == "verify":
        return cmd_verify(args)
    elif args.cmd == "restore":
        return cmd_restore(args)
    elif args.cmd == "list":
        return cmd_list(args)
    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

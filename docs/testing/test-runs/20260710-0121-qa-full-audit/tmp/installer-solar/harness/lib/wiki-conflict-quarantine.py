#!/usr/bin/env python3
"""Quarantine Obsidian sync conflict duplicates out of the live graph.

The script never deletes conflict files. It moves them to a timestamped
quarantine directory and writes a manifest containing the matching base file,
hash equality, similarity, and review status.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


VAULT = Path.home() / "Knowledge"
QUARANTINE_ROOT = Path.home() / ".solar" / "harness" / "quarantine" / "wiki-sync-conflicts"
CONFLICT_RE = re.compile(r"\.conflict-(macbook|macmini)-\d{8}T\d{6}Z(?=\.md$)", re.I)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def conflict_files(vault: Path) -> list[Path]:
    return sorted(p for p in vault.rglob("*.md") if CONFLICT_RE.search(p.name))


def base_path(path: Path) -> Path:
    return path.with_name(CONFLICT_RE.sub("", path.name))


def analyze(vault: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in conflict_files(vault):
        base = base_path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        base_text = base.read_text(encoding="utf-8", errors="replace") if base.exists() else ""
        same_sha = bool(base_text and sha256_text(text) == sha256_text(base_text))
        similarity = difflib.SequenceMatcher(None, text, base_text).ratio() if base_text else 0.0
        if same_sha:
            status = "exact_duplicate"
        elif base.exists():
            status = "divergent_needs_review"
        else:
            status = "missing_base_needs_review"
        rows.append({
            "path": str(path),
            "rel_path": str(path.relative_to(vault)),
            "base_path": str(base),
            "base_rel_path": str(base.relative_to(vault)) if str(base).startswith(str(vault)) else "",
            "base_exists": base.exists(),
            "bytes": path.stat().st_size,
            "base_bytes": base.stat().st_size if base.exists() else 0,
            "same_sha": same_sha,
            "similarity": round(similarity, 4),
            "status": status,
        })
    return rows


def apply_quarantine(vault: Path, quarantine_root: Path, rows: list[dict[str, Any]]) -> Path:
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest_root = quarantine_root / stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    moved = []
    for row in rows:
        src = Path(row["path"])
        dest = dest_root / row["rel_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        copied = dict(row)
        copied["quarantine_path"] = str(dest)
        moved.append(copied)
    manifest = {
        "created_at": stamp,
        "vault": str(vault),
        "count": len(moved),
        "exact_duplicate_count": sum(1 for row in moved if row["status"] == "exact_duplicate"),
        "divergent_needs_review_count": sum(1 for row in moved if row["status"] == "divergent_needs_review"),
        "missing_base_needs_review_count": sum(1 for row in moved if row["status"] == "missing_base_needs_review"),
        "items": moved,
    }
    (dest_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarantine sync conflict duplicate notes")
    parser.add_argument("--vault", default=str(VAULT))
    parser.add_argument("--quarantine-root", default=str(QUARANTINE_ROOT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault)
    rows = analyze(vault)
    dest = ""
    if args.apply and rows:
        dest = str(apply_quarantine(vault, Path(args.quarantine_root), rows))
    result = {
        "apply": args.apply,
        "count": len(rows),
        "exact_duplicate_count": sum(1 for row in rows if row["status"] == "exact_duplicate"),
        "divergent_needs_review_count": sum(1 for row in rows if row["status"] == "divergent_needs_review"),
        "missing_base_needs_review_count": sum(1 for row in rows if row["status"] == "missing_base_needs_review"),
        "quarantine_dir": dest,
        "items": rows,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"apply={args.apply} count={len(rows)} exact={result['exact_duplicate_count']} divergent={result['divergent_needs_review_count']} quarantine={dest or 'N/A'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
wiki-upload-audit.py — Audit a file-upload batch for qmd / vault / Solar DB coverage.

Usage:
  python3 wiki-upload-audit.py --batch <batch_id> [--json] [--vault PATH] [--db PATH]

Exit codes:
  0 — all checks pass
  1 — gaps found (but audit itself succeeded)
  2 — usage / setup error
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from qmd_resolver import resolve_qmd_bin

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
DB_PATH = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
UPLOAD_DIR: Path | None = None   # lazy-computed in audit_batch
DISPATCH_DIR: Path | None = None  # lazy-computed in audit_batch


# ── helpers ──────────────────────────────────────────────────────────────────

def batch_files(batch_id: str, vault_path: Path) -> list[Path]:
    """Return sorted list of uploaded files for a given batch."""
    upload_dir = vault_path / "_raw" / "file-uploads"
    pattern = str(upload_dir / f"{batch_id}-*")
    return sorted(Path(p) for p in glob.glob(pattern))


def find_dispatch_for_source(source_name: str, vault_path: Path) -> dict[str, Any] | None:
    """Find the best dispatch for a given source file, preferring active/completed records."""
    dispatch_dir = vault_path / "_raw" / "solar-harness" / ".dispatch"
    matches: list[dict[str, Any]] = []
    for dp in sorted(dispatch_dir.glob("wiki-ingest-*.md")):
        text = dp.read_text(errors="replace")
        if source_name in text:
            # Extract status
            m = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
            status = m.group(1) if m else "unknown"
            matches.append({"path": str(dp), "name": dp.name, "status": status})
    if not matches:
        return None
    for status in ("completed", "dispatched"):
        for item in reversed(matches):
            if item.get("status") == status:
                return item
    return matches[-1]


def find_wiki_ref(source_name: str, vault_path: Path | None = None) -> Path | None:
    """Find a vault markdown file that references the source file."""
    root = vault_path or VAULT_ROOT
    search_dirs = [
        root / "references",
        root / "concepts",
        root / "synthesis",
    ]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for md in d.glob("*.md"):
            try:
                text = md.read_text(errors="replace")
                if source_name in text:
                    return md
            except Exception:
                continue
    return None


def check_solar_db(conn: sqlite3.Connection, source_name: str) -> dict[str, Any]:
    """Check if a document is in obsidian_vault_index and fts_unified_search."""
    result = {"vault_index": False, "fts": False, "indexed": False}
    stem = Path(source_name).stem
    title = re.sub(r"^\d{8}T\d{6}Z-\d{2}-", "", stem)
    title = re.sub(r"[-_]+", " ", title).strip()

    try:
        row = conn.execute(
            """
            SELECT 1 FROM obsidian_vault_index
            WHERE deleted_at IS NULL
              AND (file_path LIKE ? OR title LIKE ? OR summary LIKE ?)
            LIMIT 1
            """,
            (f"%{stem}%", f"%{title[:80]}%", f"%{source_name}%")
        ).fetchone()
        result["vault_index"] = row is not None
    except sqlite3.OperationalError:
        result["vault_index"] = False
        result["vault_index_error"] = "table not found"

    try:
        row = conn.execute(
            "SELECT 1 FROM fts_unified_search WHERE content LIKE ? OR title LIKE ? LIMIT 1",
            (f"%{source_name}%", f"%{title[:80]}%")
        ).fetchone()
        result["fts"] = row is not None
    except sqlite3.OperationalError:
        result["fts"] = False
        result["fts_error"] = "table not found"

    result["indexed"] = bool(result["vault_index"] or result["fts"])
    return result


def check_qmd(source_name: str) -> bool:
    """Check if the source is indexed in qmd collection."""
    qmd_bin = os.environ.get("QMD_BIN", "")
    if not qmd_bin:
        qmd_bin = resolve_qmd_bin()
    if not qmd_bin:
        return False

    stem = Path(source_name).stem
    title = re.sub(r"^\d{8}T\d{6}Z-\d{2}-", "", stem)
    title = re.sub(r"[-_]+", " ", title).strip()
    queries = [
        source_name,
        stem,
        title,
        " ".join(title.split()[:10]),
    ]
    seen: set[str] = set()
    for query in queries:
        query = query.strip()
        if not query or query in seen:
            continue
        seen.add(query)
        try:
            result = subprocess.run(
                [qmd_bin, "search", query, "-c", "solar-wiki", "--json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0 or len(result.stdout.strip()) <= 2:
                continue
            rows = json.loads(result.stdout)
            if rows:
                return True
        except Exception:
            continue
    return False


# ── state + blocker derivation ───────────────────────────────────────────────

def _derive_state(has_qmd: bool, has_vault: bool, has_db: bool) -> str:
    if has_qmd and has_vault and has_db:
        return "full"
    if has_qmd and has_vault:
        return "partial:qmd+vault"
    if has_qmd and has_db:
        return "partial:qmd+db"
    if has_vault and has_db:
        return "partial:vault+db"
    if has_qmd:
        return "qmd_only"
    if has_vault:
        return "vault_only"
    if has_db:
        return "db_only"
    return "missing"


def _derive_blocker(entry: dict[str, Any]) -> str:
    dispatch = entry.get("dispatch")
    if dispatch:
        status = dispatch.get("status", "unknown")
        if status in ("failed", "error"):
            return "dispatch_failed"
        if status not in ("completed",):
            return "dispatch_pending"

    has_qmd = bool(entry.get("qmd"))
    has_vault = bool(entry.get("wiki_ref"))
    db = entry.get("solar_db", {})
    has_db = bool(db.get("indexed"))

    # DB missing but both other layers present → db write failed
    if has_qmd and has_vault and not has_db:
        return "db_write_failed"

    # No vault reference → likely parse/ingest error
    if not has_vault:
        source = entry.get("file", "")
        ext = Path(source).suffix.lower()
        if ext in (".pdf", ".docx", ".pptx", ".doc", ".xls", ".xlsx"):
            return "parse_error"
        if ext not in (".md", ".txt", ".csv", ".json", ".yaml", ".yml"):
            return "unsupported_format"

    return "unknown"


# ── main audit ───────────────────────────────────────────────────────────────

def audit_batch(batch_id: str, vault_path: Path, db_path: Path, use_json: bool = False) -> dict[str, Any]:
    """Run audit on a batch and return structured result."""
    files = batch_files(batch_id, vault_path)
    if not files:
        return {"error": f"No files found for batch {batch_id}", "batch": batch_id, "total": 0}

    conn: sqlite3.Connection | None = None
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))

    per_file = []
    found_qmd = 0
    found_vault = 0
    found_solar_db = 0
    found_dispatch = 0

    for fp in files:
        source_name = fp.name
        entry: dict[str, Any] = {
            "file": source_name,
            "index": int(re.match(r".*-(\d{2})-", source_name).group(1)) if re.match(r".*-(\d{2})-", source_name) else 0,
        }

        # Check dispatch
        dispatch = find_dispatch_for_source(source_name, vault_path)
        entry["dispatch"] = dispatch
        if dispatch and dispatch.get("status") in ("completed", "dispatched"):
            found_dispatch += 1

        # Check vault reference
        wiki_ref = find_wiki_ref(source_name, vault_path)
        entry["wiki_ref"] = str(wiki_ref) if wiki_ref else None
        if wiki_ref:
            found_vault += 1

        # Check Solar DB
        if conn:
            db_status = check_solar_db(conn, source_name)
            entry["solar_db"] = db_status
            if db_status.get("indexed"):
                found_solar_db += 1
        else:
            entry["solar_db"] = {"vault_index": False, "fts": False, "error": "db not found"}

        # Check qmd
        entry["qmd"] = check_qmd(source_name)
        if entry["qmd"]:
            found_qmd += 1

        # Derive state and blocker
        has_qmd = bool(entry["qmd"])
        has_vault = bool(wiki_ref)
        has_db = bool(entry["solar_db"].get("indexed"))
        entry["state"] = _derive_state(has_qmd, has_vault, has_db)
        if entry["state"] != "full":
            entry["blocker"] = _derive_blocker(entry)

        per_file.append(entry)

    if conn:
        conn.close()

    total = len(files)
    result = {
        "batch": batch_id,
        "total": total,
        "qmd": {"found": found_qmd, "missing": total - found_qmd},
        "vault": {"found": found_vault, "missing": total - found_vault},
        "solar_db": {"found": found_solar_db, "missing": total - found_solar_db},
        "dispatch": {"completed": found_dispatch, "pending": total - found_dispatch},
        "pages": {
            "silent_missing": [e["file"] for e in per_file if not e["wiki_ref"]],
            "files": per_file,
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a file-upload batch")
    parser.add_argument("--batch", required=True, help="Batch ID (e.g. 20260508T122047Z)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--vault", default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--db", default=str(DB_PATH), help="Solar DB path")
    args = parser.parse_args()

    result = audit_batch(args.batch, Path(args.vault), Path(args.db), use_json=args.json)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        total = result.get("total", 0)
        if total == 0:
            print(f"Audit: No files found for batch {args.batch}")
            return 2
        print(f"Audit batch {args.batch}: {total} files")
        print(f"  Dispatch completed: {result['dispatch']['completed']}/{total}")
        print(f"  Vault references:   {result['vault']['found']}/{total}")
        print(f"  Solar DB indexed:   {result['solar_db']['found']}/{total}")
        print(f"  qmd indexed:        {result['qmd']['found']}/{total}")
        if result["pages"]["silent_missing"]:
            print(f"\n  Missing vault refs ({len(result['pages']['silent_missing'])}):")
            for f in result["pages"]["silent_missing"]:
                print(f"    - {f}")

    return 1 if result.get("vault", {}).get("missing", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

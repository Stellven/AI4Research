#!/usr/bin/env python3
"""
wiki-upload-backfill.py — Backfill qmd / vault / Solar DB for a file-upload batch.

Creates stub wiki references for files missing them, then upserts all into
obsidian_vault_index + fts_unified_search. Idempotent: running twice produces
the same result.

Usage:
  python3 wiki-upload-backfill.py --batch <batch_id> [--repair] [--json]
                                   [--vault PATH] [--db PATH]

Flags:
  --repair   Create stub wiki refs for files that are missing them
  --json     Output structured JSON result
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from qmd_resolver import resolve_qmd_bin

# Optional SandboxHand routing for document-extract tool-plane CLIs.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from hands_runtime import SandboxHand  # noqa: E402
    from runtime_interfaces import ResultStatus  # noqa: E402
    _SANDBOX_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - import safety
    SandboxHand = None  # type: ignore[assignment]
    ResultStatus = None  # type: ignore[assignment]
    _SANDBOX_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
DB_PATH = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
UPLOAD_DIR: Path | None = None
DISPATCH_DIR: Path | None = None
REFS_DIR: Path | None = None

MAX_CONTENT_CHARS = 2000
_QMD_UPDATE_RAN = False

# Last-route telemetry for tests / activation proof callers.
LAST_EXTRACT_ROUTE: dict[str, Any] = {}


def _run_extract_sandboxed(
    cli_name: str,
    argv: list[str],
    timeout: int,
) -> dict[str, Any]:
    """Run a short read-only extract CLI through SandboxHand (argv mode).

    Used for `pdftotext` and `qlmanage` smoke routes so the tool-plane
    document path emits sandbox evidence by default. The disposable workspace
    is removed on dispose, so no host state is mutated.

    Returns a record with stdout / stderr / exit_code / executor /
    execution_mode / evidence_file / write_guard for callers.
    """
    base = {
        "executor": "host_fallback",
        "execution_mode": "argv",
        "evidence_file": "",
        "write_guard": {"enabled": False, "violations": []},
        "fallback_reason": "",
        "stdout": "",
        "stderr": "",
        "exit_code": 99,
        "ok": False,
        "cli": cli_name,
        "argv": list(argv),
    }
    if SandboxHand is None or ResultStatus is None:
        base["fallback_reason"] = _SANDBOX_IMPORT_ERROR or "SandboxHand not importable"
        return base
    hand = SandboxHand()
    ref = hand.provision(capabilities=["document-extract", cli_name])
    try:
        idem = hashlib.sha1(
            f"doc-extract:{cli_name}:{os.getpid()}:{time.monotonic_ns()}".encode("utf-8")
        ).hexdigest()[:24]
        result = hand.execute(
            ref,
            f"doc-extract-{cli_name}",
            {
                "argv": list(argv),
                "session_id": f"doc-extract-{os.getpid()}",
                "sprint_id": f"doc-extract-{os.getpid()}",
                "activity_id": f"doc-extract-{cli_name}-{idem}",
            },
            idempotency_key=f"doc-extract:{cli_name}:{idem}",
            timeout_seconds=timeout,
        )
        stdout = str(result.output or "")
        stderr = str((result.metadata or {}).get("stderr", "") or "")
        ok = result.status == ResultStatus.OK
        exit_code = 0 if ok else (124 if result.status == ResultStatus.TIMEOUT else 1)
        base.update({
            "executor": "sandbox",
            "execution_mode": (result.metadata or {}).get("execution_mode", "argv"),
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
            "write_guard": (result.metadata or {}).get("write_guard", {"enabled": False, "violations": []}),
            "sandbox_status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "hand_id": ref.hand_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "ok": ok,
        })
        return base
    finally:
        hand.dispose(ref)


# ── PDF text extraction ──────────────────────────────────────────────────────

def _load_upload_extractor():
    path = Path(__file__).resolve().with_name("wiki-upload-extract.py")
    spec = importlib.util.spec_from_file_location("wiki_upload_extract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load upload extractor: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wiki_upload_extract"] = module
    spec.loader.exec_module(module)
    return module


def extract_upload_text(source_path: Path, max_chars: int = 12000) -> str:
    """Extract complex uploads through the canonical upload extractor.

    This is intentionally MinerU-first for PDFs. Backfill may create tracking
    stubs, but it must not use short pdftotext snippets as if they were paper
    understanding.
    """
    global LAST_EXTRACT_ROUTE
    try:
        module = _load_upload_extractor()
        output_dir = source_path.parent / "_extracted"
        result = module.extract_file(str(source_path), str(output_dir))
        LAST_EXTRACT_ROUTE = dict(result)
        if result.get("status") == "success" and result.get("artifact"):
            artifact = Path(str(result["artifact"]))
            if artifact.exists():
                return artifact.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception as exc:
        LAST_EXTRACT_ROUTE = {
            "status": "extract_failed",
            "method": "upload_extractor_failed",
            "quality": "blocked",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return ""


def extract_pdf_text(pdf_path: Path, max_chars: int = 3000) -> str:
    """Extract PDF text through MinerU-first upload extractor.

    Legacy pdftotext is available only under
    `SOLAR_HARNESS_ALLOW_LEGACY_PDF_BACKFILL=1` for emergency diagnostics. The
    normal path must keep PDF knowledge extraction on the MinerU chain.
    """
    global LAST_EXTRACT_ROUTE
    text = extract_upload_text(pdf_path, max_chars=max_chars)
    if text.strip():
        return text
    if os.environ.get("SOLAR_HARNESS_ALLOW_LEGACY_PDF_BACKFILL") != "1":
        return ""

    argv = ["pdftotext", "-l", "3", str(pdf_path), "-"]
    route = _run_extract_sandboxed("pdftotext", argv, timeout=30)
    route["method"] = "legacy_pdftotext_diagnostic_only"
    route["quality"] = "degraded_fallback_requires_reingest"
    LAST_EXTRACT_ROUTE = route
    if route.get("ok") and (route.get("stdout") or "").strip():
        return (route["stdout"] or "").strip()[:max_chars]
    if route.get("executor") == "sandbox":
        # Sandbox ran but the binary failed (missing or empty stdout). Stay in
        # sandbox; do not fall through to host execution.
        return ""
    # Sandbox not importable; degrade to host run while recording the reason.
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()[:max_chars]
            LAST_EXTRACT_ROUTE.update({"stdout": result.stdout, "ok": True, "exit_code": 0})
            return text
    except Exception as exc:
        LAST_EXTRACT_ROUTE["host_fallback_error"] = f"{type(exc).__name__}: {exc}"
    return ""


def extract_pages_text(pages_path: Path, max_chars: int = 3000) -> str:
    """Attempt to extract text from .pages file via macOS Quick Look.

    Routed through SandboxHand so the qlmanage CLI smoke emits sandbox
    evidence by default. When the sandbox is unavailable we keep the previous
    host fallback to preserve operability.
    """
    global LAST_EXTRACT_ROUTE
    argv = ["qlmanage", "-t", "-p", str(pages_path)]
    route = _run_extract_sandboxed("qlmanage", argv, timeout=30)
    LAST_EXTRACT_ROUTE = route
    if route.get("ok") and (route.get("stdout") or "").strip():
        return (route["stdout"] or "").strip()[:max_chars]
    if route.get("executor") == "sandbox":
        return ""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=30,
        )
        if result.stdout.strip():
            text = result.stdout.strip()[:max_chars]
            LAST_EXTRACT_ROUTE.update({"stdout": result.stdout, "ok": True, "exit_code": result.returncode})
            return text
    except Exception as exc:
        LAST_EXTRACT_ROUTE["host_fallback_error"] = f"{type(exc).__name__}: {exc}"
    return ""


def extract_html_text(html_path: Path, max_chars: int = 3000) -> str:
    """Extract text from HTML file."""
    try:
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._texts: list[str] = []

            def handle_data(self, data: str) -> None:
                self._texts.append(data)

            def get_text(self) -> str:
                return " ".join(self._texts)

        content = html_path.read_text(errors="replace")[:50000]
        parser = _TextExtractor()
        parser.feed(content)
        return parser.get_text().strip()[:max_chars]
    except Exception:
        return ""


def extract_source_text(source_path: Path) -> str:
    """Extract whatever text we can from a source file."""
    ext = source_path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_text(source_path)
    elif ext in (".docx", ".pptx"):
        return extract_upload_text(source_path)
    elif ext == ".pages":
        return extract_pages_text(source_path)
    elif ext in (".html", ".htm"):
        return extract_html_text(source_path)
    elif ext == ".md":
        return source_path.read_text(errors="replace")[:3000]
    return ""


# ── filename → human title ──────────────────────────────────────────────────

def derive_title(filename: str) -> str:
    """Derive a human-readable title from batch filename."""
    # Remove batch prefix: 20260508T122047Z-NN-title.ext
    m = re.match(r"\d{8}T\d{6}Z-\d{2}-(.+)\.\w+$", filename)
    if m:
        return m.group(1).replace("-", " ").strip()
    return Path(filename).stem.replace("-", " ")


# ── DB schema ────────────────────────────────────────────────────────────────

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure obsidian_vault_index and fts_unified_search exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS obsidian_vault_index (
            file_path     TEXT PRIMARY KEY,
            vault_path    TEXT NOT NULL,
            title         TEXT NOT NULL,
            summary       TEXT,
            tags          TEXT,
            source        TEXT DEFAULT 'obsidian',
            content_hash  TEXT,
            indexed_at    TEXT DEFAULT (datetime('now')),
            deleted_at    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_obsidian_vault_indexed_at
        ON obsidian_vault_index(indexed_at)
    """)
    try:
        conn.execute("SELECT 1 FROM fts_unified_search LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_unified_search
            USING fts5(doc_id, doc_type, title, content, tags, metadata,
                       content='', contentless_delete=1)
        """)
    conn.commit()


# ── DB upsert ────────────────────────────────────────────────────────────────

def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def upsert_vault_index(
    conn: sqlite3.Connection,
    file_path: str,
    vault_path: str,
    title: str,
    summary: str,
    tags: list[str],
    content_hash: str,
    full_content: str,
) -> str:
    """Insert or update obsidian_vault_index + fts_unified_search. Returns action."""
    tags_json = json.dumps(tags, ensure_ascii=False)
    existing = conn.execute(
        "SELECT content_hash FROM obsidian_vault_index WHERE file_path = ? AND deleted_at IS NULL",
        (file_path,)
    ).fetchone()

    if existing and existing[0] == content_hash:
        return "skipped"

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("""
        INSERT INTO obsidian_vault_index
            (file_path, vault_path, title, summary, tags, source, content_hash, indexed_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, 'obsidian', ?, ?, NULL)
        ON CONFLICT(file_path) DO UPDATE SET
            title        = excluded.title,
            summary      = excluded.summary,
            tags         = excluded.tags,
            content_hash = excluded.content_hash,
            indexed_at   = excluded.indexed_at,
            deleted_at   = NULL
    """, (file_path, vault_path, title, summary, tags_json, content_hash, now))

    doc_id = f"obsidian:{file_path}"
    fts_content = full_content[:MAX_CONTENT_CHARS]
    try:
        conn.execute(
            "INSERT OR REPLACE INTO fts_unified_search(doc_id, doc_type, title, content, tags, metadata) "
            "VALUES (?, 'obsidian_vault_index', ?, ?, ?, ?)",
            (doc_id, title, fts_content, " ".join(tags),
             json.dumps({"file_path": file_path, "vault": vault_path}))
        )
    except sqlite3.OperationalError:
        pass

    return "updated" if existing else "new"


# ── find existing wiki ref ──────────────────────────────────────────────────

def find_wiki_ref(source_name: str, vault_path: Path | None = None) -> Path | None:
    """Find an existing vault markdown that references this source file."""
    root = vault_path or VAULT_ROOT
    for d in [root / "references", root / "concepts", root / "synthesis"]:
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


# ── create stub wiki ref ────────────────────────────────────────────────────

def create_stub_ref(source_path: Path, batch_id: str, vault_path: Path | None = None) -> Path | None:
    """Create a minimal tracking ref for a source that lacks one.

    This must not masquerade as knowledge extraction. In particular, PDF stubs
    are marked as `quality: stub` and `needs_deep_ingest: true` so downstream
    search/UI can distinguish provenance tracking from actual paper analysis.
    """
    root = vault_path or VAULT_ROOT
    refs_dir = root / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    source_name = source_path.name
    title = derive_title(source_name)

    # Generate a safe filename slug
    m = re.match(r"\d{8}T\d{6}Z-\d{2}-(.+)\.\w+$", source_name)
    slug = m.group(1) if m else Path(source_name).stem
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)[:80]

    ref_path = refs_dir / f"{slug}.md"
    if ref_path.exists():
        try:
            existing = ref_path.read_text(errors="replace")
            if source_name not in existing:
                with ref_path.open("a", encoding="utf-8") as f:
                    f.write(
                        "\n## Additional Source\n\n"
                        f"- Original file: `{source_name}`\n"
                        f"- Batch: `{batch_id}`\n"
                    )
        except Exception:
            pass
        return ref_path

    # Try to extract text for a summary
    extracted = extract_source_text(source_path)
    extraction_method = str(LAST_EXTRACT_ROUTE.get("method") or "")
    extraction_quality = str(LAST_EXTRACT_ROUTE.get("quality") or ("unknown" if extracted else "blocked"))
    summary = ""
    if extracted:
        # Take first meaningful paragraph
        for line in extracted.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) > 20:
                summary = stripped[:400]
                break

    ext = source_path.suffix.lower()
    file_type = {"pdf": "paper", "pages": "document", "html": "article", "md": "note"}.get(ext.lstrip("."), "document")

    tags = ["uploaded", "batch-backfill"]
    if ext == ".pdf":
        tags.append("pdf")
        if not extraction_method.startswith("mineru:"):
            tags.append("needs-mineru-reingest")
    elif ext == ".pages":
        tags.append("pages")

    content = f"""---
title: "{title}"
type: {file_type}
source_file: "{source_name}"
batch: "{batch_id}"
ingested_at: {time.strftime("%Y-%m-%d")}
tags: {json.dumps(tags, ensure_ascii=False)}
visibility: internal
backfill: true
quality: stub
extraction_method: "{extraction_method or "N/A"}"
extraction_quality: "{extraction_quality}"
needs_deep_ingest: {str(ext in {".pdf", ".docx", ".pptx"} and not extraction_method.startswith("mineru:")).lower()}
---

# {title}

> Tracking stub only. This page is not a completed knowledge extraction.

## Summary

{summary if summary else "Auto-generated stub from batch backfill. Content extraction pending."}

## Source

- Original file: `{source_name}`
- Batch: `{batch_id}`
"""
    try:
        ref_path.write_text(content, encoding="utf-8")
        return ref_path
    except Exception as e:
        print(f"Warning: Failed to create stub ref for {source_name}: {e}", file=sys.stderr)
        return None


# ── qmd registration ────────────────────────────────────────────────────────

def register_qmd(md_path: Path) -> bool:
    """Ensure a markdown file is visible in qmd solar-wiki collection."""
    qmd_bin = os.environ.get("QMD_BIN", "")
    if not qmd_bin:
        qmd_bin = resolve_qmd_bin()
    if not qmd_bin:
        return False

    def _queries() -> list[str]:
        title = ""
        try:
            text = md_path.read_text(errors="replace")[:4096]
            m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
            if m:
                title = m.group(1).strip()
        except Exception:
            pass
        return [
            md_path.name,
            md_path.stem.replace("-", " "),
            title,
        ]

    def _visible() -> bool:
        seen: set[str] = set()
        for query in _queries():
            query = query.strip()
            if not query or query in seen:
                continue
            seen.add(query)
            try:
                result = subprocess.run(
                    [qmd_bin, "search", query, "-c", "solar-wiki", "--json"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and len(result.stdout.strip()) > 2:
                    rows = json.loads(result.stdout)
                    if rows:
                        return True
            except Exception:
                continue
        return False

    if _visible():
        return True

    # qmd has collection-level indexing; there is no per-file `add` command.
    global _QMD_UPDATE_RAN
    if not _QMD_UPDATE_RAN:
        _QMD_UPDATE_RAN = True
        try:
            subprocess.run([qmd_bin, "update"], capture_output=True, text=True, timeout=120)
        except Exception:
            pass
    try:
        return _visible()
    except Exception:
        return False


# ── main backfill ────────────────────────────────────────────────────────────

def backfill_batch(
    batch_id: str,
    vault_path: Path,
    db_path: Path,
    repair: bool = False,
) -> dict[str, Any]:
    """Run backfill on a batch. Returns structured result."""
    upload_dir = vault_path / "_raw" / "file-uploads"
    pattern = str(upload_dir / f"{batch_id}-*")
    files = sorted(Path(p) for p in glob.glob(pattern))

    if not files:
        return {"error": f"No files found for batch {batch_id}", "total": 0}

    # Ensure DB schema
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)

    per_file = []
    total_qmd = 0
    total_vault = 0
    total_db = 0
    stubs_created = 0

    for fp in files:
        source_name = fp.name
        entry: dict[str, Any] = {"file": source_name}

        # Step 1: Find or create wiki reference
        wiki_ref = find_wiki_ref(source_name, vault_path)

        if wiki_ref is None and repair:
            wiki_ref = create_stub_ref(fp, batch_id, vault_path)
            if wiki_ref:
                stubs_created += 1

        if wiki_ref:
            entry["wiki_ref"] = str(wiki_ref)
            entry["wiki_ref_name"] = wiki_ref.name
            total_vault += 1

            # Step 2: Read wiki ref content for indexing
            try:
                ref_content = wiki_ref.read_text(errors="replace")
            except Exception:
                ref_content = ""

            title = derive_title(source_name)
            # Try to extract title from frontmatter
            m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', ref_content, re.MULTILINE)
            if m:
                title = m.group(1)

            # Extract summary from content
            summary = ""
            for line in ref_content.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("---") and len(stripped) > 10:
                    summary = stripped[:400]
                    break

            # Extract tags
            tags = ["uploaded"]
            m_tags = re.search(r'^tags:\s*\[(.+)\]$', ref_content, re.MULTILINE)
            if m_tags:
                tags = [t.strip().strip('"').strip("'") for t in m_tags.group(1).split(",")]

            content_hash = sha1_hex(ref_content)

            # Step 3: Upsert into Solar DB
            action = upsert_vault_index(
                conn,
                file_path=str(wiki_ref.relative_to(vault_path)),
                vault_path=str(vault_path),
                title=title,
                summary=summary,
                tags=tags,
                content_hash=content_hash,
                full_content=ref_content,
            )
            entry["db_action"] = action
            if action in ("new", "updated"):
                total_db += 1
            elif action == "skipped":
                total_db += 1  # Already indexed counts as found

            # Step 4: Register in qmd
            qmd_ok = register_qmd(wiki_ref)
            entry["qmd"] = qmd_ok
            if qmd_ok:
                total_qmd += 1
        else:
            entry["wiki_ref"] = None
            entry["db_action"] = "no_ref"
            entry["qmd"] = False

        per_file.append(entry)

    conn.commit()
    conn.close()

    total = len(files)
    return {
        "batch": batch_id,
        "total": total,
        "repair": repair,
        "stubs_created": stubs_created,
        "qmd": {"found": total_qmd, "missing": total - total_qmd},
        "vault": {"found": total_vault, "missing": total - total_vault},
        "solar_db": {"found": total_db, "missing": total - total_db},
        "files": per_file,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill qmd/vault/DB for an upload batch")
    parser.add_argument("--batch", required=True, help="Batch ID (e.g. 20260508T122047Z)")
    parser.add_argument("--repair", action="store_true", help="Create stub wiki refs for missing files")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--vault", default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--db", default=str(DB_PATH), help="Solar DB path")
    args = parser.parse_args()

    result = backfill_batch(args.batch, Path(args.vault), Path(args.db), repair=args.repair)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        total = result.get("total", 0)
        if total == 0:
            print(f"Backfill: No files found for batch {args.batch}")
            return 2
        print(f"Backfill batch {args.batch}: {total} files")
        print(f"  Repair mode:        {'ON' if args.repair else 'OFF'}")
        print(f"  Stubs created:      {result.get('stubs_created', 0)}")
        print(f"  Vault references:   {result['vault']['found']}/{total}")
        print(f"  Solar DB indexed:   {result['solar_db']['found']}/{total}")
        print(f"  qmd indexed:        {result['qmd']['found']}/{total}")
        if result["vault"]["missing"] > 0:
            print(f"\n  Still missing vault refs: {result['vault']['missing']}")
            for f in result["files"]:
                if not f["wiki_ref"]:
                    print(f"    - {f['file']}")

    return 0 if result["vault"]["missing"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

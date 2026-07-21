#!/usr/bin/env python3
"""Minimal dispatcher CLI for Solar Knowledge ingest control plane.

N2 establishes the single CLI entrypoint and delegates registry operations to
knowledge_ingest_registry. Later nodes add adapters, extraction and QMD workers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry
import knowledge_source_adapters as adapters
import knowledge_spans
import knowledge_dashboard


# ── State machine: valid transitions (B2) ──────────────────────────
VALID_TRANSITIONS: set[tuple[str, str]] = {
    # Original states
    ("NEW", "RAW_MATERIALIZED"),
    ("RAW_MATERIALIZED", "VAULT_DISCOVERED"),
    ("VAULT_DISCOVERED", "EXTRACT_ELIGIBLE"),
    ("EXTRACT_ELIGIBLE", "THUNDEROMLX_EXTRACT_RUNNING"),
    ("THUNDEROMLX_EXTRACT_RUNNING", "DONE"),
    ("RAW_MATERIALIZED", "EXTRACT_ELIGIBLE"),
    ("EXTRACT_ELIGIBLE", "DONE"),
    # B2 new transitions: retryable failure
    ("EXTRACT_ELIGIBLE", "DONE_RAW_ONLY_WARN"),
    ("THUNDEROMLX_EXTRACT_RUNNING", "EXTRACT_FAILED_RETRYABLE"),
    ("EXTRACT_FAILED_RETRYABLE", "THUNDEROMLX_EXTRACT_RUNNING"),
    ("EXTRACT_FAILED_RETRYABLE", "DONE_RAW_ONLY_WARN"),
    # Skip path
    ("EXTRACT_ELIGIBLE", "IGNORED"),
}

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SEC = 10.0


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload)


def cmd_status(args: argparse.Namespace) -> int:
    emit(registry.status(Path(args.db).expanduser()), args.json)
    return 0


def cmd_qmd_watermarks(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    registry.migrate(db_path)
    with registry.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM watermarks ORDER BY layer").fetchall()
    watermarks = [dict(zip(row.keys(), row)) for row in rows]
    emit({"ok": True, "watermarks": watermarks, "count": len(watermarks)}, args.json)
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    emit(registry.migrate(Path(args.db).expanduser()), args.json)
    return 0


def cmd_submit_event(args: argparse.Namespace) -> int:
    source_path = str(Path(args.source_path).expanduser())
    source_sha = args.source_sha256
    path = Path(source_path)
    if source_sha is None and path.exists() and path.is_file():
        source_sha = registry.hashlib.sha256(path.read_bytes()).hexdigest()
    doc = registry.upsert_document(
        source_kind=args.source_kind,
        source_path=source_path,
        source_adapter=args.source_adapter,
        content_kind=args.content_kind,
        declared_doc_type=args.declared_doc_type,
        source_sha256=source_sha,
        current_state=args.state,
        ingest_policy=args.ingest_policy,
        extract_policy=args.extract_policy,
        provenance_quality=args.provenance_quality,
        db_path=Path(args.db).expanduser(),
    )
    emit({"ok": True, "document": doc}, args.json)
    return 0


def _span_root(args: argparse.Namespace, source_kind: str) -> Path:
    if args.span_root:
        return Path(args.span_root).expanduser()
    base = Path.home() / "Knowledge"
    if source_kind == "obsidian_vault":
        return base / "_vault_index" / "spans"
    return base / "_raw" / ".spans"


def _write_and_register_spans(
    *,
    path: Path,
    doc: dict[str, Any],
    source_kind: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    sidecar = knowledge_spans.default_sidecar_path(
        path,
        root=_span_root(args, source_kind),
        doc_id=doc["doc_id"],
    )
    payload = knowledge_spans.write_span_sidecar(
        source_path=path,
        doc_id=doc["doc_id"],
        source_kind=source_kind,
        output_path=sidecar,
        max_lines=args.max_span_lines,
    )
    registry.replace_spans(
        doc_id=doc["doc_id"],
        spans=payload["spans"],
        source_sha256=payload["source_sha256"],
        db_path=Path(args.db).expanduser(),
    )
    return {"span_count": len(payload["spans"]), "sidecar_path": str(sidecar)}


def cmd_discover_raw(args: argparse.Namespace) -> int:
    root = Path(args.source_dir).expanduser()
    limit = args.limit
    count = 0
    docs: list[dict[str, Any]] = []
    span_count = 0
    for path in adapters.iter_raw_markdown(root, limit=limit):
        sha = registry.hashlib.sha256(path.read_bytes()).hexdigest()
        doc = registry.upsert_document(
            source_kind="raw",
            source_path=str(path),
            source_adapter="raw_adapter",
            content_kind="markdown",
            declared_doc_type=args.declared_doc_type,
            source_sha256=sha,
            current_state="RAW_MATERIALIZED",
            db_path=Path(args.db).expanduser(),
        )
        if args.build_spans:
            span_info = _write_and_register_spans(path=path, doc=doc, source_kind="raw", args=args)
            doc["span_sidecar_path"] = span_info["sidecar_path"]
            doc["span_count"] = span_info["span_count"]
            span_count += span_info["span_count"]
        docs.append(doc)
        count += 1
    emit({"ok": True, "source_dir": str(root), "count": count, "span_count": span_count, "documents": docs if args.verbose else []}, args.json)
    return 0


def cmd_discover_sources(args: argparse.Namespace) -> int:
    root = Path(args.source_dir).expanduser()
    materialized_root = Path(args.materialized_root).expanduser()
    limit = args.limit
    count = 0
    span_count = 0
    by_kind: dict[str, int] = {}
    docs: list[dict[str, Any]] = []
    for source_path in adapters.iter_raw_sources(root, limit=limit, include_dispatch=args.include_dispatch):
        source_kind, source_adapter, doc_type = adapters.classify_raw_source(source_path, root)
        if args.source_kind and source_kind != args.source_kind:
            continue
        ingest_path = adapters.materialize_to_markdown(source_path, target_root=materialized_root, source_kind=source_kind)
        sha = registry.hashlib.sha256(ingest_path.read_bytes()).hexdigest()
        is_ignored = source_kind == "raw_dispatch"
        doc = registry.upsert_document(
            source_kind=source_kind,
            source_path=str(ingest_path),
            source_adapter=source_adapter,
            content_kind="markdown",
            declared_doc_type=doc_type,
            source_sha256=sha,
            current_state="IGNORED" if is_ignored else "RAW_MATERIALIZED",
            ingest_policy="ignored" if is_ignored else "default",
            extract_policy="off" if is_ignored else "default",
            provenance_quality="complete" if ingest_path == source_path else "observed",
            db_path=Path(args.db).expanduser(),
        )
        if args.build_spans and not is_ignored:
            span_info = _write_and_register_spans(path=ingest_path, doc=doc, source_kind=source_kind, args=args)
            doc["span_sidecar_path"] = span_info["sidecar_path"]
            doc["span_count"] = span_info["span_count"]
            span_count += span_info["span_count"]
        docs.append(doc)
        by_kind[source_kind] = by_kind.get(source_kind, 0) + 1
        count += 1
    emit({"ok": True, "source_dir": str(root), "count": count, "span_count": span_count, "by_kind": by_kind, "documents": docs if args.verbose else []}, args.json)
    return 0


def cmd_discover_vault(args: argparse.Namespace) -> int:
    root = Path(args.vault).expanduser()
    limit = args.limit
    count = 0
    docs: list[dict[str, Any]] = []
    span_count = 0
    seen_folders: set[str] = set()
    for path, folder in adapters.iter_vault_markdown(root, include=args.include, limit=limit):
        seen_folders.add(folder)
        sha = registry.hashlib.sha256(path.read_bytes()).hexdigest()
        doc = registry.upsert_document(
            source_kind="obsidian_vault",
            source_path=str(path),
            source_adapter="obsidian_adapter",
            content_kind="markdown",
            declared_doc_type=adapters.doc_type_for_vault_folder(folder),
            source_sha256=sha,
            current_state="VAULT_DISCOVERED",
            db_path=Path(args.db).expanduser(),
        )
        if args.build_spans:
            span_info = _write_and_register_spans(path=path, doc=doc, source_kind="obsidian_vault", args=args)
            doc["span_sidecar_path"] = span_info["sidecar_path"]
            doc["span_count"] = span_info["span_count"]
            span_count += span_info["span_count"]
        docs.append(doc)
        count += 1
    emit({"ok": True, "vault": str(root), "folders": sorted(seen_folders), "count": count, "span_count": span_count, "documents": docs if args.verbose else []}, args.json)
    return 0


def cmd_process_queue(args: argparse.Namespace) -> int:
    emit({"ok": True, "processed": 0, "note": "queue processing is implemented by later DAG nodes"}, args.json)
    return 0


def _run_cmd(cmd: list[str], *, timeout: int = 900) -> dict[str, Any]:
    started = registry.now_iso()
    proc = subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    parsed: Any = None
    out = proc.stdout.strip()
    if out:
        try:
            parsed = json.loads(out[out.find("{") :])
        except Exception:
            parsed = None
    return {
        "cmd": cmd,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "started_at": started,
        "finished_at": registry.now_iso(),
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
        "json": parsed,
    }


def _python_lib_cmd(script_name: str, *args: str) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve().parent / script_name), *args]


def cmd_run_pipeline(args: argparse.Namespace) -> int:
    """Run a supervised, bounded ingest cycle from the control plane.

    This is intentionally small-batch by default. It closes the common loop:
    registry discovery -> ThunderOMLX retry/backfill -> QMD file index ->
    embedding -> extracted state advancement -> health audit.
    """
    db = str(Path(args.db).expanduser())
    steps: list[dict[str, Any]] = []

    if args.discover:
        if args.discover_raw_limit > 0:
            steps.append(
                _run_cmd(
                    _python_lib_cmd(
                        "knowledge_ingest_dispatcher.py",
                        "--db",
                        db,
                        "--json",
                        "discover-sources",
                        "--source-dir",
                        args.raw_dir,
                        "--limit",
                        str(args.discover_raw_limit),
                    ),
                    timeout=args.timeout_sec,
                )
            )
        if args.discover_vault_limit > 0:
            steps.append(
                _run_cmd(
                    _python_lib_cmd(
                        "knowledge_ingest_dispatcher.py",
                        "--db",
                        db,
                        "--json",
                        "discover-vault",
                        "--vault",
                        args.vault,
                        "--limit",
                        str(args.discover_vault_limit),
                    ),
                    timeout=args.timeout_sec,
                )
            )

    extract_cmd = _python_lib_cmd(
        "knowledge-semantic-extract.py",
        "--registry-db",
        db,
        "--max-chars",
        str(args.max_chars),
        "--max-tokens",
        str(args.max_tokens),
        "--timeout-sec",
        str(args.extract_timeout_sec),
        "--max-retries",
        str(args.max_retries),
        "--retry-backoff-sec",
        str(args.retry_backoff_sec),
        "--json",
        "supervised-backfill",
        "--source-dir",
        args.raw_dir,
        "--batch-size",
        str(args.batch_size),
        "--max-batches",
        str(args.max_batches),
        "--stale-minutes",
        str(args.stale_minutes),
        "--reap-limit",
        str(args.reap_limit),
        "--stop-on-error",
    )
    if args.force_extract:
        extract_cmd.append("--force")
    extract_step = _run_cmd(
        extract_cmd,
        timeout=args.extract_timeout_sec * max(args.batch_size, 1) * max(args.max_batches, 1) + 120,
    )
    steps.append(extract_step)
    if not extract_step["ok"] and not args.continue_on_extract_failure:
        payload = {
            "ok": False,
            "stopped_after": "semantic-extract",
            "reason": "extract step failed; QMD/index/embed steps skipped to avoid noisy no-op closure",
            "steps": [
                {
                    "cmd": " ".join(step["cmd"]),
                    "ok": step["ok"],
                    "returncode": step["returncode"],
                    "json": step.get("json"),
                    "stderr_tail": step.get("stderr", ""),
                }
                for step in steps
            ],
        }
        emit(payload, args.json)
        return 1

    steps.append(
        _run_cmd(
            _python_lib_cmd(
                "knowledge_qmd_indexer.py",
                "--db",
                db,
                "changed-only-reindex",
                "--layers",
                "raw,vault,semantic",
                "--execute",
                "--timeout-sec",
                str(args.qmd_timeout_sec),
            ),
            timeout=args.qmd_timeout_sec + 120,
        )
    )

    if not args.skip_embed:
        steps.append(_run_cmd(["solar-harness", "wiki", "qmd-embed", "run-now"], timeout=args.qmd_timeout_sec))

    steps.append(_run_cmd(_python_lib_cmd("knowledge_qmd_indexer.py", "--db", db, "advance-indexed-states"), timeout=args.timeout_sec))

    ok = all(step["ok"] for step in steps)
    payload = {
        "ok": ok,
        "steps": [
            {
                "cmd": " ".join(step["cmd"]),
                "ok": step["ok"],
                "returncode": step["returncode"],
                "json": step.get("json"),
                "stderr_tail": step.get("stderr", ""),
            }
            for step in steps
        ],
    }
    emit(payload, args.json)
    return 0 if ok else 1


def _iter_markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".markdown"}:
            continue
        parts = set(path.parts)
        text_path = str(path)
        if ".obsidian" in parts or ".git" in parts:
            continue
        if "/.spans/" in text_path or "/.materialized/" in text_path:
            continue
        files.append(path)
    return files


def _registry_snapshot(db_path: Path) -> dict[str, Any]:
    registry.migrate(db_path)
    with registry.connect(db_path) as conn:
        rows = list(conn.execute("SELECT doc_id, source_kind, source_path, current_state FROM documents"))
        output_rows = list(conn.execute("SELECT kind, path FROM extract_outputs"))
        validation_rows = list(conn.execute("SELECT passed, error_code FROM validation_results"))
    by_kind: dict[str, int] = {}
    by_state: dict[str, int] = {}
    registered_paths: set[str] = set()
    for row in rows:
        by_kind[row["source_kind"]] = by_kind.get(row["source_kind"], 0) + 1
        by_state[row["current_state"]] = by_state.get(row["current_state"], 0) + 1
        registered_paths.add(str(Path(row["source_path"]).expanduser()))
    output_paths_by_kind: dict[str, set[str]] = {}
    for row in output_rows:
        output_paths_by_kind.setdefault(row["kind"], set()).add(str(Path(row["path"]).expanduser()))
    failed_validations = sum(1 for row in validation_rows if int(row["passed"]) == 0)
    return {
        "document_count": len(rows),
        "by_kind": by_kind,
        "by_state": by_state,
        "registered_paths": registered_paths,
        "extract_output_paths_by_kind": output_paths_by_kind,
        "validation_total": len(validation_rows),
        "validation_failed": failed_validations,
    }


def _qmd_snapshot(skip: bool) -> dict[str, Any]:
    if skip:
        return {"available": False, "skipped": True}
    try:
        proc = subprocess.run(
            ["solar-harness", "wiki", "qmd-status"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    total = None
    vectors = None
    updated = None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Total:"):
            try:
                total = int(stripped.split(":", 1)[1].split()[0])
            except Exception:
                pass
        elif stripped.startswith("Vectors:"):
            try:
                vectors = int(stripped.split(":", 1)[1].split()[0])
            except Exception:
                pass
        elif stripped.startswith("Updated:"):
            updated = stripped.split(":", 1)[1].strip()
    return {
        "available": proc.returncode == 0,
        "returncode": proc.returncode,
        "indexed_files": total,
        "vectors": vectors,
        "updated": updated,
        "stderr": proc.stderr.strip()[:500],
    }


def _sample(paths: list[str], limit: int) -> list[str]:
    if limit < 0:
        return paths
    return paths[:limit]


def _read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_or_register_source_doc(
    *,
    source_path: Path | None,
    source_sha256: str | None,
    db_path: Path,
) -> tuple[str, str]:
    if source_path is not None:
        source_text = str(source_path)
        with registry.connect(db_path) as conn:
            row = conn.execute("SELECT doc_id FROM documents WHERE source_path=?", (source_text,)).fetchone()
        if row:
            return row["doc_id"], "matched_source_path"
        if source_path.exists():
            raw_root = Path.home() / "Knowledge" / "_raw"
            source_kind, source_adapter, doc_type = adapters.classify_raw_source(source_path, raw_root)
            doc = registry.upsert_document(
                source_kind=source_kind,
                source_path=source_text,
                source_adapter=source_adapter,
                content_kind="markdown",
                declared_doc_type=doc_type,
                source_sha256=source_sha256 or _file_sha256(source_path),
                current_state="RAW_MATERIALIZED",
                db_path=db_path,
            )
            return doc["doc_id"], "registered_source_path"
    fallback_path = str(source_path) if source_path is not None else "unknown"
    doc = registry.upsert_document(
        source_kind="legacy_extracted",
        source_path=fallback_path,
        source_adapter="legacy_extracted_importer",
        content_kind="markdown",
        declared_doc_type="legacy_extracted_output",
        source_sha256=source_sha256 or registry.sha256_text(fallback_path),
        current_state="NEEDS_REVIEW",
        ingest_policy="legacy",
        extract_policy="off",
        provenance_quality="inferred",
        db_path=db_path,
    )
    return doc["doc_id"], "registered_legacy_needs_review"


def drain_extract_failed_retryable(db_path: Path, max_retries: int = MAX_RETRY_ATTEMPTS,
                                    backoff_base: float = RETRY_BACKOFF_BASE_SEC) -> dict[str, Any]:
    """Drain EXTRACT_FAILED_RETRYABLE documents: retry up to max_retries times."""
    import time as _time
    registry.migrate(db_path)
    retried = 0
    skipped = 0
    with registry.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT doc_id, source_kind, source_path, updated_at FROM documents "
            "WHERE current_state = 'EXTRACT_FAILED_RETRYABLE'"
        ))
    for row in rows:
        doc_id = row["doc_id"]
        # Check repair_count in extract_jobs
        with registry.connect(db_path) as conn:
            job = conn.execute(
                "SELECT repair_count FROM extract_jobs WHERE doc_id = ? ORDER BY created_at DESC LIMIT 1",
                (doc_id,),
            ).fetchone()
        repair_count = job["repair_count"] if job else 0
        if repair_count >= max_retries:
            # Exceeded max retries → DONE_RAW_ONLY_WARN
            registry.transition_document(doc_id, "EXTRACT_FAILED_RETRYABLE", "DONE_RAW_ONLY_WARN", db_path=db_path)
            skipped += 1
        else:
            # Re-queue for extraction
            registry.transition_document(doc_id, "EXTRACT_FAILED_RETRYABLE", "THUNDEROMLX_EXTRACT_RUNNING", db_path=db_path)
            retried += 1
            _time.sleep(backoff_base * (2 ** min(repair_count, 3)))
    return {"retried": retried, "skipped_to_warn": skipped, "total": len(rows)}


def drain_extract_eligible_skip(db_path: Path) -> dict[str, Any]:
    """Skip documents with extract_policy=skip from EXTRACT_ELIGIBLE to DONE_RAW_ONLY_WARN."""
    registry.migrate(db_path)
    skipped = 0
    with registry.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT doc_id FROM documents "
            "WHERE current_state = 'EXTRACT_ELIGIBLE' AND extract_policy = 'skip'"
        ))
    for row in rows:
        registry.transition_document(doc_id=row["doc_id"], from_state="EXTRACT_ELIGIBLE",
                                    to_state="DONE_RAW_ONLY_WARN", db_path=db_path)
        skipped += 1
    return {"skipped": skipped}


def cmd_drain_retry(args: argparse.Namespace) -> int:
    result = drain_extract_failed_retryable(Path(args.db).expanduser())
    emit({"ok": True, **result}, args.json)
    return 0


def cmd_drain_skip(args: argparse.Namespace) -> int:
    result = drain_extract_eligible_skip(Path(args.db).expanduser())
    emit({"ok": True, **result}, args.json)
    return 0


def _cmd_discover_adapter(adapter_key: str, args: argparse.Namespace) -> int:
    """Generic discover command for B4 adapters."""
    root = Path(args.source_dir).expanduser()
    limit = args.limit
    db_path = Path(args.db).expanduser()
    registry.migrate(db_path)
    count = 0
    docs: list[dict[str, Any]] = []
    span_count = 0
    for path, source_kind, source_adapter, doc_type in adapters.iter_adapter_sources(root, adapter_key, limit=limit):
        sha = registry.hashlib.sha256(path.read_bytes()).hexdigest()
        doc = registry.upsert_document(
            source_kind=source_kind,
            source_path=str(path),
            source_adapter=source_adapter,
            content_kind="markdown",
            declared_doc_type=doc_type,
            source_sha256=sha,
            current_state="RAW_MATERIALIZED",
            db_path=db_path,
        )
        if args.build_spans:
            span_info = _write_and_register_spans(path=path, doc=doc, source_kind=source_kind, args=args)
            doc["span_sidecar_path"] = span_info["sidecar_path"]
            doc["span_count"] = span_info["span_count"]
            span_count += span_info["span_count"]
        docs.append(doc)
        count += 1
    emit({"ok": True, "adapter": adapter_key, "source_dir": str(root), "count": count, "span_count": span_count, "documents": docs if args.verbose else []}, args.json)
    return 0


def cmd_discover_youtube(args: argparse.Namespace) -> int:
    return _cmd_discover_adapter("youtube_transcript", args)


def cmd_discover_github(args: argparse.Namespace) -> int:
    return _cmd_discover_adapter("github_trends", args)


def cmd_discover_pdf(args: argparse.Namespace) -> int:
    return _cmd_discover_adapter("pdf_manual", args)


def cmd_discover_accepted(args: argparse.Namespace) -> int:
    return _cmd_discover_adapter("accepted_sprint", args)


def cmd_discover_solar(args: argparse.Namespace) -> int:
    return _cmd_discover_adapter("solar_artifact", args)


def cmd_coverage_report(args: argparse.Namespace) -> int:
    """Coverage report: per source_kind document counts + state breakdown, flag <20 samples."""
    db_path = Path(args.db).expanduser()
    registry.migrate(db_path)
    with registry.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT source_kind, current_state, COUNT(*) as cnt "
            "FROM documents GROUP BY source_kind, current_state ORDER BY source_kind, current_state"
        ))
    all_kinds = sorted({r["source_kind"] for r in rows})
    report: dict[str, Any] = {}
    warnings: list[str] = []
    for kind in all_kinds:
        kind_rows = [r for r in rows if r["source_kind"] == kind]
        total = sum(r["cnt"] for r in kind_rows)
        states = {r["current_state"]: r["cnt"] for r in kind_rows}
        report[kind] = {"total": total, "states": states}
        if total < 20:
            warnings.append(f"{kind}: only {total} documents (< 20)")
    payload = {"ok": True, "source_kinds": report, "warnings": warnings}
    emit(payload, args.json)
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    dashboard = knowledge_dashboard.gather_dashboard(db_path)
    html_path = getattr(args, "html", "") or ""
    if html_path:
        hp = Path(html_path).expanduser()
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(knowledge_dashboard.render_html(dashboard), encoding="utf-8")
        dashboard["html_path"] = str(hp)
    print(json.dumps(dashboard, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_import_legacy_extracted(args: argparse.Namespace) -> int:
    extracted_root = Path(args.extracted_dir).expanduser()
    db_path = Path(args.db).expanduser()
    registry.migrate(db_path)
    imported = 0
    skipped = 0
    failed = 0
    details: list[dict[str, Any]] = []
    with registry.connect(db_path) as conn:
        known = {str(Path(row["path"]).expanduser()) for row in conn.execute("SELECT path FROM extract_outputs")}

    for path in _iter_markdown_files(extracted_root):
        if not path.name.endswith(".extracted.md"):
            continue
        path_text = str(path)
        if path_text in known and not args.force:
            skipped += 1
            continue
        try:
            fm = _read_frontmatter(path)
            source_path = Path(fm["source_path"]).expanduser() if fm.get("source_path") else None
            source_sha = fm.get("source_sha256")
            doc_id, source_match = _find_or_register_source_doc(source_path=source_path, source_sha256=source_sha, db_path=db_path)
            output_sha = _file_sha256(path)
            job_id = "legacy_extract_" + registry.sha256_text(f"{doc_id}:{path_text}:{output_sha}")[:24]
            ts = registry.now_iso()
            model = fm.get("proxy_model") or fm.get("local_model") or "legacy_unknown"
            prompt = fm.get("prompt_version") or "legacy_unknown"
            report_path = path.with_name(path.name.replace(".extracted.md", ".extracted.extract.report.json"))
            with registry.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO extract_jobs(
                      job_id, doc_id, source_span_ids, prompt_template_id, model,
                      state, created_at, updated_at, repair_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (job_id, doc_id, json.dumps([], ensure_ascii=False), prompt, model, "legacy_imported", ts, ts),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO extract_outputs(output_id, job_id, kind, path, sha256, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("out_" + registry.sha256_text(f"{job_id}:extracted_md")[:24], job_id, "extracted_md", path_text, output_sha, ts),
                )
                if report_path.exists():
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO extract_outputs(output_id, job_id, kind, path, sha256, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        ("out_" + registry.sha256_text(f"{job_id}:report_json")[:24], job_id, "report_json", str(report_path), _file_sha256(report_path), ts),
                    )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO validation_results(result_id, job_id, layer, passed, error_code, detail_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "val_" + registry.sha256_text(f"{job_id}:legacy_imported")[:24],
                        job_id,
                        "extracted",
                        1,
                        None,
                        json.dumps({"legacy_imported": True, "source_match": source_match, "frontmatter": fm}, ensure_ascii=False, sort_keys=True),
                        ts,
                    ),
                )
                conn.commit()
            imported += 1
            if args.verbose:
                details.append({"path": path_text, "doc_id": doc_id, "job_id": job_id, "source_match": source_match})
        except Exception as exc:
            failed += 1
            if args.verbose:
                details.append({"path": path_text, "error": str(exc)})
    payload = {"ok": failed == 0, "extracted_dir": str(extracted_root), "imported": imported, "skipped": skipped, "failed": failed, "details": details}
    emit(payload, args.json)
    return 0 if failed == 0 else 1


def cmd_reconcile(args: argparse.Namespace) -> int:
    knowledge_root = Path(args.knowledge_root).expanduser()
    raw_root = Path(args.raw_dir).expanduser()
    vault_root = Path(args.vault).expanduser()
    extracted_root = Path(args.extracted_dir).expanduser()
    db_path = Path(args.db).expanduser()
    sample_limit = args.sample_limit

    raw_md = _iter_markdown_files(raw_root)
    vault_md: list[Path] = []
    for folder in args.vault_include:
        vault_md.extend(_iter_markdown_files(vault_root / folder))
    extracted_md = _iter_markdown_files(extracted_root)
    all_md = _iter_markdown_files(knowledge_root)

    registry_state = _registry_snapshot(db_path)
    registered_paths: set[str] = registry_state["registered_paths"]
    extract_outputs: dict[str, set[str]] = registry_state["extract_output_paths_by_kind"]

    discoverable_paths = {str(path) for path in raw_md + vault_md}
    missing_in_registry = sorted(path for path in discoverable_paths if path not in registered_paths)
    existing_registered = sorted(path for path in registered_paths if Path(path).exists())
    registered_missing = sorted(path for path in registered_paths if not Path(path).exists())
    extracted_paths = sorted(str(path) for path in extracted_md)
    known_extracted_outputs = set()
    for kind, paths in extract_outputs.items():
        if "extract" in kind or "semantic" in kind or kind.endswith("_md") or kind == "extracted_md":
            known_extracted_outputs.update(paths)
    orphan_extracted = sorted(path for path in extracted_paths if path not in known_extracted_outputs)

    registry_coverage = (len(discoverable_paths) - len(missing_in_registry)) / len(discoverable_paths) if discoverable_paths else 1.0
    qmd = _qmd_snapshot(args.skip_qmd)
    qmd_indexed = qmd.get("indexed_files") if qmd.get("available") else None
    qmd_vs_discoverable_ratio = (qmd_indexed / len(discoverable_paths)) if isinstance(qmd_indexed, int) and discoverable_paths else None

    ok = registry_coverage >= args.min_registry_coverage and not orphan_extracted and not registered_missing
    payload = {
        "ok": ok,
        "knowledge_root": str(knowledge_root),
        "counts": {
            "filesystem_md_total": len(all_md),
            "discoverable_raw_vault_md": len(discoverable_paths),
            "raw_md": len(raw_md),
            "vault_md": len(vault_md),
            "extracted_md": len(extracted_md),
            "registry_documents": registry_state["document_count"],
            "existing_registered_paths": len(existing_registered),
            "missing_in_registry": len(missing_in_registry),
            "registered_missing_file": len(registered_missing),
            "orphan_extracted_outputs": len(orphan_extracted),
        },
        "coverage": {
            "registry_coverage": registry_coverage,
            "min_registry_coverage": args.min_registry_coverage,
            "qmd_indexed_vs_discoverable_ratio": qmd_vs_discoverable_ratio,
        },
        "registry": {
            "by_kind": registry_state["by_kind"],
            "by_state": registry_state["by_state"],
            "validation_total": registry_state["validation_total"],
            "validation_failed": registry_state["validation_failed"],
        },
        "qmd": qmd,
        "samples": {
            "missing_in_registry": _sample(missing_in_registry, sample_limit),
            "registered_missing_file": _sample(registered_missing, sample_limit),
            "orphan_extracted_outputs": _sample(orphan_extracted, sample_limit),
        },
    }
    emit(payload, args.json)
    return 0 if ok or args.no_fail else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solar Knowledge ingest dispatcher")
    parser.add_argument("--db", default=str(registry.DEFAULT_DB))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    children: list[argparse.ArgumentParser] = []
    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)
    children.append(status)

    qmd_wm = sub.add_parser("qmd-watermarks")
    qmd_wm.set_defaults(func=cmd_qmd_watermarks)
    children.append(qmd_wm)

    migrate = sub.add_parser("migrate")
    migrate.set_defaults(func=cmd_migrate)
    children.append(migrate)

    submit = sub.add_parser("submit-event")
    submit.add_argument("--source-kind", required=True)
    submit.add_argument("--source-path", required=True)
    submit.add_argument("--source-adapter", required=True)
    submit.add_argument("--content-kind", default="markdown")
    submit.add_argument("--declared-doc-type")
    submit.add_argument("--source-sha256")
    submit.add_argument("--state", default="NEW")
    submit.add_argument("--ingest-policy", default="default")
    submit.add_argument("--extract-policy", default="default")
    submit.add_argument("--provenance-quality", default="observed")
    submit.set_defaults(func=cmd_submit_event)
    children.append(submit)

    raw = sub.add_parser("discover-raw")
    raw.add_argument("--source-dir", default=str(Path.home() / "Knowledge" / "_raw"))
    raw.add_argument("--declared-doc-type")
    raw.add_argument("--limit", type=int, default=20)
    raw.add_argument("--verbose", action="store_true")
    raw.add_argument("--build-spans", action="store_true", default=True)
    raw.add_argument("--span-root")
    raw.add_argument("--max-span-lines", type=int, default=120)
    raw.set_defaults(func=cmd_discover_raw)
    children.append(raw)

    sources = sub.add_parser("discover-sources")
    sources.add_argument("--source-dir", default=str(Path.home() / "Knowledge" / "_raw"))
    sources.add_argument("--source-kind")
    sources.add_argument("--limit", type=int, default=100)
    sources.add_argument("--include-dispatch", action="store_true")
    sources.add_argument("--verbose", action="store_true")
    sources.add_argument("--build-spans", action="store_true", default=True)
    sources.add_argument("--span-root")
    sources.add_argument("--max-span-lines", type=int, default=120)
    sources.add_argument("--materialized-root", default=str(Path.home() / "Knowledge" / "_raw" / ".materialized"))
    sources.set_defaults(func=cmd_discover_sources)
    children.append(sources)

    vault = sub.add_parser("discover-vault")
    vault.add_argument("--vault", default=str(Path.home() / "Knowledge"))
    vault.add_argument("--include", nargs="*")
    vault.add_argument("--limit", type=int, default=20)
    vault.add_argument("--verbose", action="store_true")
    vault.add_argument("--build-spans", action="store_true", default=True)
    vault.add_argument("--span-root")
    vault.add_argument("--max-span-lines", type=int, default=120)
    vault.set_defaults(func=cmd_discover_vault)
    children.append(vault)

    process = sub.add_parser("process-queue")
    process.set_defaults(func=cmd_process_queue)
    children.append(process)

    pipeline = sub.add_parser("run-pipeline")
    pipeline.add_argument("--raw-dir", default=str(Path.home() / "Knowledge" / "_raw"))
    pipeline.add_argument("--vault", default=str(Path.home() / "Knowledge"))
    pipeline.add_argument("--discover", action="store_true")
    pipeline.add_argument("--discover-raw-limit", type=int, default=0)
    pipeline.add_argument("--discover-vault-limit", type=int, default=0)
    pipeline.add_argument("--batch-size", type=int, default=1)
    pipeline.add_argument("--max-batches", type=int, default=1)
    pipeline.add_argument("--stale-minutes", type=int, default=30)
    pipeline.add_argument("--reap-limit", type=int, default=20)
    pipeline.add_argument("--max-chars", type=int, default=18000)
    pipeline.add_argument("--max-tokens", type=int, default=5200)
    pipeline.add_argument("--extract-timeout-sec", type=int, default=720)
    pipeline.add_argument("--max-retries", type=int, default=2)
    pipeline.add_argument("--retry-backoff-sec", type=float, default=10.0)
    pipeline.add_argument("--qmd-timeout-sec", type=int, default=900)
    pipeline.add_argument("--timeout-sec", type=int, default=120)
    pipeline.add_argument("--force-extract", action="store_true")
    pipeline.add_argument("--continue-on-extract-failure", action="store_true")
    pipeline.add_argument("--skip-embed", action="store_true")
    pipeline.set_defaults(func=cmd_run_pipeline)
    children.append(pipeline)

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--knowledge-root", default=str(Path.home() / "Knowledge"))
    reconcile.add_argument("--raw-dir", default=str(Path.home() / "Knowledge" / "_raw"))
    reconcile.add_argument("--vault", default=str(Path.home() / "Knowledge"))
    reconcile.add_argument("--vault-include", nargs="*", default=list(adapters.DEFAULT_VAULT_FOLDERS))
    reconcile.add_argument("--extracted-dir", default=str(Path.home() / "Knowledge" / "_extracted"))
    reconcile.add_argument("--sample-limit", type=int, default=20)
    reconcile.add_argument("--min-registry-coverage", type=float, default=0.99)
    reconcile.add_argument("--skip-qmd", action="store_true")
    reconcile.add_argument("--no-fail", action="store_true")
    reconcile.set_defaults(func=cmd_reconcile)
    children.append(reconcile)

    legacy = sub.add_parser("import-legacy-extracted")
    legacy.add_argument("--extracted-dir", default=str(Path.home() / "Knowledge" / "_extracted"))
    legacy.add_argument("--force", action="store_true")
    legacy.add_argument("--verbose", action="store_true")
    legacy.set_defaults(func=cmd_import_legacy_extracted)
    children.append(legacy)

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--html", default="", help="Write HTML dashboard to this path")
    dashboard.set_defaults(func=cmd_dashboard)
    children.append(dashboard)

    coverage = sub.add_parser("coverage-report")
    coverage.set_defaults(func=cmd_coverage_report)
    children.append(coverage)

    drain_retry = sub.add_parser("drain-retry")
    drain_retry.set_defaults(func=cmd_drain_retry)
    children.append(drain_retry)

    drain_skip = sub.add_parser("drain-skip")
    drain_skip.set_defaults(func=cmd_drain_skip)
    children.append(drain_skip)

    # B4: 5 new adapter discover commands
    for adapter_key, cmd_name in [
        ("youtube", "discover-youtube"),
        ("github", "discover-github"),
        ("pdf", "discover-pdf"),
        ("accepted", "discover-accepted"),
        ("solar", "discover-solar"),
    ]:
        p = sub.add_parser(cmd_name)
        p.add_argument("--source-dir", default=str(Path.home() / "Knowledge" / "_raw"))
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--build-spans", action="store_true", default=True)
        p.add_argument("--span-root")
        p.add_argument("--max-span-lines", type=int, default=120)
        func_map = {
            "discover-youtube": cmd_discover_youtube,
            "discover-github": cmd_discover_github,
            "discover-pdf": cmd_discover_pdf,
            "discover-accepted": cmd_discover_accepted,
            "discover-solar": cmd_discover_solar,
        }
        p.set_defaults(func=func_map[cmd_name])
        children.append(p)

    for child in children:
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        child.add_argument("--db", default=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

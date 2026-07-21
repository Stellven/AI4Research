#!/usr/bin/env python3
"""QMD microbatch control-plane watermarks for Solar Knowledge ingest."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry


LAYERS = ("raw", "vault", "semantic")
DEFAULT_LOCK_PATH = Path.home() / "Knowledge" / "_registry" / "qmd-update.lock"


def _connect(db_path: Path):
    registry.migrate(db_path)
    conn = registry.connect(db_path)
    ensure_manifest_columns(conn)
    return conn


def ensure_manifest_columns(conn) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(qmd_index_events)")}
    additions = {
        "path": "TEXT",
        "indexed_sha256": "TEXT",
        "indexed_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE qmd_index_events ADD COLUMN {name} {ddl}")
    conn.commit()


def watermarks(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = [registry.row_to_dict(r) for r in conn.execute("SELECT * FROM watermarks ORDER BY layer")]
    return {"ok": True, "db": str(db_path), "watermarks": rows}


def update_watermark(
    *,
    layer: str,
    pending_delta: int = 0,
    failed_delta: int = 0,
    indexed: bool = False,
    batch_id: str | None = None,
    db_path: Path = registry.DEFAULT_DB,
) -> dict[str, Any]:
    if layer not in LAYERS:
        raise ValueError(f"invalid layer: {layer}")
    ts = registry.now_iso()
    batch_id = batch_id or f"qmd-{layer}-{uuid.uuid4().hex[:10]}"
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE watermarks
            SET pending_count=max(0, pending_count + ?),
                failed_count=max(0, failed_count + ?),
                last_indexed_ts=CASE WHEN ? THEN ? ELSE last_indexed_ts END,
                last_batch_id=CASE WHEN ? THEN ? ELSE last_batch_id END,
                last_batch_ts=CASE WHEN ? THEN ? ELSE last_batch_ts END,
                updated_at=?
            WHERE layer=?
            """,
            (pending_delta, failed_delta, 1 if indexed else 0, ts, 1 if indexed else 0, batch_id, 1 if indexed else 0, ts, ts, layer),
        )
        conn.commit()
    return {"ok": True, "layer": layer, "batch_id": batch_id, "indexed": indexed, "updated_at": ts}


def record_qmd_event(
    *,
    doc_id: str,
    layer: str,
    qmd_status: str,
    qmd_batch_id: str,
    path: str | None = None,
    indexed_sha256: str | None = None,
    db_path: Path = registry.DEFAULT_DB,
) -> dict[str, Any]:
    event_id = f"qmd_evt_{uuid.uuid4().hex[:24]}"
    ts = registry.now_iso()
    path = _norm_path(path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO qmd_index_events(event_id, doc_id, layer, qmd_batch_id, qmd_status, ts, path, indexed_sha256, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, doc_id, layer, qmd_batch_id, qmd_status, ts, path, indexed_sha256, ts if qmd_status == "indexed" else None),
        )
        conn.commit()
    return {"event_id": event_id, "doc_id": doc_id, "layer": layer, "qmd_status": qmd_status}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return os.path.normpath(str(Path(str(path)).expanduser()))


def _latest_indexed_hash(conn, doc_id: str, layer: str, path: str) -> str | None:
    path = _norm_path(path) or path
    row = conn.execute(
        """
        SELECT indexed_sha256
        FROM qmd_index_events
        WHERE doc_id=? AND layer=? AND path=? AND qmd_status='indexed'
        ORDER BY indexed_at DESC, ts DESC, event_id DESC
        LIMIT 1
        """,
        (doc_id, layer, path),
    ).fetchone()
    return str(row["indexed_sha256"]) if row and row["indexed_sha256"] else None


def _transition_document(conn, *, doc_id: str, to_state: str, batch_id: str, payload: dict[str, Any]) -> bool:
    row = conn.execute("SELECT current_state FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        return False
    from_state = str(row["current_state"])
    if from_state == to_state:
        return False
    ts = registry.now_iso()
    conn.execute(
        "UPDATE documents SET current_state=?, updated_at=? WHERE doc_id=?",
        (to_state, ts, doc_id),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO ingest_events(event_id, doc_id, event_kind, from_state, to_state, source_adapter, payload_json, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"evt_{hashlib.sha256(f'{doc_id}:{from_state}:{to_state}:{batch_id}:{ts}'.encode()).hexdigest()[:24]}",
            doc_id,
            "qmd_extracted_index_state",
            from_state,
            to_state,
            "knowledge_qmd_indexer",
            json.dumps(payload | {"batch_id": batch_id}, ensure_ascii=False, sort_keys=True),
            ts,
        ),
    )
    return True


def _advance_extracted_doc_states(conn, docs: list[dict[str, Any]], *, batch_id: str) -> dict[str, int]:
    """Move successfully indexed extracted documents out of pending.

    The two-step event trail preserves the explicit EXTRACTED_QMD_INDEXED state
    while leaving fully indexed docs in DONE for health dashboards.
    """
    advanced_indexed = 0
    advanced_done = 0
    seen: set[str] = set()
    for doc in docs:
        if doc.get("layer") != "semantic":
            continue
        doc_id = str(doc["doc_id"])
        if doc_id in seen:
            continue
        seen.add(doc_id)
        row = conn.execute("SELECT current_state FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        if not row or str(row["current_state"]) != "EXTRACTED_QMD_INDEX_PENDING":
            continue
        payload = {"layer": "semantic", "path": doc.get("path"), "indexed_sha256": doc.get("sha")}
        if _transition_document(conn, doc_id=doc_id, to_state="EXTRACTED_QMD_INDEXED", batch_id=batch_id, payload=payload):
            advanced_indexed += 1
        if _transition_document(conn, doc_id=doc_id, to_state="DONE", batch_id=batch_id, payload=payload | {"previous_terminal_state": "EXTRACTED_QMD_INDEXED"}):
            advanced_done += 1
    return {"extracted_indexed": advanced_indexed, "done": advanced_done}


def _candidate_docs(conn, layers: set[str]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if "raw" in layers or "vault" in layers:
        for row in conn.execute(
            """
            SELECT doc_id, source_kind, source_path, source_sha256, current_state
            FROM documents
            WHERE current_state NOT IN ('IGNORED', 'NEEDS_REVIEW')
              AND extract_policy != 'off'
            """
        ):
            layer = "vault" if row["source_kind"] == "obsidian_vault" else "raw"
            if layer not in layers:
                continue
            path = Path(str(row["source_path"])).expanduser()
            if not path.exists():
                continue
            digest = str(row["source_sha256"]) if row["source_sha256"] else _file_sha256(path)
            docs.append({"doc_id": row["doc_id"], "layer": layer, "path": _norm_path(path), "sha": digest})
    if "semantic" in layers:
        latest_by_path: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in conn.execute(
            """
            SELECT j.doc_id, o.path, o.sha256, o.created_at
            FROM extract_outputs o
            JOIN extract_jobs j ON j.job_id=o.job_id
            JOIN documents d ON d.doc_id=j.doc_id
            WHERE o.kind='extracted_md'
              AND j.state IN ('extract_indexed', 'legacy_imported')
            ORDER BY o.created_at ASC
            """
        ):
            path = Path(str(row["path"])).expanduser()
            if not path.exists():
                continue
            # Use the file hash as the index manifest truth. Legacy outputs can
            # contain multiple rows for the same path after re-extraction.
            # Deduping by path avoids an old output hash creating a permanent
            # changed-only false positive.
            norm_path = _norm_path(path)
            key = (str(row["doc_id"]), "semantic", str(norm_path))
            latest_by_path[key] = {
                "doc_id": row["doc_id"],
                "layer": "semantic",
                "path": norm_path,
                "sha": _file_sha256(path),
                "created_at": row["created_at"],
            }
        docs.extend({k: {kk: vv for kk, vv in v.items() if kk != "created_at"} for k, v in latest_by_path.items()}.values())
    return docs


def cmd_changed_only_reindex(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    layers = set(args.layers.split(","))
    batch_id = args.batch_id or f"qmd-changed-{uuid.uuid4().hex[:10]}"
    with _connect(db_path) as conn:
        candidates = _candidate_docs(conn, layers)
        indexed_candidates: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        for doc in candidates:
            latest_hash = _latest_indexed_hash(conn, doc["doc_id"], doc["layer"], doc["path"])
            if args.force or latest_hash != doc["sha"]:
                changed.append(doc)
            elif doc["layer"] == "semantic":
                indexed_candidates.append(doc)
    if args.limit:
        changed = changed[: args.limit]
    if args.execute and changed:
        lock_path = Path(args.lock_path).expanduser()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + args.lock_timeout_sec
        with lock_path.open("w", encoding="utf-8") as lock_file:
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out waiting for QMD update lock: {lock_path}")
                    time.sleep(1)
            lock_file.write(json.dumps({"batch_id": batch_id, "layers": sorted(layers), "pid": os.getpid(), "ts": registry.now_iso()}) + "\n")
            lock_file.flush()
            subprocess.run(["solar-harness", "wiki", "qmd-update"], check=True, timeout=args.timeout_sec)
        with _connect(db_path) as conn:
            for doc in changed:
                conn.execute(
                    """
                    INSERT INTO qmd_index_events(event_id, doc_id, layer, qmd_batch_id, qmd_status, ts, path, indexed_sha256, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"qmd_evt_{uuid.uuid4().hex[:24]}",
                        doc["doc_id"],
                        doc["layer"],
                        batch_id,
                        "indexed",
                        registry.now_iso(),
                        _norm_path(doc["path"]),
                        doc["sha"],
                        registry.now_iso(),
                    ),
                )
            state_advances = _advance_extracted_doc_states(conn, changed, batch_id=batch_id)
            conn.commit()
        for layer in layers:
            update_watermark(layer=layer, indexed=True, batch_id=batch_id, db_path=db_path)
    else:
        state_advances = {"extracted_indexed": 0, "done": 0}
    if args.execute:
        with _connect(db_path) as conn:
            extra_advances = _advance_extracted_doc_states(conn, indexed_candidates, batch_id=batch_id)
            conn.commit()
        state_advances = {
            "extracted_indexed": state_advances["extracted_indexed"] + extra_advances["extracted_indexed"],
            "done": state_advances["done"] + extra_advances["done"],
        }
    payload = {
        "ok": True,
        "mode": "execute" if args.execute else "dry_run",
        "batch_id": batch_id,
        "layers": sorted(layers),
        "candidate_count": len(candidates),
        "changed_count": len(changed),
        "state_advances": state_advances,
        "changed": changed if args.verbose else [],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_advance_indexed_states(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    batch_id = args.batch_id or f"qmd-advance-{uuid.uuid4().hex[:10]}"
    with _connect(db_path) as conn:
        candidates = [doc for doc in _candidate_docs(conn, {"semantic"}) if _latest_indexed_hash(conn, doc["doc_id"], doc["layer"], doc["path"]) == doc["sha"]]
        if args.limit:
            candidates = candidates[: args.limit]
        state_advances = _advance_extracted_doc_states(conn, candidates, batch_id=batch_id)
        conn.commit()
    payload = {
        "ok": True,
        "batch_id": batch_id,
        "candidate_count": len(candidates),
        "state_advances": state_advances,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_watermarks(args: argparse.Namespace) -> int:
    print(json.dumps(watermarks(Path(args.db).expanduser()), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_mark_indexed(args: argparse.Namespace) -> int:
    batch_id = args.batch_id or f"qmd-{args.layer}-{uuid.uuid4().hex[:10]}"
    result = update_watermark(layer=args.layer, indexed=True, batch_id=batch_id, db_path=Path(args.db).expanduser())
    for doc_id in args.doc_id or []:
        record_qmd_event(doc_id=doc_id, layer=args.layer, qmd_status="indexed", qmd_batch_id=batch_id, db_path=Path(args.db).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_microbatch(args: argparse.Namespace) -> int:
    paths = [Path(p).expanduser() for p in args.path or []]
    batch_id = args.batch_id or f"qmd-{args.layer}-{uuid.uuid4().hex[:10]}"
    command = ["solar-harness", "wiki", "qmd-update"]
    if args.execute:
        lock_path = Path(args.lock_path).expanduser()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + args.lock_timeout_sec
        with lock_path.open("w", encoding="utf-8") as lock_file:
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out waiting for QMD update lock: {lock_path}")
                    time.sleep(1)
            lock_file.write(json.dumps({"batch_id": batch_id, "layer": args.layer, "pid": os.getpid(), "ts": registry.now_iso()}) + "\n")
            lock_file.flush()
            subprocess.run(command, check=True, timeout=args.timeout_sec)
        mode = "execute"
    else:
        mode = "dry_run"
    if args.execute:
        result = update_watermark(layer=args.layer, indexed=True, batch_id=batch_id, db_path=Path(args.db).expanduser())
    else:
        result = {"ok": True, "layer": args.layer, "batch_id": batch_id, "indexed": False, "updated_at": registry.now_iso()}
    result.update({"mode": mode, "paths": [str(p) for p in paths], "command": command})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solar Knowledge QMD microbatch indexer")
    parser.add_argument("--db", default=str(registry.DEFAULT_DB))
    sub = parser.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watermarks")
    w.set_defaults(func=cmd_watermarks)
    mark = sub.add_parser("mark-indexed")
    mark.add_argument("--layer", choices=LAYERS, required=True)
    mark.add_argument("--batch-id")
    mark.add_argument("--doc-id", action="append")
    mark.set_defaults(func=cmd_mark_indexed)
    micro = sub.add_parser("microbatch")
    micro.add_argument("--layer", choices=LAYERS, required=True)
    micro.add_argument("--path", action="append")
    micro.add_argument("--batch-id")
    micro.add_argument("--execute", action="store_true")
    micro.add_argument("--timeout-sec", type=int, default=180)
    micro.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH))
    micro.add_argument("--lock-timeout-sec", type=int, default=600)
    micro.set_defaults(func=cmd_microbatch)
    changed = sub.add_parser("changed-only-reindex")
    changed.add_argument("--layers", default="raw,vault,semantic")
    changed.add_argument("--batch-id")
    changed.add_argument("--execute", action="store_true")
    changed.add_argument("--force", action="store_true")
    changed.add_argument("--limit", type=int, default=0)
    changed.add_argument("--verbose", action="store_true")
    changed.add_argument("--timeout-sec", type=int, default=600)
    changed.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH))
    changed.add_argument("--lock-timeout-sec", type=int, default=600)
    changed.set_defaults(func=cmd_changed_only_reindex)
    advance = sub.add_parser("advance-indexed-states")
    advance.add_argument("--batch-id")
    advance.add_argument("--limit", type=int, default=0)
    advance.set_defaults(func=cmd_advance_indexed_states)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

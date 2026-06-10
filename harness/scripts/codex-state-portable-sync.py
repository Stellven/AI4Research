#!/usr/bin/env python3
"""Portable Codex project/thread state export and import.

This intentionally does not copy Codex SQLite files raw between hosts. It
exports a narrow, schema-checked subset of project/thread metadata and imports
rows through SQLite on the target host.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_TABLES = ("threads", "thread_dynamic_tools", "thread_goals")
SCHEMA_VERSION = "codex-state-portable-v1"
DEFAULT_FROM_PREFIX = str(Path.home())


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise SystemExit(f"missing table: {table}")
    return rows


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in _table_info(conn, table)]


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = sorted(_table_info(conn, table), key=lambda r: int(r["pk"] or 0))
    return [str(row["name"]) for row in rows if int(row["pk"] or 0) > 0]


def _rewrite_value(value: Any, from_prefix: str, to_prefix: str) -> Any:
    if isinstance(value, str) and from_prefix:
        return value.replace(from_prefix, to_prefix)
    return value


def export_state(args: argparse.Namespace) -> None:
    db = Path(args.db).expanduser()
    out = Path(args.out).expanduser()
    from_prefix = args.from_prefix
    to_prefix = args.to_prefix

    with _connect(db) as conn:
        tables: dict[str, Any] = {}
        for table in args.tables:
            cols = _columns(conn, table)
            rows = []
            for row in conn.execute(f"SELECT * FROM {table}"):
                item = {col: _rewrite_value(row[col], from_prefix, to_prefix) for col in cols}
                rows.append(item)
            tables[table] = {
                "columns": cols,
                "pk": _pk_columns(conn, table),
                "rows": rows,
            }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc(),
        "source_db": str(db),
        "path_rewrite": {"from": from_prefix, "to": to_prefix},
        "tables": tables,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "out": str(out), "tables": {k: len(v["rows"]) for k, v in tables.items()}}, ensure_ascii=False))


def _backup(db: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{db.name}.{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak"
    shutil.copy2(db, target)
    return target


def import_state(args: argparse.Namespace) -> None:
    db = Path(args.db).expanduser()
    inp = Path(args.input).expanduser()
    payload = json.loads(inp.read_text())
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"unsupported schema_version: {payload.get('schema_version')}")

    backup_path = _backup(db, Path(args.backup_dir).expanduser()) if args.backup_dir else None
    changed: dict[str, int] = {}
    with _connect(db) as conn:
        with conn:
            for table, spec in payload["tables"].items():
                local_cols = _columns(conn, table)
                incoming_cols = list(spec["columns"])
                if local_cols != incoming_cols:
                    raise SystemExit(f"schema mismatch for {table}: local={local_cols} incoming={incoming_cols}")
                pk_cols = _pk_columns(conn, table)
                if pk_cols != list(spec["pk"]):
                    raise SystemExit(f"pk mismatch for {table}: local={pk_cols} incoming={spec['pk']}")
                non_pk = [col for col in incoming_cols if col not in pk_cols]
                placeholders = ", ".join("?" for _ in incoming_cols)
                columns_sql = ", ".join(incoming_cols)
                if non_pk:
                    update_sql = ", ".join(f"{col}=excluded.{col}" for col in non_pk)
                    conflict_sql = f"ON CONFLICT({', '.join(pk_cols)}) DO UPDATE SET {update_sql}"
                else:
                    conflict_sql = f"ON CONFLICT({', '.join(pk_cols)}) DO NOTHING"
                sql = f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders}) {conflict_sql}"
                count = 0
                for row in spec["rows"]:
                    conn.execute(sql, [row.get(col) for col in incoming_cols])
                    count += 1
                changed[table] = count
    print(json.dumps({"ok": True, "imported": changed, "backup": str(backup_path) if backup_path else ""}, ensure_ascii=False))


def verify_state(args: argparse.Namespace) -> None:
    db = Path(args.db).expanduser()
    with _connect(db) as conn:
        result = {}
        for table in args.tables:
            result[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(json.dumps({"ok": True, "db": str(db), "counts": result}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--db", required=True)
    exp.add_argument("--out", required=True)
    exp.add_argument("--from-prefix", default=DEFAULT_FROM_PREFIX)
    exp.add_argument("--to-prefix", default="~")
    exp.add_argument("--tables", nargs="+", default=list(DEFAULT_TABLES))
    exp.set_defaults(func=export_state)

    imp = sub.add_parser("import")
    imp.add_argument("--db", required=True)
    imp.add_argument("--input", required=True)
    imp.add_argument("--backup-dir", default="")
    imp.set_defaults(func=import_state)

    ver = sub.add_parser("verify")
    ver.add_argument("--db", required=True)
    ver.add_argument("--tables", nargs="+", default=list(DEFAULT_TABLES))
    ver.set_defaults(func=verify_state)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

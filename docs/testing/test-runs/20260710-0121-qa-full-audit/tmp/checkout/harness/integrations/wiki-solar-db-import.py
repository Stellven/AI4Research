#!/usr/bin/env python3
"""
Export Solar's SQLite knowledge stores into the Obsidian wiki raw staging area.

The script is intentionally read-only against SQLite. It writes Markdown files
under <vault>/_raw/solar-db-export/ so the existing wiki-ingest pipeline can
extract, merge, and cross-link them like any other source material.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CONFIG = Path(os.environ.get("OBSIDIAN_WIKI_CONFIG", str(Path.home() / ".obsidian-wiki" / "config")))
DEFAULT_DB = Path.home() / ".solar" / "solar.db"
DEFAULT_TABLES = (
    "solar_kb_entries",
    "knowledge_entities",
    "knowledge_claims",
    "cortex_sources",
    "evo_memory_semantic",
)
SOLAR_TERMS = (
    "solar",
    "harness",
    "symphony",
    "obsidian",
    "wiki",
    "membrain",
    "brain router",
    "cortex",
    "牛马",
    "宣告",
    "记忆系统",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_vault() -> Path:
    env = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if env:
        return Path(env).expanduser()
    if CONFIG.exists():
        for raw in CONFIG.read_text(errors="ignore").splitlines():
            if raw.startswith("OBSIDIAN_VAULT_PATH="):
                value = raw.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return Path(value).expanduser()
    return Path.home() / "Knowledge"


def slugify(value: str, fallback: str = "solar-db") -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value, flags=re.UNICODE)
    value = value.strip("-._").lower()
    return value[:90] or fallback


def yaml_scalar(value: object) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def parse_tags(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in re.split(r"[,，;；]", text.strip("[]")) if x.strip()]


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_if_changed(path: Path, text: str, dry_run: bool) -> str:
    if dry_run:
        return "dry-run"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(errors="ignore") == text:
        return "unchanged"
    path.write_text(text, encoding="utf-8")
    return "written"


def frontmatter(table: str, source_id: object, title: str, extra: dict[str, object]) -> list[str]:
    lines = [
        "---",
        "source: solar-db",
        f"source_table: {table}",
        f"source_id: {yaml_scalar(source_id)}",
        f"title: {yaml_scalar(title)}",
        f"exported_at: {utc_now()}",
        "visibility: internal",
    ]
    tags = ["solar-db", table.replace("_", "-")]
    tags.extend(parse_tags(extra.pop("tags", "")))
    tags = list(dict.fromkeys(slugify(t, "tag") for t in tags if t))
    lines.append("tags: [" + ", ".join(tags) + "]")
    for key, value in extra.items():
        if value is None or value == "":
            continue
        safe_key = re.sub(r"[^A-Za-z0-9_]", "_", key)
        if isinstance(value, (int, float)):
            lines.append(f"{safe_key}: {value}")
        else:
            lines.append(f"{safe_key}: {yaml_scalar(value)}")
    lines.extend(["---", ""])
    return lines


def section(title: str, body: object) -> list[str]:
    text = str(body if body is not None else "").strip()
    if not text:
        text = "N/A"
    return [f"## {title}", "", text, ""]


def render_row(table: str, row: sqlite3.Row) -> tuple[str, str, str]:
    data = dict(row)
    if table == "solar_kb_entries":
        source_id = data["id"]
        title = data.get("title") or f"Solar KB Entry {source_id}"
        body = frontmatter(table, source_id, title, {
            "source_name": data.get("source"),
            "importance": data.get("importance"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "tags": data.get("tags"),
        })
        body += [f"# {title}", ""]
        body += section("Source", data.get("source"))
        body += section("Content", data.get("content"))
    elif table == "knowledge_entities":
        source_id = data["entity_id"]
        title = data.get("name") or f"Knowledge Entity {source_id}"
        body = frontmatter(table, source_id, title, {
            "entity_type": data.get("type"),
            "importance": data.get("importance"),
            "access_count": data.get("access_count"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        })
        body += [f"# {title}", ""]
        body += section("Type", data.get("type"))
        body += section("Description", data.get("description"))
        body += section("Aliases", data.get("aliases"))
        body += section("Metadata", data.get("metadata"))
    elif table == "knowledge_claims":
        source_id = data["claim_id"]
        title = str(data.get("claim_text") or f"Knowledge Claim {source_id}")[:90]
        body = frontmatter(table, source_id, title, {
            "confidence": data.get("confidence"),
            "domain": data.get("domain"),
            "freshness": data.get("freshness"),
            "created_at": data.get("created_at"),
        })
        body += [f"# {title}", ""]
        body += section("Claim", data.get("claim_text"))
        body += section("Supporting Entities", data.get("supporting_entities"))
        body += section("Supporting Sources", data.get("supporting_sources"))
        body += section("Counter Claims", data.get("counter_claims"))
    elif table == "cortex_sources":
        source_id = data["source_id"]
        title = data.get("title") or data.get("citation_key") or f"Cortex Source {source_id}"
        body = frontmatter(table, source_id, title, {
            "task_id": data.get("task_id"),
            "citation_key": data.get("citation_key"),
            "url": data.get("url"),
            "credibility": data.get("credibility"),
            "expert_model": data.get("expert_model"),
            "created_at": data.get("created_at"),
            "content_path": data.get("content_path"),
        })
        body += [f"# {title}", ""]
        body += section("Finding", data.get("finding"))
        body += section("URL", data.get("url"))
        body += section("Content Path", data.get("content_path"))
    elif table == "evo_memory_semantic":
        source_id = data["memory_id"]
        title = data.get("key") or f"Semantic Memory {source_id}"
        body = frontmatter(table, source_id, title, {
            "namespace": data.get("namespace"),
            "source_type": data.get("source_type"),
            "source_trace_id": data.get("source_trace_id"),
            "confidence": data.get("confidence"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        })
        body += [f"# {title}", ""]
        body += section("Namespace", data.get("namespace"))
        body += section("Value", data.get("value"))
    else:
        source_id = next(iter(data.values()))
        title = f"{table} {source_id}"
        body = frontmatter(table, source_id, title, {})
        body += [f"# {title}", "", "```json", json.dumps(data, ensure_ascii=False, indent=2), "```", ""]

    text = "\n".join(body).rstrip() + "\n"
    return str(source_id), title, text


def table_query(table: str, scope: str, per_table_limit: int) -> tuple[str, list[object]]:
    base = {
        "solar_kb_entries": "SELECT * FROM solar_kb_entries",
        "knowledge_entities": "SELECT * FROM knowledge_entities",
        "knowledge_claims": "SELECT * FROM knowledge_claims",
        "cortex_sources": "SELECT * FROM cortex_sources",
        "evo_memory_semantic": "SELECT * FROM evo_memory_semantic",
    }[table]
    search_cols = {
        "solar_kb_entries": "lower(coalesce(title,'') || ' ' || coalesce(content,'') || ' ' || coalesce(tags,''))",
        "knowledge_entities": "lower(coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(type,''))",
        "knowledge_claims": "lower(coalesce(claim_text,'') || ' ' || coalesce(domain,''))",
        "cortex_sources": "lower(coalesce(title,'') || ' ' || coalesce(finding,'') || ' ' || coalesce(citation_key,''))",
        "evo_memory_semantic": "lower(coalesce(namespace,'') || ' ' || coalesce(key,'') || ' ' || coalesce(value,''))",
    }[table]

    where = ""
    params: list[object] = []
    if scope == "solar":
        parts = []
        for term in SOLAR_TERMS:
            parts.append(f"{search_cols} LIKE ?")
            params.append(f"%{term.lower()}%")
        where = " WHERE " + " OR ".join(parts)

    order_by = {
        "solar_kb_entries": " ORDER BY importance DESC, datetime(created_at) DESC",
        "knowledge_entities": " ORDER BY importance DESC, datetime(created_at) DESC",
        "knowledge_claims": " ORDER BY confidence DESC, datetime(created_at) DESC",
        "cortex_sources": " ORDER BY credibility DESC, datetime(created_at) DESC",
        "evo_memory_semantic": " ORDER BY confidence DESC, datetime(created_at) DESC",
    }[table]
    params.append(per_table_limit)
    return base + where + order_by + " LIMIT ?", params


def export_table(
    con: sqlite3.Connection,
    out_root: Path,
    table: str,
    scope: str,
    per_table_limit: int,
    dry_run: bool,
) -> dict:
    query, params = table_query(table, scope, per_table_limit)
    rows = con.execute(query, params).fetchall()
    stats = {"table": table, "selected": len(rows), "written": 0, "unchanged": 0, "dry_run": 0, "files": []}
    for row in rows:
        source_id, title, text = render_row(table, row)
        filename = f"{slugify(source_id, stable_hash(title))}-{slugify(title)}.md"
        path = out_root / table / filename
        result = write_if_changed(path, text, dry_run)
        stats[result.replace("-", "_")] = stats.get(result.replace("-", "_"), 0) + 1
        stats["files"].append(str(path))
    return stats


def existing_tables(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def parse_tables(value: str) -> list[str]:
    if value == "default":
        return list(DEFAULT_TABLES)
    return [x.strip() for x in value.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Solar SQLite knowledge into Obsidian _raw")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Solar sqlite db path")
    parser.add_argument("--vault", default=str(load_vault()), help="Obsidian vault path")
    parser.add_argument("--scope", choices=("solar", "all"), default="solar", help="solar filters Solar-related rows")
    parser.add_argument("--tables", default="default", help="comma list or 'default'")
    parser.add_argument("--per-table-limit", type=int, default=25, help="max rows exported per table")
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    db_path = Path(args.db).expanduser()
    vault = Path(args.vault).expanduser()
    out_root = vault / "_raw" / "solar-db-export"

    if not db_path.exists():
        raise SystemExit(f"Solar db not found: {db_path}")
    if args.per_table_limit < 1:
        raise SystemExit("--per-table-limit must be >= 1")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    tables = parse_tables(args.tables)
    present = existing_tables(con)
    missing = [t for t in tables if t not in present]
    if missing:
        raise SystemExit(f"Missing tables in {db_path}: {', '.join(missing)}")

    summary = {
        "ok": True,
        "db": str(db_path),
        "vault": str(vault),
        "out_root": str(out_root),
        "scope": args.scope,
        "per_table_limit": args.per_table_limit,
        "dry_run": args.dry_run,
        "exported_at": utc_now(),
        "tables": [],
    }
    for table in tables:
        summary["tables"].append(export_table(con, out_root, table, args.scope, args.per_table_limit, args.dry_run))
    con.close()

    if not args.dry_run:
        out_root.mkdir(parents=True, exist_ok=True)
        manifest = out_root / ".manifest.json"
        manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

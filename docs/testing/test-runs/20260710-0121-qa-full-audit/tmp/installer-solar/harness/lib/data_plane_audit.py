#!/usr/bin/env python3
"""
data_plane_audit.py — Solar Data Plane Health Audit + State Repair.

Commands:
    audit          Print health audit (JSON or human-readable)
    repair-state   Detect and repair malformed state rows

Usage:
    python3 data_plane_audit.py audit [--json] [--verbose]
    python3 data_plane_audit.py repair-state [--dry-run] [--json]

    # Via solar-harness:
    solar-harness data-plane audit [--json]
    solar-harness data-plane repair-state [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add lib to path for solar_db import
sys.path.insert(0, str(Path(__file__).parent))
from solar_db import open_solar_db, SOLAR_DB

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SPRINTS_DIR = HARNESS_DIR / "sprints"
BRIDGE_LEDGER = Path.home() / ".solar" / "codex-bridge" / "bridge-ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_ago(dt_str: str | None) -> int | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        pass
    # Try common formats: "2026-02-06 08:36:40"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%dT%H%M%SZ"):
        try:
            dt = datetime.strptime(dt_str.strip(), fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except (ValueError, TypeError):
            continue
    return None


def _ts_from_str(s: str | None) -> str | None:
    """Return ISO timestamp from various formats, or None."""
    if not s:
        return None
    return s


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info([{table}])").fetchall()}
    except sqlite3.OperationalError:
        return set()


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        return int(conn.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _current_index_fresh(conn: sqlite3.Connection) -> dict:
    """Return current active knowledge index status used as replacement for legacy KB tables."""
    vault_count = 0
    vault_latest = None
    fts_count = 0
    try:
        vault_count, vault_latest = conn.execute(
            "SELECT count(*), MAX(indexed_at) FROM obsidian_vault_index WHERE deleted_at IS NULL"
        ).fetchone()
    except sqlite3.OperationalError:
        pass
    try:
        fts_count = conn.execute("SELECT count(*) FROM fts_unified_search").fetchone()[0]
    except sqlite3.OperationalError:
        pass
    latest_age = _days_ago(vault_latest)
    current = bool(vault_count and latest_age is not None and latest_age <= 7)
    return {
        "obsidian_vault_index": int(vault_count or 0),
        "fts_unified_search": int(fts_count or 0),
        "latest_indexed_at": vault_latest,
        "latest_age_days": latest_age,
        "current": current,
    }


# ── Audit Checks ─────────────────────────────────────────────

def check_state_integrity(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT count(*) FROM state").fetchone()[0]
    malformed = conn.execute("SELECT count(*) FROM state WHERE json_valid(value)=0").fetchone()[0]
    quarantined = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='state_quarantine'"
    ).fetchone()[0]
    return {
        "name": "state_integrity",
        "total_rows": total,
        "malformed_count": malformed,
        "quarantined_count": quarantined,
        "status": "ok" if malformed == 0 else "warn",
    }


def check_table_freshness(conn: sqlite3.Connection, table: str, ts_col: str = "updated_at") -> dict:
    try:
        row = conn.execute(
            f"SELECT count(*), MAX({ts_col}) FROM [{table}]"
        ).fetchone()
        count, freshest = row[0], row[1]
    except sqlite3.OperationalError:
        return {"name": table, "row_count": 0, "freshest": None, "status": "missing"}

    if count == 0:
        return {"name": table, "row_count": 0, "freshest": None, "status": "stale"}

    age = _days_ago(freshest)
    if age is not None and age > 90:
        status = "stale"
    elif age is not None and age > 30:
        status = "warn"
    else:
        status = "ok"

    return {"name": table, "row_count": count, "freshest": freshest, "age_days": age, "status": status}


def check_legacy_table_freshness(conn: sqlite3.Connection, table: str, ts_col: str = "updated_at") -> dict:
    """Report legacy table freshness without pretending dormant legacy tables are active writers."""
    result = check_table_freshness(conn, table, ts_col)
    if result.get("status") in ("warn", "stale"):
        replacement = _current_index_fresh(conn)
        if replacement.get("current"):
            result["status"] = "dormant"
            result["replacement"] = "obsidian_vault_index+fts_unified_search"
            result["replacement_evidence"] = replacement
            result["note"] = (
                f"{table} is a legacy/dormant table in the current data plane; "
                "active searchable knowledge is in obsidian_vault_index + fts_unified_search."
            )
    return result


def check_sys_data_ledger(conn: sqlite3.Connection) -> dict:
    try:
        row = conn.execute("SELECT count(*), MAX(last_checked) FROM sys_data_ledger").fetchone()
        count, last = row[0], row[1]
    except sqlite3.OperationalError:
        return {"name": "sys_data_ledger", "row_count": 0, "last_checked": None, "status": "missing"}

    age = _days_ago(last)
    return {
        "name": "sys_data_ledger",
        "row_count": count,
        "last_checked": last,
        "age_days": age,
        "status": "stale" if age and age > 30 else ("ok" if count > 0 else "stale"),
    }


def check_sys_resources(conn: sqlite3.Connection) -> dict:
    try:
        total = conn.execute("SELECT count(*) FROM sys_resources").fetchone()[0]
    except sqlite3.OperationalError:
        return {"name": "sys_resources", "total": 0, "accessed_count": 0, "status": "missing"}

    usage_count = 0
    latest_usage = None
    try:
        usage_count, latest_usage = conn.execute(
            "SELECT count(*), MAX(called_at) FROM sys_resource_usage"
        ).fetchone()
    except sqlite3.OperationalError:
        pass
    status = "dormant" if usage_count == 0 else "ok"
    return {
        "name": "sys_resources",
        "total": total,
        "active": conn.execute("SELECT count(*) FROM sys_resources WHERE status='active'").fetchone()[0],
        "usage_count": int(usage_count or 0),
        "latest_usage": latest_usage,
        "status": status,
        "note": "registry exists but runtime usage telemetry has no calls yet" if usage_count == 0 else "",
    }


def check_bridge_ledger() -> dict:
    if not BRIDGE_LEDGER.exists():
        return {"name": "bridge_ledger", "row_count": 0, "freshest": None, "status": "missing"}

    count = 0
    freshest = None
    try:
        with open(BRIDGE_LEDGER, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts") or obj.get("timestamp") or ""
                    if ts and (freshest is None or ts > freshest):
                        freshest = ts
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    age = _days_ago(freshest)
    status = "ok" if age is not None and age <= 7 else ("warn" if count > 0 else "stale")
    return {"name": "bridge_ledger", "row_count": count, "freshest": freshest, "age_days": age, "status": status}


def check_sprint_artifacts() -> dict:
    if not SPRINTS_DIR.exists():
        return {"name": "sprint_artifacts", "total_sprints": 0, "finalized": 0, "status": "missing"}

    status_files = list(SPRINTS_DIR.glob("sprint-*.status.json"))
    finalized = list(SPRINTS_DIR.glob("*.finalized"))

    freshest = None
    for sf in status_files:
        try:
            mtime = sf.stat().st_mtime
            ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if freshest is None or ts > freshest:
                freshest = ts
        except OSError:
            pass

    return {
        "name": "sprint_artifacts",
        "total_sprints": len(status_files),
        "finalized": len(finalized),
        "freshest": freshest,
        "status": "ok" if status_files else "stale",
    }


def check_resource_usage(conn: sqlite3.Connection) -> dict:
    """A4: Resource usage telemetry honesty check."""
    try:
        total = conn.execute("SELECT count(*) FROM sys_resources").fetchone()[0]
    except sqlite3.OperationalError:
        return {"name": "resource_usage", "note": "sys_resources table missing", "status": "missing"}
    try:
        usage_count, latest_usage = conn.execute(
            "SELECT count(*), MAX(called_at) FROM sys_resource_usage"
        ).fetchone()
    except sqlite3.OperationalError:
        usage_count, latest_usage = 0, None

    # Check if solar-knowledge-context.py actually reads from sys_resources
    ctx_script = HARNESS_DIR / "lib" / "solar-knowledge-context.py"
    reads_resources = False
    if ctx_script.exists():
        try:
            content = ctx_script.read_text()
            reads_resources = "sys_resources" in content
        except Exception:
            pass

    if usage_count == 0:
        return {
            "name": "resource_usage",
            "total_resources": total,
            "usage_count": 0,
            "consumer_exists": reads_resources,
            "status": "dormant",
            "note": "sys_resources exists but sys_resource_usage has no calls; layer is dormant"
            if reads_resources else
            "sys_resources exists but no consumer reads from it; layer is dormant",
        }
    return {
        "name": "resource_usage",
        "total_resources": total,
        "usage_count": int(usage_count or 0),
        "latest_usage": latest_usage,
        "status": "ok",
    }


def check_accepted_artifact_path(conn: sqlite3.Connection) -> dict:
    """A6: Accepted artifact ingestion path tracking."""
    finalized = list(SPRINTS_DIR.glob("*.finalized")) if SPRINTS_DIR.exists() else []

    indexed = 0
    try:
        indexed = conn.execute(
            "SELECT count(*) FROM obsidian_vault_index "
            "WHERE file_path LIKE '%/_raw/solar-harness/accepted/%.accepted.md' "
            "AND deleted_at IS NULL"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        pass

    blocked_by = []
    for sid in ["sprint-20260508-apple-notes-wechat-ingest"]:
        sf = SPRINTS_DIR / f"{sid}.status.json"
        if sf.exists():
            try:
                s = json.loads(sf.read_text()).get("status", "")
                if s not in ("passed", "approved"):
                    blocked_by.append(sid)
            except (json.JSONDecodeError, OSError):
                pass

    status = "ok" if indexed > 0 else ("blocked" if blocked_by else "warn")
    return {
        "name": "accepted_artifact_path",
        "finalized_sprints": len(finalized),
        "indexed_in_vault": indexed,
        "blocked_by": blocked_by,
        "status": status,
    }


def check_solar_cli_integration() -> dict:
    """A5: solar CLI vs solar-harness relationship."""
    solar_script = Path.home() / ".agents" / "skills" / "solar" / "scripts" / "run.sh"
    flow_state = Path.home() / ".solar" / "flow-state.json"

    exists = solar_script.exists()
    flow_exists = flow_state.exists()

    return {
        "name": "solar_cli_integration",
        "script_exists": exists,
        "mode": "local_only",
        "shared_db_writes": False,
        "flow_state_active": flow_exists,
        "status": "ok",
        "note": "solar writes ~/.solar/flow-state.json only; not sharing solar.db (Option B: by design)",
    }


# ── Main Audit ────────────────────────────────────────────────

def run_audit(json_output: bool = False, verbose: bool = False) -> int:
    conn = open_solar_db(readonly=True)
    try:
        checks = [
            check_state_integrity(conn),
            check_sys_data_ledger(conn),
            check_sys_resources(conn),
            check_table_freshness(conn, "cortex_sources", "created_at"),
            check_legacy_table_freshness(conn, "cortex_passages", "created_at"),
            check_legacy_table_freshness(conn, "solar_kb_entries", "created_at"),
            check_legacy_table_freshness(conn, "knowledge_records", "created_at"),
            check_bridge_ledger(),
            check_sprint_artifacts(),
            check_resource_usage(conn),
            check_accepted_artifact_path(conn),
            check_solar_cli_integration(),
        ]
    finally:
        conn.close()

    # Determine overall status
    statuses = [c.get("status", "ok") for c in checks]
    if "stale" in statuses or "missing" in statuses:
        overall = "warn"
    elif statuses.count("warn") > 2:
        overall = "warn"
    else:
        overall = "ok"

    # Flat keys for specific checks (contract A4/A6 verify commands)
    flat_keys = {c["name"]: c for c in checks}

    result = {
        "checks": checks,
        "overall_status": overall,
        "generated_at": _now_iso(),
        "resource_usage": flat_keys.get("resource_usage", {}),
        "accepted_artifact_path": flat_keys.get("accepted_artifact_path", {}),
    }

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"=== Solar Data Plane Audit — {result['generated_at']} ===")
        print(f"Overall: {overall.upper()}")
        print()
        for c in checks:
            name = c.get("name", "?")
            status = c.get("status", "?")
            flag = "✅" if status == "ok" else ("⚠️" if status in ("warn", "dormant") else "❌")
            print(f"  {flag} {name}: {status}")
            if verbose:
                for k, v in c.items():
                    if k not in ("name", "status"):
                        print(f"      {k}: {v}")
        print()

    return 0 if overall == "ok" else 1


# ── State Repair ──────────────────────────────────────────────

def run_repair_state(dry_run: bool = False, json_output: bool = False) -> int:
    conn = open_solar_db()
    try:
        # Find malformed rows
        malformed = conn.execute(
            "SELECT key, value FROM state WHERE json_valid(value)=0"
        ).fetchall()

        if not malformed:
            msg = {"action": "repair-state", "malformed_found": 0, "status": "ok", "note": "No malformed state rows found."}
            if json_output:
                print(json.dumps(msg, indent=2))
            else:
                print("✅ No malformed state rows found.")
            return 0

        rows_info = [{"key": r[0], "value_preview": r[1][:200]} for r in malformed]

        if dry_run:
            msg = {
                "action": "repair-state",
                "mode": "dry-run",
                "malformed_found": len(malformed),
                "rows": rows_info,
                "status": "needs_repair",
            }
            if json_output:
                print(json.dumps(msg, indent=2, ensure_ascii=False))
            else:
                print(f"⚠️ DRY RUN: {len(malformed)} malformed state rows found:")
                for r in rows_info:
                    print(f"  - key={r['key']}  value={r['value_preview']}")
                print("Run without --dry-run to repair.")
            return 1

        # Real repair: backup to state_quarantine, then delete
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state_quarantine (
                key TEXT PRIMARY KEY,
                value TEXT,
                quarantined_at TEXT,
                reason TEXT
            )
        """)

        now = _now_iso()
        for key, value in malformed:
            conn.execute(
                "INSERT OR REPLACE INTO state_quarantine (key, value, quarantined_at, reason) VALUES (?, ?, ?, ?)",
                (key, value, now, "malformed_json: json_valid(value)=0"),
            )
            conn.execute("DELETE FROM state WHERE key=?", (key,))

        conn.commit()

        # Verify
        remaining = conn.execute("SELECT count(*) FROM state WHERE json_valid(value)=0").fetchone()[0]

        msg = {
            "action": "repair-state",
            "mode": "live",
            "malformed_found": len(malformed),
            "quarantined": len(malformed),
            "remaining_malformed": remaining,
            "quarantine_table": "state_quarantine",
            "status": "ok" if remaining == 0 else "warn",
            "rows": rows_info,
        }
        if json_output:
            print(json.dumps(msg, indent=2, ensure_ascii=False))
        else:
            print(f"✅ Quarantined {len(malformed)} malformed rows → state_quarantine")
            if remaining == 0:
                print("✅ Verification: 0 malformed rows remaining.")
            else:
                print(f"⚠️ Verification: {remaining} malformed rows still remaining.")

        return 0 if remaining == 0 else 1

    except Exception as e:
        conn.rollback()
        print(f"❌ Repair failed: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


def run_refresh_ledger(dry_run: bool = False, json_output: bool = False) -> int:
    """Refresh sys_data_ledger counts and last_checked from the live DB.

    This updates ledger metadata only. It does not mutate source tables or
    fabricate activity timestamps.
    """
    conn = open_solar_db()
    try:
        if not _table_exists(conn, "sys_data_ledger"):
            result = {"action": "refresh-ledger", "status": "missing", "updated": 0}
            if json_output:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("❌ sys_data_ledger table missing")
            return 1

        rows = conn.execute(
            "SELECT ledger_id, source_type, source_name FROM sys_data_ledger"
        ).fetchall()
        now = _now_iso()
        updates = []
        for ledger_id, source_type, source_name in rows:
            record_count = None
            status = "active"
            notes = ""
            if source_type == "table":
                if _table_exists(conn, source_name):
                    record_count = _table_count(conn, source_name)
                    if source_name in {"cortex_passages", "solar_kb_entries", "knowledge_records"}:
                        replacement = _current_index_fresh(conn)
                        if replacement.get("current"):
                            status = "dormant"
                            notes = "legacy table; current searchable data plane is obsidian_vault_index+fts_unified_search"
                else:
                    record_count = 0
                    status = "missing"
                    notes = "source table missing"
            elif source_type in {"index", "file"}:
                # We can safely mark the ledger checked without claiming filesystem/index internals changed.
                record_count = None
                status = "checked"
            else:
                record_count = None
            updates.append({
                "ledger_id": ledger_id,
                "source_type": source_type,
                "source_name": source_name,
                "record_count": record_count,
                "status": status,
                "notes": notes,
            })

        if not dry_run:
            for item in updates:
                if item["record_count"] is None:
                    conn.execute(
                        "UPDATE sys_data_ledger SET status=?, last_checked=?, updated_at=?, notes=COALESCE(NULLIF(?, ''), notes) WHERE ledger_id=?",
                        (item["status"], now, now, item["notes"], item["ledger_id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE sys_data_ledger SET record_count=?, status=?, last_checked=?, updated_at=?, notes=COALESCE(NULLIF(?, ''), notes) WHERE ledger_id=?",
                        (item["record_count"], item["status"], now, now, item["notes"], item["ledger_id"]),
                    )
            conn.commit()

        result = {
            "action": "refresh-ledger",
            "mode": "dry-run" if dry_run else "live",
            "updated": len(updates),
            "status": "ok",
            "checked_at": now,
            "updates": updates,
        }
        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"✅ sys_data_ledger refreshed: {len(updates)} rows")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"❌ refresh-ledger failed: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Solar Data Plane Audit")
    sub = parser.add_subparsers(dest="command")

    audit_p = sub.add_parser("audit", help="Run data plane health audit")
    audit_p.add_argument("--json", action="store_true", help="Output as JSON")
    audit_p.add_argument("--verbose", action="store_true", help="Show details per check")

    repair_p = sub.add_parser("repair-state", help="Repair malformed state rows")
    repair_p.add_argument("--dry-run", action="store_true", help="Show what would be repaired without modifying")
    repair_p.add_argument("--json", action="store_true", help="Output as JSON")

    refresh_p = sub.add_parser("refresh-ledger", help="Refresh sys_data_ledger counts and last_checked")
    refresh_p.add_argument("--dry-run", action="store_true", help="Show what would be refreshed without modifying")
    refresh_p.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    if args.command == "audit":
        sys.exit(run_audit(json_output=args.json, verbose=args.verbose))
    elif args.command == "repair-state":
        sys.exit(run_repair_state(dry_run=args.dry_run, json_output=args.json))
    elif args.command == "refresh-ledger":
        sys.exit(run_refresh_ledger(dry_run=args.dry_run, json_output=args.json))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

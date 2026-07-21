#!/usr/bin/env python3
"""capability_registry.py — S4 Extension Framework: persist and query plugin capabilities in state DB.

Capabilities are loaded from plugin manifests and stored in the capabilities table of state.db.
This allows other components (autopilot, skill system, etc.) to discover what is available.

CLI:
  python3 capability_registry.py sync [--json]
  python3 capability_registry.py list [--json]
  python3 capability_registry.py query <capability> [--json]
  python3 capability_registry.py scorecard [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", str(HARNESS_DIR / "run" / "state.db")))
EVENTS_FILE = HARNESS_DIR / "events.jsonl"

LEVEL_MAP = {
    "dead_end": 1,
    "basic_usable": 2,
    "default_usable": 3,
    "closed_loop": 4,
}
LEVEL_REVERSE = {v: k for k, v in LEVEL_MAP.items()}


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit_event(event: str, payload: dict) -> None:
    entry = {"ts": _now(), "source": "capability_registry", "event": event, **payload}
    try:
        with open(EVENTS_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _open_db() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STATE_DB), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _ensure_capabilities_table(conn)
    return conn


def _ensure_capabilities_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS capabilities (
            pane        TEXT NOT NULL DEFAULT 'plugin',
            capability  TEXT NOT NULL,
            level       INTEGER NOT NULL DEFAULT 1,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (pane, capability)
        )
    """)
    # Extended table for plugin capabilities (separate from pane capabilities)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plugin_capabilities (
            capability  TEXT NOT NULL,
            provider    TEXT NOT NULL,
            level       INTEGER NOT NULL DEFAULT 1,
            status      TEXT NOT NULL DEFAULT 'active',
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (capability, provider)
        )
    """)
    conn.commit()


def _load_plugins_from_loader() -> list[dict]:
    """Import plugin_loader to get all plugin data without subprocess."""
    try:
        sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import plugin_loader  # type: ignore
        return plugin_loader.load_all_plugins()
    except Exception as e:
        return []
    finally:
        sys.path.pop(0)


def cmd_sync(as_json: bool) -> int:
    """Sync capabilities from plugin manifests into state DB."""
    plugins = _load_plugins_from_loader()
    conn = _open_db()
    synced = 0
    errors: list[str] = []

    for plugin in plugins:
        plugin_id = plugin.get("id", "?")
        if not plugin.get("_valid", False):
            continue
        if plugin.get("status") == "disabled":
            # Mark as inactive in DB
            conn.execute(
                "UPDATE plugin_capabilities SET status='inactive', updated_at=? WHERE provider=?",
                (_now(), plugin_id)
            )
            continue

        declared_level = plugin.get("integration_level", "dead_end")
        level_int = LEVEL_MAP.get(declared_level, 1)

        for cap in plugin.get("capabilities", []):
            try:
                conn.execute(
                    """INSERT INTO plugin_capabilities (capability, provider, level, status, updated_at)
                       VALUES (?, ?, ?, 'active', ?)
                       ON CONFLICT(capability, provider) DO UPDATE SET
                         level=excluded.level,
                         status='active',
                         updated_at=excluded.updated_at""",
                    (cap, plugin_id, level_int, _now())
                )
                synced += 1
            except Exception as e:
                errors.append(f"{plugin_id}/{cap}: {e}")

    conn.commit()
    conn.close()

    _emit_event("capability_registry.sync", {"synced": synced, "plugins": len(plugins), "errors": len(errors)})

    out = {
        "ok": len(errors) == 0,
        "synced_capabilities": synced,
        "plugins_processed": len(plugins),
        "errors": errors,
        "generated_at": _now(),
    }
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Capability sync: {synced} capabilities from {len(plugins)} plugins")
        if errors:
            for e in errors:
                print(f"  ERROR: {e}")
    return 0 if not errors else 1


def cmd_list(as_json: bool) -> int:
    """List all capabilities from state DB."""
    conn = _open_db()
    rows = conn.execute(
        "SELECT capability, provider, level, status, updated_at FROM plugin_capabilities ORDER BY level DESC, capability"
    ).fetchall()
    conn.close()

    entries = [
        {
            "capability": r["capability"],
            "provider": r["provider"],
            "level": r["level"],
            "integration_level": LEVEL_REVERSE.get(r["level"], "dead_end"),
            "status": r["status"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]

    out = {"ok": True, "total": len(entries), "capabilities": entries}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Capabilities: {len(entries)} total")
        for e in entries:
            lvl = e["integration_level"]
            print(f"  [{lvl:14s}] {e['capability']:30s}  by {e['provider']}")
    return 0


def cmd_query(capability: str, as_json: bool) -> int:
    """Query who provides a specific capability."""
    conn = _open_db()
    rows = conn.execute(
        "SELECT capability, provider, level, status, updated_at FROM plugin_capabilities "
        "WHERE capability=? AND status='active' ORDER BY level DESC",
        (capability,)
    ).fetchall()
    conn.close()

    found = [
        {
            "capability": r["capability"],
            "provider": r["provider"],
            "level": r["level"],
            "integration_level": LEVEL_REVERSE.get(r["level"], "dead_end"),
        }
        for r in rows
    ]

    out = {"ok": True, "capability": capability, "providers": found, "found": len(found) > 0}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        if found:
            for p in found:
                print(f"  {capability} ← {p['provider']} ({p['integration_level']})")
        else:
            print(f"  {capability}: no active provider found")
    return 0 if found else 1


def get_active_providers(capability: str, min_level: int = 1) -> list[dict]:
    """Return active providers for a capability without CLI side effects."""
    conn = _open_db()
    rows = conn.execute(
        "SELECT capability, provider, level, status, updated_at FROM plugin_capabilities "
        "WHERE capability=? AND status='active' AND level>=? ORDER BY level DESC, provider",
        (capability, min_level),
    ).fetchall()
    conn.close()
    return [
        {
            "capability": r["capability"],
            "provider": r["provider"],
            "level": r["level"],
            "integration_level": LEVEL_REVERSE.get(r["level"], "dead_end"),
            "status": r["status"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def cmd_scorecard(as_json: bool) -> int:
    """Generate a capability scorecard by integration level."""
    conn = _open_db()
    rows = conn.execute(
        "SELECT level, COUNT(*) as cnt FROM plugin_capabilities WHERE status='active' GROUP BY level ORDER BY level DESC"
    ).fetchall()
    conn.close()

    by_level = {LEVEL_REVERSE.get(r["level"], "dead_end"): r["cnt"] for r in rows}
    total = sum(by_level.values())
    closed_loop = by_level.get("closed_loop", 0)
    score = round((closed_loop * 4 + by_level.get("default_usable", 0) * 3 +
                   by_level.get("basic_usable", 0) * 2 + by_level.get("dead_end", 0) * 1) / max(total, 1), 2)

    out = {
        "ok": True,
        "total_capabilities": total,
        "by_level": by_level,
        "weighted_score": score,
        "max_score": 4.0,
        "generated_at": _now(),
    }
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Capability Scorecard: {score:.2f}/4.0 ({total} total)")
        for lvl in ["closed_loop", "default_usable", "basic_usable", "dead_end"]:
            cnt = by_level.get(lvl, 0)
            if cnt:
                print(f"  {lvl}: {cnt}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="capability_registry.py")
    sub = ap.add_subparsers(dest="cmd")

    sy = sub.add_parser("sync")
    sy.add_argument("--json", action="store_true", dest="as_json")

    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true", dest="as_json")

    qy = sub.add_parser("query")
    qy.add_argument("capability")
    qy.add_argument("--json", action="store_true", dest="as_json")

    sc = sub.add_parser("scorecard")
    sc.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()
    if args.cmd == "sync":
        return cmd_sync(args.as_json)
    elif args.cmd == "list":
        return cmd_list(args.as_json)
    elif args.cmd == "query":
        return cmd_query(args.capability, args.as_json)
    elif args.cmd == "scorecard":
        return cmd_scorecard(args.as_json)
    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""plugin_loader.py — S4 Extension Framework: load, validate, and manage Solar plugins.

Each plugin lives at plugins/<id>/manifest.yaml.
Scope enforcement: any write attempt outside declared write_scope is rejected + event emitted.

Integration levels:
  dead_end       — plugin present but no live connection (stubs only)
  basic_usable   — can perform core action but no bidirectional feedback
  default_usable — default workflow works; manual steps needed for edge cases
  closed_loop    — fully automated, self-healing, event-driven

CLI:
  python3 plugin_loader.py list [--json]
  python3 plugin_loader.py status [--json]
  python3 plugin_loader.py install <id> [--json]
  python3 plugin_loader.py disable <id> [--json]
  python3 plugin_loader.py validate [--id <id>] [--json]
  python3 plugin_loader.py check-scope --plugin <id> --path <path> [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
PLUGINS_DIR = HARNESS_DIR / "plugins"
EVENTS_FILE = HARNESS_DIR / "events.jsonl"

# Integration level → numeric rank (for sorting / comparison)
LEVEL_RANK = {
    "dead_end": 1,
    "basic_usable": 2,
    "default_usable": 3,
    "closed_loop": 4,
}

REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "status",
    "write_scope",
    "read_scope",
    "capabilities",
    "commands",
    "background_safety",
    "eval_packs",
    "rollback",
}


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit_event(event: str, plugin_id: str, payload: dict) -> None:
    entry = {
        "ts": _now(),
        "source": "plugin_loader",
        "event": event,
        "plugin_id": plugin_id,
        **payload,
    }
    for target in (EVENTS_FILE, HARNESS_DIR / "events" / "all.jsonl"):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _load_yaml_manifest(path: Path) -> "dict | None":
    """Minimal YAML parser for manifest files (no PyYAML dependency required)."""
    try:
        import yaml  # type: ignore
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        pass
    # Fallback: line-by-line parser for simple key: value and list items
    result: dict[str, Any] = {}
    current_key: "str | None" = None
    current_list: "list | None" = None
    with open(path) as f:
        for raw_line in f:
            line = raw_line.rstrip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            if line.startswith("  - ") or line.startswith("- "):
                item = line.lstrip("- ").strip().strip('"')
                if current_list is not None:
                    current_list.append(item)
            elif ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip().strip('"')
                if v == "":
                    current_list = []
                    result[k] = current_list
                    current_key = k
                else:
                    result[k] = v
                    current_key = k
                    current_list = None
    return result


def _validate_manifest(data: dict, plugin_id: str) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")
    if data.get("id") and data["id"] != plugin_id:
        errors.append(f"id mismatch: manifest says '{data['id']}' but dir is '{plugin_id}'")
    if data.get("status") not in (None, "enabled", "disabled", "candidate"):
        errors.append(f"invalid status: {data['status']}")
    caps = data.get("capabilities", [])
    if not isinstance(caps, list) or len(caps) == 0:
        errors.append("capabilities must be a non-empty list")
    commands = data.get("commands", [])
    if not isinstance(commands, list) or len(commands) == 0:
        errors.append("commands must be a non-empty list")
    eval_packs = data.get("eval_packs", [])
    if not isinstance(eval_packs, list) or len(eval_packs) == 0:
        errors.append("eval_packs must be a non-empty list")
    bg = data.get("background_safety", {})
    if not isinstance(bg, dict):
        errors.append("background_safety must be an object")
    else:
        if bg.get("mode") not in {"none", "idle", "bounded", "service"}:
            errors.append("background_safety.mode must be one of none/idle/bounded/service")
        if "idle_only" not in bg:
            errors.append("background_safety.idle_only is required")
        if not bg.get("rate_limit"):
            errors.append("background_safety.rate_limit is required")
    rollback = data.get("rollback", {})
    if not isinstance(rollback, dict):
        errors.append("rollback must be an object")
    else:
        if rollback.get("strategy") not in {"disable", "restore_snapshot", "manual"}:
            errors.append("rollback.strategy must be disable/restore_snapshot/manual")
        if not isinstance(rollback.get("commands"), list):
            errors.append("rollback.commands must be a list")
    return errors


def load_all_plugins() -> list[dict]:
    """Load all plugin manifests from PLUGINS_DIR. Returns list of plugin dicts with _errors key."""
    plugins: list[dict] = []
    if not PLUGINS_DIR.exists():
        return plugins
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        plugin_id = plugin_dir.name
        data = _load_yaml_manifest(manifest_path)
        if data is None:
            plugins.append({"id": plugin_id, "_errors": ["failed to parse manifest.yaml"], "status": "disabled"})
            continue
        errors = _validate_manifest(data, plugin_id)
        data["_errors"] = errors
        data["_manifest_path"] = str(manifest_path)
        data["_valid"] = len(errors) == 0
        plugins.append(data)
    return plugins


def _integration_level_for_plugin(plugin: dict) -> str:
    """Determine effective integration level based on plugin status and declared level."""
    if plugin.get("status") == "disabled":
        return "dead_end"
    declared = plugin.get("integration_level", "dead_end")
    if not plugin.get("_valid", False):
        return "dead_end"
    return declared if declared in LEVEL_RANK else "dead_end"


def _check_scope(plugin: dict, target_path: str) -> bool:
    """Return True if target_path is within the plugin's declared write_scope."""
    write_scope = plugin.get("write_scope", [])
    if not isinstance(write_scope, list):
        return False
    expanded_target = str(Path(target_path).expanduser().resolve())
    for scope_entry in write_scope:
        scope_path = Path(str(scope_entry)).expanduser()
        if not scope_path.is_absolute():
            scope_path = HARNESS_DIR / scope_path
        expanded_scope = str(scope_path.resolve())
        if expanded_target == expanded_scope or expanded_target.startswith(expanded_scope.rstrip("/") + "/"):
            return True
    # Also allow /tmp/solar-* unconditionally for temp output
    if expanded_target.startswith("/tmp/solar-"):
        return True
    return False


# ── CLI commands ──────────────────────────────────────────────────────────────

def cmd_list(as_json: bool) -> int:
    plugins = load_all_plugins()
    if as_json:
        out = {
            "ok": True,
            "total": len(plugins),
            "plugins": [
                {
                    "id": p.get("id", "?"),
                    "name": p.get("name", "?"),
                    "version": p.get("version", "?"),
                    "status": p.get("status", "disabled"),
                    "integration_level": _integration_level_for_plugin(p),
                    "capabilities": p.get("capabilities", []),
                    "valid": p.get("_valid", False),
                    "errors": p.get("_errors", []),
                }
                for p in plugins
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"Plugins: {len(plugins)} total")
        for p in plugins:
            tag = "✓" if p.get("_valid") else "✗"
            lvl = _integration_level_for_plugin(p)
            print(f"  {tag} [{p.get('status','?'):8s}] {p.get('id','?'):12s}  {lvl}  {p.get('name','?')}")
    return 0


def cmd_status(as_json: bool) -> int:
    plugins = load_all_plugins()
    by_level: dict[str, list[dict]] = {lvl: [] for lvl in LEVEL_RANK}
    for p in plugins:
        lvl = _integration_level_for_plugin(p)
        by_level.setdefault(lvl, []).append(p)

    out = {
        "ok": True,
        "generated_at": _now(),
        "total": len(plugins),
        "by_level": {
            lvl: [p.get("id", "?") for p in plist]
            for lvl, plist in by_level.items()
        },
        "plugins": [
            {
                "id": p.get("id", "?"),
                "status": p.get("status", "disabled"),
                "integration_level": _integration_level_for_plugin(p),
                "capabilities": p.get("capabilities", []),
                "valid": p.get("_valid", False),
            }
            for p in plugins
        ],
    }
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        for lvl in ["closed_loop", "default_usable", "basic_usable", "dead_end"]:
            ids = by_level.get(lvl, [])
            if ids:
                print(f"  {lvl}: {', '.join(p.get('id','?') for p in ids)}")
    return 0


def cmd_validate(plugin_id: "str | None", as_json: bool) -> int:
    plugins = load_all_plugins()
    if plugin_id:
        plugins = [p for p in plugins if p.get("id") == plugin_id]
        if not plugins:
            out = {"ok": False, "error": f"plugin not found: {plugin_id}"}
            if as_json:
                print(json.dumps(out, indent=2))
            else:
                print(f"ERROR: plugin not found: {plugin_id}")
            return 1

    results = []
    all_valid = True
    for p in plugins:
        valid = p.get("_valid", False)
        if not valid:
            all_valid = False
        results.append({
            "id": p.get("id", "?"),
            "valid": valid,
            "errors": p.get("_errors", []),
        })

    out = {"ok": all_valid, "checked": len(results), "results": results}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        for r in results:
            tag = "✓" if r["valid"] else "✗"
            print(f"  {tag} {r['id']}: {'ok' if r['valid'] else '; '.join(r['errors'])}")
    return 0 if all_valid else 1


def cmd_install(plugin_id: str, as_json: bool) -> int:
    """Enable a disabled/candidate plugin."""
    plugins = load_all_plugins()
    found = next((p for p in plugins if p.get("id") == plugin_id), None)
    if not found:
        out = {"ok": False, "error": f"plugin not found: {plugin_id}"}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"ERROR: {out['error']}")
        return 1

    if not found.get("_valid", False):
        errors = found.get("_errors", [])
        out = {"ok": False, "error": "manifest validation failed", "errors": errors}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"ERROR: manifest invalid: {'; '.join(errors)}")
        return 1

    manifest_path = Path(found["_manifest_path"])
    text = manifest_path.read_text()
    old_status = found.get("status", "disabled")
    if old_status == "enabled":
        out = {"ok": True, "id": plugin_id, "note": "already enabled"}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"Plugin {plugin_id} already enabled")
        return 0

    new_text = text.replace(f"status: {old_status}", "status: enabled", 1)
    manifest_path.write_text(new_text)
    _emit_event("plugin.installed", plugin_id, {"previous_status": old_status})

    out = {"ok": True, "id": plugin_id, "previous_status": old_status, "new_status": "enabled"}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Plugin {plugin_id}: {old_status} → enabled")
    return 0


def cmd_disable(plugin_id: str, as_json: bool) -> int:
    """Disable an enabled plugin."""
    plugins = load_all_plugins()
    found = next((p for p in plugins if p.get("id") == plugin_id), None)
    if not found:
        out = {"ok": False, "error": f"plugin not found: {plugin_id}"}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"ERROR: {out['error']}")
        return 1

    manifest_path = Path(found["_manifest_path"])
    text = manifest_path.read_text()
    old_status = found.get("status", "enabled")
    if old_status == "disabled":
        out = {"ok": True, "id": plugin_id, "note": "already disabled"}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"Plugin {plugin_id} already disabled")
        return 0

    new_text = text.replace(f"status: {old_status}", "status: disabled", 1)
    manifest_path.write_text(new_text)
    _emit_event("plugin.disabled", plugin_id, {"previous_status": old_status})

    out = {"ok": True, "id": plugin_id, "previous_status": old_status, "new_status": "disabled"}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Plugin {plugin_id}: {old_status} → disabled")
    return 0


def cmd_check_scope(plugin_id: str, target_path: str, as_json: bool) -> int:
    """Check if a path is within a plugin's declared write_scope. Emit alert if not."""
    plugins = load_all_plugins()
    found = next((p for p in plugins if p.get("id") == plugin_id), None)
    if not found:
        out = {"ok": False, "allowed": False, "error": f"plugin not found: {plugin_id}"}
        if as_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"ERROR: {out['error']}")
        return 1

    allowed = _check_scope(found, target_path)
    if not allowed:
        _emit_event("plugin.scope_violation", plugin_id, {
            "path": target_path,
            "write_scope": found.get("write_scope", []),
            "action": "rejected",
        })

    out = {
        "ok": True,
        "plugin_id": plugin_id,
        "path": target_path,
        "allowed": allowed,
        "write_scope": found.get("write_scope", []),
    }
    if not allowed:
        out["alert"] = "scope_violation_rejected"
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        tag = "✓ ALLOWED" if allowed else "✗ REJECTED (scope violation)"
        print(f"{tag}: {plugin_id} → {target_path}")
    return 0 if allowed else 1


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="plugin_loader.py")
    sub = ap.add_subparsers(dest="cmd")

    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true", dest="as_json")

    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true", dest="as_json")

    va = sub.add_parser("validate")
    va.add_argument("--id", dest="plugin_id", default=None)
    va.add_argument("--json", action="store_true", dest="as_json")

    ins = sub.add_parser("install")
    ins.add_argument("id", help="Plugin ID to enable")
    ins.add_argument("--json", action="store_true", dest="as_json")

    dis = sub.add_parser("disable")
    dis.add_argument("id", help="Plugin ID to disable")
    dis.add_argument("--json", action="store_true", dest="as_json")

    cs = sub.add_parser("check-scope")
    cs.add_argument("--plugin", required=True)
    cs.add_argument("--path", required=True)
    cs.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()
    if args.cmd == "list":
        return cmd_list(args.as_json)
    elif args.cmd == "status":
        return cmd_status(args.as_json)
    elif args.cmd == "validate":
        return cmd_validate(args.plugin_id, args.as_json)
    elif args.cmd == "install":
        return cmd_install(args.id, args.as_json)
    elif args.cmd == "disable":
        return cmd_disable(args.id, args.as_json)
    elif args.cmd == "check-scope":
        return cmd_check_scope(args.plugin, args.path, args.as_json)
    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

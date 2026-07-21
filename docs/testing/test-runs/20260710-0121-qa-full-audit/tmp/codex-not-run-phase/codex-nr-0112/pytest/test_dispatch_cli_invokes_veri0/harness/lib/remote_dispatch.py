#!/usr/bin/env python3
"""remote_dispatch.py — Remote dispatch core: config, doctor, manifest, checksum.

This module provides the Python underpinnings for solar-remote-dispatch:
  - Remote target configuration (from JSON config or env vars, never hardcoded)
  - Doctor: health-check of remote target (ssh, rsync, harness, tmux, panes)
  - Manifest generation with SHA-256 checksums of sprint files
  - Remote checksum verification before wake
  - Status pull/reconcile
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = HARNESS_DIR / "sprints"
CONFIG_FILE = HOME / ".solar" / "remote-config.json"
REMOTE_SPRINTS_FILE = HOME / ".solar" / "state" / "remote-sprints.jsonl"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(host_override: str = "", user_override: str = "",
                path_override: str = "") -> dict[str, Any]:
    """Load remote target configuration.

    Priority: function overrides > env vars > config file > defaults.
    Never hardcodes a specific user/host/path.
    """
    # Start with defaults (must be overridden)
    config: dict[str, Any] = {
        "remote_user": "",
        "remote_host": "",
        "remote_path": "",
    }

    # Layer 1: config file
    if CONFIG_FILE.exists():
        try:
            file_cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(file_cfg, dict):
                config["remote_user"] = file_cfg.get("remote_user", "")
                config["remote_host"] = file_cfg.get("remote_host", "")
                config["remote_path"] = file_cfg.get("remote_path", "")
        except Exception:
            pass

    # Layer 2: env vars (support both SOLAR_REMOTE_* and SOLAR_MAC_MINI_* aliases)
    config["remote_user"] = (
        os.environ.get("SOLAR_REMOTE_USER")
        or os.environ.get("SOLAR_MAC_MINI_USER")
        or config["remote_user"]
    )
    config["remote_host"] = (
        os.environ.get("SOLAR_REMOTE_HOST")
        or os.environ.get("SOLAR_MAC_MINI_HOST")
        or config["remote_host"]
    )
    config["remote_path"] = (
        os.environ.get("SOLAR_REMOTE_PATH")
        or os.environ.get("SOLAR_MAC_MINI_PATH")
        or config["remote_path"]
    )

    # Layer 3: function overrides (highest priority)
    if user_override:
        config["remote_user"] = user_override
    if host_override:
        config["remote_host"] = host_override
    if path_override:
        config["remote_path"] = path_override

    # Derive effective remote_path as remote $HOME if not set
    if not config["remote_path"]:
        config["remote_path"] = "~"  # resolved on remote via ssh

    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return list of missing/bad config fields."""
    errors: list[str] = []
    if not config.get("remote_user"):
        errors.append("remote_user is not set (configure ~/.solar/remote-config.json or set SOLAR_REMOTE_USER)")
    if not config.get("remote_host"):
        errors.append("remote_host is not set (configure ~/.solar/remote-config.json or set SOLAR_REMOTE_HOST)")
    return errors


def remote_harness_path(config: dict[str, Any]) -> str:
    """Return a remote-shell-safe harness path for ssh/rsync commands."""
    remote_base = config.get("remote_path", "~")
    if remote_base == "~":
        return "$HOME/.solar/harness"
    return f"{str(remote_base).rstrip('/')}/.solar/harness"


def remote_sprints_path(config: dict[str, Any]) -> str:
    return f"{remote_harness_path(config)}/sprints"


# ---------------------------------------------------------------------------
# Manifest & Checksum
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


SPRINT_EXTENSIONS = [
    "contract.md", "status.json", "prd.md", "product-brief.md",
    "design.md", "plan.md", "task_graph.json",
    "dispatch_batches.json", "handoff.md", "eval.md", "eval.json",
]


def generate_manifest(sid: str) -> dict[str, Any]:
    """Generate a manifest with SHA-256 checksums for all existing sprint files."""
    files: dict[str, Any] = {}
    for ext in SPRINT_EXTENSIONS:
        p = SPRINTS_DIR / f"{sid}.{ext}"
        if p.exists():
            files[f"{sid}.{ext}"] = {
                "path": str(p),
                "size": p.stat().st_size,
                "sha256": _sha256_file(p),
            }
    manifest = {
        "sprint_id": sid,
        "generated_at": _utc_now(),
        "file_count": len(files),
        "files": files,
        "manifest_sha256": "",  # filled after serialization
    }
    # Compute manifest-level checksum (excluding the field itself)
    manifest_copy = dict(manifest)
    manifest_copy["manifest_sha256"] = ""
    canonical = json.dumps(manifest_copy, sort_keys=True, ensure_ascii=False)
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return manifest


def write_manifest(sid: str, manifest: dict[str, Any]) -> Path:
    """Write manifest to disk next to sprint files."""
    path = SPRINTS_DIR / f"{sid}.manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(manifest) + "\n", encoding="utf-8")
    return path


def verify_remote_checksum(config: dict[str, Any], sid: str,
                           manifest: dict[str, Any]) -> dict[str, Any]:
    """SSH to remote and verify each file's checksum matches the manifest.

    Returns {"ok": True} if all checksums match, or {"ok": False, "mismatches": [...]}.
    """
    target = f"{config['remote_user']}@{config['remote_host']}"
    remote_sprints = remote_sprints_path(config)

    mismatches: list[dict[str, str]] = []
    checked: list[str] = []

    for fname, finfo in manifest.get("files", {}).items():
        expected_sha = finfo.get("sha256", "")
        remote_path = f"{remote_sprints}/{fname}"
        try:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 target, f"shasum -a 256 '{remote_path}' 2>/dev/null || echo 'MISSING'"],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout.strip()
            if "MISSING" in output or not output:
                mismatches.append({"file": fname, "error": "missing_on_remote"})
                continue
            actual_sha = output.split()[0] if output.split() else ""
            if actual_sha != expected_sha:
                mismatches.append({
                    "file": fname,
                    "expected": expected_sha[:16],
                    "actual": actual_sha[:16],
                    "error": "checksum_mismatch",
                })
            else:
                checked.append(fname)
        except subprocess.TimeoutExpired:
            mismatches.append({"file": fname, "error": "ssh_timeout"})
        except Exception as exc:
            mismatches.append({"file": fname, "error": str(exc)})

    return {
        "ok": not mismatches,
        "checked": checked,
        "mismatches": mismatches,
    }


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def doctor(config: dict[str, Any]) -> dict[str, Any]:
    """Run health checks against the remote target and return structured status."""
    errors = validate_config(config)
    if errors:
        return {"ok": False, "errors": errors, "checks": {}}

    target = f"{config['remote_user']}@{config['remote_host']}"
    checks: dict[str, Any] = {}
    remote_harness = remote_harness_path(config)

    # 1. SSH connectivity
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             target, "echo ok"],
            capture_output=True, text=True, timeout=10,
        )
        checks["ssh"] = {"ok": result.returncode == 0, "returncode": result.returncode}
    except Exception as exc:
        checks["ssh"] = {"ok": False, "error": str(exc)}

    if not checks["ssh"]["ok"]:
        return {"ok": False, "target": target, "checks": checks}

    # 2. rsync availability
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target, "which rsync"],
            capture_output=True, text=True, timeout=10,
        )
        checks["rsync"] = {"ok": result.returncode == 0, "path": result.stdout.strip()}
    except Exception as exc:
        checks["rsync"] = {"ok": False, "error": str(exc)}

    # 3. Remote harness directory
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target,
             f"test -d \"{remote_harness}\" && echo ok || echo missing"],
            capture_output=True, text=True, timeout=10,
        )
        checks["remote_harness"] = {"ok": "ok" in result.stdout}
    except Exception as exc:
        checks["remote_harness"] = {"ok": False, "error": str(exc)}

    # 4. Remote harness version
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target,
             f"cat \"{remote_harness}/VERSION\" 2>/dev/null || echo unknown"],
            capture_output=True, text=True, timeout=10,
        )
        checks["remote_version"] = {"version": result.stdout.strip()}
    except Exception as exc:
        checks["remote_version"] = {"version": "unknown", "error": str(exc)}

    # 5. Remote tmux session
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target,
             "tmux has-session -t solar-harness 2>/dev/null && echo ok || echo missing"],
            capture_output=True, text=True, timeout=10,
        )
        checks["remote_tmux"] = {"ok": "ok" in result.stdout}
    except Exception as exc:
        checks["remote_tmux"] = {"ok": False, "error": str(exc)}

    # 6. Remote panes
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target,
             "tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}' -t solar-harness 2>/dev/null || echo none"],
            capture_output=True, text=True, timeout=10,
        )
        panes = [p.strip() for p in result.stdout.strip().splitlines() if p.strip() and p.strip() != "none"]
        checks["remote_panes"] = {"ok": len(panes) > 0, "panes": panes, "count": len(panes)}
    except Exception as exc:
        checks["remote_panes"] = {"ok": False, "error": str(exc)}

    # 7. Last sync timestamp
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", target,
             "cat ~/.solar/state/last-remote-sync 2>/dev/null || echo never"],
            capture_output=True, text=True, timeout=10,
        )
        checks["last_sync"] = {"timestamp": result.stdout.strip()}
    except Exception as exc:
        checks["last_sync"] = {"timestamp": "unknown", "error": str(exc)}

    all_ok = all(c.get("ok", True) for c in checks.values())
    return {
        "ok": all_ok,
        "target": target,
        "checks": checks,
        "checked_at": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Dispatch recording
# ---------------------------------------------------------------------------

def record_dispatch(sid: str, config: dict[str, Any],
                    manifest_sha256: str, forced: bool = False) -> dict[str, Any]:
    """Append a dispatch record to remote-sprints.jsonl."""
    REMOTE_SPRINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "sprint_id": sid,
        "dispatched_at": _utc_now(),
        "remote_host": config.get("remote_host", ""),
        "remote_user": config.get("remote_user", ""),
        "manifest_sha256": manifest_sha256,
        "forced": forced,
    }
    with open(REMOTE_SPRINTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def find_dispatch(sid: str) -> list[dict[str, Any]]:
    """Find all dispatch records for a given sprint ID."""
    if not REMOTE_SPRINTS_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(REMOTE_SPRINTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("sprint_id") == sid:
                    records.append(rec)
            except Exception:
                continue
    return records


def is_duplicate_dispatch(sid: str, manifest_sha256: str) -> bool:
    """Check if this exact (sid, manifest_sha256) was already dispatched."""
    for rec in find_dispatch(sid):
        if rec.get("manifest_sha256") == manifest_sha256:
            return True
    return False


# ---------------------------------------------------------------------------
# Status pull
# ---------------------------------------------------------------------------

PULL_EXTENSIONS = [
    "status.json", "events.jsonl", "task_graph.json",
    "handoff.md", "eval.md", "eval.json",
]


def pull_remote_status(sid: str, config: dict[str, Any],
                       local_dir: Path | None = None) -> dict[str, Any]:
    """Pull remote sprint status, events, graph, handoff, eval files to local."""
    target = f"{config['remote_user']}@{config['remote_host']}"
    remote_sprints = remote_sprints_path(config)
    dest = local_dir or SPRINTS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    pulled: list[str] = []
    errors: list[dict[str, str]] = []

    for ext in PULL_EXTENSIONS:
        remote_file = f"{remote_sprints}/{sid}.{ext}"
        local_file = dest / f"{sid}.{ext}"

        try:
            result = subprocess.run(
                ["rsync", "-avz", "--timeout=30",
                 f"{target}:{remote_file}", str(dest / "")],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # Mark source host on pulled status files
                if ext == "status.json" and local_file.exists():
                    try:
                        data = json.loads(local_file.read_text(encoding="utf-8"))
                        data.setdefault("pulled_from", {
                            "host": config.get("remote_host", ""),
                            "pulled_at": _utc_now(),
                        })
                        local_file.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                pulled.append(ext)
            else:
                errors.append({"ext": ext, "error": result.stderr.strip()[:200]})
        except subprocess.TimeoutExpired:
            errors.append({"ext": ext, "error": "timeout"})
        except Exception as exc:
            errors.append({"ext": ext, "error": str(exc)[:200]})

    return {
        "ok": not errors or len(pulled) > 0,
        "pulled": pulled,
        "errors": errors,
        "source_host": config.get("remote_host", ""),
        "pulled_at": _utc_now(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="remote_dispatch.py")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("config", help="Print resolved remote config as JSON")
    p.add_argument("--host", default="")
    p.add_argument("--user", default="")
    p.add_argument("--path", default="")

    p = sub.add_parser("doctor")
    p.add_argument("--host", default="")
    p.add_argument("--user", default="")
    p.add_argument("--path", default="")
    p.add_argument("--json", action="store_true", dest="json_output")

    p = sub.add_parser("manifest")
    p.add_argument("--sprint", required=True)

    p = sub.add_parser("verify")
    p.add_argument("--sprint", required=True)
    p.add_argument("--host", default="")
    p.add_argument("--user", default="")
    p.add_argument("--path", default="")

    p = sub.add_parser("pull")
    p.add_argument("--sprint", required=True)
    p.add_argument("--host", default="")
    p.add_argument("--user", default="")
    p.add_argument("--path", default="")
    p.add_argument("--dest", default="")

    args = ap.parse_args()

    if args.cmd == "config":
        config = load_config(
            host_override=getattr(args, "host", ""),
            user_override=getattr(args, "user", ""),
            path_override=getattr(args, "path", ""),
        )
        print(_json(config))
        return 0

    elif args.cmd == "doctor":
        config = load_config(args.host, args.user, args.path)
        result = doctor(config)
        print(_json(result))
        return 0 if result.get("ok") else 1

    elif args.cmd == "manifest":
        manifest = generate_manifest(args.sprint)
        path = write_manifest(args.sprint, manifest)
        print(_json({"ok": True, "manifest_path": str(path), **manifest}))
        return 0

    elif args.cmd == "verify":
        config = load_config(args.host, args.user, args.path)
        manifest_path = SPRINTS_DIR / f"{args.sprint}.manifest.json"
        if not manifest_path.exists():
            print(_json({"ok": False, "error": f"manifest not found: {manifest_path}"}))
            return 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = verify_remote_checksum(config, args.sprint, manifest)
        print(_json(result))
        return 0 if result.get("ok") else 1

    elif args.cmd == "pull":
        config = load_config(args.host, args.user, args.path)
        local_dir = Path(args.dest) if args.dest else None
        result = pull_remote_status(args.sprint, config, local_dir)
        print(_json(result))
        return 0 if result.get("ok") else 1

    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

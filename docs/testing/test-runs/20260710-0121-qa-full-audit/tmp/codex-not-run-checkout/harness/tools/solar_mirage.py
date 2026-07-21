#!/usr/bin/env python3
"""
solar_mirage.py — Solar Mirage VFS wrapper
Sprint: sprint-20260508-mirage-unified-vfs  Slice S1

Subcommands:
  doctor [--json]
  workspace create --id <id> [--json]
  workspace status [--id <id>] [--json]
  workspace destroy --id <id> [--force]
  mounts [--id <id>] [--json]
  exec [--id <id>] [--timeout <s>] [--allow-write-drive] -- <cmd...>
  provision --dry-run -- <cmd...>
  search <query> [--json] [--max-hits N] [--max-chars N]  (routes to mirage_search.py)

Security:
  - No whole $HOME mount
  - Drive write denied unless --allow-write-drive
  - exec paths rewritten logical→physical, ../ and symlink escape blocked
  - Secrets redacted from stdout/events
  - Events: state/mirage/events.jsonl + sprints/warn.events.jsonl
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hands_runtime import SandboxHand  # noqa: E402
from runtime_interfaces import ResultStatus  # noqa: E402

# ── Paths ──
HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(HOME / ".solar" / "harness")))
CONFIG_PATH = HARNESS_DIR / "config" / "mirage.solar.yaml"
STATE_DIR = HARNESS_DIR / "state" / "mirage"
LAST_PROBE_PATH = STATE_DIR / "last-probe.json"
EVENTS_JSONL = STATE_DIR / "events.jsonl"
SPRINTS_DIR = HARNESS_DIR / "sprints"
WARN_EVENTS = SPRINTS_DIR / "warn.events.jsonl"


# ── YAML loader ──
def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    except Exception as exc:
        return {"_error": str(exc)}
    # Minimal stdlib fallback
    return _load_yaml_minimal(path)


def _load_yaml_minimal(path: Path) -> dict:
    """Minimal YAML parser for constrained Solar manifest (no PyYAML fallback)."""
    result: dict = {}
    try:
        text = path.read_text()
    except OSError:
        return {}
    current_list: Optional[list] = None
    current_list_item: Optional[dict] = None
    current_key: Optional[str] = None

    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()

        if stripped.startswith('- '):
            content = stripped[2:]
            if ':' in content:
                k, v = content.split(':', 1)
                item: dict = {k.strip(): _scalar(v.strip())}
                if current_list is not None:
                    current_list.append(item)
                    current_list_item = item
            continue

        if ':' in stripped and not stripped.startswith('"'):
            k2, v2 = stripped.split(':', 1)
            k2 = k2.strip()
            v2 = v2.strip()
            if indent == 0:
                if not v2:
                    new_list: list = []
                    result[k2] = new_list
                    current_list = new_list
                    current_key = k2
                    current_list_item = None
                else:
                    result[k2] = _scalar(v2)
                    current_key = k2
                    current_list = None
            elif indent == 2 and current_list_item is not None:
                current_list_item[k2] = _scalar(v2) if v2 else []

    return result


def _scalar(v: str):
    if not v or v in ('null', '~'):
        return None
    if v in ('true', 'True', 'yes'):
        return True
    if v in ('false', 'False', 'no'):
        return False
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.startswith('[') and v.endswith(']'):
        return [x.strip().strip('"').strip("'") for x in v[1:-1].split(',') if x.strip()]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


# ── Event emitter ──
def _emit(event_type: str, data: dict) -> None:
    """Append event. Never include secret content."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event_type,
        **data,
    }
    for target in [EVENTS_JSONL, WARN_EVENTS]:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass


# ── Secret redactor ──
_REDACT_PATS = [
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'Bearer [A-Za-z0-9._\-]+'),
    re.compile(r'api_key=[^\s"\']+'),
    re.compile(r'client_secret=[^\s"\']+'),
    re.compile(r'refresh_token=[^\s"\']+'),
]


def _redact(text: str) -> str:
    for p in _REDACT_PATS:
        text = p.sub('[REDACTED]', text)
    return text


# Exec flags captured by REMAINDER that must be stripped from cmd_parts
_EXEC_BOOL_FLAGS = {"--json", "--allow-write-drive", "--allow-write-projects"}


def _check_deny_subpaths(physical: str, mount_entry: dict) -> str:
    """Returns the matched deny pattern string if access is denied, else ''."""
    deny_subpaths = mount_entry.get("deny_subpaths") or []
    if not deny_subpaths:
        return ""
    root = mount_entry.get("root", "")
    if not root:
        return ""
    root_real = _safe_realpath(root)
    rel = physical[len(root_real):].lstrip("/") if physical.startswith(root_real) else physical
    for ds in deny_subpaths:
        ds_clean = ds.rstrip("/")
        if rel.startswith(ds_clean) or ds_clean in rel:
            return ds_clean
    return ""


# ── Config / workspace state ──
def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return _load_yaml(CONFIG_PATH)


def _workspace_path(ws_id: str) -> Path:
    return STATE_DIR / f"{ws_id}.json"


def _load_workspace(ws_id: str) -> dict:
    p = _workspace_path(ws_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_workspace(ws_id: str, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _workspace_path(ws_id).write_text(json.dumps(data, indent=2))


# ── Mount resolver ──
def _resolve_mount(logical_path: str, config: dict) -> tuple:
    """Returns (physical_abs_path, mount_entry) or (None, None)."""
    mounts = config.get("mounts") or []
    best_mount = None
    best_prefix = ""
    for m in mounts:
        mp = m.get("path", "")
        if logical_path == mp or logical_path.startswith(mp + "/"):
            if len(mp) > len(best_prefix):
                best_prefix = mp
                best_mount = m
    if best_mount is None:
        return None, None

    root = best_mount.get("root") or ""
    if not root:
        return None, best_mount  # virtual mount (gdrive, qmd)

    suffix = logical_path[len(best_prefix):]
    physical = os.path.normpath(os.path.join(root, suffix.lstrip("/")))

    physical_real = _safe_realpath(physical)
    root_real = _safe_realpath(root)
    if not physical_real.startswith(root_real):
        return None, None  # escape attempt

    return physical_real, best_mount


def _safe_realpath(p: str) -> str:
    try:
        return str(Path(p).resolve())
    except Exception:
        return str(Path(p).absolute())


def _check_write_allowed(mount: dict, extra_flags: list) -> bool:
    mode = mount.get("mode", "ro")
    mount_path = mount.get("path", "")
    source_type = mount.get("source_type", "disk")

    if mode == "rw" and mount_path == "/raw":
        return True
    if source_type == "gdrive":
        return "--allow-write-drive" in extra_flags
    return False


# ── SDK/drive/QMD detection ──
def _detect_sdk() -> dict:
    try:
        import importlib.util
        spec = importlib.util.find_spec("mirage")
        if spec:
            import mirage  # type: ignore
            ver = getattr(mirage, "__version__", "unknown")
            return {"kind": "python", "path": str(spec.origin or ""), "version": ver}
    except Exception:
        pass

    cli = shutil.which("mirage")
    if cli:
        try:
            r = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=3)
            return {"kind": "cli", "path": cli, "version": (r.stdout.strip() or "unknown")}
        except Exception:
            return {"kind": "cli", "path": cli, "version": "unknown"}

    return {"kind": "none", "path": "", "version": ""}


def _detect_drive(config: dict) -> dict:
    drive_mount = next((m for m in (config.get("mounts") or []) if m.get("path") == "/drive"), {})
    cred_env = drive_mount.get("credential_env", "GOOGLE_APPLICATION_CREDENTIALS")
    cred_path = os.environ.get(cred_env, "")
    local_root = drive_mount.get("root") or ""

    if local_root and Path(local_root).exists():
        return {
            "status": "ok",
            "reason": "local Google Drive File Provider mount found",
            "credential_env": cred_env,
            "local_root": local_root,
            "provider": drive_mount.get("local_provider", "macos-file-provider"),
        }

    cloud_storage = HOME / "Library" / "CloudStorage"
    if cloud_storage.exists():
        for candidate in sorted(cloud_storage.glob("GoogleDrive-*")):
            if candidate.is_dir():
                return {
                    "status": "ok",
                    "reason": "local Google Drive File Provider mount found",
                    "credential_env": cred_env,
                    "local_root": str(candidate),
                    "provider": "macos-google-drive-file-provider",
                }

    if cred_path and Path(cred_path).exists():
        return {"status": "ok", "reason": "credentials found", "credential_env": cred_env}

    for dp in [HOME / ".config" / "mirage" / "drive.json",
               HOME / ".config" / "gcloud" / "application_default_credentials.json"]:
        if dp.exists():
            return {"status": "warn", "reason": f"found at {dp} but env not set", "credential_env": cred_env}

    return {"status": "degraded", "reason": "no credentials found", "credential_env": cred_env}


def _detect_qmd() -> dict:
    harness_sh = HARNESS_DIR / "solar-harness.sh"
    qmd_bin = (
        os.environ.get("QMD_BIN")
        or shutil.which("qmd")
        or str(HOME / ".npm-global" / "bin" / "qmd")
    )
    if harness_sh.exists():
        try:
            r = subprocess.run(
                ["bash", str(harness_sh), "wiki", "qmd-status", "--json"],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0 and r.stdout.strip():
                try:
                    return {"status": "ok", "detail": json.loads(r.stdout)}
                except json.JSONDecodeError:
                    return {"status": "ok", "binary": qmd_bin, "detail": _parse_qmd_status_text(r.stdout)}
        except Exception:
            pass
    if Path(qmd_bin).exists() or shutil.which(qmd_bin):
        try:
            r = subprocess.run([qmd_bin, "status"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return {"status": "ok", "binary": qmd_bin, "detail": _parse_qmd_status_text(r.stdout)}
            return {"status": "error", "binary": qmd_bin, "reason": (r.stderr or r.stdout)[-300:]}
        except Exception as exc:
            return {"status": "error", "binary": qmd_bin, "reason": str(exc)}
    return {"status": "missing", "binary": ""}


def _parse_qmd_status_text(text: str) -> dict:
    out: dict[str, object] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Total:"):
            out["total"] = line.split(":", 1)[1].strip()
        elif line.startswith("Vectors:"):
            out["vectors"] = line.split(":", 1)[1].strip()
        elif line.startswith("Pending:"):
            out["pending"] = line.split(":", 1)[1].strip()
        elif "solar-wiki" in line:
            out["collection"] = "solar-wiki"
    if not out:
        out["summary"] = text[:500]
    return out


def _detect_solar_db() -> dict:
    db_path = HOME / ".solar" / "solar.db"
    if db_path.exists():
        return {"status": "ok", "path": str(db_path),
                "size_mb": round(db_path.stat().st_size / 1048576, 1)}
    return {"status": "missing", "path": str(db_path), "size_mb": 0}


def _build_mounts_status(config: dict) -> list:
    result = []
    for m in (config.get("mounts") or []):
        mpath = m.get("path", "")
        mode = m.get("mode", "ro")
        source_type = m.get("source_type", "disk")
        optional = m.get("optional", False)

        if source_type == "disk":
            root = m.get("root") or ""
            if root:
                root_p = Path(root)
                # Security: never serve whole home
                if str(root_p) in (str(HOME), "/"):
                    result.append({"path": mpath, "ready": False, "mode": mode,
                                   "reason": "blocked: whole home mount denied"})
                    continue
                ready = root_p.exists()
                result.append({"path": mpath, "ready": ready, "mode": mode,
                                "physical_root": root, "optional": optional,
                                "reason": "" if ready else f"root not found: {root}"})
            else:
                result.append({"path": mpath, "ready": True, "mode": mode,
                                "physical_root": "", "optional": optional,
                                "reason": "allowlist empty"})
        elif source_type == "gdrive":
            config_for_drive = config
            drive = _detect_drive(config_for_drive)
            ready = drive["status"] == "ok"
            physical_root = m.get("root") or drive.get("local_root", "")
            result.append({"path": mpath, "ready": ready, "mode": mode,
                            "physical_root": physical_root,
                            "optional": optional, "status": drive["status"],
                            "reason": drive["reason"]})
        elif source_type == "virtual_command":
            adapter = m.get("adapter", "")
            result.append({"path": mpath, "ready": bool(adapter), "mode": mode,
                            "adapter": adapter, "optional": True})
        else:
            result.append({"path": mpath, "ready": False, "mode": mode,
                            "reason": f"unknown source_type: {source_type}"})
    return result


# ── Subcommand implementations ──

def cmd_doctor(args) -> dict:
    config = _load_config()
    sdk = _detect_sdk()
    drive = _detect_drive(config)
    qmd = _detect_qmd()
    solar_db = _detect_solar_db()
    raw_mounts = _build_mounts_status(config)

    fuse = {"available": False, "reason": "macOS requires kernel extension; use logical mount mode"}
    try:
        if shutil.which("mount_fuse") or Path("/usr/local/lib/libfuse.dylib").exists():
            fuse = {"available": True, "reason": "libfuse found (experimental)"}
    except Exception:
        pass

    # Transform raw mounts to design §2.2 schema: {path, status, type, reason}
    mounts_v2 = []
    for m in raw_mounts:
        mpath = m.get("path", "")
        ready = m.get("ready", False)
        src_status = m.get("status", "")  # for gdrive mounts
        # status: ok | degraded | down
        if ready:
            status = "ok"
        elif src_status in ("warn", "degraded"):
            status = "degraded"
        elif m.get("optional", False):
            status = "degraded"
        else:
            status = "down"
        # type: logical (all current mounts are logical wrapper, not FUSE)
        mtype = "logical"
        mounts_v2.append({
            "path": mpath,
            "ready": bool(ready),
            "mode": m.get("mode", "ro"),
            "status": status,
            "type": mtype,
            "physical_root": m.get("physical_root", ""),
            "optional": bool(m.get("optional", False)),
            "reason": m.get("reason", ""),
        })

    # drive_status / drive_unblock for design §2.2
    drive_raw_status = drive.get("status", "missing")
    if drive_raw_status == "ok":
        drive_status = "connected"
        drive_unblock = None
    elif drive_raw_status in ("degraded", "warn", "missing"):
        drive_status = "optional_missing"
        drive_unblock = {
            "env_var": "GOOGLE_DRIVE_REFRESH_TOKEN",
            "ui_path": "/integrations#drive",
        }
    else:
        drive_status = "disabled"
        drive_unblock = None

    # sdk_decision: always wrapper_only (macFUSE requires reboot+GUI under SIP)
    sdk_decision_doc = "reports/mirage-sdk-fuse-decision-2026-05-09.md"
    sdk_decision_doc_full = str(HOME / ".solar" / sdk_decision_doc)

    result = {
        "enabled": True,
        "version": sdk.get("version") or None,
        "sdk": sdk,
        "config": str(CONFIG_PATH) if CONFIG_PATH.exists() else None,
        "fuse": fuse,
        "mounts": mounts_v2,
        "drive": drive,
        "drive_status": drive_status,
        "drive_unblock": drive_unblock,
        "sdk_decision": "wrapper_only",
        "sdk_decision_doc": sdk_decision_doc_full,
        "qmd": qmd,
        "solar_db": solar_db,
        "last_probe_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LAST_PROBE_PATH.write_text(json.dumps(result, indent=2))
    except OSError:
        pass

    return result


def cmd_workspace_create(args) -> dict:
    ws_id = getattr(args, "id", None) or "solar-default"
    config = _load_config()
    mounts = _build_mounts_status(config)

    raw_mount = next((m for m in (config.get("mounts") or []) if m.get("path") == "/raw"), {})
    raw_root = raw_mount.get("root", "")
    if raw_root:
        Path(raw_root).mkdir(parents=True, exist_ok=True)

    ws_data = {
        "workspace_id": ws_id,
        "status": "active",
        "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": str(CONFIG_PATH),
        "mounts": mounts,
    }
    _save_workspace(ws_id, ws_data)
    _emit("mirage_workspace_created", {"workspace_id": ws_id, "mount_count": len(mounts)})
    return ws_data


def cmd_workspace_status(args) -> dict:
    ws_id = getattr(args, "id", None) or "solar-default"
    ws = _load_workspace(ws_id)
    if not ws:
        return {"workspace_id": ws_id, "status": "not_found"}
    return ws


def cmd_workspace_destroy(args) -> dict:
    ws_id = getattr(args, "id", None) or "solar-default"
    force = getattr(args, "force", False)
    p = _workspace_path(ws_id)
    if not p.exists():
        return {"workspace_id": ws_id, "status": "not_found"}
    if force:
        p.unlink(missing_ok=True)
        return {"workspace_id": ws_id, "status": "destroyed"}
    return {"workspace_id": ws_id, "status": "error", "reason": "use --force to destroy"}


def cmd_mounts(args) -> dict:
    ws_id = getattr(args, "id", None) or "solar-default"
    config = _load_config()
    mounts = _build_mounts_status(config)
    return {"workspace_id": ws_id, "mounts": mounts}


def cmd_exec(args, extra_flags: list) -> dict:
    ws_id = getattr(args, "id", None) or "solar-default"
    timeout_s = getattr(args, "timeout", None) or 30
    cmd_parts = getattr(args, "cmd", [])
    # Strip top-level exec flags that nargs=REMAINDER accidentally captured
    cmd_parts = [p for p in cmd_parts if p not in _EXEC_BOOL_FLAGS]
    if not cmd_parts:
        return {"error": "no command provided after --"}

    ws = _load_workspace(ws_id)
    if not ws:
        cmd_workspace_create(args)

    config = _load_config()
    policy = config.get("policy") or {}
    allowed_verbs = policy.get("allowed_verbs") or ["ls", "find", "grep", "cat", "head", "wc", "jq", "echo"]
    max_stdout = int(policy.get("max_stdout_bytes") or 1048576)
    mounts = config.get("mounts") or []

    cmd_str = " ".join(cmd_parts)
    original_cmd = cmd_str

    try:
        argv = shlex.split(cmd_str)
    except ValueError as e:
        return {"error": f"parse error: {e}", "cmd": cmd_str}

    if not argv:
        return {"error": "empty command"}

    verb = argv[0]
    if verb not in allowed_verbs:
        return {"error": f"verb not allowed: {verb}. Allowed: {', '.join(allowed_verbs)}",
                "cmd": cmd_str}

    # Block host-absolute paths that are NOT logical mount prefixes.
    # Covers: ~/... tilde paths, /Users/..., /etc/..., /private/..., /tmp/...
    # Any path starting with / or ~ that is NOT a configured logical mount root is denied.
    mount_prefixes = tuple(m.get("path", "") + "/" for m in mounts) + tuple(m.get("path", "") for m in mounts)
    HOME_STR = str(HOME)
    for token in argv[1:]:  # skip the verb itself
        if not token.startswith("/") and not token.startswith("~"):
            continue
        # Expand ~ for comparison only
        expanded = token.replace("~", HOME_STR, 1) if token.startswith("~") else token
        # If expanded path lives inside any physical mount root → still blocked (use logical path instead)
        # If token starts with a logical mount prefix → allowed (will be rewritten)
        is_logical = token.startswith(mount_prefixes) or token in (m.get("path", "") for m in mounts)
        if not is_logical:
            _emit("mirage_host_path_blocked", {
                "cmd": cmd_str,
                "token": token,
                "reason": "host absolute path not in any logical mount",
            })
            return {
                "error": f"host path not allowed: {token!r}. Use logical mount paths (/knowledge, /raw, /sources, /papers, /qmd, /solar-db, /cortex, /sprints)",
                "cmd": cmd_str,
                "exit_code": 126,
            }

    # Rewrite logical paths in argv → physical (for security checks)
    for token in argv:
        if token.startswith("/") and any(
            token == m.get("path") or token.startswith(m.get("path", "") + "/")
            for m in mounts
        ):
            physical, mount_entry = _resolve_mount(token, config)
            if physical is None and mount_entry is not None:
                # virtual mount (gdrive, qmd) - deny read by default in exec
                source_type = mount_entry.get("source_type", "disk")
                if source_type == "gdrive":
                    _emit("mirage_write_denied", {
                        "mount": mount_entry.get("path", ""),
                        "attempted_path": token,
                        "requested_mode": "read",
                    })
                    return {"error": f"path blocked or not found: {token}", "cmd": cmd_str}
            elif physical is None and mount_entry is None:
                return {"error": f"no mount for path: {token}", "cmd": cmd_str}
            elif physical is not None and mount_entry is not None:
                denied_by = _check_deny_subpaths(physical, mount_entry)
                if denied_by:
                    return {"error": f"path blocked by deny_subpaths: {denied_by}", "cmd": cmd_str, "exit_code": 126}

    # Detect and check write attempts (shell redirections)
    is_write_attempt = '>' in cmd_str or 'tee ' in cmd_str
    if is_write_attempt:
        redirect_targets = re.findall(r'>+\s*([^\s|;&\'"]+)', cmd_str)
        for rt in redirect_targets:
            if rt.startswith("/") and any(
                rt == m.get("path") or rt.startswith(m.get("path", "") + "/")
                for m in mounts
            ):
                physical, mount_entry = _resolve_mount(rt, config)
                if mount_entry is None:
                    _emit("mirage_write_denied", {"mount": rt, "attempted_path": rt, "requested_mode": "write"})
                    return {"error": f"no mount for redirect target: {rt}", "cmd": cmd_str}
                if physical is None:
                    _emit("mirage_write_denied", {"mount": rt, "attempted_path": rt, "requested_mode": "write"})
                    return {"error": f"path escape blocked: {rt}", "cmd": cmd_str}
                mpath = mount_entry.get("path", "")
                if not _check_write_allowed(mount_entry, extra_flags):
                    _emit("mirage_write_denied", {
                        "mount": mpath, "attempted_path": rt, "requested_mode": "write",
                    })
                    return {
                        "error": f"write denied to {mpath} (mode={mount_entry.get('mode','ro')})",
                        "cmd": cmd_str,
                    }
                # Rewrite redirect target → physical
                cmd_str = cmd_str.replace(rt, physical, 1)

    # Rewrite all logical mount paths → physical in the full command string
    final_cmd = cmd_str
    for m in sorted(mounts, key=lambda x: len(x.get("path", "")), reverse=True):
        mp = m.get("path", "")
        root = m.get("root") or ""
        if not mp or not root:
            continue
        final_cmd = re.sub(re.escape(mp) + r'(?=/|$|\s|\'|"|\|)', root, final_cmd)

    t0 = time.monotonic()
    hand = SandboxHand()
    hand_ref = None
    try:
        hand_ref = hand.provision(capabilities=["mirage-exec", verb])
        writable_roots = _mirage_writable_roots(mounts, extra_flags)
        result = hand.execute(
            hand_ref,
            f"mirage-exec-{verb}",
            {
                "argv": ["/bin/sh", "-c", final_cmd],
                "write_guard_roots": _mirage_guard_roots(mounts, original_cmd),
                "write_allowed_roots": writable_roots,
                "session_id": f"mirage-exec-{ws_id}",
                "sprint_id": f"mirage-exec-{ws_id}",
                "activity_id": f"mirage-exec-{verb}",
            },
            idempotency_key=f"mirage-exec:{ws_id}:{time.time_ns()}",
            timeout_seconds=int(float(timeout_s)),
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        stdout = _redact(str(result.output or ""))
        stderr = _redact(str((result.metadata or {}).get("stderr", "") or result.error or ""))
        exit_code = 0 if result.status == ResultStatus.OK else 1
        if result.status == ResultStatus.TIMEOUT:
            exit_code = -1

        # Filter stdout/stderr lines that expose physical paths of denied subpaths
        for _m in mounts:
            _deny = _m.get("deny_subpaths") or []
            _root = _m.get("root", "")
            if _deny and _root:
                _root_real = _safe_realpath(_root)
                for _ds in _deny:
                    _ds_clean = _ds.rstrip("/")
                    _denied_prefix = os.path.join(_root_real, _ds_clean)
                    stdout = "\n".join(l for l in stdout.split("\n") if _denied_prefix not in l)
                    stderr = "\n".join(l for l in stderr.split("\n") if _denied_prefix not in l)

        truncated = False
        if len(stdout.encode()) > max_stdout:
            stdout = stdout.encode()[:max_stdout].decode(errors='replace')
            truncated = True

        _emit("mirage_command_executed", {
            "cmd_kind": verb,
            "mount": _primary_mount(final_cmd, mounts),
            "duration_ms": elapsed_ms,
            "exit_code": exit_code,
            "executor": "sandbox",
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
        })

        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr[:4096],
            "duration_ms": elapsed_ms,
            "truncated": truncated,
            "cmd": original_cmd,
            "executor": "sandbox",
            "execution_mode": (result.metadata or {}).get("execution_mode", ""),
            "write_guard": (result.metadata or {}).get("write_guard", {}),
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
        }

    except subprocess.TimeoutExpired:
        _emit("mirage_command_executed", {
            "cmd_kind": verb, "mount": "", "duration_ms": int(timeout_s * 1000), "exit_code": -1
        })
        return {"error": f"command timed out after {timeout_s}s", "cmd": original_cmd}
    except Exception as e:
        return {"error": str(e), "cmd": original_cmd}
    finally:
        if hand_ref is not None:
            hand.dispose(hand_ref)


def _primary_mount(cmd_str: str, mounts: list) -> str:
    for m in sorted(mounts, key=lambda x: len(x.get("path", "")), reverse=True):
        mp = m.get("path", "")
        if mp and mp in cmd_str:
            return mp
    return ""


def _mirage_guard_roots(mounts: list, cmd_str: str) -> list[str]:
    roots: list[str] = []
    for m in mounts:
        mp = str(m.get("path") or "")
        if not mp or not re.search(re.escape(mp) + r"(?=/|$|\s|\'|\"|\|)", cmd_str):
            continue
        root = m.get("root") or m.get("physical_root") or ""
        if not root:
            continue
        try:
            p = Path(str(root)).expanduser()
            if p.exists():
                roots.append(str(p))
        except OSError:
            continue
    return sorted(set(roots))


def _mirage_writable_roots(mounts: list, extra_flags: list) -> list[str]:
    allowed: list[str] = []
    for m in mounts:
        root = m.get("root") or m.get("physical_root") or ""
        if not root:
            continue
        mode = str(m.get("mode") or "ro").lower()
        path = str(m.get("path") or "")
        if mode == "rw" or (path == "/drive" and "--allow-write-drive" in extra_flags):
            try:
                allowed.append(str(Path(str(root)).expanduser()))
            except OSError:
                continue
    return sorted(set(allowed))


def cmd_provision(args, extra_flags: list) -> dict:
    cmd_parts = getattr(args, "cmd", [])
    cmd_str = " ".join(cmd_parts)
    config = _load_config()
    mounts = config.get("mounts") or []
    plan = []
    for m in mounts:
        mp = m.get("path", "")
        root = m.get("root") or ""
        if mp and root and mp in cmd_str:
            plan.append({"logical": mp, "physical": root, "mode": m.get("mode", "ro")})
    return {"dry_run": True, "cmd": cmd_str, "mount_rewrites": plan, "would_execute": False}


def cmd_search(rest: list) -> None:
    """Route to mirage_search.py for unified search."""
    search_py = HARNESS_DIR / "lib" / "mirage_search.py"
    if not search_py.exists():
        print(json.dumps({
            "hits": [], "degraded_sources": ["mirage_search:module_missing"],
            "error": "mirage_search.py not found (S2 pending)", "query": " ".join(rest),
        }))
        sys.exit(1)
    r = subprocess.run([sys.executable, str(search_py)] + rest, capture_output=False)
    sys.exit(r.returncode)


# ── CLI ──
def main():
    parser = argparse.ArgumentParser(prog="solar_mirage", add_help=True)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="subcmd")

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--json", action="store_true")

    p_ws = sub.add_parser("workspace")
    ws_sub = p_ws.add_subparsers(dest="ws_action")
    for act in ("create", "status", "destroy"):
        p_wsa = ws_sub.add_parser(act)
        p_wsa.add_argument("--id", default="solar-default")
        p_wsa.add_argument("--json", action="store_true")
        if act == "destroy":
            p_wsa.add_argument("--force", action="store_true")

    p_mounts = sub.add_parser("mounts")
    p_mounts.add_argument("--id", default="solar-default")
    p_mounts.add_argument("--json", action="store_true")

    p_exec = sub.add_parser("exec")
    p_exec.add_argument("--id", default="solar-default")
    p_exec.add_argument("--timeout", type=int, default=30)
    p_exec.add_argument("--allow-write-drive", action="store_true", dest="allow_write_drive")
    p_exec.add_argument("--allow-write-projects", action="store_true", dest="allow_write_projects")
    p_exec.add_argument("--json", action="store_true")
    p_exec.add_argument("cmd", nargs=argparse.REMAINDER)

    p_prov = sub.add_parser("provision")
    p_prov.add_argument("--dry-run", action="store_true", default=True, dest="dry_run")
    p_prov.add_argument("cmd", nargs=argparse.REMAINDER)

    sub.add_parser("install")
    sub.add_parser("search")

    # Separate extra flags before argparse
    raw_argv = sys.argv[1:]
    extra_flags = []
    filtered_argv = []
    for a in raw_argv:
        if a in ("--allow-write-drive", "--allow-write-projects"):
            extra_flags.append(a)
        else:
            filtered_argv.append(a)

    # Special-case: search routes to mirage_search.py
    if filtered_argv and filtered_argv[0] == "search":
        cmd_search(filtered_argv[1:] + extra_flags)
        return

    args = parser.parse_args(filtered_argv)
    use_json = getattr(args, "json", False) or "--json" in sys.argv

    def out(data):
        print(json.dumps(data, indent=2, default=str))

    if args.subcmd is None or args.subcmd in ("help", None):
        parser.print_help()
        return

    if args.subcmd == "doctor":
        out(cmd_doctor(args))

    elif args.subcmd == "workspace":
        ws_action = getattr(args, "ws_action", None)
        if ws_action == "create":
            out(cmd_workspace_create(args))
        elif ws_action == "destroy":
            out(cmd_workspace_destroy(args))
        else:
            out(cmd_workspace_status(args))

    elif args.subcmd == "mounts":
        out(cmd_mounts(args))

    elif args.subcmd == "exec":
        cmd = getattr(args, "cmd", [])
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        args.cmd = cmd
        result = cmd_exec(args, extra_flags)
        if use_json:
            out(result)
        else:
            if "error" in result:
                print(f"ERROR: {result['error']}", file=sys.stderr)
                sys.exit(1)
            if result.get("stdout"):
                print(result["stdout"], end="")
            if result.get("stderr"):
                print(result["stderr"], end="", file=sys.stderr)
            if result.get("exit_code", 0) != 0:
                sys.exit(result["exit_code"])

    elif args.subcmd == "provision":
        cmd = getattr(args, "cmd", [])
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        args.cmd = cmd
        out(cmd_provision(args, extra_flags))

    elif args.subcmd == "install":
        sdk = _detect_sdk()
        if sdk["kind"] != "none":
            out({"status": "already_installed", "sdk": sdk})
            _emit("mirage_installed", {"method": "existing", "version": sdk["version"]})
        else:
            out({
                "status": "not_installed",
                "instructions": [
                    "pip install mirage-ai  # verify PyPI package name first",
                    "npm install -g @struktoai/mirage-node  # alternative",
                ],
                "warning": "Verify package names at https://github.com/strukto-ai/mirage",
            })

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

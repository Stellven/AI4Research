#!/usr/bin/env python3
"""Shared flow-control helpers for operator-backed and direct model calls."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import fcntl
import subprocess
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
PHYSICAL_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))
TASK_CONTROL_FILENAME = "operator-task-control.json"
BLOCKING_STATES = {"cooldown", "quota_exhausted", "auth_expired"}
ANTIGRAVITY_PROBE_PROMPT = "Reply with exactly: SOLAR_AGY_OK"
RATE_LIMIT_RE = re.compile(
    r"RESOURCE_EXHAUSTED|\bquota(?:\s+exhausted)?\b|monthly usage limit|"
    r"rate[- ]?limit|\b429\b|too many requests|resets?\s+in|"
    r"Upgrade your plan|You've hit .*limit|Individual quota reached|\bcapacity\b",
    re.I,
)
# NOTE: \bquota\b requires a word boundary after "quota", so "quotaProject=" is
# NOT matched — the word continues with "P" which is a word character.
AUTH_RE = re.compile(
    r"not logged in|you are not logged|auth(?:entication)? failed|oauth token|permission denied|"
    r"sign in|login wall|login required|logged out|auth expired",
    re.I,
)
AUTH_SUCCESS_RE = re.compile(
    r"OAuth:\s*authenticated successfully|silent auth succeeded|Auth done received|authenticated via keyring",
    re.I,
)
# Conversation bootstrap failure — distinct from auth: session exists but no active conversation.
NO_ACTIVE_CONVERSATION_RE = re.compile(
    r"no active conversation|failed to send message.*no active|Error:.*no active conversation",
    re.I,
)
RESET_TZ_RE = re.compile(r"\(([A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)\)")
RESET_RELATIVE_RE = re.compile(
    r"resets?\s+(?:in\s+)?(?:(?P<days>\d+)\s*d(?:ays?)?\s*)?"
    r"(?:(?P<hours>\d+)\s*h(?:ours?)?\s*)?"
    r"(?:(?P<minutes>\d+)\s*m(?:in(?:ute)?s?)?\s*)?"
    r"(?:(?P<seconds>\d+)\s*s(?:ec(?:ond)?s?)?)?",
    re.I,
)
RESET_COLON_RE = re.compile(r"resets?\s+in\s+(?P<hours>\d{1,2}):(?P<minutes>\d{2})(?::(?P<seconds>\d{2}))?", re.I)
RESET_AT_RE = re.compile(
    r"resets?(?:\s+(?:at|on))?\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
    re.I,
)


class FlowControlBlocked(RuntimeError):
    """Raised when a call is attempted during cooldown/auth-expired windows."""

    def __init__(self, operator_id: str, runtime_state: str, *, expires_at: str = "") -> None:
        self.operator_id = operator_id
        self.runtime_state = runtime_state
        self.expires_at = expires_at
        detail = f"operator {operator_id} blocked by flow control: state={runtime_state}"
        if expires_at:
            detail += f" until {expires_at}"
        super().__init__(detail)


def _operator_runtime_module():
    if str(HARNESS_DIR / "lib") not in sys.path:
        sys.path.insert(0, str(HARNESS_DIR / "lib"))
    import operator_runtime  # type: ignore

    return operator_runtime


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso_z(moment: dt.datetime | None = None) -> str:
    return (moment or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return dt.datetime.fromisoformat(raw).astimezone(dt.timezone.utc)
    except Exception:
        return None


def _timezone_from_text(text: str) -> dt.tzinfo:
    match = RESET_TZ_RE.search(text or "")
    if match:
        try:
            return ZoneInfo(match.group(1))
        except ZoneInfoNotFoundError:
            pass
    env_tz = os.environ.get("TZ") or "America/Toronto"
    try:
        return ZoneInfo(env_tz)
    except ZoneInfoNotFoundError:
        return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_rate_limit_reset_at(text: str, *, now: dt.datetime | None = None) -> dt.datetime | None:
    """Parse a TUI/API rate-limit reset timestamp from failure text.

    Supports common Claude/CLI strings such as:
    - "You've hit your limit · resets 1:40pm (America/Toronto)"
    - "rate limit resets in 2h 15m"
    - "resets in 01:30:00"
    """
    raw = text or ""
    tz = _timezone_from_text(raw)
    base = (now or _now()).astimezone(tz)

    match = RESET_COLON_RE.search(raw)
    if match:
        hours = int(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        seconds = int(match.group("seconds") or 0)
        return (base + dt.timedelta(hours=hours, minutes=minutes, seconds=seconds)).astimezone(dt.timezone.utc)

    match = RESET_RELATIVE_RE.search(raw)
    if match and any(match.group(name) for name in ("days", "hours", "minutes", "seconds")):
        delta = dt.timedelta(
            days=int(match.group("days") or 0),
            hours=int(match.group("hours") or 0),
            minutes=int(match.group("minutes") or 0),
            seconds=int(match.group("seconds") or 0),
        )
        if delta.total_seconds() > 0:
            return (base + delta).astimezone(dt.timezone.utc)

    match = RESET_AT_RE.search(raw)
    if match:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        ampm = str(match.group("ampm") or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= base:
                candidate += dt.timedelta(days=1)
            return candidate.astimezone(dt.timezone.utc)
    return None


def _seconds_until(moment: dt.datetime | None, fallback: int) -> int:
    if moment is None:
        return max(0, int(fallback or 0))
    seconds = int((moment - _now()).total_seconds())
    if int(fallback or 0) > 0:
        seconds = min(seconds, int(fallback))
    return max(1, seconds)


def _excerpt(text: str, limit: int = 800) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:limit]


def auth_failure_is_current(text: str) -> bool:
    raw = text or ""
    last_auth = None
    for match in AUTH_RE.finditer(raw):
        last_auth = match
    if last_auth is None:
        return False
    for success in AUTH_SUCCESS_RE.finditer(raw):
        if success.start() > last_auth.start():
            return False
    return True


def _is_antigravity_operator(operator_id: str, op: dict[str, Any]) -> bool:
    provider = str(op.get("provider") or "").strip().lower()
    backend = str(op.get("backend") or op.get("runtime") or op.get("command_backend") or "").strip().lower()
    model = str(op.get("model") or "").strip().lower()
    auth = op.get("auth") if isinstance(op.get("auth"), dict) else {}
    auth_mode = str(op.get("auth_mode") or auth.get("mode") or "").strip().lower()
    return (
        "antigravity" in operator_id.lower()
        or "antigravity" in backend
        or (provider in {"google", "antigravity"} and auth_mode == "oauth" and "gemini" in model)
    )


def _antigravity_auth_probe_enabled() -> bool:
    return bool_value(os.environ.get("SOLAR_ANTIGRAVITY_AUTH_PROBE"), True)


def run_antigravity_auth_probe() -> dict[str, Any]:
    """Return whether Antigravity CLI OAuth is currently usable.

    This intentionally verifies the real command backend instead of trusting a
    time-based auth_expired TTL. A user can re-authenticate at any time; stale
    flow-control blocks must then clear on the next reconcile.
    """
    if not _antigravity_auth_probe_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled"}
    agy = os.environ.get("AGY_BIN", str(HOME / ".local" / "bin" / "agy"))
    timeout_seconds = int_value(os.environ.get("SOLAR_ANTIGRAVITY_AUTH_PROBE_TIMEOUT"), 25)
    print_timeout = os.environ.get("SOLAR_ANTIGRAVITY_AUTH_PROBE_PRINT_TIMEOUT", "20s")
    log_file = Path(os.environ.get("SOLAR_ANTIGRAVITY_AUTH_PROBE_LOG", HARNESS_DIR / "run" / "antigravity-auth-probe.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        agy,
        "--log-file",
        str(log_file),
        "--dangerously-skip-permissions",
        "--print-timeout",
        str(print_timeout),
        "--print",
        ANTIGRAVITY_PROBE_PROMPT,
    ]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=max(5, timeout_seconds),
            cwd=str(HOME),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "ok": False,
            "reason": "timeout",
            "excerpt": _excerpt("\n".join([stdout, stderr]), 500),
        }
    except FileNotFoundError:
        return {"ok": False, "reason": "agy_not_found", "path": agy}
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__, "excerpt": _excerpt(str(exc), 500)}

    combined = "\n".join(part for part in [proc.stdout or "", proc.stderr or "", tail_file_text(log_file)] if part)
    if proc.returncode == 0 and "SOLAR_AGY_OK" in (proc.stdout or "") and not auth_failure_is_current(combined):
        return {"ok": True, "reason": "probe_success", "returncode": proc.returncode}
    state = classify_failure_state(combined)
    return {
        "ok": False,
        "reason": state or f"exit_{proc.returncode}",
        "returncode": proc.returncode,
        "excerpt": _excerpt(combined, 500),
    }


def tail_file_text(path: Path, limit: int = 4000) -> str:
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def bool_value(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def int_value(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def classify_failure_state(text: str) -> str:
    """Return a failure state string from operator output text.

    Priority: auth_expired > cooldown > bootstrap_failed > "".
    bootstrap_failed is a transient state (recoverable with --continue) and is
    NOT a member of BLOCKING_STATES; it exists only for diagnostics.
    """
    if auth_failure_is_current(text or ""):
        return "auth_expired"
    if RATE_LIMIT_RE.search(text or ""):
        return "cooldown"
    if NO_ACTIVE_CONVERSATION_RE.search(text or ""):
        return "bootstrap_failed"
    return ""


def format_auth_blocker_message(
    operator_id: str,
    runtime_state: str,
    *,
    expires_at: str = "",
    recovery_cmd: str = "agy login",
) -> str:
    """Return a human-readable auth blocker surface message with recovery suggestion."""
    lines = [
        f"[auth-blocker] operator={operator_id} state={runtime_state}",
    ]
    if expires_at:
        lines.append(f"  Blocked until: {expires_at}")
    if runtime_state == "auth_expired":
        lines.append("  Cause: Antigravity session not authenticated or token expired.")
        lines.append(f"  Recovery: Run `{recovery_cmd}` and re-authenticate, then clear the operator block:")
        lines.append(f"    python3 -m operator_runtime clear-override --operator {operator_id}")
    elif runtime_state == "bootstrap_failed":
        lines.append("  Cause: No active Antigravity conversation; --continue retry also failed.")
        lines.append("  Recovery: Start a new conversation in Antigravity, then retry the dispatch.")
    return "\n".join(lines)


def current_block_state(
    operator_id: str,
    *,
    allow_unregistered: bool = False,
    blocking_states: set[str] | None = None,
) -> dict[str, Any] | None:
    states = set(blocking_states or BLOCKING_STATES)
    runtime = _operator_runtime_module()
    status = runtime.get_operator_status(operator_id) or {}
    runtime_state = str(status.get("runtime_state") or "").strip()
    if runtime_state in states:
        return {
            "operator_id": operator_id,
            "runtime_state": runtime_state,
            "expires_at": str(status.get("expires_at") or "").strip(),
        }
    config = runtime.get_operator_config(operator_id)
    if config is None and allow_unregistered:
        return None
    if config is None:
        return None
    runtime_state = str(runtime.get_operator_runtime_state(operator_id) or "").strip()
    if runtime_state in states:
        return {
            "operator_id": operator_id,
            "runtime_state": runtime_state,
            "expires_at": str(status.get("expires_at") or "").strip(),
        }
    return None


def ensure_operator_available(
    operator_id: str,
    *,
    allow_unregistered: bool = False,
    blocking_states: set[str] | None = None,
) -> None:
    snapshot = current_block_state(
        operator_id,
        allow_unregistered=allow_unregistered,
        blocking_states=blocking_states,
    )
    if snapshot:
        raise FlowControlBlocked(
            operator_id,
            str(snapshot.get("runtime_state") or "cooldown"),
            expires_at=str(snapshot.get("expires_at") or ""),
        )


def set_operator_state(operator_id: str, runtime_state: str, *, ttl_seconds: int | None = None) -> dict[str, Any]:
    return _operator_runtime_module().set_operator_status(
        operator_id,
        runtime_state,
        ttl_seconds=ttl_seconds,
    )


def _load_operator_registry() -> dict[str, Any]:
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        data = json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "operators": {}}
    except Exception:
        return {"version": 1, "operators": {}}


def _write_operator_registry(payload: dict[str, Any]) -> None:
    PHYSICAL_OPERATORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(PHYSICAL_OPERATORS_PATH) + ".lock"

    with open(lock_path, "w") as lock_file:
        tmp = str(PHYSICAL_OPERATORS_PATH) + f".{os.getpid()}.{time.time_ns()}.tmp"
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, str(PHYSICAL_OPERATORS_PATH))
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def clear_expired_operator_config_block(operator_id: str) -> bool:
    registry = _load_operator_registry()
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    op = operators.get(operator_id)
    if not isinstance(op, dict):
        return False
    expires = _parse_time(op.get("quota_refresh_at") or (op.get("state") or {}).get("cooldown_until"))
    if expires is None or expires > _now():
        return False
    op["quota_guard_state"] = "ok"
    op["quota_refresh_at"] = None
    state = op.get("state") if isinstance(op.get("state"), dict) else {}
    state["runtime_state"] = "idle"
    state["cooldown_until"] = None
    state["last_error"] = None
    op["state"] = state
    _write_operator_registry(registry)
    return True


def _clear_registry_block(
    op: dict[str, Any],
    *,
    now: dt.datetime,
    reason: str,
) -> None:
    op["quota_guard_state"] = "ok"
    op["quota_refresh_at"] = None
    state = op.get("state") if isinstance(op.get("state"), dict) else {}
    state["runtime_state"] = "idle"
    state["cooldown_until"] = None
    state["last_error"] = None
    state["last_pruned_at"] = _iso_z(now)
    op["state"] = state
    flow = op.get("flow_control") if isinstance(op.get("flow_control"), dict) else {}
    flow["last_pruned_at"] = _iso_z(now)
    flow["last_prune_reason"] = reason
    op["flow_control"] = flow


def prune_expired_operator_config_blocks() -> dict[str, Any]:
    """Clear all expired rate-limit/auth blocks persisted in physical operators.

    This is safe to run periodically: non-expired blocks are preserved, expired
    blocks are reset to dispatchable baseline state, and operators without a
    persisted cooldown are ignored.
    """
    registry = _load_operator_registry()
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    now = _now()
    pruned: list[dict[str, str]] = []
    kept: list[dict[str, str]] = []
    antigravity_auth_probe: dict[str, Any] | None = None
    antigravity_auth_ok = False
    needs_antigravity_probe = any(
        isinstance(op, dict)
        and _is_antigravity_operator(str(operator_id), op)
        and str(
            (op.get("state") if isinstance(op.get("state"), dict) else {}).get("runtime_state")
            or op.get("quota_guard_state")
            or ""
        ).strip() == "auth_expired"
        for operator_id, op in operators.items()
    )
    if needs_antigravity_probe:
        antigravity_auth_probe = run_antigravity_auth_probe()
        antigravity_auth_ok = bool(antigravity_auth_probe.get("ok"))
    for operator_id, op in operators.items():
        if not isinstance(op, dict):
            continue
        state = op.get("state") if isinstance(op.get("state"), dict) else {}
        runtime_state = str(state.get("runtime_state") or op.get("quota_guard_state") or "").strip()
        if runtime_state not in {"cooldown", "quota_exhausted", "auth_expired"}:
            continue
        expires_raw = str(op.get("quota_refresh_at") or state.get("cooldown_until") or "").strip()
        if runtime_state == "auth_expired" and _is_antigravity_operator(str(operator_id), op):
            if antigravity_auth_ok:
                _clear_registry_block(op, now=now, reason="antigravity_auth_probe_success")
                pruned.append({
                    "operator_id": str(operator_id),
                    "runtime_state": runtime_state,
                    "expired_at": "antigravity_auth_probe_success",
                })
                continue
            if antigravity_auth_probe is not None:
                kept.append({
                    "operator_id": str(operator_id),
                    "runtime_state": runtime_state,
                    "expires_at": expires_raw or "auth_probe_failed",
                })
                continue
        expires = _parse_time(expires_raw)
        flow = op.get("flow_control") if isinstance(op.get("flow_control"), dict) else {}
        reason = str(flow.get("last_block_reason") or state.get("last_error") or "").strip().lower()
        source = str(flow.get("last_block_source") or "").strip().lower()
        excerpt = str(flow.get("last_block_excerpt") or "").lower()
        weak_pane_cooldown = (
            runtime_state == "cooldown"
            and reason in {"pane_tui_rate_limit_fallback_ttl", "pane_tui_rate_limit"}
            and source.startswith("tmux_pane:")
            and not any(
                token in excerpt
                for token in (
                    "rate limit",
                    "rate-limit",
                    "rate_limit",
                    "usage limit",
                    "quota exhausted",
                    "resource_exhausted",
                    "api error",
                    "/rate-limit-options",
                )
            )
        )
        if expires is not None and expires > now:
            if weak_pane_cooldown:
                pass
            else:
                kept.append({"operator_id": str(operator_id), "runtime_state": runtime_state, "expires_at": expires_raw})
                continue
        if expires is None and not weak_pane_cooldown:
            kept.append({"operator_id": str(operator_id), "runtime_state": runtime_state, "expires_at": expires_raw})
            continue
        _clear_registry_block(
            op,
            now=now,
            reason="weak_pane_rate_limit_evidence" if weak_pane_cooldown else "expired_operator_block",
        )
        pruned.append({
            "operator_id": str(operator_id),
            "runtime_state": runtime_state,
            "expired_at": "weak_pane_rate_limit_evidence" if weak_pane_cooldown else (expires_raw or "N/A"),
        })
    if pruned:
        _write_operator_registry(registry)
    status_pruned, status_kept = _prune_dynamic_operator_status_blocks(now, antigravity_auth_ok=antigravity_auth_ok)
    pruned.extend(status_pruned)
    kept.extend(status_kept)
    result: dict[str, Any] = {"ok": True, "checked": len(operators), "pruned": pruned, "kept": kept}
    if antigravity_auth_probe is not None:
        result["antigravity_auth_probe"] = antigravity_auth_probe
    return result


def _prune_dynamic_operator_status_blocks(
    now: dt.datetime,
    *,
    antigravity_auth_ok: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Prune transient operator-status cooldowns.

    Dynamic status files are written by runtime automation, not by the registry.
    A cooldown without reason/evidence and with a healthy operator is weak
    evidence; keeping it blocks the fleet even when provider quota is available.
    """
    runtime = _operator_runtime_module()
    status_dir = Path(getattr(runtime, "OPERATOR_STATUS_DIR", HARNESS_DIR / "run" / "operator-status"))
    health_dir = HARNESS_DIR / "run" / "operator-health"
    pruned: list[dict[str, str]] = []
    kept: list[dict[str, str]] = []
    if not status_dir.exists():
        return pruned, kept
    for path in status_dir.glob("*.json"):
        operator_id = path.stem
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        runtime_state = str(status.get("runtime_state") or "").strip()
        if runtime_state not in {"cooldown", "quota_exhausted", "auth_expired"}:
            continue
        if runtime_state == "auth_expired" and antigravity_auth_ok and "antigravity" in operator_id.lower():
            runtime.clear_operator_status(operator_id)
            pruned.append({
                "operator_id": operator_id,
                "runtime_state": runtime_state,
                "expired_at": "antigravity_auth_probe_success",
            })
            continue
        expires_raw = str(status.get("expires_at") or "").strip()
        expires = _parse_time(expires_raw)
        reason = str(status.get("reason") or status.get("last_error") or status.get("source") or "").strip()
        evidence = str(status.get("evidence") or status.get("evidence_text") or status.get("last_output_excerpt") or "").strip()
        weak_cooldown = runtime_state == "cooldown" and not reason and not evidence
        health_ok = False
        health_path = health_dir / f"{operator_id}.json"
        if health_path.exists():
            try:
                health = json.loads(health_path.read_text(encoding="utf-8"))
                health_ok = bool(health.get("ok"))
            except Exception:
                health_ok = False
        if expires is not None and expires <= now:
            runtime.clear_operator_status(operator_id)
            pruned.append({"operator_id": operator_id, "runtime_state": runtime_state, "expired_at": expires_raw or "N/A"})
            continue
        if weak_cooldown and health_ok:
            runtime.clear_operator_status(operator_id)
            pruned.append({"operator_id": operator_id, "runtime_state": runtime_state, "expired_at": "weak_no_evidence_health_ok"})
            continue
        kept.append({"operator_id": operator_id, "runtime_state": runtime_state, "expires_at": expires_raw or "N/A"})
    return pruned, kept


def persist_operator_block(
    operator_id: str,
    runtime_state: str,
    *,
    expires_at: dt.datetime | str | None = None,
    reason: str = "",
    source: str = "operator_flow_control",
    evidence_text: str = "",
) -> dict[str, Any]:
    """Persist a dispatch block into physical-operators.json for auditability."""
    reason_l = str(reason or "").strip().lower()
    source_l = str(source or "").strip().lower()
    evidence_l = str(evidence_text or "").lower()
    if reason_l in {"pane_tui_rate_limit_fallback_ttl", "pane_tui_rate_limit"} and source_l.startswith("tmux_pane:"):
        explicit_rate_limit = any(
            token in evidence_l
            for token in (
                "rate limit",
                "rate-limit",
                "rate_limit",
                "usage limit",
                "quota exhausted",
                "resource_exhausted",
                "api error",
                "/rate-limit-options",
            )
        )
        if not explicit_rate_limit:
            return {
                "ok": False,
                "reason": "weak_pane_rate_limit_evidence",
                "operator_id": operator_id,
            }

    if isinstance(expires_at, dt.datetime):
        expires_iso = _iso_z(expires_at.astimezone(dt.timezone.utc))
    else:
        expires_iso = str(expires_at or "").strip()

    registry = _load_operator_registry()
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    op = operators.get(operator_id)
    if not isinstance(op, dict):
        return {"ok": False, "reason": "operator_not_found", "operator_id": operator_id}

    op["quota_guard_state"] = runtime_state
    if expires_iso:
        op["quota_refresh_at"] = expires_iso
    state = op.get("state") if isinstance(op.get("state"), dict) else {}
    state.update(
        {
            "availability": "enabled",
            "runtime_state": runtime_state,
            "cooldown_until": expires_iso or None,
            "last_error": reason or runtime_state,
            "last_error_at": _iso_z(),
        }
    )
    op["state"] = state
    flow = op.get("flow_control") if isinstance(op.get("flow_control"), dict) else {}
    flow.update(
        {
            "last_block_state": runtime_state,
            "last_block_reason": reason or runtime_state,
            "last_block_source": source,
            "last_block_detected_at": _iso_z(),
            "last_block_expires_at": expires_iso,
            "last_block_excerpt": _excerpt(evidence_text),
        }
    )
    op["flow_control"] = flow
    _write_operator_registry(registry)
    return {"ok": True, "operator_id": operator_id, "runtime_state": runtime_state, "expires_at": expires_iso}


def apply_success_cooldown(operator_id: str, *, success_cooldown_seconds: int) -> dict[str, Any] | None:
    if int(success_cooldown_seconds or 0) <= 0:
        return None
    return set_operator_state(operator_id, "cooldown", ttl_seconds=int(success_cooldown_seconds))


def task_control_path(task_dir: Path) -> Path:
    return Path(task_dir) / TASK_CONTROL_FILENAME


def clear_task_control(task_dir: Path) -> None:
    task_control_path(task_dir).unlink(missing_ok=True)


def write_task_control(
    task_dir: Path,
    *,
    operator_id: str,
    action: str,
    runtime_state: str,
    reason: str,
    delay_seconds: int = 0,
) -> dict[str, Any]:
    task_dir = Path(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    now = _now()
    payload: dict[str, Any] = {
        "operator_id": operator_id,
        "action": action,
        "runtime_state": runtime_state,
        "reason": reason,
        "written_at": _iso_z(now),
    }
    if delay_seconds > 0:
        next_attempt = now + dt.timedelta(seconds=int(delay_seconds))
        payload["delay_seconds"] = int(delay_seconds)
        payload["not_before"] = _iso_z(next_attempt)
    path = task_control_path(task_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def read_task_control(task_dir: Path) -> dict[str, Any] | None:
    path = task_control_path(task_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def apply_failure_flow_control(
    task_dir: Path,
    *,
    operator_id: str,
    failure_text: str,
    rate_limit_cooldown_seconds: int,
    auth_cooldown_seconds: int,
    defer_on_cooldown: bool = False,
    defer_on_auth: bool = False,
) -> dict[str, Any]:
    runtime_state = classify_failure_state(failure_text)
    result = {"runtime_state": runtime_state, "task_control": None, "expires_at": "", "config_block": None}
    if runtime_state == "cooldown":
        reset_at = parse_rate_limit_reset_at(failure_text)
        cooldown = _seconds_until(reset_at, int(rate_limit_cooldown_seconds or 0))
        expires_iso = _iso_z(reset_at) if reset_at else ""
        if cooldown > 0:
            set_operator_state(operator_id, "cooldown", ttl_seconds=cooldown)
            result["expires_at"] = expires_iso or _iso_z(_now() + dt.timedelta(seconds=cooldown))
            result["config_block"] = persist_operator_block(
                operator_id,
                "cooldown",
                expires_at=str(result["expires_at"]),
                reason="rate_limit",
                source="failure_flow_control",
                evidence_text=failure_text,
            )
        if defer_on_cooldown and cooldown > 0:
            result["task_control"] = write_task_control(
                task_dir,
                operator_id=operator_id,
                action="defer",
                runtime_state="cooldown",
                reason="rate_limit",
                delay_seconds=cooldown,
            )
        return result
    if runtime_state == "auth_expired":
        cooldown = int(auth_cooldown_seconds or 0)
        expires = _now() + dt.timedelta(seconds=cooldown) if cooldown > 0 else None
        set_operator_state(
            operator_id,
            "auth_expired",
            ttl_seconds=cooldown if cooldown > 0 else None,
        )
        result["expires_at"] = _iso_z(expires) if expires else ""
        result["config_block"] = persist_operator_block(
            operator_id,
            "auth_expired",
            expires_at=str(result["expires_at"]),
            reason="auth_expired",
            source="failure_flow_control",
            evidence_text=failure_text,
        )
        if defer_on_auth and cooldown > 0:
            result["task_control"] = write_task_control(
                task_dir,
                operator_id=operator_id,
                action="defer",
                runtime_state="auth_expired",
                reason="auth_expired",
                delay_seconds=cooldown,
            )
        return result
    return result


def envelope_not_before_ready(envelope: dict[str, Any]) -> bool:
    not_before = _parse_time(envelope.get("not_before") or envelope.get("defer_until"))
    if not_before is None:
        return True
    return not_before <= _now()

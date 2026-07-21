#!/usr/bin/env python3
"""multi_task_status.py — operator lifecycle observability for multi-task bridge.

Provides path-injected helpers for reading operator runtime artifacts
(lease, heartbeat/status) and producing enriched status dicts that
include operator_id, role, resolved_persona, lifecycle_state, and
heartbeat fields required by the monitor bridge.

Design
------
All functions accept explicit ``personas_dir``, ``status_dir``, and
``lease_dir`` keyword arguments so tests can inject tmp directories
without monkeypatching global constants.  The module-level defaults
mirror the paths used by operator_runtime.py.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
OPERATOR_LEASE_DIR = HARNESS_DIR / "run" / "operator-leases"
OPERATOR_STATUS_DIR = HARNESS_DIR / "run" / "operator-status"
OPERATOR_PERSONAS_DIR = HARNESS_DIR / "personas"
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get(
        "SOLAR_MULTI_TASK_OPERATORS",
        HARNESS_DIR / "config" / "physical-operators.json",
    )
)

# Must stay in sync with operator_runtime.VALID_STATES.
_VALID_STATES = frozenset({
    "idle",
    "leased",
    "running",
    "draining",
    "cooldown",
    "quota_exhausted",
    "auth_expired",
    "disabled",
})


# ---------------------------------------------------------------------------
# Disk-read helpers (path-injected, read-only)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_heartbeat(op_id: str, status_dir: Path) -> Dict[str, Any]:
    """Return the daemon heartbeat dict for *op_id*, or ``{}`` if absent."""
    return _read_json(status_dir / f"{op_id}.json")


def _read_lease(op_id: str, lease_dir: Path) -> Dict[str, Any]:
    """Return the active lease dict for *op_id*, or ``{}`` if absent."""
    return _read_json(lease_dir / f"{op_id}.json")


# ---------------------------------------------------------------------------
# Lifecycle state resolution (mirrors operator_runtime logic, path-injected)
# ---------------------------------------------------------------------------

def _resolve_lifecycle_state(
    op_id: str,
    op_cfg: Dict[str, Any],
    lease_dir: Path,
    status_dir: Path,
) -> str:
    """Return the lifecycle state string for one operator.

    Resolution order (mirrors ``operator_runtime.get_operator_runtime_state``):
    1. Disabled in registry config.
    2. Active, non-expired lease.
    3. Dynamic status / heartbeat override.
    4. Registry ``state.runtime_state`` baseline.
    5. ``"idle"`` fallback.
    """
    if not op_cfg.get("enabled", True):
        return "disabled"

    reg_state = op_cfg.get("state", {})
    if isinstance(reg_state, dict):
        if (
            reg_state.get("availability") == "disabled"
            or reg_state.get("runtime_state") == "disabled"
        ):
            return "disabled"

    # Lease takes highest precedence when active and not expired.
    lease = _read_lease(op_id, lease_dir)
    if lease:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        if lease.get("expires_at", "") > now_str:
            state = lease.get("state")
            if state in _VALID_STATES:
                return str(state)
            return "leased"

    # Heartbeat / dynamic status override.
    hb = _read_heartbeat(op_id, status_dir)
    if hb:
        r_state = hb.get("runtime_state")
        if r_state in _VALID_STATES:
            return str(r_state)

    # Registry baseline.
    if isinstance(reg_state, dict):
        baseline = reg_state.get("runtime_state")
        if baseline in _VALID_STATES:
            return str(baseline)

    return "idle"


# ---------------------------------------------------------------------------
# Per-operator enriched status entry
# ---------------------------------------------------------------------------

def get_operator_status_entry(
    op_id: str,
    op_cfg: Dict[str, Any],
    *,
    personas_dir: Path = OPERATOR_PERSONAS_DIR,
    status_dir: Path = OPERATOR_STATUS_DIR,
    lease_dir: Path = OPERATOR_LEASE_DIR,
) -> Dict[str, Any]:
    """Return a fully-enriched status dict for one operator.

    Always-present fields
    ---------------------
    operator_id       Operator ID string.
    role              Role from registry config.
    resolved_persona  Persona name: config.persona → config.role → heartbeat → "N/A".
    lifecycle_state   Runtime lifecycle state (see _VALID_STATES).
    heartbeat_at      ISO-8601 timestamp from last daemon heartbeat, or "N/A".
    daemon_state      State recorded in last heartbeat, or "N/A".
    current_task_id   Task ID daemon is executing, or "N/A".
    submit_state      Active lease dict (task_id/sprint_id/node_id/state/…), or None.
    display_name      Human-readable name from config.
    profile           Persona/profile name from config.
    provider          Provider string from config.
    vendor            Vendor string from config.
    model             Model string from config.
    enabled           Whether operator is enabled in registry.
    surface           Surface config dict from registry (``operator.surface``), or None.
    billing_surface   Billing surface string from registry, or "N/A".
    billing_pool      Billing pool string from registry, or "N/A".
    """
    lifecycle_state = _resolve_lifecycle_state(op_id, op_cfg, lease_dir, status_dir)

    hb = _read_heartbeat(op_id, status_dir)
    heartbeat_at: str = str(hb.get("heartbeat_at") or "N/A")
    daemon_state: str = str(hb.get("state") or hb.get("runtime_state") or "N/A")
    current_task_id: str = str(hb.get("current_task_id") or "N/A")
    heartbeat_persona: Optional[str] = hb.get("resolved_persona") or None

    resolved_persona: str = (
        str(op_cfg.get("persona") or "")
        or str(op_cfg.get("role") or "")
        or str(heartbeat_persona or "")
        or "N/A"
    )

    # Submit state from the active, non-expired lease.
    lease = _read_lease(op_id, lease_dir)
    submit_state: Optional[Dict[str, Any]] = None
    if lease:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        if lease.get("expires_at", "") > now_str:
            submit_state = {
                "task_id": str(lease.get("task_id") or "N/A"),
                "sprint_id": str(lease.get("sprint_id") or "N/A"),
                "node_id": str(lease.get("node_id") or "N/A"),
                "state": str(lease.get("state") or "N/A"),
                "leased_at": str(lease.get("leased_at") or "N/A"),
                "expires_at": str(lease.get("expires_at") or "N/A"),
            }

    # Claude surface / billing fields from registry config.
    raw_surface = op_cfg.get("surface")
    surface: Optional[Dict[str, Any]] = raw_surface if isinstance(raw_surface, dict) else None

    return {
        "operator_id": op_id,
        "role": str(op_cfg.get("role") or "N/A"),
        "resolved_persona": resolved_persona,
        "lifecycle_state": lifecycle_state,
        "heartbeat_at": heartbeat_at,
        "daemon_state": daemon_state,
        "current_task_id": current_task_id,
        "submit_state": submit_state,
        "display_name": str(op_cfg.get("display_name") or op_id),
        "profile": str(op_cfg.get("profile") or op_cfg.get("persona") or "N/A"),
        "provider": str(op_cfg.get("provider") or "N/A"),
        "vendor": str(op_cfg.get("vendor") or "N/A"),
        "model": str(op_cfg.get("model") or "N/A"),
        "enabled": bool(op_cfg.get("enabled", True)),
        "surface": surface,
        "billing_surface": str(op_cfg.get("billing_surface") or "N/A"),
        "billing_pool": str(op_cfg.get("billing_pool") or "N/A"),
    }


# ---------------------------------------------------------------------------
# Actor-based status (N4 lease-fleet observability)
# ---------------------------------------------------------------------------

ACTORS_PATH = HARNESS_DIR / "config" / "agent-actors.json"
HOSTS_PATH = HARNESS_DIR / "config" / "actor-hosts.json"
LOGICAL_OPS_PATH = HARNESS_DIR / "config" / "logical-operators.json"
ACTOR_LEASE_DIR = HARNESS_DIR / "run" / "actor-leases"
CANONICAL_HOST_TYPES = (
    "claude_code_session",
    "tmux_pane",
    "operator_pool",
    "antigravity_managed_env",
    "browser_profile",
    "remote_shell",
    "api_worker",
    "local_process",
)

# Fields that must never be emitted in observability output.
# Uses substring containment check; whitelist safe compound keys separately.
_SECRET_PATTERNS = frozenset({
    "api_key", "secret", "password", "cookie", "credential",
    "raw_key", "prompt_body", "context_body", "session_key",
    "private_key", "access_token", "refresh_token", "auth_token",
    "bearer", "sk-", "session_token",
})
# Keys that contain a secret pattern substring but are safe summaries.
_SAFE_KEY_SUFFIXES = frozenset({
    "capability_token_summary",
    "token_budget_class",
})


def _redact_secrets(d: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any key whose name suggests secret content."""
    if not isinstance(d, dict):
        return d
    out: Dict[str, Any] = {}
    for k, v in d.items():
        kl = k.lower()
        if kl in _SAFE_KEY_SUFFIXES:
            pass  # explicitly safe
        elif any(sf in kl for sf in _SECRET_PATTERNS):
            continue
        if isinstance(v, dict):
            out[k] = _redact_secrets(v)
        elif isinstance(v, list):
            out[k] = [_redact_secrets(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_actors(path: Path = ACTORS_PATH) -> Dict[str, Any]:
    return _load_json(path).get("actors", {})


def load_hosts(path: Path = HOSTS_PATH) -> Dict[str, Any]:
    return _load_json(path).get("hosts", {})


def load_logical_operator_bindings(path: Path = LOGICAL_OPS_PATH) -> Dict[str, Any]:
    data = _load_json(path)
    return data.get("bindings", {})


def _operator_pane_matches(pane: str, configured: str) -> bool:
    pane = str(pane or "").strip()
    configured = str(configured or "").strip()
    if not pane or not configured:
        return False
    if configured == pane:
        return True
    if configured.endswith("*"):
        return pane.startswith(configured[:-1])
    return False


def _lease_state_for_actor(actor_id: str, lease_dir: Path = ACTOR_LEASE_DIR) -> str:
    lease_data = _read_json(lease_dir / f"{actor_id}.json")
    if not lease_data:
        return "idle"
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if lease_data.get("expires_at", "") > now_str:
        return str(lease_data.get("state") or "leased")
    return "stale"


def _capability_match(
    actor_cfg: Dict[str, Any],
    required_capabilities: Optional[list[str]] = None,
) -> Dict[str, Any]:
    profile = actor_cfg.get("capability_profile")
    if not isinstance(profile, dict):
        profile = actor_cfg.get("capability") if isinstance(actor_cfg.get("capability"), dict) else {}
    required = [str(item) for item in (required_capabilities or []) if str(item)]
    observed = sorted(str(k) for k, v in profile.items() if isinstance(v, (int, float)) and v)
    matched = sorted(set(required).intersection(observed))
    return {
        "required": required,
        "matched": matched,
        "missing": sorted(set(required).difference(observed)),
        "observed": observed,
    }


def resolve_actorhost_status(
    *,
    actor_id: str = "",
    pane: str = "",
    operator_id: str = "",
    actors_path: Path = ACTORS_PATH,
    hosts_path: Path = HOSTS_PATH,
    physical_operators_path: Path = PHYSICAL_OPERATORS_PATH,
    lease_dir: Path = ACTOR_LEASE_DIR,
    required_capabilities: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Resolve actor/host taxonomy using actor-hosts first, compat only as evidence."""
    actors = load_actors(actors_path)
    hosts = load_hosts(hosts_path)
    resolved_actor_id = str(actor_id or operator_id or "").strip()
    if pane.startswith("operator:") and not resolved_actor_id:
        resolved_actor_id = pane.split(":", 1)[1].strip()

    actor_cfg = actors.get(resolved_actor_id) if resolved_actor_id else {}
    if isinstance(actor_cfg, dict) and actor_cfg:
        host_id = str(actor_cfg.get("host_id") or "unknown")
        host_cfg = hosts.get(host_id, {}) if isinstance(hosts, dict) else {}
        host_type = str(host_cfg.get("host_type") or "unknown")
        return _redact_secrets({
            "actor_id": resolved_actor_id,
            "host_id": host_id,
            "host_type": host_type,
            "lease_state": _lease_state_for_actor(resolved_actor_id, lease_dir),
            "capability_match": _capability_match(actor_cfg, required_capabilities),
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "actor_hosts",
            "canonical_host_type": host_type in CANONICAL_HOST_TYPES,
        })

    physical = _load_json(physical_operators_path).get("operators", {})
    if isinstance(physical, dict):
        for op_id, op_cfg in physical.items():
            if not isinstance(op_cfg, dict):
                continue
            if operator_id and str(op_id) != str(operator_id):
                continue
            if not operator_id and not _operator_pane_matches(pane, str(op_cfg.get("pane") or "")):
                continue
            compat = op_cfg.get("compat_maps_to")
            if not isinstance(compat, dict):
                continue
            host_type = str(compat.get("host_type") or "unknown")
            return _redact_secrets({
                "actor_id": str(op_id),
                "host_id": "N/A",
                "host_type": host_type,
                "lease_state": "unknown",
                "capability_match": {
                    "required": [str(item) for item in (required_capabilities or []) if str(item)],
                    "matched": [],
                    "missing": [str(item) for item in (required_capabilities or []) if str(item)],
                    "observed": [],
                },
                "compat_fallback": True,
                "compat_maps_to": compat,
                "resolution_source": "physical_operators.compat_maps_to",
                "canonical_host_type": host_type in CANONICAL_HOST_TYPES,
            })

    return {
        "actor_id": resolved_actor_id or "N/A",
        "host_id": "N/A",
        "host_type": "unknown",
        "lease_state": "unknown",
        "capability_match": {
            "required": [str(item) for item in (required_capabilities or []) if str(item)],
            "matched": [],
            "missing": [str(item) for item in (required_capabilities or []) if str(item)],
            "observed": [],
        },
        "compat_fallback": False,
        "compat_maps_to": None,
        "resolution_source": "unresolved",
        "canonical_host_type": False,
    }


def get_actor_status_entry(
    actor_id: str,
    actor_cfg: Dict[str, Any],
    *,
    hosts: Optional[Dict[str, Any]] = None,
    lease_dir: Path = ACTOR_LEASE_DIR,
) -> Dict[str, Any]:
    """Return enriched status dict for one agent actor.

    Includes actor_id, host_id, host_type, lease_state, billing_pool,
    operator_score summary, verification_gate status, capability/risk/cost
    summary, evidence path, context_packet info, capability-token summary,
    failure-fingerprint penalties, and antigravity denials.
    """
    hosts = hosts or {}
    host_id = str(actor_cfg.get("host_id") or "unknown")
    host_cfg = hosts.get(host_id, {})
    host_type = str(host_cfg.get("host_type") or "unknown")
    host_lifecycle = host_cfg.get("lifecycle", {})
    host_state = str(host_lifecycle.get("state") or "unknown")
    host_last_seen = str(host_lifecycle.get("last_seen_at") or "N/A")

    # Lease state from actor-leases dir
    lease_data = _read_json(lease_dir / f"{actor_id}.json")
    lease_state = "idle"
    if lease_data:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        if lease_data.get("expires_at", "") > now_str:
            lease_state = str(lease_data.get("state") or "leased")
        else:
            lease_state = "stale"

    # Profiles (summaries only, no raw secrets)
    cap_profile = actor_cfg.get("capability_profile", {})
    risk_profile = actor_cfg.get("risk_profile", {})
    cost_profile = actor_cfg.get("cost_profile", {})

    cap_summary = {
        k: v for k, v in cap_profile.items()
        if isinstance(v, (int, float))
    }
    risk_summary = {
        k: str(v) for k, v in risk_profile.items()
        if not k.startswith("requires_human")
    }
    cost_summary = {
        k: str(v) if isinstance(v, list) else v
        for k, v in cost_profile.items()
        if k in ("cost_tier", "token_budget_class", "effort", "reserve_ratio")
    }

    # Evidence and context
    ev_ref = actor_cfg.get("evidence_ledger_ref", {})
    ctx_ref = actor_cfg.get("context_packet_ref", {})
    evidence_path = str(ev_ref.get("path") or "N/A") if isinstance(ev_ref, dict) else "N/A"
    context_packet_id = str(ctx_ref.get("packet_id") or "N/A") if isinstance(ctx_ref, dict) else "N/A"
    context_packet_path = str(ctx_ref.get("path") or "N/A") if isinstance(ctx_ref, dict) else "N/A"

    # Billing
    billing_pool = str(cost_profile.get("cost_tier") or "N/A")

    return _redact_secrets({
        "actor_id": actor_id,
        "host_id": host_id,
        "host_type": host_type,
        "host_state": host_state,
        "host_last_seen": host_last_seen,
        "lease_state": lease_state,
        "role": str(actor_cfg.get("role") or "N/A"),
        "enabled": bool(actor_cfg.get("enabled", True)),
        "billing_pool": billing_pool,
        "capability_summary": cap_summary,
        "risk_summary": risk_summary,
        "cost_summary": cost_summary,
        "evidence_path": evidence_path,
        "context_packet_id": context_packet_id,
        "context_packet_path": context_packet_path,
        "operator_score_summary": None,
        "verification_gate_status": None,
        "capability_token_summary": None,
        "failure_fingerprint_penalties": None,
        "antigravity_denials": None,
    })


def get_host_status_entry(
    host_id: str,
    host_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Return enriched status dict for one host."""
    lifecycle = host_cfg.get("lifecycle", {})
    address = host_cfg.get("address", {})
    heartbeat = host_cfg.get("heartbeat", {})
    probe = host_cfg.get("probe", {})

    return {
        "host_id": host_id,
        "host_type": str(host_cfg.get("host_type") or "unknown"),
        "display_name": str(host_cfg.get("display_name") or host_id),
        "state": str(lifecycle.get("state") or "unknown"),
        "started_at": str(lifecycle.get("started_at") or "N/A"),
        "last_seen_at": str(lifecycle.get("last_seen_at") or "N/A"),
        "shutdown_policy": str(lifecycle.get("shutdown_policy") or "N/A"),
        "hostname": str(address.get("hostname") or "N/A"),
        "heartbeat_interval_sec": heartbeat.get("interval_sec", "N/A"),
        "last_probe_result": str(probe.get("last_probe_result") or "N/A"),
    }


def load_actor_fleet(
    actors_path: Path = ACTORS_PATH,
    hosts_path: Path = HOSTS_PATH,
    *,
    lease_dir: Path = ACTOR_LEASE_DIR,
) -> Dict[str, Any]:
    """Load all actors and return enriched fleet dict."""
    actors = load_actors(actors_path)
    hosts = load_hosts(hosts_path)
    fleet: Dict[str, Any] = {}
    for aid, acfg in actors.items():
        if not isinstance(acfg, dict):
            continue
        fleet[aid] = get_actor_status_entry(aid, acfg, hosts=hosts, lease_dir=lease_dir)
    return fleet


def load_host_fleet(
    hosts_path: Path = HOSTS_PATH,
) -> Dict[str, Any]:
    """Load all hosts and return enriched fleet dict."""
    hosts = load_hosts(hosts_path)
    fleet: Dict[str, Any] = {}
    for hid, hcfg in hosts.items():
        if not isinstance(hcfg, dict):
            continue
        fleet[hid] = get_host_status_entry(hid, hcfg)
    return fleet


def get_logical_operator_binding_summary(
    bindings_path: Path = LOGICAL_OPS_PATH,
) -> Dict[str, Any]:
    """Return logical operator bindings summary for observability.

    Each operator gets: candidates (actor_ids), selection_policy, fallback_policy.
    No raw context or config details leaked.
    """
    bindings = load_logical_operator_bindings(bindings_path)
    summary: Dict[str, Any] = {}
    for op, entry in bindings.items():
        if not isinstance(entry, dict):
            continue
        candidates = entry.get("candidates", [])
        if candidates and isinstance(candidates[0], dict):
            cids = [c.get("actor_id", "") for c in candidates]
        else:
            cids = list(candidates)
        summary[op] = {
            "candidates": cids,
            "selection_policy": str(entry.get("selection_policy", "N/A")),
            "fallback_policy": str(entry.get("fallback_policy", "N/A")),
        }
    return summary


# ---------------------------------------------------------------------------
# Fleet loader
# ---------------------------------------------------------------------------

def load_operator_fleet(
    operators_path: Path = PHYSICAL_OPERATORS_PATH,
    *,
    personas_dir: Path = OPERATOR_PERSONAS_DIR,
    status_dir: Path = OPERATOR_STATUS_DIR,
    lease_dir: Path = OPERATOR_LEASE_DIR,
) -> Dict[str, Any]:
    """Load all operators from *operators_path* and return an enriched fleet dict.

    Returns a ``{operator_id: enriched_entry}`` mapping.  Empty dict on any
    read/parse error so callers can always iterate safely.
    """
    try:
        registry = json.loads(operators_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(registry, dict):
        return {}
    operators = registry.get("operators", {})
    if not isinstance(operators, dict):
        return {}

    fleet: Dict[str, Any] = {}
    for op_id, op_cfg in operators.items():
        if not isinstance(op_cfg, dict):
            continue
        fleet[op_id] = get_operator_status_entry(
            op_id,
            op_cfg,
            personas_dir=personas_dir,
            status_dir=status_dir,
            lease_dir=lease_dir,
        )
    return fleet

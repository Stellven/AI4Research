#!/usr/bin/env python3
"""operator_naming.py — Canonical operator-id and pane-title helpers.

Provides deterministic, human-readable identifiers for Solar Harness
operators across all backends (Claude, Codex, Antigravity, local).

Public API:
    canonical_operator_id(operator_id, config=None) -> str
    pane_title(operator_id, role, vendor=None, model=None) -> str
    apply_pane_title(title, pane_id=None) -> None   # safe no-op outside tmux
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

# Maps raw backend/provider/vendor strings → canonical vendor slug
_VENDOR_SLUG: dict[str, str] = {
    # Anthropic / Claude
    "anthropic": "claude",
    "claude-cli": "claude",
    "claude": "claude",
    # OpenAI / Codex
    "openai": "codex",
    "codex": "codex",
    "openai-api": "codex",
    # Google Antigravity
    "google": "antigravity",
    "agy": "antigravity",
    "agy-cli": "antigravity",
    "antigravity": "antigravity",
    # Local / on-device
    "local": "local",
    "thunderomlx": "local",
    "glm": "local",
    "ripgrep": "local",
    "command": "local",
}

# Human-readable labels per vendor slug (for pane titles)
_VENDOR_LABEL: dict[str, str] = {
    "claude": "Claude",
    "codex": "Codex",
    "antigravity": "Antigravity",
    "local": "Local",
}


def _vendor_slug(config: dict[str, Any]) -> str:
    """Derive canonical vendor slug from an operator config dict.

    Priority order: provider > backend > vendor > model.
    Generic backends like ``"command"`` and ``"local"`` are resolved last
    so that a specific ``provider`` (e.g. ``"google"``) takes precedence.
    """
    # Separate generic backends that should not override a specific provider
    _GENERIC_BACKENDS = {"command", "local"}

    backend_raw = str(config.get("backend", "")).lower()
    backend_is_generic = backend_raw in _GENERIC_BACKENDS

    if not backend_is_generic:
        slug = _VENDOR_SLUG.get(backend_raw)
        if slug:
            return slug

    for key in ("provider", "vendor", "model"):
        raw = str(config.get(key, "")).lower()
        if raw in _VENDOR_SLUG:
            return _VENDOR_SLUG[raw]

    # Fall back to the generic backend slug if nothing else matched
    if backend_raw in _VENDOR_SLUG:
        return _VENDOR_SLUG[backend_raw]

    return "local"


def canonical_operator_id(operator_id: str, config: Optional[dict[str, Any]] = None) -> str:
    """Return a stable canonical operator ID string.

    The canonical form is:  <vendor>/<role>/<slug>
    where <slug> is the original operator_id with leading "mini-" stripped.

    Examples
    --------
    >>> canonical_operator_id("mini-claude-sonnet-builder",
    ...     {"backend": "claude-cli", "role": "builder", "model": "sonnet"})
    'claude/builder/claude-sonnet-builder'

    >>> canonical_operator_id("mini-antigravity-gemini35-flash-high",
    ...     {"backend": "agy-cli", "role": "builder", "model": "gemini-3.5-flash-high"})
    'antigravity/builder/antigravity-gemini35-flash-high'

    >>> canonical_operator_id("mini-thunderomlx-qwen36-knowledge",
    ...     {"provider": "local", "role": "builder"})
    'local/builder/thunderomlx-qwen36-knowledge'
    """
    cfg = config or {}
    vendor = _vendor_slug(cfg)
    role = str(cfg.get("role", "builder")).lower()
    slug = operator_id.removeprefix("mini-")
    return f"{vendor}/{role}/{slug}"


def pane_title(
    operator_id: str,
    role: str,
    vendor: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> str:
    """Build a concise, human-readable tmux pane title.

    Format:  [VendorLabel] <role-label> | <model>
    Falls back gracefully when fields are missing.

    Examples
    --------
    Claude builder:
        [Claude] Builder | sonnet

    Codex builder:
        [Codex] Builder | gpt-4o

    Antigravity planner:
        [Antigravity] Planner | gemini-3.1-pro

    Local knowledge extractor:
        [Local] Builder | thunderomlx
    """
    cfg = config or {}

    # Resolve vendor slug
    if vendor is None:
        vendor = _vendor_slug(cfg)
    else:
        vendor = _VENDOR_SLUG.get(vendor.lower(), vendor.lower())

    vendor_label = _VENDOR_LABEL.get(vendor, vendor.capitalize())

    # Resolve model display string
    if model is None:
        model = str(cfg.get("model", "")).strip()
    model_part = f" | {model}" if model else ""

    role_label = role.replace("-", " ").title()

    return f"[{vendor_label}] {role_label}{model_part}"


def apply_pane_title(title: str, pane_id: Optional[str] = None) -> None:
    """Set the current tmux pane title to *title*.

    This is a safe no-op when:
    - Not running inside a tmux session (``TMUX`` env var is absent).
    - The ``tmux`` binary is not available.
    - Any tmux command fails for any reason.

    Parameters
    ----------
    title:
        The title string to apply.
    pane_id:
        Optional explicit tmux pane target (e.g. ``%3``).  When *None*,
        ``select-pane`` targets the current pane implicitly.
    """
    if not os.environ.get("TMUX"):
        return  # Outside tmux — safe no-op

    target_args: list[str] = []
    if pane_id:
        target_args = ["-t", pane_id]

    try:
        subprocess.run(
            ["tmux", "select-pane"] + target_args + ["-T", title],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # tmux not on PATH — safe no-op
    except Exception:
        pass  # Any other failure — safe no-op

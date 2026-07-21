#!/usr/bin/env python3
"""Claude command surface classifier and reserve routing policy.

Classifies physical operators by their Claude invocation surface:

  CLAUDE_INTERACTIVE  — "claude" or "claude --model opus" launched as a
                        persistent REPL session inside a tmux pane.  Billed
                        under the Pro/Team subscription interactive quota.

  CLAUDE_PRINT        — "claude --print" / "claude -p" invoked once per task
                        and exits when done.  Billed under the Anthropic Agent
                        SDK credit pool (anthropic_agent_sdk_credit).

Reserve-routing enforcement
───────────────────────────
claude_print operators carry a quota.reserve_for list that names the high-value
task types they exist to serve (ARCH_DECISION, ROOT_CAUSE_DEBUG, FINAL_REVIEW,
…).  They MUST be excluded from low-value bulk / fanout / scan work so that
their credit budget is preserved for those high-value invocations.

Public API
──────────
  classify_surface(operator)            → CLAUDE_PRINT | CLAUDE_INTERACTIVE | SURFACE_UNKNOWN
  is_claude_print(operator)             → bool
  is_claude_interactive(operator)       → bool
  claude_print_reserve_allows(operator, task_type) → bool
"""

from __future__ import annotations

import re
import shlex
from typing import Any

# ── Surface type constants ──────────────────────────────────────────────────

CLAUDE_PRINT = "claude_print"
CLAUDE_INTERACTIVE = "claude_code_interactive"
SURFACE_UNKNOWN = "unknown"

# ── Bulk / fanout task-type tokens that must never consume a claude_print ───
# These mirror the avoid_for tags used in physical-operators.json so that the
# classifier enforces the same policy even when an operator omits those tags.

_BULK_TOKENS: frozenset[str] = frozenset({
    "fanout",
    "bulk",
    "bulk_edit",
    "bulk-edit",
    "test_run",
    "test-run",
    "low_value",
    "low-value",
    "low_value_scan",
    "low-value-scan",
    "scan",
})


# ── Internal helpers ─────────────────────────────────────────────────────────

def _token_set(text: str) -> frozenset[str]:
    """Return the lowercased word-level tokens of *text* plus the whole string."""
    text = text.lower()
    parts = [p for p in re.split(r"[^a-z0-9]+", text) if p]
    return frozenset([text] + parts)


def _launch_cmd_has_print_flag(launch_cmd: str) -> bool:
    """Return True if *launch_cmd* contains a standalone ``--print`` or ``-p`` token.

    Handles quoting via shlex so that embedded ``-p`` inside a quoted string
    (e.g. a prompt argument) is not mis-detected as the print flag.
    """
    try:
        tokens = shlex.split(launch_cmd)
    except ValueError:
        tokens = launch_cmd.split()

    for token in tokens:
        if token in ("--print", "-p"):
            return True
    return False


# ── Surface classifier ────────────────────────────────────────────────────────

def classify_surface(operator: dict[str, Any]) -> str:
    """Classify the Claude command surface for *operator*.

    Precedence (first match wins):
    1. ``operator["surface"]["type"]``        — explicit, most authoritative
    2. ``operator["launch_cmd_kind"]``         — structural hint
    3. ``operator["billing_surface"]``         — billing pool hint
    4. Parse ``operator["surface"]["launch_cmd"]`` for ``--print`` / ``-p``

    Returns one of: ``CLAUDE_PRINT``, ``CLAUDE_INTERACTIVE``, ``SURFACE_UNKNOWN``.
    """
    surface = operator.get("surface")

    # 1. Explicit surface.type field
    if isinstance(surface, dict):
        surface_type = str(surface.get("type") or "").strip()
        if surface_type == CLAUDE_PRINT:
            return CLAUDE_PRINT
        if surface_type == CLAUDE_INTERACTIVE:
            return CLAUDE_INTERACTIVE

    # 2. launch_cmd_kind
    launch_cmd_kind = str(operator.get("launch_cmd_kind") or "").strip().lower()
    if launch_cmd_kind == "print_once":
        return CLAUDE_PRINT
    if launch_cmd_kind == "interactive_repl":
        return CLAUDE_INTERACTIVE

    # 3. billing_surface / billing_pool
    billing_surface = str(operator.get("billing_surface") or "").strip().lower()
    billing_pool = str(operator.get("billing_pool") or "").strip().lower()
    for tag in (billing_surface, billing_pool):
        if "agent_sdk_credit" in tag or (tag.endswith("credit") and "subscription" not in tag):
            return CLAUDE_PRINT
        if "interactive" in tag:
            return CLAUDE_INTERACTIVE

    # 4. Parse launch_cmd from the surface dict
    if isinstance(surface, dict):
        launch_cmd = str(surface.get("launch_cmd") or "")
        if launch_cmd and _launch_cmd_has_print_flag(launch_cmd):
            return CLAUDE_PRINT

    return SURFACE_UNKNOWN


# ── Boolean helpers ───────────────────────────────────────────────────────────

def is_claude_print(operator: dict[str, Any]) -> bool:
    """Return True if *operator* uses the ``claude --print`` surface."""
    return classify_surface(operator) == CLAUDE_PRINT


def is_claude_interactive(operator: dict[str, Any]) -> bool:
    """Return True if *operator* uses the interactive Claude Code REPL surface."""
    return classify_surface(operator) == CLAUDE_INTERACTIVE


# ── Reserve routing policy ────────────────────────────────────────────────────

def claude_print_reserve_allows(operator: dict[str, Any], task_type: str) -> bool:
    """Return True if *operator*'s reserve policy permits *task_type*.

    Enforcement rules (only applied when ``is_claude_print(operator)`` is True):

    * If ``quota.reserve_for`` is set → only allow task types that appear in
      that list (case-insensitive exact match).
    * If no ``reserve_for`` is defined → exclude any task whose token-set
      overlaps ``_BULK_TOKENS``; allow everything else.

    Non-``claude_print`` operators are always allowed (returns True).
    Empty *task_type* is allowed (no type information → skip enforcement).
    """
    if not is_claude_print(operator):
        return True

    if not task_type:
        return True

    task_lower = task_type.lower()

    quota = operator.get("quota")
    if isinstance(quota, dict):
        reserve_for = quota.get("reserve_for")
        if reserve_for:
            if not isinstance(reserve_for, list):
                reserve_for = [reserve_for]
            reserve_lower = [str(x).lower() for x in reserve_for]
            return task_lower in reserve_lower

    # No reserve_for defined: apply bulk-exclusion heuristic
    return not bool(_token_set(task_lower) & _BULK_TOKENS)

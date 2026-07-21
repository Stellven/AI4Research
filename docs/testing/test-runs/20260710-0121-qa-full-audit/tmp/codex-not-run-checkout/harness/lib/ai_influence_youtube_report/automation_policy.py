"""Automation safety policy for external report side effects."""

from __future__ import annotations


def decide_external_action(*, has_secret: bool, logged_in: bool, dry_run: bool) -> dict[str, str]:
    if dry_run:
        return {"status": "dry-run", "reason": "dry_run_enabled"}
    if not has_secret:
        return {"status": "blocked", "reason": "missing_secret"}
    if not logged_in:
        return {"status": "blocked", "reason": "browser_agent_not_logged_in"}
    return {"status": "ready", "reason": "external_action_allowed"}

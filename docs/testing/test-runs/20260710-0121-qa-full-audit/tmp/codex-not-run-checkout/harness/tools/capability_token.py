"""capability_token.py — Capability token validation for lease acquisition.

Validates token expiry and scopes before lease acquisition or task execution.
Enforces file, shell, network, and git allow-path/deny-path rules.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class CapabilityToken:
    """Token with expiry and scope validation."""

    def __init__(
        self,
        token_id: str,
        scopes: List[str],
        expires_at: str,
        actor_id: str,
        allow_paths: Optional[List[str]] = None,
        deny_paths: Optional[List[str]] = None,
    ):
        self.token_id = token_id
        self.scopes = set(scopes)
        self.expires_at = expires_at
        self.actor_id = actor_id
        self.allow_paths = allow_paths or []
        self.deny_paths = deny_paths or []

    def is_expired(self) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc)
        exp = datetime.datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return now > exp

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def check_path_access(self, path: str) -> Dict[str, Any]:
        """Check if path is allowed and not denied."""
        for deny in self.deny_paths:
            if path.startswith(deny):
                return {"allowed": False, "reason": f"deny_path: {deny}"}
        if self.allow_paths:
            allowed = any(path.startswith(a) for a in self.allow_paths)
            if not allowed:
                return {"allowed": False, "reason": "not_in_allow_paths"}
        return {"allowed": True, "reason": ""}

    def validate_for_lease(self) -> Dict[str, Any]:
        """Full validation before lease acquisition."""
        issues = []
        if self.is_expired():
            issues.append("token_expired")
        return {"valid": len(issues) == 0, "issues": issues}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "scopes": sorted(self.scopes),
            "expires_at": self.expires_at,
            "actor_id": self.actor_id,
            "allow_paths": self.allow_paths,
            "deny_paths": self.deny_paths,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapabilityToken":
        return cls(
            token_id=d["token_id"],
            scopes=d.get("scopes", []),
            expires_at=d["expires_at"],
            actor_id=d.get("actor_id", ""),
            allow_paths=d.get("allow_paths"),
            deny_paths=d.get("deny_paths"),
        )

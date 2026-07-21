"""schema.py — Compiler profile schema definition and validation.

A compiler profile is a named, versioned collection of 6 policy
configurations that parameterize the requirement compilation pipeline.
GEPA optimises profiles; the production compile pipeline consumes them
deterministically.

Schema::

    profile_id:   str           — unique identifier
    version:      int >= 1      — monotonically increasing version
    name:         str           — human-readable name
    tags:         list[str]     — categorisation tags
    created_at:   str (ISO 8601)
    policies:     dict with exactly 6 keys
      intake_policy:              {version: str, params: dict}
      requirement_ir_policy:      {version: str, params: dict}
      contract_compiler_policy:   {version: str, params: dict}
      dag_compiler_policy:        {version: str, params: dict}
      evidence_policy:            {version: str, params: dict}
      handoff_policy:             {version: str, params: dict}
"""
from __future__ import annotations

from typing import Any

__all__ = ["validate_profile", "REQUIRED_POLICY_KEYS"]

REQUIRED_POLICY_KEYS: tuple[str, ...] = (
    "intake_policy",
    "requirement_ir_policy",
    "contract_compiler_policy",
    "dag_compiler_policy",
    "evidence_policy",
    "handoff_policy",
)

_REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "profile_id",
    "version",
    "name",
    "tags",
    "created_at",
    "policies",
)


def validate_profile(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a compiler profile dict against the schema.

    Returns
    -------
    (is_valid, errors) : tuple[bool, list[str]]
        ``is_valid`` is True when ``errors`` is empty.
    """
    if not isinstance(data, dict):
        return False, ["profile must be a dict"]

    errors: list[str] = []

    # --- top-level required fields ---
    for key in _REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"missing required field: {key!r}")

    if errors:
        # Cannot proceed with deeper checks if top-level keys are missing.
        return False, errors

    # --- profile_id ---
    if not isinstance(data["profile_id"], str) or not data["profile_id"].strip():
        errors.append("'profile_id' must be a non-empty string")

    # --- version ---
    version = data["version"]
    if not isinstance(version, int) or version < 1:
        errors.append("'version' must be an integer >= 1")

    # --- name ---
    if not isinstance(data["name"], str) or not data["name"].strip():
        errors.append("'name' must be a non-empty string")

    # --- tags ---
    tags = data["tags"]
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errors.append("'tags' must be a list of strings")

    # --- created_at ---
    created_at = data["created_at"]
    if not isinstance(created_at, str) or not created_at.strip():
        errors.append("'created_at' must be a non-empty ISO 8601 string")

    # --- policies ---
    policies = data["policies"]
    if not isinstance(policies, dict):
        errors.append("'policies' must be a dict")
    else:
        present_keys = set(policies.keys())
        expected_keys = set(REQUIRED_POLICY_KEYS)
        missing = expected_keys - present_keys
        extra = present_keys - expected_keys
        if missing:
            errors.append(f"'policies' missing keys: {sorted(missing)}")
        if extra:
            errors.append(f"'policies' has unexpected keys: {sorted(extra)}")

        for key in REQUIRED_POLICY_KEYS:
            policy = policies.get(key)
            if policy is None:
                continue  # already reported as missing
            if not isinstance(policy, dict):
                errors.append(f"'policies.{key}' must be a dict")
                continue
            if "version" not in policy:
                errors.append(f"'policies.{key}' missing 'version'")
            elif not isinstance(policy["version"], str):
                errors.append(f"'policies.{key}.version' must be a string")
            if "params" not in policy:
                errors.append(f"'policies.{key}' missing 'params'")
            elif not isinstance(policy["params"], dict):
                errors.append(f"'policies.{key}.params' must be a dict")

    return (len(errors) == 0, errors)

"""Profile loading utilities for DeepDive Insight Runtime."""

from __future__ import annotations

import os
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PROFILE = "cais-agent-insight"


def _load_yaml_profile(path: str) -> dict[str, Any]:
    if yaml is None:
        raise ImportError("PyYAML is required for profile loading: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Profile file {path} did not produce a dict")
    return data


def load_profile(profile_id: str | None = None) -> dict[str, Any]:
    """Load a named profile from the profiles directory.

    Returns the parsed YAML dict.  Raises FileNotFoundError when the
    profile file does not exist.
    """
    pid = (profile_id or DEFAULT_PROFILE).strip()
    filename = f"{pid}.yaml" if not pid.endswith(".yaml") else pid
    filepath = os.path.join(_PROFILES_DIR, filename)
    if not os.path.isfile(filepath) and "-" in filename:
        filepath = os.path.join(_PROFILES_DIR, filename.replace("-", "_"))
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Profile not found: {filepath}")
    return _load_yaml_profile(filepath)


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate that a profile dict declares all required contract fields.

    Returns a dict with ``ok`` (bool), ``errors`` (list[str]), and the
    extracted fields for downstream use.
    """
    errors: list[str] = []
    required_fields = [
        "profile_id",
        "mode",
        "must_answer_questions",
        "required_signal_clusters",
        "required_outputs",
        "forbidden_outputs",
        "strict_defaults",
        "required_gates",
    ]
    for field_name in required_fields:
        if field_name not in profile:
            errors.append(f"missing_required_field:{field_name}")

    strict = profile.get("strict_defaults") or {}
    if not isinstance(strict, dict):
        errors.append("strict_defaults_must_be_dict")
    elif not strict.get("strict"):
        errors.append("strict_defaults.strict_must_be_true")

    must_answer = profile.get("must_answer_questions") or []
    if not isinstance(must_answer, list) or len(must_answer) < 3:
        errors.append("must_answer_questions_requires_at_least_3_entries")

    required_outputs = profile.get("required_outputs") or []
    if not isinstance(required_outputs, list) or len(required_outputs) < 3:
        errors.append("required_outputs_requires_at_least_3_entries")

    return {
        "ok": not errors,
        "errors": errors,
        "profile_id": profile.get("profile_id", ""),
        "mode": profile.get("mode", ""),
        "must_answer_questions": must_answer,
        "required_signal_clusters": profile.get("required_signal_clusters") or [],
        "required_outputs": required_outputs,
        "forbidden_outputs": profile.get("forbidden_outputs") or [],
        "strict_defaults": strict,
        "required_gates": profile.get("required_gates") or [],
    }


def profile_contract_to_scope_boundaries(validated: dict[str, Any]) -> dict[str, Any]:
    """Convert a validated profile into scope_boundaries must_answer and must_not_do."""
    must_answer = list(validated.get("must_answer_questions") or [])
    must_not_do = list(validated.get("forbidden_outputs") or [])
    return {
        "must_answer": must_answer,
        "must_not_do": must_not_do,
    }

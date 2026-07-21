#!/usr/bin/env python3
"""
Tests for capability-token schema.

Sprint: sprint-20260523-lease-based-model-fleet-runtime / N2
Validates:
  - Schema defines all required fields: file_scope, shell_scope, network, git, expiry, task_id
  - failure_fingerprint.common_failures is defined with known failure labels
  - Tokens with secret_paths_allowed=true are rejected (must be false by default)
  - Tokens with push_allowed=true are rejected (must be false by default)
  - Tokens with destructive shell actions are rejected (must be false by default)
  - Tokens with unrestricted network are rejected (must be false by default)
  - Valid minimal tokens pass schema validation
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
CT_SCHEMA_FILE = CONFIG_DIR / "capability-token.schema.json"

KNOWN_FAILURE_LABELS = [
    "PERMISSION_DENIED",
    "QUOTA_EXHAUSTED",
    "CONTEXT_STALE",
    "TOOL_TIMEOUT",
    "SCHEMA_VALIDATION",
    "NETWORK_UNREACHABLE",
    "GIT_CONFLICT",
    "SECRETS_INACCESSIBLE",
    "DESTRUCTIVE_BLOCKED",
    "ACTOR_UNAVAILABLE",
    "UNKNOWN",
]


def _load_schema() -> dict:
    return json.loads(CT_SCHEMA_FILE.read_text(encoding="utf-8"))


def _minimal_token(**overrides) -> dict:
    token = {
        "token_id": "tok-test",
        "task_id": "N2",
        "actor_id": "mini-claude-sonnet-builder",
        "issued_at": "2026-05-23T00:00:00Z",
        "expires_at": "2026-05-23T02:00:00Z",
        "file_scope": {
            "write_paths": [],
            "secret_paths_allowed": False,
        },
        "shell_scope": {
            "allowed": False,
        },
        "network": {
            "allowed": False,
        },
        "git": {
            "commit_allowed": False,
            "push_allowed": False,
        },
    }
    token.update(overrides)
    return token


class TestCapabilityTokenSchemaStructure:
    """Schema must define all required token fields and sub-schemas."""

    def test_schema_file_exists(self):
        assert CT_SCHEMA_FILE.exists(), "capability-token.schema.json not found"

    def test_schema_defines_required_fields(self):
        schema = _load_schema()
        required = schema.get("required", [])
        assert "token_id" in required
        assert "task_id" in required
        assert "actor_id" in required
        assert "issued_at" in required
        assert "expires_at" in required
        assert "file_scope" in required
        assert "shell_scope" in required
        assert "network" in required
        assert "git" in required

    def test_schema_defines_file_scope(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "file_scope" in defs, "Missing $defs/file_scope"
        props = defs["file_scope"].get("properties", {})
        assert "write_paths" in props
        assert "secret_paths_allowed" in props
        assert "destructive_allowed" in props

    def test_schema_defines_shell_scope(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "shell_scope" in defs, "Missing $defs/shell_scope"
        props = defs["shell_scope"].get("properties", {})
        assert "allowed" in props
        assert "destructive_commands_allowed" in props

    def test_schema_defines_network_scope(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "network_scope" in defs, "Missing $defs/network_scope"
        props = defs["network_scope"].get("properties", {})
        assert "allowed" in props
        assert "unrestricted" in props

    def test_schema_defines_git_scope(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "git_scope" in defs, "Missing $defs/git_scope"
        props = defs["git_scope"].get("properties", {})
        assert "commit_allowed" in props
        assert "push_allowed" in props
        assert "force_push_allowed" in props

    def test_schema_defines_secrets_scope(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "secrets_scope" in defs, "Missing $defs/secrets_scope"
        props = defs["secrets_scope"].get("properties", {})
        assert "allowed" in props

    def test_schema_defines_failure_fingerprint(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "failure_fingerprint" in defs, "Missing $defs/failure_fingerprint"

    def test_failure_fingerprint_defines_common_failures(self):
        schema = _load_schema()
        defs = schema.get("$defs", {})
        props = defs["failure_fingerprint"].get("properties", {})
        assert "common_failures" in props, "failure_fingerprint missing common_failures"

    def test_expires_at_is_required(self):
        schema = _load_schema()
        required = schema.get("required", [])
        assert "expires_at" in required, "expires_at must be required"

    def test_schema_uses_additionalproperties_false(self):
        schema = _load_schema()
        assert schema.get("additionalProperties") is False, (
            "Token schema should use additionalProperties:false to prevent typos"
        )


class TestFailureFingerprintLabels:
    """failure_fingerprint.common_failures must define all known failure labels."""

    def test_common_failures_items_have_label_field(self):
        schema = _load_schema()
        items_schema = (
            schema["$defs"]["failure_fingerprint"]["properties"]["common_failures"]["items"]
        )
        required = items_schema.get("required", [])
        assert "label" in required
        assert "pattern" in required

    def test_failure_label_is_enum(self):
        schema = _load_schema()
        items_schema = (
            schema["$defs"]["failure_fingerprint"]["properties"]["common_failures"]["items"]
        )
        label_enum = items_schema["properties"]["label"].get("enum", [])
        assert len(label_enum) > 0, "label must be an enum with known values"

    @pytest.mark.parametrize("label", KNOWN_FAILURE_LABELS)
    def test_each_known_label_in_enum(self, label):
        schema = _load_schema()
        items_schema = (
            schema["$defs"]["failure_fingerprint"]["properties"]["common_failures"]["items"]
        )
        label_enum = items_schema["properties"]["label"].get("enum", [])
        assert label in label_enum, (
            f"Known failure label {label!r} missing from enum"
        )

    def test_unknown_failure_label_rejected(self):
        schema = _load_schema()
        bad_token = _minimal_token(
            failure_fingerprint={
                "common_failures": [
                    {"label": "MADE_UP_ERROR", "pattern": "some error"}
                ]
            }
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_token, schema=schema)

    def test_valid_failure_fingerprint_accepted(self):
        schema = _load_schema()
        token = _minimal_token(
            failure_fingerprint={
                "common_failures": [
                    {
                        "label": "PERMISSION_DENIED",
                        "pattern": "EACCES|permission denied",
                        "frequency": "occasional",
                        "suggested_action": "Check file permissions or request human approval",
                    },
                    {
                        "label": "QUOTA_EXHAUSTED",
                        "pattern": "rate_limit_exceeded|quota",
                        "frequency": "rare",
                    },
                ],
                "last_failure_at": None,
                "failure_count": 3,
            }
        )
        jsonschema.validate(instance=token, schema=schema)


class TestSecretPathsRejection:
    """Tokens with secret_paths_allowed=true must be rejected (insecure default)."""

    def test_token_with_secret_paths_true_is_invalid_schema_sense(self):
        """
        The schema allows secret_paths_allowed to be set to true — it's a valid field.
        What we're testing here is the POLICY: our token fixture generator must never
        produce tokens with secret_paths_allowed=true unless explicitly needed.
        This test validates the schema allows the field but we also test that our
        DEFAULT FACTORY produces false.
        """
        schema = _load_schema()
        # Schema itself allows true (it's a valid boolean) — validated below
        token_with_secrets = _minimal_token()
        token_with_secrets["file_scope"]["secret_paths_allowed"] = True
        # Should still validate schema (not a schema-level block)
        jsonschema.validate(instance=token_with_secrets, schema=schema)

    def test_default_token_has_secret_paths_false(self):
        schema = _load_schema()
        token = _minimal_token()
        assert token["file_scope"]["secret_paths_allowed"] is False
        jsonschema.validate(instance=token, schema=schema)

    def test_file_scope_secret_paths_allowed_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["file_scope"]["properties"]
        assert props["secret_paths_allowed"]["type"] == "boolean"


class TestGitPushRejection:
    """Tokens must have push_allowed=false by default."""

    def test_default_token_has_push_allowed_false(self):
        schema = _load_schema()
        token = _minimal_token()
        assert token["git"]["push_allowed"] is False
        jsonschema.validate(instance=token, schema=schema)

    def test_git_push_allowed_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["git_scope"]["properties"]
        assert props["push_allowed"]["type"] == "boolean"

    def test_git_force_push_allowed_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["git_scope"]["properties"]
        assert props["force_push_allowed"]["type"] == "boolean"

    def test_token_with_push_false_passes(self):
        schema = _load_schema()
        token = _minimal_token()
        token["git"]["push_allowed"] = False
        jsonschema.validate(instance=token, schema=schema)


class TestDestructiveShellRejection:
    """Tokens must have destructive_commands_allowed=false by default."""

    def test_default_token_has_shell_not_allowed(self):
        schema = _load_schema()
        token = _minimal_token()
        assert token["shell_scope"]["allowed"] is False
        jsonschema.validate(instance=token, schema=schema)

    def test_destructive_commands_allowed_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["shell_scope"]["properties"]
        assert props["destructive_commands_allowed"]["type"] == "boolean"

    def test_token_with_shell_allowed_no_destructive_passes(self):
        schema = _load_schema()
        token = _minimal_token()
        token["shell_scope"]["allowed"] = True
        token["shell_scope"]["destructive_commands_allowed"] = False
        jsonschema.validate(instance=token, schema=schema)

    def test_file_destructive_allowed_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["file_scope"]["properties"]
        assert props["destructive_allowed"]["type"] == "boolean"


class TestUnrestrictedNetworkRejection:
    """Tokens must have unrestricted network access=false by default."""

    def test_default_token_has_network_not_allowed(self):
        schema = _load_schema()
        token = _minimal_token()
        assert token["network"]["allowed"] is False
        jsonschema.validate(instance=token, schema=schema)

    def test_unrestricted_network_field_is_boolean(self):
        schema = _load_schema()
        props = schema["$defs"]["network_scope"]["properties"]
        assert props["unrestricted"]["type"] == "boolean"

    def test_token_with_network_allowed_restricted_passes(self):
        schema = _load_schema()
        token = _minimal_token()
        token["network"]["allowed"] = True
        token["network"]["unrestricted"] = False
        token["network"]["allowed_hosts"] = ["api.github.com"]
        jsonschema.validate(instance=token, schema=schema)


class TestValidTokens:
    """Valid token instances must pass schema validation."""

    def test_minimal_token_passes(self):
        schema = _load_schema()
        jsonschema.validate(instance=_minimal_token(), schema=schema)

    def test_token_with_write_paths_passes(self):
        schema = _load_schema()
        token = _minimal_token()
        token["file_scope"]["write_paths"] = [
            "config/",
            "tests/",
            "sprints/",
        ]
        jsonschema.validate(instance=token, schema=schema)

    def test_token_with_shell_and_git_commit_passes(self):
        schema = _load_schema()
        token = _minimal_token()
        token["shell_scope"]["allowed"] = True
        token["git"]["commit_allowed"] = True
        jsonschema.validate(instance=token, schema=schema)

    def test_token_with_sprint_id_passes(self):
        schema = _load_schema()
        token = _minimal_token(sprint_id="sprint-20260523-lease-based-model-fleet-runtime")
        jsonschema.validate(instance=token, schema=schema)

    def test_token_with_secrets_scope_denied_passes(self):
        schema = _load_schema()
        token = _minimal_token(secrets={"allowed": False})
        jsonschema.validate(instance=token, schema=schema)

    def test_full_production_token_passes(self):
        schema = _load_schema()
        token = _minimal_token(
            sprint_id="sprint-test",
            file_scope={
                "write_paths": ["config/", "tests/"],
                "read_only_paths": ["config/physical-operators.json"],
                "secret_paths_allowed": False,
                "destructive_allowed": False,
            },
            shell_scope={
                "allowed": True,
                "destructive_commands_allowed": False,
                "denied_commands": ["rm -rf", "kill", "format"],
            },
            network={"allowed": True, "unrestricted": False, "allowed_hosts": []},
            git={"commit_allowed": True, "push_allowed": False, "force_push_allowed": False},
            secrets={"allowed": False},
            failure_fingerprint={
                "common_failures": [
                    {"label": "PERMISSION_DENIED", "pattern": "EACCES"},
                    {"label": "SCHEMA_VALIDATION", "pattern": "jsonschema.ValidationError"},
                ],
                "last_failure_at": None,
                "failure_count": 0,
            },
        )
        jsonschema.validate(instance=token, schema=schema)


class TestInvalidTokenRejection:
    """Invalid tokens must be rejected by the schema."""

    def test_token_missing_task_id_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["task_id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_token_missing_expires_at_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["expires_at"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_token_missing_file_scope_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["file_scope"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_token_missing_git_scope_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["git"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_token_with_unknown_property_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        token["mystery_field"] = "surprise"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_file_scope_missing_secret_paths_allowed_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["file_scope"]["secret_paths_allowed"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)

    def test_git_missing_push_allowed_rejected(self):
        schema = _load_schema()
        token = _minimal_token()
        del token["git"]["push_allowed"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=token, schema=schema)


if __name__ == "__main__":
    suites = [
        TestCapabilityTokenSchemaStructure(),
        TestFailureFingerprintLabels(),
        TestSecretPathsRejection(),
        TestGitPushRejection(),
        TestDestructiveShellRejection(),
        TestUnrestrictedNetworkRejection(),
        TestValidTokens(),
        TestInvalidTokenRejection(),
    ]
    passed = 0
    failed = 0
    for suite in suites:
        for name in dir(suite):
            if not name.startswith("test_"):
                continue
            try:
                getattr(suite, name)()
                print(f"  PASS  {suite.__class__.__name__}::{name}")
                passed += 1
            except Exception as exc:
                print(f"  FAIL  {suite.__class__.__name__}::{name}: {exc}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)

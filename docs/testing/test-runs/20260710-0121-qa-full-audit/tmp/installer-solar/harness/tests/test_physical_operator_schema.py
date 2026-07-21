#!/usr/bin/env python3
"""
Tests for physical-operators registry schema additions.

Sprint: sprint-20260523-claude-operator-billing-split / N2
Validates:
  - billing_surface and surface fields are present on all claude-cli operators
  - Schema conditional rejects claude-cli operators that lack surface/billing_surface
  - Both interactive (claude_code_interactive) and print (claude_print) examples exist
  - No raw secrets appear in the config
  - Print reserve operators carry quota.reserve_for restrictions
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
OPERATORS_FILE = CONFIG_DIR / "physical-operators.json"
SCHEMA_FILE = CONFIG_DIR / "physical-operators.schema.json"


def _load_config() -> dict:
    return json.loads(OPERATORS_FILE.read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _claude_cli_operators(config: dict) -> dict[str, dict]:
    return {
        op_id: op
        for op_id, op in config["operators"].items()
        if op.get("backend") == "claude-cli"
    }


class TestClaudeSurfaceFields:
    """All claude-cli operators must carry surface and billing_surface."""

    def test_all_claude_cli_operators_have_surface(self):
        config = _load_config()
        for op_id, op in _claude_cli_operators(config).items():
            assert "surface" in op, f"{op_id}: missing surface field"
            assert "type" in op["surface"], f"{op_id}.surface: missing type"

    def test_all_claude_cli_operators_have_billing_surface(self):
        config = _load_config()
        for op_id, op in _claude_cli_operators(config).items():
            assert "billing_surface" in op, f"{op_id}: missing billing_surface"

    def test_all_claude_cli_operators_have_billing_pool(self):
        config = _load_config()
        for op_id, op in _claude_cli_operators(config).items():
            assert "billing_pool" in op, f"{op_id}: missing billing_pool"

    def test_billing_surface_values_are_valid(self):
        valid = {
            "subscription_interactive",
            "anthropic_agent_sdk_credit",
            "usage_credit",
            "local_compute",
            "unknown",
        }
        config = _load_config()
        for op_id, op in _claude_cli_operators(config).items():
            val = op.get("billing_surface")
            assert val in valid, f"{op_id}: unexpected billing_surface={val!r}"


class TestSurfaceTypeExamples:
    """Both interactive and print surface types must exist in the registry."""

    def test_interactive_surface_example_exists(self):
        config = _load_config()
        types = {op.get("surface", {}).get("type") for op in config["operators"].values()}
        assert "claude_code_interactive" in types, (
            "No operator with surface.type=claude_code_interactive found"
        )

    def test_print_surface_example_exists(self):
        config = _load_config()
        types = {op.get("surface", {}).get("type") for op in config["operators"].values()}
        assert "claude_print" in types, (
            "No operator with surface.type=claude_print found"
        )

    def test_interactive_operators_use_subscription_billing(self):
        config = _load_config()
        for op_id, op in config["operators"].items():
            if op.get("surface", {}).get("type") == "claude_code_interactive":
                assert op.get("billing_surface") == "subscription_interactive", (
                    f"{op_id}: interactive operator should use subscription_interactive billing"
                )

    def test_print_operators_use_agent_sdk_billing(self):
        config = _load_config()
        for op_id, op in config["operators"].items():
            if op.get("surface", {}).get("type") == "claude_print":
                assert op.get("billing_surface") == "anthropic_agent_sdk_credit", (
                    f"{op_id}: print operator should use anthropic_agent_sdk_credit billing"
                )


class TestPrintReservePolicy:
    """Print reserve operators must carry quota.reserve_for restrictions."""

    def test_print_operators_have_quota_reserve_for(self):
        config = _load_config()
        for op_id, op in config["operators"].items():
            if op.get("surface", {}).get("type") == "claude_print":
                quota = op.get("quota", {})
                assert "reserve_for" in quota, (
                    f"{op_id}: claude_print operator missing quota.reserve_for"
                )
                assert len(quota["reserve_for"]) > 0, (
                    f"{op_id}: quota.reserve_for must not be empty"
                )

    def test_print_operators_avoid_bulk_tasks(self):
        bulk_tasks = {"FANOUT", "BULK_EDIT", "TEST_RUN", "LOW_VALUE_SCAN"}
        config = _load_config()
        for op_id, op in config["operators"].items():
            if op.get("surface", {}).get("type") == "claude_print":
                avoid = set(op.get("avoid_for", []))
                overlap = bulk_tasks & avoid
                assert overlap == bulk_tasks, (
                    f"{op_id}: print reserve missing avoid_for entries: {bulk_tasks - overlap}"
                )

    def test_print_operators_have_compat_alias(self):
        config = _load_config()
        for op_id, op in config["operators"].items():
            if op.get("surface", {}).get("type") == "claude_print":
                assert "compat_alias_for" in op, (
                    f"{op_id}: print operator missing compat_alias_for"
                )
                alias_target = op["compat_alias_for"]
                assert alias_target in config["operators"], (
                    f"{op_id}: compat_alias_for={alias_target!r} not found in operators"
                )


class TestSchemaConditionalValidation:
    """The JSON schema must enforce surface/billing_surface on claude-cli operators."""

    def test_schema_rejects_claude_cli_without_surface(self):
        schema = _load_schema()
        bad_instance = {
            "version": 1,
            "operators": {
                "generic-claude-no-surface": {
                    "display_name": "Generic Claude without surface",
                    "backend": "claude-cli",
                    "model": "opus",
                    # Intentionally no surface or billing_surface
                }
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_instance, schema=schema)

    def test_schema_rejects_claude_cli_without_billing_surface(self):
        schema = _load_schema()
        bad_instance = {
            "version": 1,
            "operators": {
                "claude-missing-billing": {
                    "display_name": "Claude missing billing_surface",
                    "backend": "claude-cli",
                    "model": "opus",
                    "surface": {"type": "claude_code_interactive", "tool": "claude"},
                    # Intentionally no billing_surface
                }
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_instance, schema=schema)

    def test_schema_accepts_valid_interactive_operator(self):
        schema = _load_schema()
        valid_instance = {
            "version": 1,
            "operators": {
                "test-claude-interactive": {
                    "display_name": "Test Claude interactive",
                    "backend": "claude-cli",
                    "model": "opus",
                    "surface": {
                        "type": "claude_code_interactive",
                        "tool": "claude",
                        "launch_cmd": "claude --dangerously-skip-permissions --model opus",
                    },
                    "billing_surface": "subscription_interactive",
                }
            },
        }
        # Should not raise
        jsonschema.validate(instance=valid_instance, schema=schema)

    def test_schema_accepts_valid_print_operator(self):
        schema = _load_schema()
        valid_instance = {
            "version": 1,
            "operators": {
                "test-claude-print": {
                    "display_name": "Test Claude print reserve",
                    "backend": "claude-cli",
                    "model": "opus",
                    "surface": {
                        "type": "claude_print",
                        "tool": "claude",
                        "launch_cmd": "claude --print --model opus",
                    },
                    "billing_surface": "anthropic_agent_sdk_credit",
                }
            },
        }
        jsonschema.validate(instance=valid_instance, schema=schema)

    def test_schema_accepts_non_claude_operator_without_surface(self):
        """Non-claude-cli operators are NOT required to have surface."""
        schema = _load_schema()
        valid_instance = {
            "version": 1,
            "operators": {
                "local-tool": {
                    "display_name": "Local tool without surface",
                    "backend": "local",
                    "model": "ripgrep",
                    # No surface required for non-claude-cli
                }
            },
        }
        jsonschema.validate(instance=valid_instance, schema=schema)


class TestNoRawSecrets:
    """The config file must not contain raw credential values."""

    def test_no_raw_api_keys_in_config(self):
        config_text = OPERATORS_FILE.read_text(encoding="utf-8")
        # Check for raw sk-prefixed API keys
        assert not re.search(r'"sk-[A-Za-z0-9]{20,}"', config_text), (
            "Raw OpenAI-style sk- API key found in config"
        )

    def test_no_raw_anthropic_keys_in_config(self):
        config_text = OPERATORS_FILE.read_text(encoding="utf-8")
        # Anthropic key pattern: sk-ant-...
        assert not re.search(r'"sk-ant-[A-Za-z0-9\-_]{20,}"', config_text), (
            "Raw Anthropic API key found in config"
        )

    def test_no_bare_credential_fields(self):
        config_text = OPERATORS_FILE.read_text(encoding="utf-8")
        # Disallow fields named api_key/password/token/client_secret with non-empty values
        forbidden = re.findall(
            r'"(?:api_key|password|client_secret)"\s*:\s*"([^"]+)"',
            config_text,
        )
        assert not forbidden, f"Raw credential fields found: {forbidden}"

    def test_key_refs_use_reference_format(self):
        config = _load_config()
        for op_id, op in config["operators"].items():
            key_ref = op.get("key_ref", "")
            # key_ref should be a symbolic name, not a raw key value
            assert not key_ref.startswith("sk-"), (
                f"{op_id}: key_ref looks like a raw API key"
            )


class TestConfigIntegrity:
    """Config file is valid JSON and passes schema validation end-to-end."""

    def test_config_json_valid(self):
        # Should not raise
        config = _load_config()
        assert "operators" in config
        assert config["version"] == 1

    def test_full_config_passes_schema(self):
        config = _load_config()
        schema = _load_schema()
        jsonschema.validate(instance=config, schema=schema)

    def test_three_interactive_claude_operators_exist(self):
        config = _load_config()
        interactive_ops = [
            op_id
            for op_id, op in config["operators"].items()
            if op.get("surface", {}).get("type") == "claude_code_interactive"
        ]
        assert len(interactive_ops) >= 3, (
            f"Expected >= 3 interactive Claude operators, got: {interactive_ops}"
        )

    def test_three_print_reserve_operators_exist(self):
        config = _load_config()
        print_ops = [
            op_id
            for op_id, op in config["operators"].items()
            if op.get("surface", {}).get("type") == "claude_print"
        ]
        assert len(print_ops) >= 3, (
            f"Expected >= 3 print reserve operators, got: {print_ops}"
        )


if __name__ == "__main__":
    # Manual run without pytest
    tests = [
        TestClaudeSurfaceFields(),
        TestSurfaceTypeExamples(),
        TestPrintReservePolicy(),
        TestSchemaConditionalValidation(),
        TestNoRawSecrets(),
        TestConfigIntegrity(),
    ]
    passed = 0
    failed = 0
    for suite in tests:
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

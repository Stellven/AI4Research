#!/usr/bin/env python3
"""
Tests for agent-actor and actor-host registry schemas and fixtures.

Sprint: sprint-20260523-lease-based-model-fleet-runtime / N2
Validates:
  - AgentActor schema includes all required sub-schemas (lease, mailbox, capability,
    quota, policy, evidence, persona_binding, fallback_ladder, display_meta)
  - Lease schema includes acquired_at, expires_at, renewable, preemptible,
    heartbeat_timeout_sec
  - Mailbox schema includes inbox, outbox, logs, state_json, heartbeat_json
  - ActorHost schema includes host_id, host_type, lifecycle, address, heartbeat, probe
  - tmux_pane_index is only allowed in display_meta, not as a top-level actor field
  - All actors carry operator_alias mapping to a known physical-operators.json key
  - All physical operator ids appear as operator_alias in the actor registry
  - Fixtures validate against their respective schemas
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
ACTORS_FILE = CONFIG_DIR / "agent-actors.json"
ACTORS_SCHEMA_FILE = CONFIG_DIR / "agent-actors.schema.json"
HOSTS_FILE = CONFIG_DIR / "actor-hosts.json"
HOSTS_SCHEMA_FILE = CONFIG_DIR / "actor-hosts.schema.json"
PHYSICAL_OPS_FILE = CONFIG_DIR / "physical-operators.json"


def _load_actors() -> dict:
    return json.loads(ACTORS_FILE.read_text(encoding="utf-8"))


def _load_actors_schema() -> dict:
    return json.loads(ACTORS_SCHEMA_FILE.read_text(encoding="utf-8"))


def _load_hosts() -> dict:
    return json.loads(HOSTS_FILE.read_text(encoding="utf-8"))


def _load_hosts_schema() -> dict:
    return json.loads(HOSTS_SCHEMA_FILE.read_text(encoding="utf-8"))


def _load_physical_ops() -> dict:
    return json.loads(PHYSICAL_OPS_FILE.read_text(encoding="utf-8"))


class TestActorSchemaDefinitions:
    """The agent-actors schema must define all required sub-schemas."""

    def test_schema_defines_lease(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "lease" in defs, "agent-actors schema missing $defs/lease"

    def test_schema_defines_mailbox(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "mailbox" in defs, "agent-actors schema missing $defs/mailbox"

    def test_schema_defines_capability(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "capability" in defs, "agent-actors schema missing $defs/capability"

    def test_schema_defines_quota(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "quota" in defs, "agent-actors schema missing $defs/quota"

    def test_schema_defines_policy(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "policy" in defs, "agent-actors schema missing $defs/policy"

    def test_schema_defines_evidence(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "evidence" in defs, "agent-actors schema missing $defs/evidence"

    def test_schema_defines_persona_binding(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "persona_binding" in defs, "agent-actors schema missing $defs/persona_binding"

    def test_schema_defines_fallback_ladder(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "fallback_ladder" in defs, "agent-actors schema missing $defs/fallback_ladder"

    def test_schema_defines_display_meta(self):
        schema = _load_actors_schema()
        defs = schema.get("$defs", {})
        assert "display_meta" in defs, "agent-actors schema missing $defs/display_meta"


class TestLeaseSchemaFields:
    """Lease schema must include the five required lease fields."""

    def _lease_props(self) -> dict:
        schema = _load_actors_schema()
        return schema["$defs"]["lease"].get("properties", {})

    def test_lease_has_acquired_at(self):
        assert "acquired_at" in self._lease_props(), "lease schema missing acquired_at"

    def test_lease_has_expires_at(self):
        assert "expires_at" in self._lease_props(), "lease schema missing expires_at"

    def test_lease_has_renewable(self):
        props = self._lease_props()
        assert "renewable" in props, "lease schema missing renewable"
        assert props["renewable"]["type"] == "boolean"

    def test_lease_has_preemptible(self):
        props = self._lease_props()
        assert "preemptible" in props, "lease schema missing preemptible"
        assert props["preemptible"]["type"] == "boolean"

    def test_lease_has_heartbeat_timeout_sec(self):
        props = self._lease_props()
        assert "heartbeat_timeout_sec" in props, "lease schema missing heartbeat_timeout_sec"
        assert props["heartbeat_timeout_sec"]["type"] == "integer"
        assert props["heartbeat_timeout_sec"]["minimum"] >= 1


class TestMailboxSchemaFields:
    """Mailbox schema must define paths for all five mailbox entries."""

    def _mailbox_props(self) -> dict:
        schema = _load_actors_schema()
        return schema["$defs"]["mailbox"].get("properties", {})

    def test_mailbox_has_inbox(self):
        assert "inbox" in self._mailbox_props(), "mailbox schema missing inbox"

    def test_mailbox_has_outbox(self):
        assert "outbox" in self._mailbox_props(), "mailbox schema missing outbox"

    def test_mailbox_has_logs(self):
        assert "logs" in self._mailbox_props(), "mailbox schema missing logs"

    def test_mailbox_has_state_json(self):
        props = self._mailbox_props()
        assert "state_json" in props, "mailbox schema missing state_json (for state.json)"

    def test_mailbox_has_heartbeat_json(self):
        props = self._mailbox_props()
        assert "heartbeat_json" in props, "mailbox schema missing heartbeat_json (for heartbeat.json)"


class TestDisplayMetaTmuxConstraint:
    """tmux_pane_index must appear only in display_meta, not as a top-level actor field."""

    def test_display_meta_allows_tmux_pane_index(self):
        schema = _load_actors_schema()
        display_props = schema["$defs"]["display_meta"].get("properties", {})
        assert "tmux_pane_index" in display_props, (
            "display_meta should define tmux_pane_index for display/debug use"
        )

    def test_actor_top_level_does_not_define_tmux_pane_index(self):
        schema = _load_actors_schema()
        actor_props = schema["$defs"]["agent_actor"].get("properties", {})
        assert "tmux_pane_index" not in actor_props, (
            "tmux_pane_index must not appear as a top-level actor property — "
            "it belongs in display_meta only"
        )

    def test_no_actor_has_top_level_tmux_pane_index(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "tmux_pane_index" not in actor, (
                f"{actor_id}: tmux_pane_index must not be a top-level actor field"
            )


class TestHostSchemaDefinitions:
    """The actor-hosts schema must define lifecycle, address, heartbeat, and probe."""

    def test_schema_defines_host_lifecycle(self):
        schema = _load_hosts_schema()
        assert "host_lifecycle" in schema.get("$defs", {}), (
            "actor-hosts schema missing $defs/host_lifecycle"
        )

    def test_schema_defines_host_address(self):
        schema = _load_hosts_schema()
        assert "host_address" in schema.get("$defs", {}), (
            "actor-hosts schema missing $defs/host_address"
        )

    def test_schema_defines_heartbeat_config(self):
        schema = _load_hosts_schema()
        assert "heartbeat_config" in schema.get("$defs", {}), (
            "actor-hosts schema missing $defs/heartbeat_config"
        )

    def test_schema_defines_probe_metadata(self):
        schema = _load_hosts_schema()
        assert "probe_metadata" in schema.get("$defs", {}), (
            "actor-hosts schema missing $defs/probe_metadata"
        )

    def test_actor_host_requires_host_id(self):
        schema = _load_hosts_schema()
        required = schema["$defs"]["actor_host"].get("required", [])
        assert "host_id" in required, "actor_host must require host_id"

    def test_actor_host_requires_host_type(self):
        schema = _load_hosts_schema()
        required = schema["$defs"]["actor_host"].get("required", [])
        assert "host_type" in required, "actor_host must require host_type"

    def test_actor_host_defines_lifecycle_property(self):
        schema = _load_hosts_schema()
        props = schema["$defs"]["actor_host"].get("properties", {})
        assert "lifecycle" in props, "actor_host schema missing lifecycle property"

    def test_actor_host_defines_address_property(self):
        schema = _load_hosts_schema()
        props = schema["$defs"]["actor_host"].get("properties", {})
        assert "address" in props, "actor_host schema missing address property"

    def test_actor_host_defines_heartbeat_property(self):
        schema = _load_hosts_schema()
        props = schema["$defs"]["actor_host"].get("properties", {})
        assert "heartbeat" in props, "actor_host schema missing heartbeat property"

    def test_actor_host_defines_probe_property(self):
        schema = _load_hosts_schema()
        props = schema["$defs"]["actor_host"].get("properties", {})
        assert "probe" in props, "actor_host schema missing probe property"


class TestActorFixtureFields:
    """Every actor in the fixture must carry required structural fields."""

    def test_all_actors_have_actor_id(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "actor_id" in actor, f"{actor_id}: missing actor_id"
            assert actor["actor_id"] == actor_id, (
                f"{actor_id}: actor_id value mismatch (key={actor_id!r}, "
                f"actor_id={actor['actor_id']!r})"
            )

    def test_all_actors_have_host_id(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "host_id" in actor, f"{actor_id}: missing host_id"
            assert actor["host_id"], f"{actor_id}: host_id is empty"

    def test_all_actors_have_lease(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "lease" in actor, f"{actor_id}: missing lease"

    def test_all_actors_lease_has_required_fields(self):
        actors = _load_actors()
        required_lease_fields = {
            "acquired_at", "expires_at", "renewable", "preemptible", "heartbeat_timeout_sec"
        }
        for actor_id, actor in actors["actors"].items():
            lease = actor.get("lease", {})
            for field in required_lease_fields:
                assert field in lease, f"{actor_id}.lease: missing {field}"

    def test_all_actors_lease_heartbeat_timeout_is_positive_int(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            timeout = actor["lease"]["heartbeat_timeout_sec"]
            assert isinstance(timeout, int) and timeout >= 1, (
                f"{actor_id}.lease.heartbeat_timeout_sec must be int >= 1, got {timeout!r}"
            )

    def test_all_actors_have_mailbox(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "mailbox" in actor, f"{actor_id}: missing mailbox"

    def test_all_actors_mailbox_has_required_paths(self):
        actors = _load_actors()
        required_mailbox_keys = {"inbox", "outbox", "logs", "state_json", "heartbeat_json"}
        for actor_id, actor in actors["actors"].items():
            mailbox = actor.get("mailbox", {})
            for key in required_mailbox_keys:
                assert key in mailbox, f"{actor_id}.mailbox: missing {key}"
                assert mailbox[key], f"{actor_id}.mailbox.{key}: path is empty"

    def test_all_actors_mailbox_state_json_path_ends_in_state_json(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            path = actor["mailbox"]["state_json"]
            assert path.endswith("state.json"), (
                f"{actor_id}.mailbox.state_json should point to a state.json file, got {path!r}"
            )

    def test_all_actors_mailbox_heartbeat_json_path_ends_in_heartbeat_json(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            path = actor["mailbox"]["heartbeat_json"]
            assert path.endswith("heartbeat.json"), (
                f"{actor_id}.mailbox.heartbeat_json should point to a heartbeat.json file, "
                f"got {path!r}"
            )

    def test_all_actors_have_persona_binding(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "persona_binding" in actor, f"{actor_id}: missing persona_binding"
            binding = actor["persona_binding"]
            assert "persona_id" in binding, f"{actor_id}.persona_binding: missing persona_id"

    def test_all_actors_have_fallback_ladder(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "fallback_ladder" in actor, f"{actor_id}: missing fallback_ladder"
            assert isinstance(actor["fallback_ladder"], list), (
                f"{actor_id}.fallback_ladder must be a list"
            )

    def test_all_actors_have_evidence(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "evidence" in actor, f"{actor_id}: missing evidence"


class TestOperatorAliasMapping:
    """Every actor must have an operator_alias; all physical operator ids must be covered."""

    def test_all_actors_have_operator_alias(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "operator_alias" in actor, f"{actor_id}: missing operator_alias"
            assert actor["operator_alias"], f"{actor_id}: operator_alias is empty"

    def test_all_actor_operator_aliases_match_physical_operators(self):
        actors = _load_actors()
        physical_ops = _load_physical_ops()
        known_op_ids = set(physical_ops["operators"].keys())
        for actor_id, actor in actors["actors"].items():
            alias = actor["operator_alias"]
            assert alias in known_op_ids, (
                f"{actor_id}: operator_alias={alias!r} not found in physical-operators.json"
            )

    def test_all_physical_operator_ids_appear_as_actor_aliases(self):
        actors = _load_actors()
        physical_ops = _load_physical_ops()
        actor_aliases = {a["operator_alias"] for a in actors["actors"].values()}
        for op_id in physical_ops["operators"]:
            assert op_id in actor_aliases, (
                f"physical operator {op_id!r} has no corresponding actor (operator_alias)"
            )


class TestHostFixtureFields:
    """Host fixture entries must carry required structural fields."""

    def test_all_hosts_have_host_id(self):
        hosts = _load_hosts()
        for host_key, host in hosts["hosts"].items():
            assert "host_id" in host, f"{host_key}: missing host_id"
            assert host["host_id"] == host_key, (
                f"{host_key}: host_id value mismatch"
            )

    def test_all_hosts_have_host_type(self):
        hosts = _load_hosts()
        valid_types = {
            "mac_mini", "remote_vm", "local_workstation",
            "cloud_container", "localhost",
            "browser_profile_host", "browser_agent_session",
        }
        for host_key, host in hosts["hosts"].items():
            assert "host_type" in host, f"{host_key}: missing host_type"
            assert host["host_type"] in valid_types, (
                f"{host_key}: unknown host_type={host['host_type']!r}"
            )

    def test_all_hosts_have_lifecycle(self):
        hosts = _load_hosts()
        for host_key, host in hosts["hosts"].items():
            assert "lifecycle" in host, f"{host_key}: missing lifecycle"

    def test_all_hosts_have_address(self):
        hosts = _load_hosts()
        for host_key, host in hosts["hosts"].items():
            assert "address" in host, f"{host_key}: missing address"

    def test_all_hosts_have_heartbeat(self):
        hosts = _load_hosts()
        for host_key, host in hosts["hosts"].items():
            assert "heartbeat" in host, f"{host_key}: missing heartbeat"

    def test_all_hosts_have_probe(self):
        hosts = _load_hosts()
        for host_key, host in hosts["hosts"].items():
            assert "probe" in host, f"{host_key}: missing probe"

    def test_all_actor_host_ids_resolve_to_known_hosts(self):
        actors = _load_actors()
        hosts = _load_hosts()
        known_hosts = set(hosts["hosts"].keys())
        for actor_id, actor in actors["actors"].items():
            host_id = actor["host_id"]
            assert host_id in known_hosts, (
                f"{actor_id}: host_id={host_id!r} not found in actor-hosts.json"
            )


class TestSchemaValidation:
    """Fixtures must validate against their schemas end-to-end."""

    def test_actors_fixture_validates_against_schema(self):
        actors = _load_actors()
        schema = _load_actors_schema()
        jsonschema.validate(instance=actors, schema=schema)

    def test_hosts_fixture_validates_against_schema(self):
        hosts = _load_hosts()
        schema = _load_hosts_schema()
        jsonschema.validate(instance=hosts, schema=schema)

    def test_actors_fixture_is_valid_json(self):
        actors = _load_actors()
        assert "actors" in actors
        assert actors["version"] >= 1

    def test_hosts_fixture_is_valid_json(self):
        hosts = _load_hosts()
        assert "hosts" in hosts
        assert hosts["version"] >= 1

    def test_schema_rejects_actor_missing_host_id(self):
        schema = _load_actors_schema()
        bad = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "actor_id": "test-actor"
                    # host_id intentionally absent
                }
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_rejects_actor_missing_actor_id(self):
        schema = _load_actors_schema()
        bad = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "host_id": "mini"
                    # actor_id intentionally absent
                }
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_rejects_host_missing_host_type(self):
        schema = _load_hosts_schema()
        bad = {
            "version": 1,
            "hosts": {
                "test-host": {
                    "host_id": "test-host"
                    # host_type intentionally absent
                }
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_accepts_valid_actor(self):
        schema = _load_actors_schema()
        valid = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "actor_id": "test-actor",
                    "host_id": "mini",
                    "lease": {
                        "acquired_at": None,
                        "expires_at": None,
                        "renewable": True,
                        "preemptible": False,
                        "heartbeat_timeout_sec": 60
                    },
                    "mailbox": {
                        "inbox": "actors/test-actor/inbox",
                        "outbox": "actors/test-actor/outbox",
                        "logs": "actors/test-actor/logs",
                        "state_json": "actors/test-actor/state.json",
                        "heartbeat_json": "actors/test-actor/heartbeat.json"
                    }
                }
            }
        }
        jsonschema.validate(instance=valid, schema=schema)

    def test_schema_accepts_valid_host(self):
        schema = _load_hosts_schema()
        valid = {
            "version": 1,
            "hosts": {
                "test-host": {
                    "host_id": "test-host",
                    "host_type": "localhost"
                }
            }
        }
        jsonschema.validate(instance=valid, schema=schema)


class TestFallbackLadderIntegrity:
    """Fallback ladder entries must reference valid actor_ids within the registry."""

    def test_all_fallback_actor_ids_exist(self):
        actors = _load_actors()
        known_ids = set(actors["actors"].keys())
        for actor_id, actor in actors["actors"].items():
            for i, step in enumerate(actor.get("fallback_ladder", [])):
                target = step.get("actor_id")
                assert target in known_ids, (
                    f"{actor_id}.fallback_ladder[{i}]: actor_id={target!r} not in registry"
                )

    def test_actors_do_not_self_reference_in_fallback(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            for step in actor.get("fallback_ladder", []):
                assert step.get("actor_id") != actor_id, (
                    f"{actor_id}: fallback_ladder must not self-reference"
                )


CAPABILITY_PROFILE_FIELDS = {
    "architecture_reasoning", "code_impl", "root_cause_debug",
    "test_generation", "test_execution", "research_synthesis",
    "academic_critique", "browser_use", "gui_use",
    "long_context", "multi_agent_coordination", "speed",
}

RISK_PROFILE_FIELDS = {
    "allowed_write_scope", "allowed_shell_scope", "allowed_network",
    "allowed_secrets", "destructive_actions", "git_commit",
    "git_push", "payment_or_external_action", "requires_human_for",
}

COST_PROFILE_FIELDS = {
    "cost_tier", "token_budget_class", "quota_period",
    "reserve_ratio", "effort", "prefer_for", "avoid_for",
}


class TestCapabilityProfileSchema:
    """Schema must define capability_profile with all 12 fields."""

    def test_schema_defines_capability_profile(self):
        schema = _load_actors_schema()
        assert "capability_profile" in schema.get("$defs", {}), (
            "agent-actors schema missing $defs/capability_profile"
        )

    def test_capability_profile_has_all_12_fields(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["capability_profile"].get("properties", {})
        missing = CAPABILITY_PROFILE_FIELDS - set(props.keys())
        assert not missing, f"capability_profile missing fields: {missing}"

    def test_capability_profile_fields_are_integers_0_to_5(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["capability_profile"].get("properties", {})
        for field in CAPABILITY_PROFILE_FIELDS:
            if field not in props:
                continue
            assert props[field].get("type") == "integer", (
                f"capability_profile.{field} must be integer"
            )
            assert props[field].get("minimum") == 0, (
                f"capability_profile.{field} minimum must be 0"
            )
            assert props[field].get("maximum") == 5, (
                f"capability_profile.{field} maximum must be 5"
            )

    def test_capability_profile_rejects_score_out_of_range(self):
        schema = _load_actors_schema()
        bad = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "actor_id": "test-actor",
                    "host_id": "mini",
                    "capability_profile": {"code_impl": 9},
                }
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_capability_profile_accepts_valid_scores(self):
        schema = _load_actors_schema()
        valid = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "actor_id": "test-actor",
                    "host_id": "mini",
                    "capability_profile": {
                        "architecture_reasoning": 5,
                        "code_impl": 4,
                        "root_cause_debug": 3,
                        "test_generation": 2,
                        "test_execution": 1,
                        "research_synthesis": 0,
                        "academic_critique": 3,
                        "browser_use": 0,
                        "gui_use": 0,
                        "long_context": 4,
                        "multi_agent_coordination": 3,
                        "speed": 2,
                    },
                }
            }
        }
        jsonschema.validate(instance=valid, schema=schema)


class TestRiskProfileSchema:
    """Schema must define risk_profile with all 9 fields."""

    def test_schema_defines_risk_profile(self):
        schema = _load_actors_schema()
        assert "risk_profile" in schema.get("$defs", {}), (
            "agent-actors schema missing $defs/risk_profile"
        )

    def test_risk_profile_has_all_9_fields(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["risk_profile"].get("properties", {})
        missing = RISK_PROFILE_FIELDS - set(props.keys())
        assert not missing, f"risk_profile missing fields: {missing}"

    def test_risk_profile_allowed_write_scope_is_enum(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["risk_profile"]["properties"]
        enum_vals = props["allowed_write_scope"].get("enum", [])
        assert "harness" in enum_vals
        assert "harness_readonly" in enum_vals
        assert "project" in enum_vals
        assert "denied" in enum_vals

    def test_risk_profile_allowed_shell_scope_is_enum(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["risk_profile"]["properties"]
        enum_vals = props["allowed_shell_scope"].get("enum", [])
        assert "allowed" in enum_vals
        assert "read_only" in enum_vals
        assert "denied" in enum_vals

    def test_risk_profile_requires_human_for_is_array(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["risk_profile"]["properties"]
        assert props["requires_human_for"]["type"] == "array"

    def test_risk_profile_rejects_unknown_write_scope(self):
        schema = _load_actors_schema()
        bad = {
            "version": 1,
            "actors": {
                "test-actor": {
                    "actor_id": "test-actor",
                    "host_id": "mini",
                    "risk_profile": {"allowed_write_scope": "universe"},
                }
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)


class TestCostProfileSchema:
    """Schema must define cost_profile with all 7 fields."""

    def test_schema_defines_cost_profile(self):
        schema = _load_actors_schema()
        assert "cost_profile" in schema.get("$defs", {}), (
            "agent-actors schema missing $defs/cost_profile"
        )

    def test_cost_profile_has_all_7_fields(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["cost_profile"].get("properties", {})
        missing = COST_PROFILE_FIELDS - set(props.keys())
        assert not missing, f"cost_profile missing fields: {missing}"

    def test_cost_profile_cost_tier_enum(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["cost_profile"]["properties"]
        enum_vals = props["cost_tier"].get("enum", [])
        assert set(enum_vals) == {"low", "medium", "high"}

    def test_cost_profile_token_budget_class_enum(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["cost_profile"]["properties"]
        enum_vals = props["token_budget_class"].get("enum", [])
        assert "small" in enum_vals
        assert "medium" in enum_vals
        assert "large" in enum_vals
        assert "xlarge" in enum_vals

    def test_cost_profile_reserve_ratio_bounds(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["cost_profile"]["properties"]
        rr = props["reserve_ratio"]
        assert rr.get("minimum") == 0.0
        assert rr.get("maximum") == 1.0

    def test_cost_profile_prefer_for_and_avoid_for_are_arrays(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["cost_profile"]["properties"]
        assert props["prefer_for"]["type"] == "array"
        assert props["avoid_for"]["type"] == "array"


class TestActorProfileFixtures:
    """All actors in the fixture must carry capability_profile, risk_profile, cost_profile."""

    def test_all_actors_have_capability_profile(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "capability_profile" in actor, (
                f"{actor_id}: missing capability_profile"
            )

    def test_all_actors_capability_profile_has_all_12_fields(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            cp = actor.get("capability_profile", {})
            missing = CAPABILITY_PROFILE_FIELDS - set(cp.keys())
            assert not missing, (
                f"{actor_id}.capability_profile missing fields: {missing}"
            )

    def test_all_actors_capability_profile_scores_in_range(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            cp = actor.get("capability_profile", {})
            for field, val in cp.items():
                assert isinstance(val, int) and 0 <= val <= 5, (
                    f"{actor_id}.capability_profile.{field}={val!r} must be int 0-5"
                )

    def test_all_actors_have_risk_profile(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "risk_profile" in actor, f"{actor_id}: missing risk_profile"

    def test_all_actors_risk_profile_has_all_9_fields(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            rp = actor.get("risk_profile", {})
            missing = RISK_PROFILE_FIELDS - set(rp.keys())
            assert not missing, (
                f"{actor_id}.risk_profile missing fields: {missing}"
            )

    def test_all_actors_have_cost_profile(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "cost_profile" in actor, f"{actor_id}: missing cost_profile"

    def test_all_actors_cost_profile_has_all_7_fields(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            cp = actor.get("cost_profile", {})
            missing = COST_PROFILE_FIELDS - set(cp.keys())
            assert not missing, (
                f"{actor_id}.cost_profile missing fields: {missing}"
            )

    def test_all_actors_have_context_packet_ref(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "context_packet_ref" in actor, (
                f"{actor_id}: missing context_packet_ref"
            )

    def test_all_actors_context_packet_ref_idle_state(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            cpr = actor.get("context_packet_ref", {})
            assert "path" in cpr, f"{actor_id}.context_packet_ref: missing path"
            assert "packet_id" in cpr, (
                f"{actor_id}.context_packet_ref: missing packet_id"
            )

    def test_all_actors_have_evidence_ledger_ref(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            assert "evidence_ledger_ref" in actor, (
                f"{actor_id}: missing evidence_ledger_ref"
            )

    def test_all_actors_evidence_ledger_ref_has_path(self):
        actors = _load_actors()
        for actor_id, actor in actors["actors"].items():
            elr = actor.get("evidence_ledger_ref", {})
            assert "path" in elr, f"{actor_id}.evidence_ledger_ref: missing path"


class TestContextPacketAndEvidenceSchemas:
    """Schema must define context_packet_ref and evidence_ledger_ref sub-schemas."""

    def test_schema_defines_context_packet_ref(self):
        schema = _load_actors_schema()
        assert "context_packet_ref" in schema.get("$defs", {}), (
            "agent-actors schema missing $defs/context_packet_ref"
        )

    def test_schema_defines_evidence_ledger_ref(self):
        schema = _load_actors_schema()
        assert "evidence_ledger_ref" in schema.get("$defs", {}), (
            "agent-actors schema missing $defs/evidence_ledger_ref"
        )

    def test_context_packet_ref_has_path_and_packet_id(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["context_packet_ref"].get("properties", {})
        assert "path" in props, "context_packet_ref missing path"
        assert "packet_id" in props, "context_packet_ref missing packet_id"

    def test_evidence_ledger_ref_has_path(self):
        schema = _load_actors_schema()
        props = schema["$defs"]["evidence_ledger_ref"].get("properties", {})
        assert "path" in props, "evidence_ledger_ref missing path"


if __name__ == "__main__":
    suites = [
        TestActorSchemaDefinitions(),
        TestLeaseSchemaFields(),
        TestMailboxSchemaFields(),
        TestDisplayMetaTmuxConstraint(),
        TestHostSchemaDefinitions(),
        TestActorFixtureFields(),
        TestOperatorAliasMapping(),
        TestHostFixtureFields(),
        TestSchemaValidation(),
        TestFallbackLadderIntegrity(),
        TestCapabilityProfileSchema(),
        TestRiskProfileSchema(),
        TestCostProfileSchema(),
        TestActorProfileFixtures(),
        TestContextPacketAndEvidenceSchemas(),
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

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANONICAL_HOST_TYPES = {
    "tmux_pane",
    "codex_worktree",
    "codex_cloud",
    "antigravity_managed_env",
    "claude_code_session",
    "local_mlx_process",
    "ssh_devbox",
    "docker_sandbox",
}
LEGACY_HOST_TYPES = {
    "mac_mini",
    "remote_vm",
    "local_workstation",
    "cloud_container",
    "localhost",
    "browser_profile_host",
    "browser_agent_session",
    "group_host",
}


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def actor_host_schema() -> dict:
    return load_json("harness/config/actor-hosts.schema.json")


def actor_hosts() -> dict:
    return load_json("harness/config/actor-hosts.json")["hosts"]


def test_schema_host_type_enum_is_canonical_eight_value_set():
    props = actor_host_schema()["$defs"]["actor_host"]["properties"]
    assert set(props["host_type"]["enum"]) == CANONICAL_HOST_TYPES
    assert len(props["host_type"]["enum"]) == 8


def test_schema_host_type_enum_excludes_legacy_values():
    enum = set(actor_host_schema()["$defs"]["actor_host"]["properties"]["host_type"]["enum"])
    assert enum.isdisjoint(LEGACY_HOST_TYPES)


def test_schema_has_required_carrier_meta_defs():
    defs = actor_host_schema()["$defs"]
    assert set(defs["tmux_pane_meta"]["required"]) == {"session", "window", "pane"}
    assert set(defs["codex_meta"]["required"]) == {"worktree_path"}
    assert set(defs["antigravity_meta"]["required"]) == {"environment_id"}
    assert set(defs["mlx_meta"]["required"]) == {"model_path", "port"}
    assert set(defs["ssh_meta"]["required"]) == {"hostname", "user"}


def test_registry_covers_all_canonical_host_types():
    host_types = {host["host_type"] for host in actor_hosts().values()}
    assert CANONICAL_HOST_TYPES <= host_types


def test_registry_entries_include_required_fields():
    required = {"host_id", "host_type", "display_name", "lifecycle", "address"}
    missing = {
        host_id: sorted(required - set(host))
        for host_id, host in actor_hosts().items()
        if required - set(host)
    }
    assert missing == {}


def test_mini_is_claude_code_session_with_display_label():
    mini = actor_hosts()["mini"]
    assert mini["host_type"] == "claude_code_session"
    assert mini["display_meta"]["label"] == "mini"


def test_browser_profile_host_is_antigravity_managed_env():
    browser_host = actor_hosts()["browser_profile_host"]
    assert browser_host["host_type"] == "antigravity_managed_env"
    assert browser_host["carrier"]["antigravity_meta"]["browser_profile"]


def test_registry_host_type_values_have_no_legacy_residue():
    host_types = {host["host_type"] for host in actor_hosts().values()}
    assert host_types.isdisjoint(LEGACY_HOST_TYPES)


def test_agent_actor_host_references_resolve_to_registry():
    hosts = actor_hosts()
    actors = load_json("harness/config/agent-actors.json")["actors"]
    missing = []
    for actor_id, actor in actors.items():
        for field in ("host_id", "preferred_host"):
            host_id = actor.get(field)
            if isinstance(host_id, str) and host_id not in hosts:
                missing.append((actor_id, field, host_id))
    assert missing == []

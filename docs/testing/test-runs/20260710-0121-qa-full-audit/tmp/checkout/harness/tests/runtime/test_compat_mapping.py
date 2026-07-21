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
REQUIRED_CARRIER_HINTS = {
    "tmux_pane_meta",
    "codex_meta",
    "antigravity_meta",
    "mlx_meta",
    "ssh_meta",
}


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def physical_operators() -> dict:
    return load_json("harness/config/physical-operators.json")


def operator_entries() -> list[dict]:
    return list(physical_operators()["operators"].values())


def test_physical_operator_meta_transition_is_read_only():
    meta = physical_operators()["_meta"]
    assert meta["transition_status"] == "read_only"
    assert meta["deprecated_at"]
    assert meta["sunset_target"]


def test_physical_operator_schema_exposes_deprecation_fields():
    props = load_json("harness/config/physical-operators.schema.json")["properties"]
    assert props["deprecated"]["const"] is True
    assert props["deprecation_note"]["minLength"] >= 1
    assert props["transition_status"]["const"] == "read_only"
    assert set(props["transition_status"]["enum"]) == {"read_only", "deprecated", "sunset"}
    assert props["sunset_after_slice"]["const"] == "S05"


def test_all_operators_have_compat_alias_for():
    entries = operator_entries()
    assert len(entries) == 45
    assert all("compat_alias_for" in entry for entry in entries)


def test_compat_alias_values_are_canonical_host_types():
    bad = sorted({entry["compat_alias_for"] for entry in operator_entries()} - CANONICAL_HOST_TYPES)
    assert bad == []


def test_compat_maps_to_host_type_matches_alias():
    mismatches = [
        entry.get("id")
        for entry in operator_entries()
        if entry["compat_maps_to"]["host_type"] != entry["compat_alias_for"]
    ]
    assert mismatches == []


def test_all_operators_are_marked_deprecated():
    assert all(entry.get("deprecated") is True for entry in operator_entries())


def test_compat_mapping_covers_required_carrier_hints():
    hints = set()
    for entry in operator_entries():
        hints.update(entry["compat_maps_to"]["carrier_hint"].keys())
    assert REQUIRED_CARRIER_HINTS <= hints


def test_operator_entries_do_not_have_top_level_host_type():
    offenders = [entry.get("id") for entry in operator_entries() if "host_type" in entry]
    assert offenders == []

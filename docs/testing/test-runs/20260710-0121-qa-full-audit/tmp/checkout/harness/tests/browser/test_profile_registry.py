"""Tests for harness/lib/browser/profile_registry.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from browser.profile_registry import ProfileRegistry  # noqa: E402


def test_profile_registry_meta_and_health_and_cdp(tmp_path: Path) -> None:
    registry = ProfileRegistry(root=tmp_path)
    profile_id = "dev-profile"

    meta = registry.write_meta(profile_id, {"owner": "qa-team"})
    assert registry.read_meta(profile_id) == meta
    assert registry.meta_path(profile_id).exists()

    health = {"status": "ok", "last_ping_seconds_ago": 0}
    registry.write_health(profile_id, health)
    read_health = registry.read_health(profile_id)
    assert read_health["status"] == "ok"
    assert read_health["profile_id"] == profile_id
    assert registry.health_path(profile_id).exists()

    cdp = {"page": "about:blank", "session_id": "sid-001"}
    registry.write_cdp_last(profile_id, cdp)
    read_cdp = registry.read_cdp_last(profile_id)
    assert read_cdp["page"] == "about:blank"
    assert read_cdp["profile_id"] == profile_id
    assert registry.cdp_last_path(profile_id).exists()


def test_profile_registry_evidence_and_state_refs(tmp_path: Path) -> None:
    registry = ProfileRegistry(root=tmp_path)
    profile_id = "dev-profile-2"

    evidence = registry.evidence_dir(profile_id)
    assert evidence.exists()
    assert evidence.is_dir()

    storage_ref = "/tmp/storage_state.json"
    assert registry.set_storage_state_ref(profile_id, storage_ref) == storage_ref
    assert registry.get_storage_state_ref(profile_id) == storage_ref

    allowed = ["alice@example.com", "Bob@Example.Com", "alice@example.com"]
    saved = registry.set_allowed_account_identifiers(profile_id, allowed)
    assert saved == ["alice@example.com", "bob@example.com"]
    assert registry.get_allowed_account_identifiers(profile_id) == ["alice@example.com", "bob@example.com"]


def test_profile_registry_defaults(tmp_path: Path) -> None:
    custom = tmp_path / "custom-root"
    registry = ProfileRegistry(root=custom)
    assert registry.root == custom
    assert custom.exists()
    assert isinstance(registry.meta_path("p").parent, Path)


def test_profile_registry_supports_nested_profile_ids(tmp_path: Path) -> None:
    registry = ProfileRegistry(root=tmp_path)
    meta = registry.write_meta("chatgpt/example-user", {"status": "healthy"})
    assert meta["profile_id"] == "chatgpt/example-user"
    assert registry.meta_path("chatgpt/example-user").exists()

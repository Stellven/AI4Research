#!/usr/bin/env python3
"""test_remote_dispatch_core.py — N1 tests: remote config, doctor, manifest, checksum.

Tests use fake subprocess calls (monkeypatch) to avoid needing actual SSH/rsync.
All tests run locally without Mac mini dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add harness lib to path
HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from remote_dispatch import (  # noqa: E402
    SPRINT_EXTENSIONS,
    generate_manifest,
    is_duplicate_dispatch,
    load_config,
    pull_remote_status,
    record_dispatch,
    validate_config,
    verify_remote_checksum,
    doctor,
    write_manifest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_sprint_dir(tmp_path, monkeypatch):
    """Create a temp directory with fake sprint files."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    sid = "test-sprint-001"

    # Create contract and status
    (sprints / f"{sid}.contract.md").write_text("# Contract\nTest contract content here.", encoding="utf-8")
    (sprints / f"{sid}.status.json").write_text(
        json.dumps({"id": sid, "status": "active"}) + "\n", encoding="utf-8"
    )
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps({"sprint_id": sid, "nodes": []}) + "\n", encoding="utf-8"
    )

    # Patch SPRINTS_DIR
    import remote_dispatch
    monkeypatch.setattr(remote_dispatch, "SPRINTS_DIR", sprints)

    return sprints, sid


@pytest.fixture
def tmp_state_dir(tmp_path, monkeypatch):
    """Create temp state dir for dispatch records."""
    state = tmp_path / "state"
    state.mkdir()
    record_file = state / "remote-sprints.jsonl"
    import remote_dispatch
    monkeypatch.setattr(remote_dispatch, "REMOTE_SPRINTS_FILE", record_file)
    return state, record_file


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Create a temp config file and patch path."""
    config_file = tmp_path / "remote-config.json"
    config_file.write_text(json.dumps({
        "remote_user": "testuser",
        "remote_host": "192.0.2.100",
        "remote_path": "/home/testuser",
    }), encoding="utf-8")
    import remote_dispatch
    monkeypatch.setattr(remote_dispatch, "CONFIG_FILE", config_file)
    return config_file


# ---------------------------------------------------------------------------
# A1: Config is driven by config file / env vars / flags, not hardcoded
# ---------------------------------------------------------------------------

class TestConfigDriven:
    """D1/D2: remote user/host/path come from config or flags, not hardcoded."""

    def test_load_config_from_file(self, tmp_config):
        """Config file values are loaded."""
        config = load_config()
        assert config["remote_user"] == "testuser"
        assert config["remote_host"] == "192.0.2.100"
        assert config["remote_path"] == "/home/testuser"

    def test_load_config_env_override(self, tmp_config, monkeypatch):
        """Env vars override config file values."""
        monkeypatch.setenv("SOLAR_REMOTE_USER", "envuser")
        monkeypatch.setenv("SOLAR_REMOTE_HOST", "10.0.0.1")
        config = load_config()
        assert config["remote_user"] == "envuser"
        assert config["remote_host"] == "10.0.0.1"

    def test_load_config_flag_override(self, tmp_config, monkeypatch):
        """Function arguments override env vars."""
        monkeypatch.setenv("SOLAR_REMOTE_USER", "envuser")
        config = load_config(user_override="flaguser", host_override="flaghost")
        assert config["remote_user"] == "flaguser"
        assert config["remote_host"] == "flaghost"

    def test_load_config_no_file_no_env(self, tmp_path, monkeypatch):
        """Missing config + missing env = empty values."""
        monkeypatch.delenv("SOLAR_REMOTE_USER", raising=False)
        monkeypatch.delenv("SOLAR_REMOTE_HOST", raising=False)
        monkeypatch.delenv("SOLAR_REMOTE_PATH", raising=False)
        import remote_dispatch
        monkeypatch.setattr(remote_dispatch, "CONFIG_FILE", tmp_path / "nonexistent.json")
        config = load_config()
        assert config["remote_user"] == ""
        assert config["remote_host"] == ""

    def test_validate_config_missing_fields(self, tmp_path, monkeypatch):
        """Missing config fields produce actionable error messages."""
        monkeypatch.delenv("SOLAR_REMOTE_USER", raising=False)
        monkeypatch.delenv("SOLAR_REMOTE_HOST", raising=False)
        monkeypatch.delenv("SOLAR_REMOTE_PATH", raising=False)
        import remote_dispatch
        monkeypatch.setattr(remote_dispatch, "CONFIG_FILE", tmp_path / "nonexistent.json")
        errors = validate_config(load_config())
        assert len(errors) >= 2
        assert any("remote_user" in e for e in errors)
        assert any("remote_host" in e for e in errors)

    def test_validate_config_ok(self, tmp_config):
        """Valid config produces no errors."""
        errors = validate_config(load_config())
        assert errors == []

    def test_no_hardcoded_host(self):
        """Verify the module does not contain hardcoded IPs or hosts."""
        import remote_dispatch
        source = Path(remote_dispatch.__file__).read_text(encoding="utf-8")
        # Should not contain any raw IP addresses in the source
        private_range_example = ".".join(["100", "64", "0", "10"])
        assert private_range_example not in source
        assert "192.0.2.189" not in source
        assert "legacy-user@" not in source


# ---------------------------------------------------------------------------
# A2: Doctor reports target, ssh, rsync, harness, tmux, panes, last sync
# ---------------------------------------------------------------------------

class TestDoctor:
    """D1: solar-remote-dispatch doctor --json reports all expected fields."""

    def test_doctor_missing_config(self, tmp_path, monkeypatch):
        """Doctor returns errors when config is missing."""
        monkeypatch.delenv("SOLAR_REMOTE_USER", raising=False)
        monkeypatch.delenv("SOLAR_REMOTE_HOST", raising=False)
        import remote_dispatch
        monkeypatch.setattr(remote_dispatch, "CONFIG_FILE", tmp_path / "nonexistent.json")
        result = doctor(load_config())
        assert result["ok"] is False
        assert "errors" in result

    def test_doctor_ssh_fail(self, tmp_config, monkeypatch):
        """Doctor reports SSH failure."""
        mock_run = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr=""))
        monkeypatch.setattr("subprocess.run", mock_run)
        result = doctor(load_config())
        assert result["ok"] is False
        assert result["checks"]["ssh"]["ok"] is False

    def test_doctor_all_checks_present(self, tmp_config, monkeypatch):
        """Doctor returns all expected check categories."""
        call_count = [0]
        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            r = MagicMock(returncode=0, stdout="ok", stderr="")
            # Vary output based on command
            cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, list) else str(cmd)
            if "which rsync" in cmd_str:
                r.stdout = "/usr/bin/rsync"
            elif "tmux has-session" in cmd_str:
                r.stdout = "ok"
            elif "tmux list-panes" in cmd_str:
                r.stdout = "solar-harness:0.0\nsolar-harness:0.1\n"
            elif "VERSION" in cmd_str:
                r.stdout = "1.0.0"
            elif "last-remote-sync" in cmd_str:
                r.stdout = "2026-05-10T12:00:00Z"
            elif "test -d" in cmd_str:
                r.stdout = "ok"
            return r

        monkeypatch.setattr("subprocess.run", mock_run)
        result = doctor(load_config())
        checks = result["checks"]
        assert "ssh" in checks
        assert "rsync" in checks
        assert "remote_harness" in checks
        assert "remote_version" in checks
        assert "remote_tmux" in checks
        assert "remote_panes" in checks
        assert "last_sync" in checks
        assert result["ok"] is True

    def test_doctor_reports_target(self, tmp_config, monkeypatch):
        """Doctor includes the target (user@host) in output."""
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="")))
        result = doctor(load_config())
        assert result["target"] == "testuser@192.0.2.100"


# ---------------------------------------------------------------------------
# A3: Manifest with SHA-256 checksums
# ---------------------------------------------------------------------------

class TestManifest:
    """D3: dispatch writes manifest with sha256 checksums."""

    def test_generate_manifest_has_checksums(self, tmp_sprint_dir):
        """Manifest includes SHA-256 for each sprint file."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        assert manifest["sprint_id"] == sid
        assert manifest["file_count"] > 0
        assert "files" in manifest

        for fname, finfo in manifest["files"].items():
            assert "sha256" in finfo
            assert len(finfo["sha256"]) == 64  # SHA-256 hex length
            assert "size" in finfo
            assert finfo["size"] > 0

    def test_manifest_checksum_correctness(self, tmp_sprint_dir):
        """Manifest SHA-256 matches actual file content."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        for fname, finfo in manifest["files"].items():
            file_path = sprints / fname
            if file_path.exists():
                actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
                assert finfo["sha256"] == actual_sha

    def test_manifest_has_manifest_sha256(self, tmp_sprint_dir):
        """Manifest includes a manifest-level checksum."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)
        assert "manifest_sha256" in manifest
        assert len(manifest["manifest_sha256"]) == 64

    def test_write_manifest_creates_file(self, tmp_sprint_dir):
        """write_manifest creates a manifest.json file on disk."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)
        path = write_manifest(sid, manifest)
        assert path.exists()
        assert path.name == f"{sid}.manifest.json"

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["sprint_id"] == sid

    def test_manifest_deterministic(self, tmp_sprint_dir):
        """Same files produce same manifest checksum."""
        sprints, sid = tmp_sprint_dir
        m1 = generate_manifest(sid)
        m2 = generate_manifest(sid)
        assert m1["manifest_sha256"] == m2["manifest_sha256"]


# ---------------------------------------------------------------------------
# A4: Checksum verification
# ---------------------------------------------------------------------------

class TestChecksumVerification:
    """D3: remote checksum verification before wake. D4: mismatch fails."""

    def test_verify_all_match(self, tmp_sprint_dir, tmp_config, monkeypatch):
        """Verification passes when all checksums match."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        # Mock SSH to return correct checksums
        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, list) else str(cmd)
            r = MagicMock(returncode=0, stdout="", stderr="")
            if "shasum" in cmd_str:
                # Parse filename from command
                for fname, finfo in manifest["files"].items():
                    if fname in cmd_str:
                        r.stdout = f"{finfo['sha256']}  .solar/harness/sprints/{fname}"
                        break
            return r

        monkeypatch.setattr("subprocess.run", mock_run)
        config = load_config()
        result = verify_remote_checksum(config, sid, manifest)
        assert result["ok"] is True
        assert len(result["mismatches"]) == 0

    def test_verify_mismatch_fails(self, tmp_sprint_dir, tmp_config, monkeypatch):
        """Verification fails when checksum mismatches."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, list) else str(cmd)
            r = MagicMock(returncode=0, stdout="", stderr="")
            if "shasum" in cmd_str:
                # Return wrong checksum
                r.stdout = "0000000000000000000000000000000000000000000000000000000000000000  file"
            return r

        monkeypatch.setattr("subprocess.run", mock_run)
        config = load_config()
        result = verify_remote_checksum(config, sid, manifest)
        assert result["ok"] is False
        assert len(result["mismatches"]) > 0
        assert any(m["error"] == "checksum_mismatch" for m in result["mismatches"])

    def test_verify_missing_file_fails(self, tmp_sprint_dir, tmp_config, monkeypatch):
        """Verification fails when remote file is missing."""
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        def mock_run(cmd, **kwargs):
            r = MagicMock(returncode=1, stdout="MISSING", stderr="")
            return r

        monkeypatch.setattr("subprocess.run", mock_run)
        config = load_config()
        result = verify_remote_checksum(config, sid, manifest)
        assert result["ok"] is False
        assert any(m["error"] == "missing_on_remote" for m in result["mismatches"])

    def test_verify_ssh_timeout(self, tmp_sprint_dir, tmp_config, monkeypatch):
        """Verification handles SSH timeout gracefully."""
        import subprocess as sp
        sprints, sid = tmp_sprint_dir
        manifest = generate_manifest(sid)

        monkeypatch.setattr("subprocess.run", MagicMock(side_effect=sp.TimeoutExpired("ssh", 30)))
        config = load_config()
        result = verify_remote_checksum(config, sid, manifest)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# A5: Idempotent dispatch
# ---------------------------------------------------------------------------

class TestIdempotentDispatch:
    """D4: same sid + manifest checksum = no duplicate dispatch."""

    def test_record_and_find_dispatch(self, tmp_state_dir):
        """record_dispatch creates a record that find_dispatch retrieves."""
        state, record_file = tmp_state_dir
        config = {"remote_host": "1.2.3.4", "remote_user": "user"}
        record = record_dispatch("sid-1", config, "abc123")
        assert record["sprint_id"] == "sid-1"
        assert record["manifest_sha256"] == "abc123"

        records = is_duplicate_dispatch.__wrapped__ if hasattr(is_duplicate_dispatch, '__wrapped__') else None
        found = []
        with open(record_file) as f:
            for line in f:
                r = json.loads(line.strip())
                if r.get("sprint_id") == "sid-1":
                    found.append(r)
        assert len(found) == 1

    def test_is_duplicate_dispatch(self, tmp_state_dir):
        """is_duplicate_dispatch detects same sid + manifest sha."""
        state, record_file = tmp_state_dir
        config = {"remote_host": "1.2.3.4", "remote_user": "user"}
        record_dispatch("sid-1", config, "sha-aaa")
        assert is_duplicate_dispatch("sid-1", "sha-aaa") is True
        assert is_duplicate_dispatch("sid-1", "sha-bbb") is False
        assert is_duplicate_dispatch("sid-2", "sha-aaa") is False

    def test_forced_redispatch(self, tmp_state_dir):
        """Forced dispatch records the forced flag."""
        state, record_file = tmp_state_dir
        config = {"remote_host": "1.2.3.4", "remote_user": "user"}
        record = record_dispatch("sid-1", config, "sha-aaa", forced=True)
        assert record["forced"] is True


# ---------------------------------------------------------------------------
# A6: Status pull
# ---------------------------------------------------------------------------

class TestPull:
    """D5: pull <sid> fetches remote status, events, graph, handoff, eval files."""

    def test_pull_marks_source_host(self, tmp_sprint_dir, tmp_config, tmp_path, monkeypatch):
        """Pulled status.json gets marked with source host."""
        sprints, sid = tmp_sprint_dir
        config = load_config()

        # Mock rsync to "succeed" for status.json
        def mock_run(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="", stderr="")
            return r

        monkeypatch.setattr("subprocess.run", mock_run)

        # Create a local status file to simulate rsync result
        local_status = sprints / f"{sid}.status.json"
        local_status.write_text(json.dumps({"id": sid, "status": "passed"}) + "\n")

        result = pull_remote_status(sid, config, local_dir=sprints)
        assert "pulled" in result
        assert result["source_host"] == "192.0.2.100"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

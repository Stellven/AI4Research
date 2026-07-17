"""Regression tests for pytest isolation from installed Solar runtime."""
from __future__ import annotations

import types
from pathlib import Path

import conftest


def test_installed_harness_path_detection(monkeypatch, tmp_path):
    installed = tmp_path / ".solar" / "harness"
    monkeypatch.setattr(conftest, "_INSTALLED_HARNESS", installed.resolve())

    assert conftest._path_is_installed_harness(installed)
    assert conftest._path_is_installed_harness(installed / "lib" / "graph_node_dispatcher.py")
    assert not conftest._path_is_installed_harness(tmp_path / "repo" / "harness")


def test_collects_env_syspath_and_module_leaks(monkeypatch, tmp_path):
    installed = tmp_path / ".solar" / "harness"
    installed_lib = installed / "lib"
    installed_lib.mkdir(parents=True)
    module = types.SimpleNamespace(__file__=str(installed_lib / "runtime_status.py"))
    monkeypatch.setattr(conftest, "_INSTALLED_HARNESS", installed.resolve())

    leaks = conftest._collect_installed_harness_leaks(
        paths=[str(installed_lib), str(tmp_path / "repo" / "harness" / "lib")],
        modules={"runtime_status": module},
        env={"HARNESS_DIR": str(installed), "SOLAR_HARNESS_DIR": str(tmp_path / "repo" / "harness")},
    )

    assert f"env:HARNESS_DIR={installed}" in leaks
    assert f"sys.path:{installed_lib}" in leaks
    assert f"module:runtime_status={installed_lib / 'runtime_status.py'}" in leaks


def test_repo_path_is_allowed_when_installed_runtime_symlinks_to_repo(monkeypatch, tmp_path):
    repo_harness = tmp_path / "repo" / "harness"
    installed_link = tmp_path / ".solar" / "harness"
    repo_harness.mkdir(parents=True)
    installed_link.parent.mkdir(parents=True)
    installed_link.symlink_to(repo_harness, target_is_directory=True)

    monkeypatch.setattr(conftest, "_HARNESS_DIR_REAL", repo_harness.resolve())
    monkeypatch.setattr(conftest, "_INSTALLED_HARNESS_LINK", installed_link)
    monkeypatch.setattr(conftest, "_INSTALLED_HARNESS", installed_link.resolve())

    assert not conftest._path_is_installed_harness(repo_harness / "lib")
    assert conftest._path_is_installed_harness(installed_link / "lib")

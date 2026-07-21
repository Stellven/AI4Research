#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "sprint_mirror_audit",
        ROOT / "tools" / "sprint_mirror_audit.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, text: str = "ok\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_audit_reports_missing_runtime_sidecars_in_repo_mirror(tmp_path: Path):
    mod = _load_tool()
    runtime = tmp_path / "runtime" / "sprints"
    repo = tmp_path / "repo" / "sprints"
    sid = "sprint-demo"
    _write(runtime / f"{sid}.status.json", json.dumps({"status": "passed", "phase": "completed"}))
    _write(runtime / f"{sid}.task_graph.json", json.dumps({"nodes": []}))
    _write(runtime / f"{sid}.N1-eval.json", json.dumps({"verdict": "pass"}))
    _write(runtime / f"{sid}.N1-handoff.md", "# handoff\n")
    _write(runtime / f"{sid}.events.jsonl", "{}\n")
    _write(runtime / f"{sid}.N1-dispatch.md.runtime-context.json", "{}\n")
    _write(repo / sid / f"{sid}.status.json", json.dumps({"status": "passed", "phase": "completed"}))

    payload = mod.audit_mirror(runtime_sprints=runtime, repo_sprints=repo, sprint_ids=[sid])

    assert payload["summary"]["sprints"] == 1
    assert payload["summary"]["missing"] == 3
    assert payload["summary"]["different"] == 0
    files = {Path(item["source"]).name for item in payload["sprints"][0]["files"]}
    assert f"{sid}.events.jsonl" not in files
    assert f"{sid}.N1-dispatch.md.runtime-context.json" not in files
    assert f"{sid}.N1-eval.json" in files
    assert f"{sid}.N1-handoff.md" in files


def test_apply_copies_only_allowed_missing_artifacts(tmp_path: Path):
    mod = _load_tool()
    runtime = tmp_path / "runtime" / "sprints"
    repo = tmp_path / "repo" / "sprints"
    sid = "sprint-copy"
    _write(runtime / f"{sid}.status.json", json.dumps({"status": "passed", "phase": "completed"}))
    _write(runtime / f"{sid}.task_graph.json", json.dumps({"nodes": []}))
    _write(runtime / f"{sid}.N1-eval.json", json.dumps({"verdict": "pass"}))
    _write(runtime / f"{sid}.events.jsonl", "{}\n")

    payload = mod.audit_mirror(runtime_sprints=runtime, repo_sprints=repo, sprint_ids=[sid])
    applied = mod.apply_mirror(payload)

    assert applied["copied_count"] == 3
    assert (repo / sid / f"{sid}.status.json").exists()
    assert (repo / sid / f"{sid}.task_graph.json").exists()
    assert (repo / sid / f"{sid}.N1-eval.json").exists()
    assert not (repo / sid / f"{sid}.events.jsonl").exists()


def test_existing_flat_repo_artifact_keeps_flat_target(tmp_path: Path):
    mod = _load_tool()
    runtime = tmp_path / "runtime" / "sprints"
    repo = tmp_path / "repo" / "sprints"
    sid = "sprint-flat"
    _write(runtime / f"{sid}.status.json", json.dumps({"status": "passed"}))
    _write(repo / f"{sid}.status.json", json.dumps({"status": "active"}))

    payload = mod.audit_mirror(runtime_sprints=runtime, repo_sprints=repo, sprint_ids=[sid])
    item = payload["sprints"][0]["files"][0]

    assert Path(item["target"]) == repo / f"{sid}.status.json"
    assert item["state"] == "different"

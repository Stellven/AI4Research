from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
HARNESS = CHECKOUT / "harness"
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"


def _run_shim(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "SOLAR_HOME": str(tmp_path / "solar-home"),
            "CLAUDE_DIR": str(tmp_path / "claude"),
            "HARNESS_DIR": str(tmp_path),
        }
    )
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _load_action_evidence(summary: dict[str, object]) -> dict[str, object]:
    payload = json.loads(Path(str(summary["evidence_path"])).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    return json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))


def test_clean_start_resets_only_stale_runtime_coordination_state(tmp_path: Path) -> None:
    source = (HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
    start = source.index("reset_stale_runtime_state() {")
    end = source.index("\n}\n\nbg_now_iso()", start) + 2
    function_text = source[start:end]

    fixture = tmp_path / "harness"
    run_dir = fixture / "run"
    for lease_dir in (run_dir / "pane-leases", run_dir / "actor-leases"):
        lease_dir.mkdir(parents=True)
        (lease_dir / "stale.json").write_text("{}\n", encoding="utf-8")
        (lease_dir / "stale.json.lock").write_text("locked\n", encoding="utf-8")
        (lease_dir / "user-note.txt").write_text("preserve\n", encoding="utf-8")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pane-hygiene.json").write_text('{"pane":"needs_respawn"}\n', encoding="utf-8")
    for marker in (
        ".pane-assignments",
        ".drafting-flow-dispatched",
        ".drafting-flow-retry",
        ".builder-flow-dispatched",
    ):
        (fixture / marker).write_text("stale\n", encoding="utf-8")
    (fixture / "sprints").mkdir()
    (fixture / "logs").mkdir()
    (fixture / "sprints" / "keep.status.json").write_text('{"status":"active"}\n', encoding="utf-8")
    (fixture / "logs" / "keep.log").write_text("preserve\n", encoding="utf-8")

    script = tmp_path / "invoke-clean-start.sh"
    script.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nlog() { :; }\n"
        + function_text
        + "\nreset_stale_runtime_state audit-approved-clean-start\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "HARNESS_DIR": str(fixture)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads((run_dir / "pane-hygiene.json").read_text(encoding="utf-8")) == {}
    assert not list((run_dir / "pane-leases").glob("*.json*"))
    assert not list((run_dir / "actor-leases").glob("*.json*"))
    assert (run_dir / "pane-leases" / "user-note.txt").read_text(encoding="utf-8") == "preserve\n"
    assert (run_dir / "actor-leases" / "user-note.txt").read_text(encoding="utf-8") == "preserve\n"
    assert not any((fixture / marker).exists() for marker in (
        ".pane-assignments",
        ".drafting-flow-dispatched",
        ".drafting-flow-retry",
        ".builder-flow-dispatched",
    ))
    assert (fixture / "sprints" / "keep.status.json").exists()
    assert (fixture / "logs" / "keep.log").exists()
    assert 'reset_stale_runtime_state "already-running --clean"' in source
    assert 'reset_stale_runtime_state "fresh-session"' in source


def test_approved_raw_add_has_exact_follow_up_and_does_not_auto_ingest(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts" / "autosci" / "workspace" / "wiki"
    (wiki_root / "graph").mkdir(parents=True)
    before = tmp_path / "raw-before.md"
    after = tmp_path / "raw-after.md"
    runtime = tmp_path / "runtime.json"
    allowlist = tmp_path / "allowlist.json"
    before.write_text("raw target is absent\n", encoding="utf-8")
    after.write_text("# Approved raw source\n", encoding="utf-8")
    runtime.write_text('{"status":"completed","exit_code":0,"evidence_ids":["runtime:raw-add"]}\n', encoding="utf-8")
    allowlist.write_text('{"allowed":["edit_wiki_plan"]}\n', encoding="utf-8")

    proc = _run_shim(
        tmp_path,
        "$edit",
        "raw/papers/approved-source.md",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-audit-raw-add",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "audit-approved-raw-add",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    evidence = _load_action_evidence(summary)
    change = evidence["outputs"]["changes"][0]
    assert change["follow_up"] == "Run /ingest on this raw source to register it in the research wiki."
    assert [item["action"] for item in json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"]] == ["edit_wiki_plan"]
    artifact_types = {item["type"] for item in evidence["artifacts"]}
    assert not any("ingest" in item for item in artifact_types)


def test_survey_archive_requires_explicit_approval_before_wiki_mutation(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "audit-survey",
                "status": "completed",
                "outputs": {
                    "query": "approval audit",
                    "candidates": [
                        {
                            "candidate_id": "local:audit-source",
                            "title": "Audit Source",
                            "source_ref": "fixture://audit-source",
                            "source_channels": ["references"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = _run_shim(
        tmp_path,
        "$survey",
        "topic:approval-audit",
        "--title",
        "Approval Audit Survey",
        "--discovery-evidence",
        str(discovery),
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "audit-survey-no-approval",
    )
    assert proc.returncode in {2, 3}, proc.stdout + proc.stderr
    assert not list((wiki_root / "outputs").glob("*.md")) if (wiki_root / "outputs").exists() else True
    assert not (wiki_root / "graph" / "edges.jsonl").exists()
    assert not (wiki_root / "log.md").exists()

"""Artifact manifest (Lane 3, design §1.5 / R6, AC-R6.1–6.3).

The manifest is the discovery authority on the contracted path: rows carry
{path, resolved_root, size, sha256, mtime}; sidecars are keyed by KIND (no
per-filename special cases); writes outside declared roots are reported as
ARTIFACT_ROOT_VIOLATION and block the proof gate.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import artifact_manifest as am  # noqa: E402


SID = "lane3-manifest-sprint"


def _roots(tmp_path):
    ws = tmp_path / "workspace"
    wd = tmp_path / "workdir"
    ws.mkdir(parents=True, exist_ok=True)
    wd.mkdir(parents=True, exist_ok=True)
    return {"canonical": str(ws), "workdir": str(wd)}


def _node(write_scope):
    return {"id": "S2", "write_scope": list(write_scope)}


def test_write_and_read_roundtrip_with_hashes(tmp_path):
    roots = _roots(tmp_path)
    target = Path(roots["canonical"]) / "report.md"
    target.write_text("# report\n", encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path, SID, _node(["report.md"]), generation=1, roots=roots,
    )
    assert manifest is not None
    on_disk = am.read_manifest(tmp_path, SID, "S2")
    assert on_disk["sid"] == SID
    assert on_disk["node_id"] == "S2"
    assert on_disk["generation"] == 1
    row = on_disk["rows"][0]
    assert row["declared"] == "report.md"
    assert row["resolved_root"] == "canonical"
    assert row["exists"] is True
    assert row["size"] == len("# report\n")
    assert row["sha256"] == hashlib.sha256(b"# report\n").hexdigest()
    assert row["mtime"]
    assert Path(row["path"]) == target


def test_v9_workdir_written_artifact_resolves_via_alias_root(tmp_path):
    """AC-R6.1 (v9 replay shape): declared under the canonical workspace, actually
    written under workdir/ — the manifest resolves it instead of losing it."""
    roots = _roots(tmp_path)
    stray = Path(roots["workdir"]) / "rsi-deep-research-report" / "sources.json"
    stray.parent.mkdir(parents=True)
    stray.write_text('{"sources": []}', encoding="utf-8")

    manifest = am.write_manifest(
        tmp_path, SID, _node(["rsi-deep-research-report/sources.json"]),
        generation=1, roots=roots,
    )
    row = manifest["rows"][0]
    assert row["exists"] is True
    assert row["resolved_root"] == "workdir"
    assert Path(row["path"]) == stray
    assert not manifest["violations"]


def test_v9_publish_rule_produces_canonical_copy(tmp_path):
    """AC-R6.1 second half: the publish step copies resolved artifacts into the
    canonical root so consumers get the contract-declared location."""
    roots = _roots(tmp_path)
    stray = Path(roots["workdir"]) / "rsi-deep-research-report" / "sources.json"
    stray.parent.mkdir(parents=True)
    stray.write_text('{"sources": []}', encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path, SID, _node(["rsi-deep-research-report/sources.json"]),
        generation=1, roots=roots,
    )
    copies = am.publish_canonical(manifest, roots["canonical"])
    canonical_copy = Path(roots["canonical"]) / "rsi-deep-research-report" / "sources.json"
    assert canonical_copy.exists()
    assert canonical_copy.read_text(encoding="utf-8") == '{"sources": []}'
    assert copies and copies[0]["to"] == str(canonical_copy)


def test_missing_artifact_row_reports_absent(tmp_path):
    roots = _roots(tmp_path)
    manifest = am.write_manifest(tmp_path, SID, _node(["never-written.md"]), generation=1, roots=roots)
    row = manifest["rows"][0]
    assert row["exists"] is False
    assert row["resolved_root"] == ""
    assert manifest["all_outputs_present"] is False


def test_sidecar_map_keyed_by_kind_no_filename_special_cases(tmp_path):
    """AC-R6.2: patch/handoff/eval discovery is by sidecar KIND. The consumer never
    matches filename shapes — the ff35c302/a8203924/92c5615d shapes all reduce to
    'the dispatcher hands the manifest a path under the right kind'."""
    roots = _roots(tmp_path)
    weird_patch = tmp_path / "S2-attempt2.PATCH.DIFF.txt"   # ff35c302-shaped odd name
    weird_patch.write_text("--- a\n+++ b\n", encoding="utf-8")
    handoff = tmp_path / "handoff-final-v2.md"              # a8203924-shaped synthesis name
    handoff.write_text("done", encoding="utf-8")
    eval_a = tmp_path / "eval-gen1.json"
    eval_a.write_text("{}", encoding="utf-8")

    manifest = am.write_manifest(
        tmp_path, SID, _node([]), generation=2, roots=roots,
        sidecars={
            "patch_diff": str(weird_patch),
            "handoff_md": str(handoff),
            "eval": [str(eval_a)],
            "guard_decision": str(tmp_path / "absent-guard.json"),
        },
        operator_result_ids=["mini-codex-1:task-7"],
    )
    sidecars = manifest["sidecars"]
    assert sidecars["patch_diff"]["exists"] is True
    assert sidecars["handoff_md"]["exists"] is True
    assert sidecars["eval"][0]["exists"] is True
    assert sidecars["guard_decision"]["exists"] is False
    assert manifest["operator_result_ids"] == ["mini-codex-1:task-7"]

    presence = am.presence_map(manifest)
    assert presence["patch_diff"] is True
    assert presence["handoff_md"] is True
    assert presence["eval_json"] is True
    assert presence["guard_decision"] is False


def test_write_outside_declared_roots_is_reported_and_blocks(tmp_path):
    """AC-R6.3: an observed write outside every declared root => ARTIFACT_ROOT_VIOLATION."""
    roots = _roots(tmp_path)
    inside = Path(roots["canonical"]) / "ok.md"
    inside.write_text("ok", encoding="utf-8")
    outside = tmp_path / "repo-root-stray.md"
    outside.write_text("contamination", encoding="utf-8")

    manifest = am.write_manifest(
        tmp_path, SID, _node(["ok.md"]), generation=1, roots=roots,
        observed=[str(inside), str(outside)],
    )
    assert manifest["violations"], "outside-root write must be reported"
    violation = manifest["violations"][0]
    assert violation["code"] == "ARTIFACT_ROOT_VIOLATION"
    assert violation["path"] == str(outside)
    presence = am.presence_map(manifest)
    assert presence["artifact_root_violation"] is True


def test_observed_writes_inside_roots_are_clean(tmp_path):
    roots = _roots(tmp_path)
    inside = Path(roots["workdir"]) / "sub" / "ok.md"
    inside.parent.mkdir(parents=True)
    inside.write_text("ok", encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path, SID, _node([]), generation=1, roots=roots, observed=[str(inside)],
    )
    assert manifest["violations"] == []
    assert am.presence_map(manifest)["artifact_root_violation"] is False


def test_relative_roots_anchor_at_base_dir_not_cwd(tmp_path):
    """P2 smoke 20260707T190540Z (S1 failed_review): code.cli_smoke declares
    RELATIVE roots (sprints/<sid>/workdir/). The builder wrote the file — it
    existed at <HARNESS_DIR>/sprints/<sid>/workdir/uniqwords.py — but the
    manifest resolved the relative path against the process CWD, looked in the
    wrong place, and reported every output missing. Relative roots and declared
    paths must anchor at base_dir (HARNESS_DIR), never the CWD."""
    sid = "sprint-x-wf-code-cli-smoke"
    harness = tmp_path / "harness"
    real = harness / "sprints" / sid / "workdir" / "uniqwords.py"
    real.parent.mkdir(parents=True)
    real.write_text("print('hi')\n", encoding="utf-8")

    manifest = am.write_manifest(
        harness / "sprints", sid,
        {"id": "S1", "write_scope": [f"sprints/{sid}/workdir/uniqwords.py"]},
        generation=0,
        roots={"canonical": f"sprints/{sid}/workdir/"},
        base_dir=harness,
    )
    row = manifest["rows"][0]
    assert row["exists"] is True, row
    assert row["resolved_root"] == "canonical"
    assert Path(row["path"]) == real
    assert manifest["all_outputs_present"] is True


def test_relative_declared_with_root_prefix_not_double_joined(tmp_path):
    """A declared path that already includes the relative root prefix must not
    be joined onto the root a second time (…/workdir/sprints/…)."""
    sid = "sprint-y-wf-code-cli-smoke"
    harness = tmp_path / "harness"
    real = harness / "sprints" / sid / "workdir" / "README.md"
    real.parent.mkdir(parents=True)
    real.write_text("# r\n", encoding="utf-8")
    manifest = am.write_manifest(
        harness / "sprints", sid,
        {"id": "S1", "write_scope": [f"sprints/{sid}/workdir/README.md"]},
        generation=0,
        roots={"canonical": f"sprints/{sid}/workdir/"},
        base_dir=harness,
    )
    assert manifest["rows"][0]["exists"] is True
    assert "workdir/sprints" not in manifest["rows"][0]["path"]


def test_observed_writes_anchor_at_base_dir_for_violations(tmp_path):
    """Observed relative paths get the same anchoring before the root check."""
    sid = "sprint-z"
    harness = tmp_path / "harness"
    inside = harness / "sprints" / sid / "workdir" / "ok.md"
    inside.parent.mkdir(parents=True)
    inside.write_text("ok", encoding="utf-8")
    manifest = am.write_manifest(
        harness / "sprints", sid, {"id": "S1", "write_scope": []},
        generation=0,
        roots={"canonical": f"sprints/{sid}/workdir/"},
        observed=[f"sprints/{sid}/workdir/ok.md", "stray-at-base.md"],
        base_dir=harness,
    )
    codes = [v["code"] for v in manifest["violations"]]
    assert codes == [am.ARTIFACT_ROOT_VIOLATION], manifest["violations"]
    assert "stray-at-base.md" in manifest["violations"][0]["path"]


def test_absolute_roots_unaffected_by_base_dir(tmp_path):
    roots = _roots(tmp_path)
    target = Path(roots["canonical"]) / "r.md"
    target.write_text("x", encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path, SID, _node(["r.md"]), generation=1, roots=roots,
        base_dir=tmp_path / "elsewhere",
    )
    assert manifest["rows"][0]["exists"] is True
    assert manifest["rows"][0]["resolved_root"] == "canonical"


def test_manifest_write_is_atomic_and_best_effort(tmp_path):
    # Unwritable sprints dir: returns None, never raises.
    import os
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    os.chmod(blocked, 0o500)
    try:
        out = am.write_manifest(blocked / "sub", SID, _node([]), generation=1, roots={})
        assert out is None
    finally:
        os.chmod(blocked, 0o700)


def test_read_manifest_missing_returns_empty(tmp_path):
    assert am.read_manifest(tmp_path, SID, "nope") == {}


# ---------------------------------------------------------------------------
# Dispatcher consult — the manifest replaces filename-shape scans on the
# contracted path (design §1.5 consumers: _proof_artifact_presence)
# ---------------------------------------------------------------------------

import graph_node_dispatcher as gnd  # noqa: E402


@pytest.fixture()
def dispatcher_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    return tmp_path


def test_proof_presence_consults_manifest_over_filename_scan(dispatcher_sandbox, tmp_path):
    """A patch sidecar with an ff35c302-shaped odd filename is invisible to the
    legacy scan but present via the manifest's kind-keyed sidecar map."""
    weird_patch = tmp_path / "S2-attempt2.PATCH.DIFF.txt"
    weird_patch.write_text("--- a\n+++ b\n", encoding="utf-8")
    am.write_manifest(
        dispatcher_sandbox, SID, {"id": "S2", "write_scope": []}, generation=1,
        roots={}, sidecars={"patch_diff": str(weird_patch)},
    )
    node = {"id": "S2"}
    presence = gnd._proof_artifact_presence(SID, node)
    assert presence["patch_diff"] is True, "manifest sidecar must satisfy patch presence"


def test_proof_presence_without_manifest_unchanged(dispatcher_sandbox):
    node = {"id": "S9"}
    presence = gnd._proof_artifact_presence(SID, node)
    assert presence["patch_diff"] is False
    assert "artifact_root_violation" not in presence


def test_root_violation_blocks_proof_obligations(dispatcher_sandbox, tmp_path):
    """AC-R6.3 end-to-end at the gate: a manifest with an outside-root write fails
    the node's proof obligations with ARTIFACT_ROOT_VIOLATION."""
    roots = {"canonical": str(tmp_path / "ws")}
    (tmp_path / "ws").mkdir()
    outside = tmp_path / "stray.md"
    outside.write_text("x", encoding="utf-8")
    am.write_manifest(
        dispatcher_sandbox, SID, {"id": "S2", "write_scope": []}, generation=1,
        roots=roots, observed=[str(outside)],
    )
    node = {
        "id": "S2",
        "proof_obligations": [
            {"kind": "pass_condition", "requirement": "output_present", "field": "handoff_md"},
        ],
    }
    gate = gnd._evaluate_proof_obligations(SID, node)
    assert gate["required"] is True
    assert gate["ok"] is False
    reasons = {item.get("reason") for item in gate["missing"]}
    assert "ARTIFACT_ROOT_VIOLATION" in reasons


def test_flag_off_never_consults_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    weird_patch = tmp_path / "S2.PATCH.odd"
    weird_patch.write_text("--- a\n", encoding="utf-8")
    am.write_manifest(
        tmp_path, SID, {"id": "S2", "write_scope": []}, generation=1,
        roots={}, sidecars={"patch_diff": str(weird_patch)},
    )
    presence = gnd._proof_artifact_presence(SID, {"id": "S2"})
    assert presence["patch_diff"] is False, "flag-off must keep the legacy filename scan"

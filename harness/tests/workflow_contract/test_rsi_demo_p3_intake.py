#!/usr/bin/env python3
"""P3 pre-live blocker replays — rsi_demo must be intakeable and its gate
commands fully specified (found by the P3 deterministic rehearsal, 2026-07-08).

Blocker 1: contracted intake of research.deepdive.rsi_demo failed closed with
UNRESOLVED_PLACEHOLDERS ['resolved_root'] — the contract's validator_command
carries `<resolved_root>` and nothing supplied it. Author intent (readable
from `validate_rsi_demo_report.py`, whose ROOT constant is the artifact dir
basename and which checks `rsi-deep-research-report/` under --workspace):
resolved_root = the RESOLVED WORKSPACE dir that CONTAINS the canonical
artifact dir, i.e. the canonical root's parent. instantiate() now derives it
from artifact_roots.canonical and adds it to the substitution table.

Blocker 2 (contract v1.0 -> v1.1): the D2 gate command named a flag that does
not exist (`research eval-artifacts --sources` — argparse would exit 2), D3's
eval-artifacts had no --eval-json (a REQUIRED flag), and D6's stage command
diverged from the top-level validator_command (no --workspace). v1.1 pins:
D2 -> `research source-audit --output-dir ... --json`, D3 -> eval-artifacts
with an explicit --eval-json under the canonical root, D6 -> the
validator_command form. The executor that RUNS these gates is a separate
seam; these tests pin the contract/instantiation layer only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import workflow_contract as wc  # noqa: E402
import workflow_intake as wi  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
WF = "research.deepdive.rsi_demo"


@pytest.fixture()
def contract():
    found = wc.find_contract(WF, WORKFLOWS_DIR)
    assert found is not None
    return found


def test_contracted_intake_succeeds(tmp_path):
    """The rehearsal's exact red: UNRESOLVED_PLACEHOLDERS ['resolved_root']."""
    res = wi.create_contract_sprint(
        workflow_id=WF,
        request="Bounded RSI demo: reliability of LLM-based code review",
        workspace_root=str(tmp_path / "ws"),
        sprints_dir=tmp_path / "sprints",
        workflows_dir=WORKFLOWS_DIR,
    )
    sid = str(res.get("sprint_id") or res.get("sid") or "")
    assert sid, res
    graph_path = tmp_path / "sprints" / f"{sid}.task_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert graph.get("workflow_contract_id") == WF
    assert [n["id"] for n in graph["nodes"]] == ["D1", "D2", "D3", "D4", "D5", "D6"]
    leftover = sorted(set(__import__("re").findall(r"<([a-z_][a-z0-9_]*)>", json.dumps(graph))))
    assert leftover == [], f"unresolved placeholders in instantiated graph: {leftover}"


def test_resolved_root_is_canonical_parent(contract):
    # v1.3: the canonical root anchors at the node WORKDIR (the P2-proven
    # anchor builders actually write under — live run 2 proved they resolve
    # relative roots against their workdir, and $HARNESS/workspace never
    # existed, so the D3 gate hit WORKSPACE_UNREACHABLE while artifacts sat
    # at sprints/<sid>/workdir/...). resolved_root = the workdir.
    graph = wc.instantiate(contract, {"sprint_id": "p3-sub-probe", "sid": "p3-sub-probe"})
    cmd = str(graph.get("validator_command") or "")
    assert "<resolved_root>" not in cmd
    assert "--workspace sprints/p3-sub-probe/workdir" in cmd, cmd


def test_gate_commands_are_executable_shapes(contract):
    """v1.1 contract: every deterministic gate command must name real flags."""
    graph = wc.instantiate(contract, {"sprint_id": "p3-cmd-probe", "sid": "p3-cmd-probe"})
    gates = {n["id"]: (n.get("evaluator_gate") or {}) for n in graph["nodes"]}
    d2 = str(gates["D2"].get("command") or "")
    # v1.3: `research source-audit` is VACUOUS on a missing/empty dir
    # (ok:true, source_count:0, exit 0 — live run 2 "passed" D2 against a
    # directory that did not exist). The demo validator's --sources-only mode
    # actually fails on missing dir / too-few sources.
    assert d2.startswith("python3 scripts/validate_rsi_demo_report.py "), d2
    assert d2.endswith("--sources-only"), d2
    d3 = str(gates["D3"].get("command") or "")
    # v1.2: the bounded seed-pack demo gates D3 on the deterministic
    # claims/linkage validator — `research eval-artifacts` fundamentally needs
    # a NATIVE engine run's research_eval.json (build_research_eval_payload is
    # sqlite-backed), which the seed-pack demo path does not produce; the
    # native gate remains the engine-native path's gate (P4+/AutoSci).
    assert d3 == "python3 scripts/validate_rsi_demo_report.py --workspace sprints/p3-cmd-probe/workdir --claims-only", d3
    d6 = str(gates["D6"].get("command") or "")
    assert d6 == str(graph.get("validator_command") or ""), (
        "D6 stage gate must match the contract-level validator_command"
    )
    for nid in ("D2", "D3", "D6"):
        assert "<" not in str(gates[nid].get("command") or "")


def test_gate_kinds_unchanged_by_amendment(contract):
    kinds = {s["id"]: (s.get("evaluator_gate") or {}).get("kind", "none") for s in contract["stages"]}
    assert kinds == {
        "D1": "none",
        "D2": "deterministic_command",
        "D3": "deterministic_command",
        "D4": "none",
        "D5": "llm_eval",
        "D6": "deterministic_command",
    }


def test_forbidden_block_survives_amendment(contract):
    forbidden = contract.get("forbidden") or {}
    assert "cap.requirement-compiler-implementation" in (forbidden.get("capsules") or [])


def test_cli_smoke_goldens_unaffected_by_resolved_root():
    """resolved_root is derived for every contract; the P2 contracts must
    instantiate byte-identically (they never reference the token)."""
    goldens = Path(__file__).resolve().parent / "goldens"
    inputs = {"sid": "golden-sid", "sprint_id": "sprint-golden", "tool": "wordfreq"}
    for wf_id in ("code.cli_smoke", "code.cli_smoke_anthropic"):
        contract = wc.find_contract(wf_id, WORKFLOWS_DIR)
        produced = wc.canonical_graph_json(wc.instantiate(contract, dict(inputs)))
        golden = (goldens / f"{wf_id}.instantiated.golden.json").read_text(encoding="utf-8")
        assert produced == golden, f"{wf_id} drifted — resolved_root must be inert for P2 contracts"


# ---------------------------------------------------------------------------
# v1.2 — the demo has CONTENT: authored stage goals + shipped seed pack
# (P3 live run 1: every D-stage had an EMPTY goal and the seed pack did not
# exist, so builders improvised hand-written JSON that the D3 gate rightly
# refused — Turing/STaR/Reflexion boilerplate, research_eval_json_missing.)
# ---------------------------------------------------------------------------

SEED_PACK = _HARNESS / "demo-rsi" / "source-pack"


def test_seed_pack_ships_inside_the_harness_tree():
    """inputs.seed_pack must resolve under the harness root (installed and
    sandboxed harnesses copy harness/** only — a repo-root pack never ships)."""
    assert (SEED_PACK / "sources.json").is_file()
    notes = sorted(p.name for p in (SEED_PACK / "source-notes").glob("*.md"))
    assert len(notes) >= 9, notes
    pack = json.loads((SEED_PACK / "sources.json").read_text(encoding="utf-8"))
    rows = pack if isinstance(pack, list) else pack.get("sources", [])
    assert len(rows) >= 9
    for row in rows:
        assert row.get("id") and row.get("title") and row.get("citation_hint"), row


def test_every_stage_has_an_authored_goal(contract):
    for stage in contract["stages"]:
        goal = str(stage.get("goal") or "").strip()
        assert len(goal) > 80, f"{stage['id']} goal is empty/thin: {goal!r}"
    # the evidence stages must anchor builders to the seed pack, not the web
    for sid_ in ("D1", "D2", "D3"):
        stage = next(s for s in contract["stages"] if s["id"] == sid_)
        assert "demo-rsi/source-pack" in stage["goal"], sid_


def test_d3_gate_is_the_claims_only_validator(contract):
    d3 = next(s for s in contract["stages"] if s["id"] == "D3")
    cmd = str((d3.get("evaluator_gate") or {}).get("command") or "")
    assert cmd == "python3 scripts/validate_rsi_demo_report.py --workspace <resolved_root> --claims-only", cmd
    canonical = str((contract.get("artifact_roots") or {}).get("canonical") or "")
    assert canonical == "sprints/<sid>/workdir/rsi-deep-research-report/", canonical


def test_claims_only_validator_red_green(tmp_path):
    """The D3 gate command itself: green on linked claims, red on boilerplate
    with dangling source ids (the live failure shape)."""
    import subprocess, sys as _sys
    ws = tmp_path / "ws"
    root = ws / "rsi-deep-research-report"
    root.mkdir(parents=True)
    sources = [{"id": f"s{i}", "title": f"T{i}", "citation_hint": f"C{i}"} for i in range(6)]
    claims = [{"claim_id": f"c{i}", "source_id": f"s{i % 6}", "claim_text": f"claim {i}"} for i in range(12)]
    (root / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    (root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    validator = _HARNESS / "scripts" / "validate_rsi_demo_report.py"
    green = subprocess.run(
        [_sys.executable, str(validator), "--workspace", str(ws), "--claims-only"],
        capture_output=True, text=True,
    )
    assert green.returncode == 0, green.stdout + green.stderr
    # red: a claim citing a source that does not exist (boilerplate shape)
    claims.append({"claim_id": "c99", "source_id": "turing1950", "claim_text": "boilerplate"})
    (root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    red = subprocess.run(
        [_sys.executable, str(validator), "--workspace", str(ws), "--claims-only"],
        capture_output=True, text=True,
    )
    assert red.returncode != 0
    assert "LINKAGE" in (red.stdout + red.stderr)


def test_sources_only_validator_red_green(tmp_path):
    """The v1.3 D2 gate: fails on a MISSING workspace (the source-audit
    vacuity contrast) and on too-few sources; passes on a faithful pack set."""
    import subprocess, sys as _sys
    validator = _HARNESS / "scripts" / "validate_rsi_demo_report.py"
    missing = subprocess.run(
        [_sys.executable, str(validator), "--workspace", str(tmp_path / "nope"), "--sources-only"],
        capture_output=True, text=True)
    assert missing.returncode != 0
    assert "WORKSPACE_UNREACHABLE" in (missing.stdout + missing.stderr)
    ws = tmp_path / "ws"
    root = ws / "rsi-deep-research-report"
    root.mkdir(parents=True)
    (root / "sources.json").write_text(json.dumps(
        [{"id": f"s{i}", "title": f"T{i}", "citation_hint": f"C{i}"} for i in range(6)]), encoding="utf-8")
    green = subprocess.run(
        [_sys.executable, str(validator), "--workspace", str(ws), "--sources-only"],
        capture_output=True, text=True)
    assert green.returncode == 0, green.stdout + green.stderr
    (root / "sources.json").write_text(json.dumps([{"id": "s1", "title": "T", "citation_hint": "C"}]), encoding="utf-8")
    few = subprocess.run(
        [_sys.executable, str(validator), "--workspace", str(ws), "--sources-only"],
        capture_output=True, text=True)
    assert few.returncode != 0
    assert "TOO_FEW_SOURCES" in (few.stdout + few.stderr)

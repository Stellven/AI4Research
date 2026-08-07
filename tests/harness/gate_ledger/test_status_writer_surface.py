"""AC-R4.3 — the status-writer surface (review round-1 finding 3.1 / C4 list;
widened repo-wide by round-4 G3).

Two halves:

1. Source audit: every node-status assignment (and node_results mutation) in
   ANY module under harness/lib must live inside an allowlisted function, and
   every "ledger"-mode writer must report through the gate-ledger seam. The
   scan is repo-wide so the NEXT hidden writer fails this suite; the allowlist
   is explicit per file+function with a reason for every exemption.

2. Runtime property (SOLAR_GATE_LEDGER=1, sandboxed SPRINTS_DIR): no status
   transition without a ledger record; suppressed rank-guard writes record
   nothing; terminal absorbing = no exit without an applied audited record;
   doctor_graph is neutralized on the contracted path (applied=false records,
   no direct status); the pool/research/evolution reopens record; flag-off
   writes leave no ledger file.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Source audit — the writer surface is repo-wide (round-4 G3)
# ---------------------------------------------------------------------------

# The audited writer surface, keyed by path relative to harness/lib. Modes:
#   "ledger"  — the function must contain a gate-ledger recording call
#               (_ledger_transition/_gs_ledger_transition/_doctor_write_suppressed).
#   anything else — a documented exemption; the string IS the reason and must
#               say why no record is required (loader / derived view / not the
#               task graph). An empty reason fails the audit.
AUDITED_WRITERS: dict[str, dict[str, str]] = {
    "graph_scheduler.py": {
        "_attach_runtime_planes": "loader: rehydrates already-recorded state from disk on graph load",
        "mark_node_result": "ledger",
        "set_node_status": "ledger",
        "doctor_graph": "ledger",
        "enter_node_human_review": "ledger",
        "commit_human_review_resume": "ledger",
    },
    "graph_node_dispatcher.py": {
        "_prepare_human_search_handoff": "ledger",
        "_start_node_repair_from_eval_fail": "ledger",
        "_reconcile_existing_dispatches": "ledger",
        # rc.9 operator-completion fence: terminal failed asynchronous workers
        # move reviewing -> pending for a clean retry.  The rank guard in
        # set_node_status intentionally refuses that backwards transition, so
        # this helper records _ledger_transition immediately before the direct
        # reset and remains an explicitly audited writer.
        "_requeue_node_after_operator_closeout": "ledger",
        "_mark_graph_node": "ledger",
        "dispatch_node_evals": "ledger",
        "node_verdict": (
            "recorded via mark_node_result: the inline write repeats the "
            "same-status force-write mark_node_result just recorded"
        ),
    },
    "multi_task_runner.py": {
        "recover_quota_failed_nodes": "ledger",
    },
    "research/cli.py": {
        "_enqueue_source_audit_followup": "ledger",
    },
    "evolution_engine.py": {
        "repair_deepresearch_gates": "ledger",
        "restore_nonrequired_deepresearch_repairs": "ledger",
    },
    "task_graph_io.py": {
        "compile_mirror": (
            "false positive: builds a compat MIRROR dict (merged = dict(node)) "
            "from already-recorded node_results; never mutates the live graph"
        ),
        "backfill_state_from_legacy": (
            "loader: extracts already-recorded inline/node_results status into "
            "the state plane during migration; not a transition"
        ),
    },
    "task_graph_state_io.py": {
        "backfill_state_from_legacy": (
            "loader: extracts already-recorded inline/node_results status into "
            "the state plane during migration; not a transition"
        ),
    },
    "compat/legacy_adapter.py": {
        "dispatch": (
            "false positive: writes the sprint status.json projection payload, "
            "not the task-graph node status"
        ),
    },
    "epic_projection_closeout.py": {
        "_sync_graph_from_children": (
            "epic projection: mirrors CHILD SPRINT status files into the "
            "epic-level graph (derived view; epic graphs carry no "
            "workflow_contract_id — off the contracted sprint-graph scope)"
        ),
    },
    "hf_s03_core_runtime_closeout.py": {
        "auto_closeout_hf_s03_nodes": (
            "false positive: a LOCAL result-collection dict named node_results; "
            "the graph write goes through acceptance_closeout."
            "auto_closeout_graph_nodes -> the audited node_verdict seam"
        ),
    },
    "understand_anything_operator_productization_closeout.py": {
        "auto_closeout_understand_anything_operator_productization": (
            "false positive: a LOCAL result-collection dict named node_results; "
            "the graph write goes through acceptance_closeout."
            "auto_closeout_graph_nodes -> the audited node_verdict seam"
        ),
    },
    "epic_decomposer.py": {
        "sync_graph_from_children": (
            "epic projection: mirrors child sprint status into the epic-level "
            "graph (derived view, off the contracted sprint-graph scope)"
        ),
        "activate_ready": (
            "epic-level activation write on the epic graph's child-sprint "
            "pointer nodes; epic graphs are off the contracted sprint-graph "
            "scope — recording them is the epic lane's follow-up (see "
            "docs/product/lane3-spec-mismatches.md D10)"
        ),
    },
}

# Receiver-filtered node-status assignment. Documented bound: receivers must
# look like a graph node (node/nodes[...]/live/ids[...]/merged) — a writer that
# aliases a node dict to an unrelated name evades the regex; the allowlist
# review is the human backstop.
_NODE_STATUS_WRITE = re.compile(
    r'(?:\bnode|\bnodes\[[^\]]*\]|\blive|\bids\[[^\]]*\]|\bmerged)'
    r'\[["\']status["\']\]\s*=[^=]'
)
# node_results mutations change effective status (node_status folds them) —
# assignments, pops, and nested status writes all count (round-4 G3).
_NODE_RESULTS_MUTATION = re.compile(
    r'(?:\[["\']node_results["\']\]|\bnode_results)\s*'
    r'(?:\.pop\(|\[[^\]]+\]\s*(?:=[^=]|\.pop\(|\[["\']status["\']\]\s*=[^=]))'
)

_LEDGER_CALL_MARKERS = ("_ledger_transition(", "_doctor_write_suppressed(")


def _lib_python_files() -> list[Path]:
    return sorted(
        p for p in (_HARNESS / "lib").rglob("*.py")
        if "__pycache__" not in p.parts
    )


def _status_writer_functions(path: Path) -> dict[str, list[int]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
        spans = [
            (fn.lineno, fn.end_lineno or fn.lineno, fn.name)
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    except SyntaxError:
        spans = []  # hits attribute to <module> and fail the audit loudly
    writers: dict[str, list[int]] = {}
    matches = list(_NODE_STATUS_WRITE.finditer(src)) + list(_NODE_RESULTS_MUTATION.finditer(src))
    for match in matches:
        lineno = src[: match.start()].count("\n") + 1
        enclosing = [name for (a, b, name) in spans if a <= lineno <= b]
        name = enclosing[-1] if enclosing else "<module>"
        writers.setdefault(name, []).append(lineno)
    return writers


def _function_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == name:
            return ast.get_source_segment(src, fn) or ""
    return ""


def test_no_status_write_outside_audited_surface_repo_wide():
    """Every node-status write / node_results mutation under harness/lib must
    be allowlisted. This is the round-4 G3 teeth: the next hidden writer in ANY
    module fails here, not just in the two original files."""
    unaudited: dict[str, dict[str, list[int]]] = {}
    for path in _lib_python_files():
        rel = path.relative_to(_HARNESS / "lib").as_posix()
        writers = _status_writer_functions(path)
        if not writers:
            continue
        allowed = AUDITED_WRITERS.get(rel, {})
        extra = {name: lines for name, lines in writers.items() if name not in allowed}
        if extra:
            unaudited[rel] = extra
    assert not unaudited, (
        f"node-status writes outside the audited surface: {unaudited}. "
        "Route the write through set_node_status/mark_node_result, or add a "
        "gate-ledger recording call and extend AUDITED_WRITERS deliberately "
        "(with a reason string if no record is required)."
    )


@pytest.mark.parametrize("filename", sorted(AUDITED_WRITERS))
def test_every_audited_writer_reports_to_the_ledger(filename):
    path = _HARNESS / "lib" / filename
    for name, mode in AUDITED_WRITERS[filename].items():
        if mode != "ledger":
            continue
        body = _function_source(path, name)
        assert body, f"{filename}: audited writer {name} not found"
        assert any(marker in body for marker in _LEDGER_CALL_MARKERS), (
            f"{filename}:{name} writes node status but never reports to the gate ledger"
        )


def test_every_exemption_carries_a_reason():
    for filename, entries in AUDITED_WRITERS.items():
        for name, mode in entries.items():
            if mode == "ledger":
                continue
            assert len(str(mode).strip()) >= 20, (
                f"{filename}:{name} is exempted without a substantive reason"
            )


def test_audited_surface_matches_reality():
    """The allowlist itself may not go stale: every listed writer must still write."""
    for filename, expected in AUDITED_WRITERS.items():
        writers = _status_writer_functions(_HARNESS / "lib" / filename)
        for name in expected:
            assert name in writers, (
                f"{filename}: {name} is allowlisted but no longer writes node status — prune it"
            )


# ---------------------------------------------------------------------------
# 2. Runtime property
# ---------------------------------------------------------------------------

SID = "lane3-property"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    return tmp_path


def _graph(contracted: bool = False) -> dict:
    graph = {
        "sprint_id": SID,
        "nodes": [
            {"id": "S1", "status": "pending", "depends_on": []},
            {"id": "S2", "status": "pending", "depends_on": ["S1"]},
        ],
        "node_results": {},
        "gate_results": {},
    }
    if contracted:
        graph["workflow_contract_id"] = "code.cli_smoke"
    return graph


def _transitions(tmp_path, node_id=None):
    return gl.read_records(tmp_path, SID, node_id=node_id, kind="status_transition")


def test_set_node_status_records_every_applied_write(sandbox):
    graph = _graph()
    gs.set_node_status(graph, "S1", "assigned")
    gs.set_node_status(graph, "S1", "running")
    rows = _transitions(sandbox, "S1")
    assert [(r["from_status"], r["to_status"]) for r in rows] == [
        ("pending", "assigned"), ("assigned", "running"),
    ]
    assert all(r["writer"] == "set_node_status" for r in rows)
    assert gl.project_node_status(sandbox, SID, "S1") == gs.node_status(graph, "S1") == "running"


def test_rank_guard_suppressed_write_records_nothing(sandbox):
    graph = _graph()
    gs.set_node_status(graph, "S1", "reviewing")
    before = len(_transitions(sandbox, "S1"))
    gs.set_node_status(graph, "S1", "queued")  # rank 1 < reviewing 4: refused
    assert gs.node_status(graph, "S1") == "reviewing"
    assert len(_transitions(sandbox, "S1")) == before


def test_mark_node_result_records_forced_write(sandbox):
    graph = _graph()
    gs.set_node_status(graph, "S1", "reviewing")
    gs.mark_node_result(graph, "S1", "failed", note="eval FAIL")
    rows = _transitions(sandbox, "S1")
    assert rows[-1]["writer"] == "mark_node_result"
    assert (rows[-1]["from_status"], rows[-1]["to_status"]) == ("reviewing", "failed")
    assert gl.project_node_status(sandbox, SID, "S1") == "failed"


def test_terminal_statuses_absorbing_in_projection(sandbox):
    """Absorbing = no exit from terminal without an APPLIED audited record
    (round-4 G6 semantics): unapplied would-be writes never project; a real
    applied record — scheduler or human — always does."""
    graph = _graph()
    gs.mark_node_result(graph, "S1", "failed")
    # A neutralized (applied=False) post-terminal write is recorded but not projected.
    gl.record_status_transition(sandbox, SID, "S1", from_status="failed", to_status="pending",
                                author_type="scheduler", writer="test_force", applied=False)
    assert gl.project_node_status(sandbox, SID, "S1") == "failed"
    # An APPLIED post-terminal record projects — the writer really performed it.
    gl.record_status_transition(sandbox, SID, "S1", from_status="failed", to_status="pending",
                                author_type="scheduler", writer="recover_quota_failed_nodes")
    assert gl.project_node_status(sandbox, SID, "S1") == "pending"
    # A human-authored reopen is projected.
    gl.record_status_transition(sandbox, SID, "S1", from_status="pending", to_status="reviewing",
                                author_type="human", writer="human_verdict")
    assert gl.project_node_status(sandbox, SID, "S1") == "reviewing"


def test_mark_graph_node_records_transition(sandbox, tmp_path):
    graph_path = tmp_path / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    assert gnd._mark_graph_node(str(graph_path), "S1", "dispatched", pane="operator-pool:x", dispatch_id="d1")
    rows = _transitions(sandbox, "S1")
    assert rows and rows[-1]["writer"] == "_mark_graph_node"
    assert rows[-1]["to_status"] == "dispatched"


def test_doctor_neutralized_on_contracted_path(sandbox):
    graph = _graph(contracted=True)
    # Manufacture drift: inline passed vs node_results failed, no timestamps.
    graph["nodes"][0]["status"] = "passed"
    graph["node_results"]["S1"] = {"status": "failed", "updated_at": ""}
    report = gs.doctor_graph(graph, repair=True)
    # No direct status write happened...
    assert graph["nodes"][0]["status"] == "passed"
    assert graph["node_results"]["S1"]["status"] == "failed"
    assert not report["repairs"]
    assert report.get("suppressed"), "doctor would-be writes must surface as suppressed records"
    # ...and the would-be write exists as a non-applied doctor record.
    rows = [r for r in _transitions(sandbox, "S1") if r.get("applied") is False]
    assert rows and rows[-1]["author"]["type"] == "doctor"
    assert gl.is_gate_consumable(rows[-1]) is False


def test_doctor_still_repairs_off_contract_and_records(sandbox):
    graph = _graph(contracted=False)
    graph["nodes"][0]["status"] = "passed"
    graph["node_results"]["S1"] = {"status": "failed", "updated_at": ""}
    report = gs.doctor_graph(graph, repair=True)
    assert report["repairs"], "legacy (uncontracted) doctor repair must keep working"
    rows = _transitions(sandbox, "S1")
    assert rows and rows[-1]["author"]["type"] == "doctor"
    assert rows[-1].get("applied") is not False


def test_quota_fallback_reopen_records(sandbox, tmp_path, monkeypatch):
    """Round-4 G3 (reviewer probe): multi_task_runner's quota-fallback reopen
    (terminal failed -> pending + node_results pop) must leave a ledger record."""
    import multi_task_runner as mtr

    monkeypatch.setattr(mtr, "load_profiles", lambda: {"profiles": {"p1": {}, "p2": {}}})
    monkeypatch.setattr(mtr, "output_log_failure_kind", lambda tid: "quota_exhausted")
    monkeypatch.setattr(mtr, "read_task_status", lambda path: {"profile": "p1"})
    monkeypatch.setattr(mtr, "normalize_profile_name", lambda name, profiles: str(name or ""))
    monkeypatch.setattr(mtr, "select_quota_fallback_profile", lambda node, prof, profiles: "p2")

    sid = "lane3-mtr-reopen"
    graph = {"sprint_id": sid,
             "workflow_contract_id": "research.deepdive.rsi_demo",
             "nodes": [{"id": "S1", "status": "failed", "depends_on": [],
                        "dispatch_id": "d-1", "updated_at": "2026-07-07T00:00:00Z"}],
             "node_results": {"S1": {"status": "failed", "updated_at": "2026-07-07T00:00:00Z"}},
             "gate_results": {}}
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    changed = mtr.recover_quota_failed_nodes(graph_path, graph)
    assert changed == 1
    assert graph["nodes"][0]["status"] == "pending"
    rows = gl.read_records(sandbox, sid, node_id="S1", kind="status_transition")
    assert rows, "the quota-fallback reopen must record a status transition"
    assert rows[-1]["writer"] == "recover_quota_failed_nodes"
    assert (rows[-1]["from_status"], rows[-1]["to_status"]) == ("failed", "pending")
    assert gl.project_node_status(sandbox, sid, "S1") == "pending"


def test_source_audit_followup_reopen_records(sandbox, tmp_path, monkeypatch):
    """Round-4 G3 (reviewer probe): research/cli's source-audit followup reopen
    of a TERMINAL node must leave a ledger record."""
    from research import cli as rcli

    # _sync_harness_runtime_paths mutates gs globals from env — pin env to the
    # sandbox and register restorations so the mutation cannot leak.
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(tmp_path))
    monkeypatch.setattr(gs, "HARNESS_DIR", gs.HARNESS_DIR)
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gs, "STATE_DB", gs.STATE_DB)
    try:
        import task_queue
        for attr in ("HARNESS_DIR", "QUEUE_DIR", "LEASE_DIR"):
            monkeypatch.setattr(task_queue, attr, getattr(task_queue, attr))
    except Exception:
        pass

    sid = "lane3-rcli-reopen"
    node_id = "R_SOURCE_AUDIT_FOLLOWUP"
    graph = {"sprint_id": sid,
             "workflow_contract_id": "research.deepdive.rsi_demo",
             "nodes": [{"id": node_id, "status": "passed", "depends_on": [],
                        "updated_at": "2026-07-07T00:00:00Z"}],
             "node_results": {}, "gate_results": {}}
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    monkeypatch.setattr(rcli, "_source_gap_node",
                        lambda args, payload: {"id": node_id, "status": "pending",
                                               "depends_on": [], "task_type": "research"})
    import argparse
    args = argparse.Namespace(graph=str(graph_path), output_dir=str(tmp_path),
                              ttl=900, dry_run=True, pane="dry-run:0.0")
    followup = rcli._enqueue_source_audit_followup(
        args, {"handoff_path": str(tmp_path / "handoff.md"), "output_dir": str(tmp_path)})
    assert followup.get("ok") is True, followup
    assert followup.get("action") == "updated"

    rows = gl.read_records(tmp_path, sid, node_id=node_id, kind="status_transition")
    assert rows, "the terminal-node followup reopen must record a status transition"
    assert rows[-1]["writer"] == "_enqueue_source_audit_followup"
    assert (rows[-1]["from_status"], rows[-1]["to_status"]) == ("passed", "pending")


def test_evolution_quality_gate_reopen_records(sandbox, tmp_path, monkeypatch):
    """Round-4 G3 widened-scan writer: evolution_engine's quality-gate debt
    sweep reopens terminal research nodes — it must record too."""
    import evolution_engine as ee

    monkeypatch.setattr(ee, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(ee, "EVENTS_FILE", tmp_path / "events.jsonl")
    sid = "sprint-lane3-evo"
    graph = {"sprint_id": sid,
             "workflow_contract_id": "research.deepdive.rsi_demo",
             "nodes": [{"id": "R1", "status": "passed", "depends_on": [],
                        "research_quality_gate_required": True}],
             "node_results": {"R1": {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}},
             "gate_results": {}}
    (tmp_path / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")

    report = ee.repair_deepresearch_gates(apply=True)
    assert report["repaired"], report
    rows = gl.read_records(tmp_path, sid, node_id="R1", kind="status_transition")
    assert rows, "the evolution-engine reopen must record a status transition"
    assert rows[-1]["writer"] == "repair_deepresearch_gates"
    assert rows[-1]["to_status"] == "reviewing"
    assert rows[-1]["author"]["type"] == "policy"


def test_flag_off_writes_no_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
    graph = _graph()
    gs.set_node_status(graph, "S1", "running")
    gs.mark_node_result(graph, "S1", "passed")
    assert gs.node_status(graph, "S1") == "passed"
    assert not list(Path(tmp_path).glob("*.gate-ledger.jsonl"))

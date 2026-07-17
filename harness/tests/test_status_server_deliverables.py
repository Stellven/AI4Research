from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
STATUS_SERVER = HARNESS_ROOT / "lib" / "symphony" / "status-server.py"


def _load_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    reports = harness / "reports"
    sprints.mkdir(parents=True)
    reports.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location(
        f"status_server_deliverables_{time.time_ns()}", STATUS_SERVER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HARNESS_DIR = harness
    module.SPRINTS_DIR = sprints
    module.REPORTS_DIR = reports
    return module, harness, sprints


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_canonical_workdir_outputs_are_visible_without_exposing_cache_or_symlink_escape(
    tmp_path: Path,
) -> None:
    module, harness, sprints = _load_status_server(tmp_path)
    sid = "sprint-deliverables"
    workdir = sprints / sid / "workdir"
    output = _write(workdir / "workspace" / "wrapcol.py", "print('wrapped')\n")
    _write(workdir / ".pytest_cache" / "README.md", "pytest cache internals\n")

    cross_sprint_secret = _write(
        sprints / "sprint-other" / "secret.txt",
        "must never be served through this sprint\n",
    )
    escape = workdir / "workspace" / "escape.txt"
    symlink_created = False
    try:
        escape.symlink_to(cross_sprint_secret)
        symlink_created = True
    except OSError:
        # Windows CI may deny unprivileged symlink creation. Linux still exercises
        # the containment assertion, while the core visibility assertions remain
        # portable.
        pass

    items = module._discover_sprint_deliverables(sid)
    names = {item["name"] for item in items}

    assert "wrapcol.py" in names
    assert "README.md" not in names
    if symlink_created:
        assert "escape.txt" not in names
        assert "secret.txt" not in names

    wrapcol = next(item for item in items if item["name"] == "wrapcol.py")
    assert wrapcol["source"] == "output"
    assert wrapcol["stage"] == "source"
    assert module._resolve_sprint_deliverable(sid, wrapcol["rel_path"]) == output.resolve()
    assert module._is_within(output.resolve(), harness)


def test_recorded_external_workdir_remains_supported(tmp_path: Path) -> None:
    module, _harness, sprints = _load_status_server(tmp_path)
    sid = "sprint-external-workdir"
    external = tmp_path / "external-workspace"
    output = _write(external / "result.py", "print('external')\n")
    _write(
        sprints / f"{sid}.raw_intent.json",
        json.dumps({"task": {"cwd": str(external)}}),
    )

    items = module._discover_sprint_deliverables(sid)
    result = next(item for item in items if item["name"] == "result.py")

    assert result["source"] == "output"
    assert module._resolve_sprint_deliverable(sid, result["rel_path"]) == output.resolve()


def test_workdir_report_outranks_larger_planner_report(tmp_path: Path) -> None:
    """WRONG_RESULT_SELECTED: process prose must not become the user result.

    The live failure had a 3.5 KiB ``N0.pm-result.md`` planning summary and a
    smaller ``workdir/workspace/test_report.md`` produced by the task.  Both are
    classified as reports, so choosing by size alone opens the planner summary.
    """
    module, _harness, sprints = _load_status_server(tmp_path)
    sid = "sprint-result-selection"
    planner_report = _write(
        sprints / f"{sid}.N0.pm-result.md",
        "# Planner result\n\n" + ("planning details\n" * 200),
    )
    user_report = _write(
        sprints / sid / "workdir" / "workspace" / "test_report.md",
        "# Test report\n\n5 tests passed.\n",
    )

    items = module._discover_sprint_deliverables(sid)
    selected = [item for item in items if item["result"]]

    assert planner_report.stat().st_size > user_report.stat().st_size
    assert len(selected) == 1
    assert selected[0]["name"] == "test_report.md"
    assert selected[0]["source"] == "output"


def test_user_deliverable_outranks_larger_supporting_evidence(tmp_path: Path) -> None:
    """A verification artifact must not replace the requested user output.

    The graph already distinguishes delivery work (``implementation``) from
    supporting work (``tests``).  The result selector must honor that contract
    instead of treating every produced markdown file as an equal candidate and
    choosing the largest one.
    """
    module, _harness, sprints = _load_status_server(tmp_path)
    sid = "sprint-result-role-selection"
    workdir = sprints / sid / "workdir"
    readme = _write(
        workdir / "workspace" / "README.md",
        "# Line statistics\n\nRun `python line_stats.py`.\n",
    )
    _write(workdir / "workspace" / "line_stats.py", "print('ready')\n")
    evidence = _write(
        workdir / "workspace" / "evidence" / "test_report.md",
        "# Verification evidence\n\n" + ("all checks passed\n" * 200),
    )
    _write(
        sprints / f"{sid}.task_graph.json",
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "BUILD",
                        "task_type": "implementation",
                        "write_scope": [
                            "workspace/line_stats.py",
                            "workspace/README.md",
                        ],
                    },
                    {
                        "id": "VERIFY",
                        "task_type": "tests",
                        "depends_on": ["BUILD"],
                        "write_scope": ["workspace/evidence/test_report.md"],
                    },
                ]
            }
        ),
    )

    items = module._discover_sprint_deliverables(sid)
    selected = [item for item in items if item["result"]]
    evidence_item = next(item for item in items if item["name"] == "test_report.md")

    assert evidence.stat().st_size > readme.stat().st_size
    assert len(selected) == 1
    assert selected[0]["name"] == "README.md"
    assert selected[0]["producer_task_type"] == "implementation"
    assert selected[0]["supporting"] is False
    assert evidence_item["producer_task_type"] == "tests"
    assert evidence_item["supporting"] is True


def test_supporting_evidence_remains_result_when_it_is_the_only_output(tmp_path: Path) -> None:
    module, _harness, sprints = _load_status_server(tmp_path)
    sid = "sprint-evidence-only-result"
    _write(
        sprints / sid / "workdir" / "workspace" / "evidence" / "review.md",
        "# Review\n\nPASS\n",
    )
    _write(
        sprints / f"{sid}.task_graph.json",
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "REVIEW",
                        "task_type": "verification",
                        "write_scope": ["workspace/evidence/review.md"],
                    }
                ]
            }
        ),
    )

    items = module._discover_sprint_deliverables(sid)
    selected = [item for item in items if item["result"]]

    assert len(selected) == 1
    assert selected[0]["name"] == "review.md"
    assert selected[0]["supporting"] is True

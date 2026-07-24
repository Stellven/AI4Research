from __future__ import annotations

import json
from pathlib import Path


MATRIX = Path(__file__).with_name("l2_execution_matrix.json")


def load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_covers_every_l2_once() -> None:
    matrix = load_matrix()
    rows = matrix["features"]
    assert len(rows) == 142
    assert len({row["case_id"] for row in rows}) == 142
    assert len({row["test_name"] for row in rows}) == 142
    assert len({(row["sheet"], row["level_1_feature"], row["level_2_feature"]) for row in rows}) == 142


def test_implemented_rows_have_executable_probes_and_blocked_rows_do_not() -> None:
    matrix = load_matrix()
    probes = matrix["probes"]
    implemented = [row for row in matrix["features"] if row["implementation_status"] != "NOT_IMPLEMENTED"]
    blocked = [row for row in matrix["features"] if row["implementation_status"] == "NOT_IMPLEMENTED"]
    assert len(implemented) == 132
    assert len(blocked) == 10
    assert all(row["probe_id"] in probes for row in implemented)
    assert all(not row["probe_id"] and row["blocked_reason"] for row in blocked)


def test_probe_targets_are_current_files() -> None:
    repo = Path(__file__).resolve().parents[3]
    matrix = load_matrix()
    for probe_id, probe in matrix["probes"].items():
        target = probe["target"].split("::", 1)[0]
        assert probe["runner"] in {"pytest", "python_script", "node", "node_ts", "bash", "bun"}, probe_id
        assert (repo / target).is_file(), (probe_id, target)
        assert probe["rationale"].strip(), probe_id

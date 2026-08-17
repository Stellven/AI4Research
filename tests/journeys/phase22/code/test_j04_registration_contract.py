from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("test_j04_paper_ingestion.py")
SPEC = importlib.util.spec_from_file_location("j04_registration_contract", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_jsonl_reads_registration_edges(tmp_path: Path) -> None:
    path = tmp_path / "edges.jsonl"
    path.write_text(
        json.dumps({"target_id": "paper-one", "relation": "registered"}) + "\n"
        + json.dumps({"target_id": "paper-two", "relation": "describes"}) + "\n",
        encoding="utf-8",
    )

    assert [row["target_id"] for row in MODULE._jsonl(path)] == ["paper-one", "paper-two"]


def test_jsonl_missing_artifact_is_not_self_attested(tmp_path: Path) -> None:
    assert MODULE._jsonl(tmp_path / "missing.jsonl") == []

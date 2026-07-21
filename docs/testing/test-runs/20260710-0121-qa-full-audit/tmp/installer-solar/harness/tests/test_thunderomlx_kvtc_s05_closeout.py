from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import thunderomlx_kvtc_s05_closeout as tkc  # noqa: E402


def test_auto_closeout_thunderomlx_kvtc_s05_builds_eval_payload(tmp_path, monkeypatch):
    runtime_root = tmp_path
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = tkc.SPRINT_ID

    for suffix in [
        f".{tkc.NODE_ID}-handoff.md",
        ".handoff.md",
        ".traceability.json",
        ".task_graph.json",
    ]:
        payload = "{}" if suffix.endswith(".json") else f"artifact {suffix}"
        (sprints / f"{sid}{suffix}").write_text(payload, encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "node_results": {tkc.NODE_ID: {"ok": True}}, "status_sync": {"ok": True}}

    monkeypatch.setattr(tkc, "auto_closeout_graph_nodes", fake_closeout)

    result = tkc.auto_closeout_thunderomlx_kvtc_s05(runtime_root)

    assert result["ok"] is True
    assert captured["reason"] == "thunderomlx_kvtc_s05_d0_eval_restored"
    payload = captured["node_payloads"][tkc.NODE_ID]
    assert payload["verdict"] == "PASS"

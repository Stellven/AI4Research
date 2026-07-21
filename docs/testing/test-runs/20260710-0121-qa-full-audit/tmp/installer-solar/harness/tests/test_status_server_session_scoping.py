#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_SERVER = ROOT / "lib" / "symphony" / "status-server.py"


def _load_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    for rel in ("sprints", "sessions", "events", "run"):
        (harness / rel).mkdir(parents=True, exist_ok=True)
    os.environ["HARNESS_DIR"] = str(harness)
    name = f"status_server_session_scoping_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, STATUS_SERVER)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, harness


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_events_for_request_normalizes_session_file_and_drops_wrong_sprint(tmp_path: Path) -> None:
    mod, harness = _load_status_server(tmp_path)
    sid = "sprint-session-a"
    _jsonl(
        harness / "sessions" / sid / "events.jsonl",
        [
            {"ts": "2026-06-26T00:00:01Z", "type": "missing_id"},
            {"ts": "2026-06-26T00:00:02Z", "type": "right_id", "sprint_id": sid},
            {"ts": "2026-06-26T00:00:03Z", "type": "wrong_id", "sprint_id": "sprint-b"},
        ],
    )

    events = mod._events_for_request(sid, limit=10)

    assert [event["type"] for event in events] == ["missing_id", "right_id"]
    assert {event["sprint_id"] for event in events} == {sid}
    assert {event["_event_scope"] for event in events} == {"requested"}
    assert {event["_event_source"] for event in events} == {"session_file"}


def test_events_for_request_filters_global_events_for_requested_sprint(tmp_path: Path) -> None:
    mod, harness = _load_status_server(tmp_path)
    _jsonl(
        harness / "events" / "all.jsonl",
        [
            {"ts": "2026-06-26T00:00:01Z", "type": "a", "sprint_id": "sprint-a"},
            {"ts": "2026-06-26T00:00:02Z", "type": "b", "sprint_id": "sprint-b"},
            {"ts": "2026-06-26T00:00:03Z", "type": "missing"},
        ],
    )

    events = mod._events_for_request("sprint-b", limit=10)

    assert [event["type"] for event in events] == ["b"]
    assert events[0]["sprint_id"] == "sprint-b"
    assert events[0]["_event_source"] == "global_file"


def test_latest_sprint_candidate_reports_ambiguous_intake_window(tmp_path: Path) -> None:
    mod, harness = _load_status_server(tmp_path)
    before = time.time()
    for sid in ("sprint-a", "sprint-b"):
        (harness / "sprints" / f"{sid}.status.json").write_text(
            json.dumps({"sprint_id": sid}) + "\n",
            encoding="utf-8",
        )

    result = mod._latest_sprint_candidate_after(before)

    assert result["sprint_id"] == ""
    assert result["ambiguous"] is True
    assert result["attribution"] == "ambiguous_latest_status_file"
    assert set(result["candidates"]) == {"sprint-a", "sprint-b"}


def test_status_payload_signature_changes_when_scoped_events_change(tmp_path: Path) -> None:
    mod, harness = _load_status_server(tmp_path)
    sid = "sprint-cache"
    (harness / "sprints" / f"{sid}.status.json").write_text(
        json.dumps({"sprint_id": sid}) + "\n",
        encoding="utf-8",
    )
    events_path = harness / "sessions" / sid / "events.jsonl"
    _jsonl(events_path, [{"ts": "2026-06-26T00:00:01Z", "type": "first"}])
    before = mod._status_payload_signature(sid)

    time.sleep(0.002)
    _jsonl(events_path, [{"ts": "2026-06-26T00:00:02Z", "type": "second"}])
    after = mod._status_payload_signature(sid)

    assert after != before

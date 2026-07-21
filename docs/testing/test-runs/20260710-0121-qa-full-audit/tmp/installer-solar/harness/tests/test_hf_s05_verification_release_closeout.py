from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from hf_s05_verification_release_closeout import _payload  # noqa: E402


def test_payload_marks_fail_when_required_artifact_missing(tmp_path):
    existing = tmp_path / "exists.md"
    existing.write_text("ok", encoding="utf-8")
    missing = tmp_path / "missing.md"
    payload = _payload("V1", "summary", [existing, missing])
    assert payload["verdict"] == "FAIL"
    assert str(missing) in payload["evidence"]["missing_paths"]


def test_payload_marks_pass_when_all_required_artifacts_exist(tmp_path):
    p1 = tmp_path / "one.md"
    p2 = tmp_path / "two.json"
    p1.write_text("ok", encoding="utf-8")
    p2.write_text(json.dumps({"ok": True}), encoding="utf-8")
    payload = _payload("V2", "summary", [p1, p2])
    assert payload["verdict"] == "PASS"
    assert payload["failed_conditions"] == []

"""SubprocessEvaluator sandbox tests."""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

from integrations.gepa_optimizer.evaluator import (
    EvaluatorError,
    EvaluatorResult,
    SubprocessEvaluator,
)


def _write_script(tmp_path: Path, body: str) -> Path:
    p = tmp_path / f"evaluator_{abs(hash(body)) & 0xFFFFFF:06x}.py"
    p.write_text(body)
    return p


def test_constructor_rejects_missing_script(tmp_path):
    with pytest.raises(EvaluatorError):
        SubprocessEvaluator(tmp_path / "no-such-file.py")


def test_constructor_rejects_nonpositive_timeout(tmp_path):
    p = _write_script(tmp_path, "import sys; sys.exit(0)")
    with pytest.raises(EvaluatorError):
        SubprocessEvaluator(p, timeout=0)


def test_happy_path_returns_score(tmp_path):
    script = _write_script(
        tmp_path,
        textwrap.dedent(
            """
            import json, sys
            data = json.load(sys.stdin)
            print(json.dumps({"score": len(data["candidate"]) / 100.0, "info": "ok"}))
            """
        ),
    )
    ev = SubprocessEvaluator(script, timeout=10.0)
    result = ev("hello world")
    assert isinstance(result, EvaluatorResult)
    assert result.ok is True
    assert result.score == pytest.approx(0.11)
    assert result.metadata.get("info") == "ok"


def test_timeout_returns_structured_failure(tmp_path):
    script = _write_script(
        tmp_path,
        textwrap.dedent(
            """
            import time, sys, json
            json.load(sys.stdin)
            time.sleep(5)
            """
        ),
    )
    ev = SubprocessEvaluator(script, timeout=0.5)
    result = ev("anything")
    assert result.ok is False
    assert result.timed_out is True
    assert "timed out" in (result.error or "").lower()


def test_exception_returns_structured_failure(tmp_path):
    script = _write_script(
        tmp_path,
        textwrap.dedent(
            """
            import sys, json
            json.load(sys.stdin)
            raise RuntimeError("intentional boom")
            """
        ),
    )
    ev = SubprocessEvaluator(script, timeout=5.0)
    result = ev("anything")
    assert result.ok is False
    assert result.exit_code is not None and result.exit_code != 0


def test_secret_env_not_forwarded(tmp_path, monkeypatch):
    script = _write_script(
        tmp_path,
        textwrap.dedent(
            """
            import os, sys, json
            json.load(sys.stdin)
            print(json.dumps({
                "score": 1.0,
                "leaked_token": os.environ.get("MY_TEST_API_KEY"),
                "kept_path": bool(os.environ.get("PATH")),
            }))
            """
        ),
    )
    monkeypatch.setenv("MY_TEST_API_KEY", "sk-supersecret-should-not-leak")
    ev = SubprocessEvaluator(script, timeout=5.0)
    result = ev("hello")
    assert result.ok is True
    assert result.metadata.get("leaked_token") in (None, "")
    assert result.metadata.get("kept_path") is True


def test_application_level_error_in_json(tmp_path):
    script = _write_script(
        tmp_path,
        textwrap.dedent(
            """
            import sys, json
            json.load(sys.stdin)
            print(json.dumps({"error": "bad candidate format"}))
            """
        ),
    )
    ev = SubprocessEvaluator(script, timeout=5.0)
    result = ev("anything")
    assert result.ok is False
    assert "bad candidate format" in (result.error or "")

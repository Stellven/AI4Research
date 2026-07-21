from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey import chief_editor


def _write_human_final(root):
    (root / "human_final.md").write_text(
        """# Professor-Grade Survey: Test

## 核心结论

Agentic Runtime is an execution system.

## 证据基础

Sources cover papers and official docs.

## 架构范式

### 本章判断

- Runtime requires durable execution and state.

### 风险与争议

- Official docs are not independent proof.

## 评估体系

### 本章判断

- Benchmarks must test end-to-end execution.

### 未解问题

- Cross-runtime comparability remains open.

## 证据脚注

[^1]: Test source (paper) https://arxiv.org/abs/2501.00001
""",
        encoding="utf-8",
    )


def test_chief_editor_deterministic_writes_quality_payload(tmp_path):
    _write_human_final(tmp_path)
    payload = chief_editor.run_chief_editor(tmp_path, backend="deterministic", min_chars=100)

    assert payload["ok"] is True
    assert (tmp_path / "chief_editor_final.md").exists()
    assert (tmp_path / "survey_chief_editor_backend.json").exists()
    assert payload["quality_gate"]["ok"] is True
    text = (tmp_path / "chief_editor_final.md").read_text(encoding="utf-8")
    assert "## 架构范式" in text
    assert "## 评估体系" in text
    assert "[claim:" not in text


def test_chief_editor_can_require_hitl_approval(tmp_path):
    _write_human_final(tmp_path)
    payload = chief_editor.run_chief_editor(tmp_path, backend="deterministic", min_chars=100, require_hitl=True)

    assert payload["ok"] is False
    assert payload["reason"] == "hitl_approval_required"
    assert (tmp_path / "survey_chief_editor_hitl.md").exists()

    (tmp_path / "chief_editor_approval.txt").write_text("APPROVED", encoding="utf-8")
    approved = chief_editor.run_chief_editor(tmp_path, backend="deterministic", min_chars=100, require_hitl=True)
    assert approved["ok"] is True
    saved = json.loads((tmp_path / "survey_chief_editor_backend.json").read_text(encoding="utf-8"))
    assert saved["hitl_approved"] is True


def test_chief_editor_uses_fallback_model_after_primary_failure(tmp_path, monkeypatch):
    _write_human_final(tmp_path)
    calls = []

    def fake_run_claude(prompt, *, model, timeout, max_budget_usd):
        calls.append(model)
        if model == "opus":
            raise RuntimeError("claude_cli_failed:1:opus unavailable")
        return "## 架构范式\n\n改写后的架构范式章节。\n" if "架构范式" in prompt else "## 评估体系\n\n改写后的评估体系章节。\n"

    monkeypatch.setattr(chief_editor, "_run_claude", fake_run_claude)

    payload = chief_editor.run_chief_editor(
        tmp_path,
        backend="claude-cli",
        model="opus",
        fallback_models="sonnet",
        min_chars=40,
    )

    assert payload["ok"] is True
    assert payload["requested_model"] == "opus"
    assert payload["model"] == "sonnet"
    assert calls == ["opus", "sonnet", "sonnet"]
    assert any(item["model"] == "opus" and item["ok"] is False for item in payload["model_attempts"])
    usage_rows = [
        json.loads(line)
        for line in (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(usage_rows) == 2
    assert usage_rows[0]["token_usage_is_estimated"] is True


def test_chief_editor_local_command_records_real_usage_json(tmp_path):
    _write_human_final(tmp_path)
    script = tmp_path / "chief_json.py"
    script.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        "heading = '架构范式' if '架构范式' in prompt else '评估体系'\n"
        "result = f'## {heading}\\n\\nJSON chief editor output.\\n'\n"
        "print(json.dumps({'result': result, 'usage': {'input_tokens': 222, 'output_tokens': 33, 'total_tokens': 255}}))\n",
        encoding="utf-8",
    )
    payload = chief_editor.run_chief_editor(
        tmp_path,
        backend="local-command",
        command=f"{sys.executable} {script}",
        min_chars=40,
    )

    assert payload["ok"] is True
    usage_rows = [
        json.loads(line)
        for line in (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(usage_rows) == 2
    assert usage_rows[0]["token_usage_is_estimated"] is False
    assert usage_rows[0]["total_tokens"] == 255


def test_chief_editor_publishes_status_projection(tmp_path, monkeypatch):
    _write_human_final(tmp_path)
    reports_root = tmp_path / "harness-home" / "reports"
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path / "harness-home"))

    (tmp_path / "survey_final_summary.json").write_text(
        json.dumps({"title": "CAIS 2026 DeepDive"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "survey_source_gap.json").write_text(
        json.dumps(
            {
                "brief": "CAIS 2026",
                "source_count": 23,
                "evidence_count": 46,
                "claim_count": 46,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "survey_section_factual_audit.json").write_text(
        json.dumps({"section_grounding_accuracy": 1.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "survey_section_scorecard.json").write_text(
        json.dumps({"section_count": 32}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "survey_human_execution_metrics.json").write_text(
        json.dumps({"total_tokens": 255, "document_word_count": 1234}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "survey_eval.json").write_text(json.dumps({"ok": False}, ensure_ascii=False), encoding="utf-8")

    payload = chief_editor.run_chief_editor(tmp_path, backend="deterministic", min_chars=100)

    report_dir = reports_root / tmp_path.name
    manifest = report_dir / f"{tmp_path.name}-research_eval.json"
    assert payload["ok"] is True
    assert manifest.exists()
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["final_md"].endswith("chief_editor_final.md")
    assert saved["status"] == "partial"
    assert saved["source_count"] == 23
    assert (report_dir / "chief_editor_final.md").exists()

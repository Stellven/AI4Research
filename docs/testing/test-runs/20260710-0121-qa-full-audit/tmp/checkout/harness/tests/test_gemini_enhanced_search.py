#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import gemini_adapter  # noqa: E402
import gemini_enhanced_search as ges  # noqa: E402


def test_parse_json_payload_accepts_fenced_json():
    text = """preface

```json
{"rewritten_prompt":"hello","rewrite_notes":["tighten scope"]}
```

tail
"""
    payload = ges._parse_json_payload(text)
    assert payload["rewritten_prompt"] == "hello"
    assert payload["rewrite_notes"] == ["tighten scope"]


def test_normalize_citations_filters_invalid_and_dedupes():
    rows = ges._normalize_citations(
        [
            {"title": "One", "url": "https://a.test", "publisher": "A"},
            {"title": "Dup", "url": "https://a.test", "publisher": "A2"},
            {"title": "Missing"},
            "bad-row",
            {"title": "Two", "url": "https://b.test", "why_relevant": "useful"},
        ]
    )
    assert rows == [
        {
            "title": "One",
            "url": "https://a.test",
            "publisher": "A",
            "why_relevant": "",
        },
        {
            "title": "Two",
            "url": "https://b.test",
            "publisher": "",
            "why_relevant": "useful",
        },
    ]


def test_run_pipeline_assembles_expected_contract(monkeypatch):
    monkeypatch.setattr(
        ges,
        "_run_rewrite_stage",
        lambda *args, **kwargs: (
            {
                "rewritten_prompt": "Rewrite me",
                "rewrite_notes": ["note-1"],
                "search_focus": ["focus-1"],
            },
            {"mode": "command_template", "model": "rewrite-model"},
        ),
    )
    monkeypatch.setattr(
        ges,
        "_run_research_stage",
        lambda *args, **kwargs: (
            {
                "analysis_markdown": "## Analysis\n\nBody",
                "citations": [
                    {"title": "A", "url": "https://a.test"},
                    {"title": "A-dup", "url": "https://a.test"},
                    {"title": "B", "url": "https://b.test"},
                ],
            },
            {"mode": "agy_prompt", "model": "research-model"},
        ),
    )

    payload = ges.run_pipeline("original prompt", gem_name="李教授提示词大师")
    assert payload["ok"] is True
    assert payload["gem_name"] == "李教授提示词大师"
    assert payload["rewritten_prompt"] == "Rewrite me"
    assert payload["analysis_markdown"].startswith("## Analysis")
    assert [row["url"] for row in payload["citations"]] == ["https://a.test", "https://b.test"]
    assert payload["provider_metadata"]["rewrite"]["mode"] == "command_template"
    assert payload["provider_metadata"]["deep_research"]["mode"] == "agy_prompt"


def test_rewrite_stage_can_require_direct_gem(monkeypatch):
    monkeypatch.delenv(ges.REWRITE_CMD_ENV, raising=False)
    with pytest.raises(RuntimeError, match="direct Gem invocation required"):
        ges._run_rewrite_stage(
            "prompt",
            gem_name="李教授提示词大师",
            rewrite_model="gemini-3.5-flash-high",
            print_timeout="10m",
            subprocess_timeout_sec=5,
            require_direct_gem=True,
        )


def test_gemini_adapter_enhanced_search_forwards(monkeypatch, tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("hello", encoding="utf-8")
    captured: list[str] = []

    def fake_main(argv: list[str] | None = None) -> int:
        captured.extend(argv or [])
        return 0

    monkeypatch.setattr(gemini_adapter, "gemini_enhanced_search_main", fake_main)
    rc = gemini_adapter.main(
        [
            "enhanced-search",
            "--prompt-file",
            str(prompt_file),
            "--gem-name",
            "李教授提示词大师",
            "--rewrite-model",
            "gemini-3.5-flash-high",
            "--research-model",
            "gemini-3.1-pro",
            "--print-timeout",
            "8m",
            "--subprocess-timeout-sec",
            "120",
            "--require-direct-gem",
        ]
    )
    assert rc == 0
    assert captured == [
        "run",
        "--prompt-file",
        str(prompt_file),
        "--gem-name",
        "李教授提示词大师",
        "--rewrite-model",
        "gemini-3.5-flash-high",
        "--research-model",
        "gemini-3.1-pro",
        "--print-timeout",
        "8m",
        "--subprocess-timeout-sec",
        "120",
        "--require-direct-gem",
    ]

from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.auto_continue import continue_survey_run
from research.survey.planner import create_survey_plan, write_survey_plan


def _search_results(count: int = 16) -> str:
    source_types = ["paper", "repo", "official_doc", "benchmark"]
    url_templates = {
        "paper": ["https://arxiv.org/abs/2412.06769", "https://openreview.net/forum?id=latent-reasoning", "https://doi.org/10.1145/latent-reasoning", "https://ieeexplore.ieee.org/document/123456"],
        "repo": ["https://github.com/example/latent-reasoning", "https://github.com/facebookresearch/coconut"],
        "official_doc": ["https://docs.example.edu/latent-reasoning", "https://docs.example.edu/latent-reasoning/api"],
        "benchmark": ["https://paperswithcode.com/task/latent-reasoning", "https://huggingface.co/datasets/example/latent-reasoning"],
    }
    type_seen = {key: 0 for key in url_templates}
    blocks = ["# External Search Results: latent reasoning"]
    for idx in range(1, count + 1):
        source_type = source_types[(idx - 1) % len(source_types)]
        urls = url_templates[source_type]
        url = urls[type_seen[source_type] % len(urls)]
        type_seen[source_type] += 1
        blocks.append(f"""
## Source {idx}: Latent Reasoning Source {idx}
URL: {url}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: {source_type}
Research Angles: {["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"][(idx - 1) % 5]}

Summary:
- Latent reasoning source {idx} covers architecture evaluation deployment.

Key Claims:
- Latent reasoning claim {idx}A requires evidence for architecture evaluation.
- Latent reasoning claim {idx}B requires evidence for deployment constraints.

Relevant Quotes:
> Latent reasoning source {idx} preserves evidence boundaries.
""")
    return "\n".join(blocks)


def test_continue_survey_pauses_on_source_gap(tmp_path):
    payload = continue_survey_run(tmp_path, brief="latent reasoning", max_steps=2)
    assert payload["ok"] is True
    assert payload["completed"] is False
    assert payload["paused"] is True
    assert payload["status"] == "need_search_results"
    assert (tmp_path / "survey_source_gap_handoff.md").exists()
    assert any(step.get("executed") == "survey-finalize-run" for step in payload["steps"])


def test_continue_survey_imports_returned_markdown_and_finishes(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    returned = tmp_path / "returned_sources.md"
    returned.write_text(_search_results(), encoding="utf-8")
    payload = continue_survey_run(
        tmp_path,
        brief="latent reasoning",
        returned_md=returned,
        max_steps=3,
        section_limit=1,
        repair_limit=1,
        min_finalized=1,
        min_chars=100,
    )
    assert payload["ok"] is True
    assert payload["completed"] is True
    assert payload["status"] == "done"
    assert (tmp_path / "final.md").exists()
    assert any(step.get("executed") == "survey-import-search-results" for step in payload["steps"])


def test_continue_survey_cli_allow_pending(tmp_path, capsys):
    rc = main([
        "survey-continue",
        "--output-dir", str(tmp_path),
        "--brief", "latent reasoning",
        "--max-steps", "2",
        "--allow-pending",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "need_search_results"
    assert payload["completed"] is False


def test_continue_survey_cli_requires_completion_without_allow_pending(tmp_path, capsys):
    rc = main([
        "survey-continue",
        "--output-dir", str(tmp_path),
        "--brief", "latent reasoning",
        "--max-steps", "2",
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "need_search_results"


def test_continue_survey_supports_require_complete(tmp_path):
    payload = continue_survey_run(
        tmp_path,
        brief="latent reasoning",
        max_steps=2,
        require_complete=True,
    )
    assert payload["status"] == "need_search_results"
    assert (tmp_path / "survey_finalize_run.json").exists()


def test_continue_survey_require_complete_writes_remaining_sections(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    returned = tmp_path / "returned_sources.md"
    returned.write_text(_search_results(), encoding="utf-8")
    payload = continue_survey_run(
        tmp_path,
        returned_md=returned,
        max_steps=5,
        section_limit=1,
        repair_limit=1,
        min_chars=100,
        require_complete=True,
    )
    assert payload["ok"] is True
    assert payload["completed"] is True
    assert payload["status"] == "done"
    assert any(step.get("status") == "needs_more_sections" and step.get("section_limit") == 0 for step in payload["steps"])

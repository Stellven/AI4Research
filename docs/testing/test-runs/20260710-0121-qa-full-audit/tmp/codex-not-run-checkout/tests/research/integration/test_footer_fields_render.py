"""Integration test: footer 4-field precise text rendering.

Verifies render_execution_metrics_section and append_execution_metrics_section
produce the exact footer text required by S02 footer_fields.md contract.
"""

from __future__ import annotations

from harness.lib.research import report_metrics


def _make_metrics(**overrides):
    base = {
        "document_word_count": 1234,
        "document_char_count": 5678,
        "total_token_consumption": 9000,
        "input_tokens": 6000,
        "output_tokens": 3000,
        "token_usage_source": "provider_usage_ledger",
        "token_usage_is_estimated": False,
    }
    base.update(overrides)
    return base


def test_footer_four_fields_provider():
    """Footer has exact 4-field text with provider_usage_ledger."""
    metrics = _make_metrics()
    section = report_metrics.render_execution_metrics_section(metrics)
    assert "Document word count: 1234" in section
    assert "Total token consumption: 9000" in section
    assert "Token usage source: provider_usage_ledger" in section
    assert "Token usage estimated: no" in section


def test_token_usage_footer_fields_are_not_double_rendered():
    """Token usage source/estimated should appear only in the S02 footer block."""
    metrics = _make_metrics()
    section = report_metrics.render_execution_metrics_section(metrics)
    assert section.count("Token usage source:") == 1
    assert section.count("Token usage estimated:") == 1
    assert "- Token usage source:" not in section
    assert "- Token usage estimated:" not in section


def test_footer_four_fields_estimated():
    """Footer has exact 4-field text with estimated source."""
    metrics = _make_metrics(
        token_usage_source="estimated_from_report_artifacts",
        token_usage_is_estimated=True,
    )
    section = report_metrics.render_execution_metrics_section(metrics)
    assert "Document word count: 1234" in section
    assert "Total token consumption: 9000" in section
    assert "Token usage source: estimated_from_report_artifacts" in section
    assert "Token usage estimated: yes" in section


def test_footer_surrounded_by_horizontal_rules():
    """Footer block is delimited by --- lines."""
    metrics = _make_metrics()
    section = report_metrics.render_execution_metrics_section(metrics)
    lines = section.strip().splitlines()
    footer_start = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            footer_start = i
            break
    assert footer_start is not None, "No opening --- found"
    remaining = lines[footer_start:]
    assert remaining[-1].strip() == "---", "No closing --- found"


def test_append_execution_metrics_section_footer():
    """append_execution_metrics_section produces markdown with 4-field footer."""
    base_md = "# Test Report\n\nSome content here."
    final_md, metrics = report_metrics.append_execution_metrics_section(base_md, None)
    assert "Document word count:" in final_md
    assert "Total token consumption:" in final_md
    assert "Token usage source:" in final_md
    assert "Token usage estimated:" in final_md
    assert final_md.startswith("# Test Report"), "Original content preserved"

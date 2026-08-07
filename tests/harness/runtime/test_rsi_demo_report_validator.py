"""Deterministic tests for the RSI demo report validator (Lane 4 port).

Ported from feat/rc8-demo-golden-path. This lane restores ONLY the copied-workspace
report validator (scripts/validate_rsi_demo_report.py); the source-pack validator
and demo-rsi/source-pack/ live on the demo-golden-path branch and are out of Lane 4
scope (see docs/product/lane4-spec-mismatches.md). No live Codex; builds fixture
workspaces and invokes the CLI validator exactly as the live wrapper does
(cwd == the copied sandbox workspace).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REPORT_VALIDATOR = ROOT / "scripts" / "validate_rsi_demo_report.py"

HTML_BODY = (
    "<!doctype html><html><head><title>RSI</title></head><body>"
    "<h1>Recursive Self-Improving Models</h1>"
    "<p>" + ("A cited synthesis across nine sources covering recursive self-improvement, "
             "self-improving LLMs, verifier-driven improvement, research agents, and safety. ") * 6
    + "</p></body></html>"
)
MD_BODY = "# RSI report\n\n" + ("Executive summary and cross-source synthesis. " * 20)


def _write_good_workspace(ws: Path) -> Path:
    r = ws / "rsi-deep-research-report"
    r.mkdir(parents=True)
    (r / "report.html").write_text(HTML_BODY, encoding="utf-8")
    (r / "report.md").write_text(MD_BODY, encoding="utf-8")
    sources = [{"id": f"s{i}", "title": f"Source {i}"} for i in range(1, 7)]
    claims = [
        {"claim_id": f"c{i}", "source_id": f"s{(i % 6) + 1}", "claim_text": f"claim number {i}"}
        for i in range(1, 12)
    ]
    (r / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    (r / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (r / "evaluation-checklist.md").write_text("# checklist\n- all sources represented\n", encoding="utf-8")
    return r


def _run_report_validator(ws: Path):
    return subprocess.run(
        [sys.executable, str(REPORT_VALIDATOR)],
        cwd=str(ws), text=True, capture_output=True,
    )


# ---- happy path ----
def test_report_validator_passes_on_good_workspace(tmp_path):
    _write_good_workspace(tmp_path)
    proc = _run_report_validator(tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "RSI demo report validated" in proc.stdout


# ---- each failure mode ----
def test_report_validator_missing_file(tmp_path):
    r = _write_good_workspace(tmp_path)
    (r / "claims.json").unlink()
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "ARTIFACT_MISSING" in proc.stderr


def test_report_validator_html_not_html(tmp_path):
    r = _write_good_workspace(tmp_path)
    (r / "report.html").write_text("plain text, no markup, " * 40, encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "HTML_INVALID" in proc.stderr


def test_report_validator_too_few_sources(tmp_path):
    r = _write_good_workspace(tmp_path)
    (r / "sources.json").write_text(json.dumps([{"id": "s1", "title": "x"}]), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "TOO_FEW_SOURCES" in proc.stderr


def test_report_validator_too_few_claims(tmp_path):
    r = _write_good_workspace(tmp_path)
    claims = [{"claim_id": "c1", "source_id": "s1", "claim_text": "only one"}]
    (r / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "TOO_FEW_CLAIMS" in proc.stderr


def test_report_validator_rejects_duplicate_source_ids(tmp_path):
    r = _write_good_workspace(tmp_path)
    sources = [{"id": "s_dup", "title": f"Duplicate source {i}"} for i in range(1, 7)]
    (r / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    claims = [
        {"claim_id": f"c{i}", "source_id": "s_dup", "claim_text": f"claim number {i}"}
        for i in range(1, 12)
    ]
    (r / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "DUPLICATE_SOURCE_ID" in proc.stderr


def test_report_validator_rejects_duplicate_claim_ids(tmp_path):
    r = _write_good_workspace(tmp_path)
    claims = json.loads((r / "claims.json").read_text(encoding="utf-8"))
    for idx, claim in enumerate(claims):
        claim["claim_id"] = "c_dup"
        claim["claim_text"] = f"conflicting duplicate claim text {idx}"
    (r / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "DUPLICATE_CLAIM_ID" in proc.stderr


def test_report_validator_bad_linkage(tmp_path):
    r = _write_good_workspace(tmp_path)
    claims = json.loads((r / "claims.json").read_text())
    claims[0]["source_id"] = "does-not-exist"
    (r / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "LINKAGE" in proc.stderr


def test_report_validator_placeholder_content(tmp_path):
    r = _write_good_workspace(tmp_path)
    (r / "report.md").write_text(MD_BODY + "\n\nTODO: write the rest\n", encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0
    assert "PLACEHOLDER_CONTENT" in proc.stderr


def test_report_validator_allows_no_placeholder_prose(tmp_path):
    # Regression for the v4 false positive: a finished report may legitimately use
    # the WORD "placeholder" in prose that asserts completeness.
    r = _write_good_workspace(tmp_path)
    (r / "report.md").write_text(
        MD_BODY
        + "\n\n## Verification\n\n- route-proof: No placeholder text remains; this section "
          "contains the concrete provider/model/operator details.\n"
          "- placeholder check passed; no placeholders were found.\n"
          "- Citations are inserted here from the source pack.\n",
        encoding="utf-8",
    )
    proc = _run_report_validator(tmp_path)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("stub", [
    "[placeholder]", "[PLACEHOLDER]", "<placeholder>", "{{placeholder}}",
    "TODO", "FIXME", "TBD", "XXX", "lorem ipsum", "INSERT_HERE",
    "replace me", "insert your name here", "<insert value here>",
])
def test_report_validator_flags_stub_markers(tmp_path, stub):
    r = _write_good_workspace(tmp_path)
    (r / "report.md").write_text(MD_BODY + f"\n\nSection body {stub} more text.\n", encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode != 0, f"stub {stub!r} not flagged"
    assert "PLACEHOLDER_CONTENT" in proc.stderr


def test_report_validator_accepts_wrapped_dicts(tmp_path):
    r = _write_good_workspace(tmp_path)
    srcs = json.loads((r / "sources.json").read_text())
    clms = json.loads((r / "claims.json").read_text())
    (r / "sources.json").write_text(json.dumps({"sources": srcs}), encoding="utf-8")
    (r / "claims.json").write_text(json.dumps({"claims": clms}), encoding="utf-8")
    proc = _run_report_validator(tmp_path)
    assert proc.returncode == 0, proc.stderr

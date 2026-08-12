from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "harness" / "tools" / "markdown_pdf.py"


def _module():
    spec = importlib.util.spec_from_file_location("markdown_pdf_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builds_structural_multipage_pdf_with_source_markers(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "report.md"
    source.write_text("# Evidence Report\n\n" + "Grounded result line with evidence.\n" * 120, encoding="utf-8")
    output = tmp_path / "report.pdf"
    result = module.build_pdf(source, output)
    assert result["valid"] is True
    assert result["page_count"] >= 2
    assert len(result["sha256"]) == 64


def test_verifier_rejects_truncated_pdf(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "report.md"
    source.write_text("# Evidence Report\nGrounded result line with evidence.\n", encoding="utf-8")
    output = tmp_path / "report.pdf"
    module.build_pdf(source, output)
    output.write_bytes(output.read_bytes()[:-20])
    assert module.verify_pdf(output)["valid"] is False

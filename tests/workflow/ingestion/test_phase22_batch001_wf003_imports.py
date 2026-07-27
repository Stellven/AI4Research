from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "harness" / "plugins" / "autosci"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from backends import paper_prepare  # type: ignore


def _read_input_result(path: Path, tmp_root: Path) -> dict:
    return paper_prepare.read_paper_source(
        path,
        raw_root=tmp_root / "raw",
        workspace_root=tmp_root,
    )


def test_wf003_02_markdown_import(tmp_path: Path) -> None:
    source = tmp_path / "paper.md"
    source.write_text("# Solar Markdown\n\nThis is a markdown fixture.", encoding="utf-8")
    result = _read_input_result(source, tmp_path)

    assert result["status"] == "completed"
    assert result["parse_status"] == "parsed"
    assert result["source_type"] == "markdown"
    assert result["title"] == "Solar Markdown"


def test_wf003_03_latex_import(tmp_path: Path) -> None:
    source = tmp_path / "paper.tex"
    source.write_text(
        "\\title{Solar Latex}\n"
        "\\begin{document}\n"
        "\\begin{abstract}Abstract fixture.\\end{abstract}\n"
        "\\section{Method}\n"
        "Solar latex body.\n"
        "\\end{document}",
        encoding="utf-8",
    )
    result = _read_input_result(source, tmp_path)

    assert result["status"] == "completed"
    assert result["source_type"] == "latex"
    assert result["parse_status"] == "parsed"
    assert result["title"] == "Solar Latex"


def test_wf003_04_html_import(tmp_path: Path) -> None:
    source = tmp_path / "paper.html"
    source.write_text("<html><body><h1>Title</h1><p>Body</p></body></html>", encoding="utf-8")
    result = _read_input_result(source, tmp_path)

    assert result["status"] == "completed"
    assert result["source_type"] == "html"
    assert result["parse_status"] in {"parsed", "partial", "failed"}
    assert result["title"] == "paper"


def test_wf003_05_text_import(tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text("Plain text fixture for user supplied import.", encoding="utf-8")
    result = _read_input_result(source, tmp_path)

    assert result["status"] == "completed"
    assert result["parse_status"] == "parsed"
    assert result["source_type"] == "unknown"
    assert result["title"] == "Plain text fixture for user supplied import."


def test_wf003_06_archive_import(tmp_path: Path) -> None:
    source_dir = tmp_path / "archive-input"
    source_dir.mkdir()
    (source_dir / "main.tex").write_text(
        "\\title{Archive Paper}\n"
        "\\begin{document}\n"
        "\\section{Archive}\n"
        "Archive body.\n"
        "\\end{document}",
        encoding="utf-8",
    )
    archive = tmp_path / "paper.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(source_dir / "main.tex", arcname="main.tex")

    result = paper_prepare.read_paper_source(
        archive,
        raw_root=tmp_path / "raw",
        workspace_root=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["source_type"] == "latex"
    assert result["parse_status"] == "parsed"
    assert result["preparation"]["status"] == "completed"


def test_wf003_07_directory_import(tmp_path: Path) -> None:
    source_dir = tmp_path / "paper-dir"
    source_dir.mkdir()
    (source_dir / "main.tex").write_text(
        "\\title{Directory Paper}\n"
        "\\begin{document}\n"
        "\\section{Directory}\n"
        "Directory body.\n"
        "\\end{document}",
        encoding="utf-8",
    )
    result = _read_input_result(source_dir, tmp_path)

    assert result["status"] == "completed"
    assert result["source_type"] == "latex"
    assert result["parse_status"] == "parsed"


def test_wf003_08_arxiv_import_requires_network_or_references(tmp_path: Path) -> None:
    result = paper_prepare.read_paper_source(
        "https://arxiv.org/abs/2401.00001",
        raw_root=tmp_path / "raw",
        workspace_root=tmp_path,
        allow_network_fetch=False,
    )

    assert result["source_type"] == "arxiv"
    assert result["status"] == "completed"
    assert result["source_fetch_status"] == "skipped_network_disabled"
    assert any("skipped_network_disabled" in item for item in result.get("limitations", []))


def test_wf003_09_scanned_pdf_without_ocr(tmp_path: Path) -> None:
    scanned_pdf = tmp_path / "scanned.pdf"
    scanned_pdf.write_bytes(b"%PDF-1.4\n")

    result = _read_input_result(scanned_pdf, tmp_path)

    assert result["status"] == "failed"
    assert result["parse_status"] == "failed"
    assert any("PDF decode produced empty text" in item for item in result["limitations"])


def test_wf003_10_malformed_archive(tmp_path: Path) -> None:
    malformed_archive = tmp_path / "broken.zip"
    malformed_archive.write_bytes(b"not-a-real-zip")

    result = paper_prepare.prepare_paper_source(
        malformed_archive,
        raw_root=tmp_path / "raw",
        workspace_root=tmp_path,
    )

    assert result["status"] == "completed"
    assert any("archive extraction failed" in warning for warning in result["warnings"])


def test_wf003_11_unsupported_material_type(tmp_path: Path) -> None:
    source = tmp_path / "paper.xyz"
    source.write_bytes(b"not-supported-format")
    result = _read_input_result(source, tmp_path)

    assert result["status"] == "completed"
    assert result["parse_status"] in {"parsed", "partial"}
    assert result["source_type"] == "unknown"

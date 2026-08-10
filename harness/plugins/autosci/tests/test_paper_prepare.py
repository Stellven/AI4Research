from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

HARNESS = Path(__file__).resolve().parents[3]
PLUGIN = HARNESS / "plugins" / "autosci"
BRIDGE = PLUGIN / "bin" / "autosci_bridge.py"
sys.path.insert(0, str(PLUGIN))

from backends import paper_prepare  # noqa: E402


def write_pdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def test_extract_pdf_text_uses_pypdf_fallback_when_pymupdf_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    class FakePage:
        def extract_text(self) -> str:
            return "SKILLGEN fallback text from pypdf."

    class FakeReader:
        def __init__(self, path: str) -> None:
            assert path == str(pdf_path)
            self.pages = [FakePage()]

    class FakePypdf:
        PdfReader = FakeReader

    monkeypatch.setattr(paper_prepare, "HAS_PYMUPDF", False)
    monkeypatch.setattr(paper_prepare, "fitz", None)
    monkeypatch.setitem(sys.modules, "pypdf", FakePypdf)
    text, warnings = paper_prepare._extract_pdf_text(pdf_path)
    assert "SKILLGEN fallback text" in text
    assert any("PyMuPDF unavailable" in warning for warning in warnings)


def test_guess_title_combines_wrapped_pdf_title_lines() -> None:
    title = paper_prepare._guess_title_from_text(
        "SKILLGEN: Verified Inference-Time Agent Skill\n"
        "Synthesis\n"
        "Yuchen Ma1 Yue Huang2\n"
        "Abstract\n"
        "Body text.",
        "fallback",
    )
    assert title == "SKILLGEN: Verified Inference-Time Agent Skill Synthesis"


def test_prepare_pdf_prefers_arxiv_source_when_recovered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "raw" / "papers" / "2401.00001.pdf"
    write_pdf(
        pdf_path,
        "Solar PDF Fixture Title\narXiv: 2401.00001\nAbstract\nThis local PDF should recover an arXiv source.",
    )

    def fake_download(arxiv_id: str, dest_dir: Path, *, timeout: int = 30) -> dict[str, object]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_dir.joinpath("main.tex").write_text(
            "\\title{Fetched Source Title}\n"
            "\\begin{document}\n"
            "\\begin{abstract}Fetched source abstract.\\end{abstract}\n"
            "\\section{Method}\n"
            "Fetched method section from arXiv source.\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        return {"success": True, "format": "directory", "error": None}

    monkeypatch.setattr(paper_prepare, "_download_arxiv_source", fake_download)
    prepared = paper_prepare.prepare_paper_source(
        pdf_path,
        raw_root=tmp_path / "raw",
        workspace_root=tmp_path,
        repository_root=HARNESS,
    )
    assert prepared["arxiv_id"] == "2401.00001"
    assert prepared["source_fetch_status"] == "downloaded_source"
    assert str(prepared["canonical_ingest_path"]).endswith("-arxiv-src")

    paper = paper_prepare.read_paper_source(
        pdf_path,
        raw_root=tmp_path / "raw",
        workspace_root=tmp_path,
        repository_root=HARNESS,
    )
    assert paper["source_type"] == "latex"
    assert paper["identifiers"]["arxiv"] == "2401.00001"
    assert any("Fetched method section" in section.get("text", "") for section in paper["sections"])


def test_bridge_pdf_ingest_generates_synthetic_tex_when_network_disabled(tmp_path: Path) -> None:
    pdf_path = tmp_path / "raw" / "papers" / "2401.00002.pdf"
    write_pdf(
        pdf_path,
        "Solar Synthetic PDF Fixture\narXiv: 2401.00002\nAbstract\n"
        "This PDF validates offline synthetic TeX fallback.\n"
        "1. Introduction\nThe method writes explicit preparation artifacts.",
    )
    envelope = tmp_path / "envelope.pdf-ingest.json"
    envelope.write_text(
        json.dumps(
            {
                "task_id": "task-pdf-ingest",
                "sprint_id": "phase19-pdf-prepare",
                "node_id": "node-ingest-pdf",
                "mode": "fixture",
                "output_dir": "artifacts/scientific/pdf-smoke",
                "inputs": {
                    "paper_path": str(pdf_path),
                    "raw_root": "raw",
                    "allow_network_fetch": False,
                },
                "outputs": {
                    "evidence_payload_path": "artifacts/scientific/pdf-smoke/research_paper.json",
                    "result_path": "artifacts/scientific/pdf-smoke/ingest_paper.result.json",
                    "evidence_jsonl": "artifacts/scientific/pdf-smoke/evidence.jsonl",
                },
            }
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", "ingest_paper", "--envelope", str(envelope)],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    paper = payload["outputs"]["paper"]
    preparation = paper["preparation"]
    assert payload["status"] == "completed"
    assert paper["source_type"] == "latex"
    assert paper["identifiers"]["arxiv"] == "2401.00002"
    assert preparation["source_fetch_status"] == "skipped_network_disabled"
    assert preparation["prepared_path"].endswith(".tex")
    assert {artifact["type"] for artifact in payload["artifacts"]} >= {"extracted_pdf_text", "synthetic_latex"}
    raw_artifact_paths = [
        artifact["path"]
        for artifact in payload["artifacts"]
        if artifact["type"] in {"extracted_pdf_text", "synthetic_latex"}
    ]
    assert all(path.startswith("raw/tmp/papers/") for path in raw_artifact_paths)
    assert not any("/OpenSolar/harness/artifacts/autosci/workspace/raw" in path for path in raw_artifact_paths)

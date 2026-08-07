from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "harness"
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
BIN = HARNESS / "plugins" / "autosci" / "bin"
sys.path.insert(0, str(BIN))

from research_control_plane import classify_research_input  # noqa: E402


def run_bridge(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path / "harness-out")
    return subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


def write_pdf(path: Path) -> Path:
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Count 0 >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )
    return path


def test_input_taxonomy_is_explicit_and_extensible(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "paper.pdf")
    pack = tmp_path / "source-pack"
    pack.mkdir()
    (pack / "source.md").write_text("## Findings\nThe paper shows a result.\n", encoding="utf-8")
    evidence = tmp_path / "experiment.json"
    evidence.write_text('{"experiment_result": {"metric": "accuracy", "value": 0.91}}\n', encoding="utf-8")

    cases = [
        ({"prompt": "Analyze https://example.org/x", "sources": [], "import_evidence": [], "run_mode": "execute"}, "website", "web_fetch"),
        ({"prompt": "Survey agent memory evaluation", "sources": [], "import_evidence": [], "run_mode": "execute"}, "topic", "source_discovery"),
        ({"prompt": "Ingest the PDF", "sources": [str(pdf)], "import_evidence": [], "run_mode": "execute"}, "local_pdf", "paper_ingest"),
        ({"prompt": "Synthesize this source pack", "sources": [str(pack)], "import_evidence": [], "run_mode": "execute"}, "source_pack", "material_ingest"),
        ({"prompt": "Use the experiment evidence", "sources": [str(evidence)], "import_evidence": [], "run_mode": "execute"}, "experiment_evidence", "evidence_import"),
        ({"prompt": "Resume the prior run", "sources": [], "import_evidence": [], "run_mode": "resume"}, "resume", "evidence_import"),
    ]

    for kwargs, expected_kind, expected_stage in cases:
        classification = classify_research_input(**kwargs)
        assert classification.input_kind == expected_kind
        assert classification.start_stage == expected_stage


def test_research_cli_preserves_complete_prompt_and_routes_by_input(tmp_path: Path) -> None:
    marker = "END_MARKER_CONTROL_PLANE_12345"
    prompt = "Survey durable agent memory evaluation. " + ("Preserve this sentence. " * 200) + marker
    artifact_root = tmp_path / "artifacts"
    proc = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        prompt,
        "--run-id",
        "long-prompt",
        "--artifact-root",
        str(artifact_root),
        "--max-steps",
        "1",
    )

    data = payload(proc)
    assert proc.returncode == 0
    assert data["input_classification"]["input_kind"] == "topic"
    assert data["start_node"] == "source_discovery"
    contract = json.loads(Path(data["task_contract_path"]).read_text(encoding="utf-8"))
    assert contract["user_intent"] == prompt
    assert contract["constraints"]["request_capture"]["raw_prompt"].endswith(marker)
    assert contract["constraints"]["request_capture"]["raw_prompt_length_chars"] == len(prompt)


def test_research_cli_exposes_distinct_initial_nodes_for_supported_inputs(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "paper.pdf")
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "source.md").write_text(
        "## Findings\nThe study shows that evidence ledgers reduce unsupported claims by 32 percent.\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "experiment.json"
    evidence.write_text('{"experiment_result": {"metric": "claim_support", "value": 0.87}}\n', encoding="utf-8")

    cases = [
        ("web", ["--prompt", "Analyze https://example.org/research and report findings."], "website", "seed_fetch"),
        ("topic", ["--prompt", "Survey benchmark methods for agent memory."], "topic", "source_discovery"),
        ("pdf", ["--prompt", "Ingest the supplied PDF.", "--source", str(pdf)], "local_pdf", "paper_ingest"),
        ("pack", ["--prompt", "Synthesize the source pack.", "--source", str(pack)], "source_pack", "material_ingest"),
        ("evidence", ["--prompt", "Use the experiment evidence.", "--source", str(evidence)], "experiment_evidence", "evidence_import"),
    ]

    starts = {}
    for run_id, args, expected_kind, expected_start in cases:
        proc = run_bridge(
            tmp_path,
            "research",
            *args,
            "--run-id",
            run_id,
            "--artifact-root",
            str(tmp_path / f"artifacts-{run_id}"),
            "--max-steps",
            "1",
        )
        data = payload(proc)
        assert proc.returncode in {0, 2}, proc.stdout + proc.stderr
        assert data["input_classification"]["input_kind"] == expected_kind
        assert data.get("start_node", expected_start) == expected_start
        starts[expected_kind] = expected_start

    assert len(set(starts.values())) >= 4
    assert starts["local_pdf"] == "paper_ingest"
    assert starts["topic"] != "paper_ingest"


def test_research_cli_parameter_semantics_are_observable(tmp_path: Path) -> None:
    repo_file = tmp_path / "repo" / "analysis.py"
    repo_file.parent.mkdir()
    repo_file.write_text("def score():\n    return 1\n", encoding="utf-8")

    proc = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        "Analyze this repository evidence and write a report.",
        "--run-id",
        "params",
        "--artifact-root",
        str(tmp_path / "artifacts"),
        "--repository",
        str(repo_file),
        "--workflow",
        "scientific_lifecycle",
        "--output-language",
        "en",
        "--max-steps",
        "1",
    )
    data = payload(proc)
    contract = json.loads(Path(data["task_contract_path"]).read_text(encoding="utf-8"))
    assert data["route"]["workflow_kind"] == "scientific_lifecycle"
    assert contract["deliverable"]["language"] == "en"
    assert contract["constraints"]["repository_inputs"][0]["file_count"] == 1

    blocked = payload(
        run_bridge(
            tmp_path,
            "research",
            "--prompt",
            "Analyze https://nonexistent.invalid/research-control-plane",
            "--run-id",
            "no-network",
            "--artifact-root",
            str(tmp_path / "no-network"),
            "--max-steps",
            "1",
        )
    )
    network = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        "Analyze https://nonexistent.invalid/research-control-plane",
        "--run-id",
        "with-network",
        "--artifact-root",
        str(tmp_path / "with-network"),
        "--max-steps",
        "1",
        "--allow-network",
    )
    network_payload = payload(network)
    assert blocked["final_status"] == "awaiting_external"
    assert network.returncode == 2
    assert network_payload["final_status"] == "failed"
    assert "host resolution failed" in network_payload["current_blockers"][0]["reason"]


def test_negative_inputs_fail_closed_or_request_clarification(tmp_path: Path) -> None:
    blank = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        " ",
        "--run-id",
        "blank",
        "--artifact-root",
        str(tmp_path / "blank"),
    )
    assert blank.returncode == 2
    assert payload(blank)["error_type"] == "ResearchControlPlaneError"

    conflict = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        "请用中文写最终报告, but the final deliverable must be English.",
        "--run-id",
        "conflict",
        "--artifact-root",
        str(tmp_path / "conflict"),
    )
    conflict_payload = payload(conflict)
    assert conflict.returncode == 0
    assert conflict_payload["final_status"] == "awaiting_human"
    assert "output_language" in conflict_payload["current_blockers"][0]["contradictions"]

    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_text("not actually a PDF", encoding="utf-8")
    broken = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        "Ingest the supplied PDF.",
        "--source",
        str(broken_pdf),
        "--run-id",
        "broken",
        "--artifact-root",
        str(tmp_path / "broken"),
    )
    assert broken.returncode == 2
    assert "not a readable PDF" in payload(broken)["error"]

    unknown = run_bridge(
        tmp_path,
        "research",
        "--prompt",
        "Survey memory.",
        "--run-id",
        "unknown-mode",
        "--artifact-root",
        str(tmp_path / "unknown"),
        "--run-mode",
        "teleport",
    )
    assert unknown.returncode == 2
    assert "invalid choice" in unknown.stderr
